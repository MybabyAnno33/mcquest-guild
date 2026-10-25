#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
McQuest Guild 结算卡本地生成脚本（仅标准库，无网络、无 MCP、无副作用）。

用途：读取本地 JSON 任务数据与 assets/settlement-card.html 模板，生成一份新的
HTML 结算卡副本。不修改模板本身，不覆盖任何已存在的文件。

用法：
    python build_settlement.py --data <task.json> --output <out.html>

数据约定（单位）：
    - total_price_fen / budget_fen / discount_fen / remaining_fen 以「分」为单位
      （整数），展示时由本脚本 ÷100 转为「元」。
    - items[].menu_price / verified_price 为「元」字符串（与 MCP 返回口径一致，
      如 "29.0"）；verified_price 必须来自当次成功的 calculate-price 结果。
    - items[].quantity 为可选整数（≥1），缺省按 1 计，用于行合计一致性校验。
    - total_price_fen 为 null 或缺省表示「价格待核实」：结算卡不得显示 0 元，
      不得判定任务完成，不得授予"任务全勘"。
    - 缺失的优惠/营养数据用 "未查询" 表示；未核验的价格显示 "待核实"，绝不填 0。

价格一致性校验：
    - 商品行合计（Σ verified_price × quantity × 100）必须等于核验总价
      total_price_fen；若提供 discount_fen，则允许 行合计 == total_price_fen + discount_fen。
    - 任一行价格无法解析为数值时，校验结果为「无法校验」并输出警告，
      与「校验通过」明确区分，不得误报。
    - 菜单价（menu_price）仅为展示口径，不参与一致性校验。

安全与边界：
    - 仅使用 Python 标准库；不发起任何网络请求，不调用 MCP，不产生业务副作用。
    - 对商品名等动态内容做 HTML 转义。
    - 输出文件已存在时拒绝生成（防覆盖），除非显式提供 --force（仍不建议）。
"""

import argparse
import html
import json
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "assets" / "settlement-card.html"

# 模板中位于 CSS 注释里的文档性占位符（非数据字段），统一替换为说明文字
DOC_PLACEHOLDER = "当次任务的真实核验数据"

REQUIRED_FIELDS = [
    "quest_no", "quest_name", "quest_result", "challenge_type",
    "store_name", "store_code", "quest_time",
    "items", "budget_fen",
    "price_status", "coupon_status", "nutrition_status", "unlocked_titles",
]

OPTIONAL_DEFAULTS = {
    "discount_fen": None,
    "remaining_fen": None,
}

PLACEHOLDER_ORDER = [
    "QUEST_NO", "QUEST_NAME", "QUEST_RESULT", "CHALLENGE_TYPE",
    "STORE_NAME", "STORE_CODE", "QUEST_TIME",
    "TOTAL_PRICE", "BUDGET", "PRICE_STATUS", "COUPON_STATUS",
    "NUTRITION_STATUS", "UNLOCKED_TITLES",
]


def fen_to_yuan(fen):
    """分 -> 元字符串（两位小数）。"""
    return "{:.2f}".format(fen / 100)


def fail(msg):
    print("[错误] " + msg)
    sys.exit(1)


def warn(msg):
    print("[警告] " + msg)


def load_data(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        fail("数据文件不存在: {}".format(path))
    except json.JSONDecodeError as e:
        fail("数据文件不是有效 JSON: {} ({})".format(path, e))
    if not isinstance(data, dict):
        fail("数据文件顶层必须是 JSON 对象")
    return data


def _is_valid_fen(v):
    """分字段允许 int（≥0，不含 bool）或 None。"""
    if v is None:
        return True
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


def check_required(data):
    missing = [k for k in REQUIRED_FIELDS if k not in data]
    if missing:
        fail("缺少必需字段: " + ", ".join(missing))
    for k in ("quest_no", "quest_name", "quest_result", "challenge_type",
              "store_name", "store_code", "quest_time",
              "price_status", "coupon_status", "nutrition_status"):
        if not isinstance(data[k], str) or not data[k].strip():
            fail("字段 {} 必须是非空字符串".format(k))

    # total_price_fen：整数（分）或 null/缺省（待核实）
    total = data.get("total_price_fen")
    if total is not None and (not isinstance(total, int) or isinstance(total, bool) or total < 0):
        fail("total_price_fen 必须是非负整数（单位：分），或 null/缺省表示待核实；不得填 0 冒充已核验")

    for k in ("budget_fen", "discount_fen", "remaining_fen"):
        if not _is_valid_fen(data.get(k)):
            fail("{} 必须是非负整数（单位：分）或 null".format(k))
    if total is None and data.get("discount_fen") is not None:
        fail("总价待核实时不得提供 discount_fen（无核验依据的优惠金额不得展示）")
    if total is None and data.get("remaining_fen") is not None:
        fail("总价待核实时不得提供 remaining_fen（剩余预算无法计算，不得伪造）")

    if not isinstance(data["budget_fen"], int) or isinstance(data["budget_fen"], bool) or data["budget_fen"] < 0:
        fail("budget_fen 必须是非负整数（单位：分）")
    if not isinstance(data["items"], list):
        fail("items 必须是数组")
    if not isinstance(data["unlocked_titles"], list):
        fail("unlocked_titles 必须是字符串数组")
    for t in data["unlocked_titles"]:
        if not isinstance(t, str) or not t.strip():
            fail("unlocked_titles 中每个称号必须是非空字符串")


def check_status_rules(data):
    """轻量一致性校验：状态与称号的明显矛盾要报错，不生成伪成功结果。"""
    result = data["quest_result"]
    titles = data["unlocked_titles"]
    total = data.get("total_price_fen")

    if ("未完成" in result or "退出" in result) and ("通关" in result or result.strip().startswith("已完成")):
        fail("quest_result 同时包含“未完成/退出”与“已完成/通关”，状态矛盾")
    if "退出" in result and "任务全勘" in titles:
        warn("玩家主动退出的任务中保留了“任务全勘”：请确认其解锁条件（核验成功且满足目标）在退出前已满足")
    if "未查询" in data["coupon_status"] and "无券勇者" in titles:
        fail("优惠券未查询时不得授予“无券勇者”")
    if "待核实" in data["price_status"] and "任务全勘" in titles:
        fail("价格待核实时不得授予“任务全勘”")

    # 价格待核实（total 缺省/null）时的额外硬约束
    if total is None:
        if "已完成" in result or "通关" in result:
            fail("总价待核实时不得将任务标记为“已完成/通关”")
        if "任务全勘" in titles:
            fail("总价待核实时不得授予“任务全勘”（其解锁条件要求核验成功且满足目标）")
        if "无券勇者" in titles:
            fail("总价待核实时不得授予“无券勇者”（其解锁条件要求玩家最终达成挑战）")
        if "已核验" in data["price_status"]:
            fail("总价待核实时 price_status 不得宣称“已核验”（与缺省的总价矛盾）")


def check_price_consistency(data):
    """商品行合计与核验总价的一致性校验。

    返回 "pass"（校验通过）或 "skip"（无法校验）；不一致时直接 fail。
    menu_price 仅为展示口径，不参与本校验。
    """
    total = data.get("total_price_fen")
    if total is None:
        warn("价格一致性：总价待核实，跳过行合计校验")
        return "skip"

    discount = data.get("discount_fen")
    row_sum = Decimal("0")
    for i, it in enumerate(data["items"]):
        qty = it.get("quantity", 1)
        try:
            price = Decimal(str(it["verified_price"]))
        except (InvalidOperation, ValueError):
            warn("价格一致性：无法校验（items[{}].verified_price={!r} 不是可解析的数值）"
                 "——本卡未做行合计核对，不得宣称一致性校验通过".format(i, it["verified_price"]))
            return "skip"
        if price < 0:
            fail("items[{}].verified_price 不得为负数".format(i))
        row_sum += price * qty * 100

    expected = total + (discount if discount is not None else 0)
    if row_sum != Decimal(expected):
        fail("价格不一致：商品行合计 {} 分 ≠ 核验总价 {} 分{}（若商品数量大于 1，请提供结构化 quantity 字段）".format(
            int(row_sum), total,
            " + 优惠 {} 分".format(discount) if discount is not None else ""))
    print("[校验] 价格一致性：通过（商品行合计 {} 分 = 核验总价 {} 分{}）".format(
        int(row_sum), total,
        " + 优惠 {} 分".format(discount) if discount is not None else ""))
    return "pass"


def build_items_rows(items):
    """生成商品行；无已核验商品时显示待核实占位行（完整 <tr>，避免被浏览器提升到表格外）。"""
    if not items:
        return ('<tr class="empty-row"><td colspan="4">'
                + html.escape("待核实（无已核验商品）") + "</td></tr>")
    rows = []
    for i, it in enumerate(items):
        for k in ("name", "code", "menu_price", "verified_price"):
            if k not in it:
                fail("items[{}] 缺少字段 {}".format(i, k))
        rows.append("<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            html.escape(str(it["name"])),
            html.escape(str(it["code"])),
            html.escape(str(it["menu_price"])),
            html.escape(str(it["verified_price"])),
        ))
    return "\n        ".join(rows)


def build_values(data):
    total = data.get("total_price_fen")
    budget = data["budget_fen"]

    values = {
        "QUEST_NO": html.escape(data["quest_no"]),
        "QUEST_NAME": html.escape(data["quest_name"]),
        "QUEST_RESULT": html.escape(data["quest_result"]),
        "CHALLENGE_TYPE": html.escape(data["challenge_type"]),
        "STORE_NAME": html.escape(data["store_name"]),
        "STORE_CODE": html.escape(data["store_code"]),
        "QUEST_TIME": html.escape(data["quest_time"]),
        "TOTAL_PRICE": fen_to_yuan(total) if total is not None else "待核实",
        "BUDGET": fen_to_yuan(budget),
        "PRICE_STATUS": html.escape(data["price_status"]),
        "COUPON_STATUS": html.escape(data["coupon_status"]),
        "NUTRITION_STATUS": html.escape(data["nutrition_status"]),
        "UNLOCKED_TITLES": html.escape(" · ".join(data["unlocked_titles"]) if data["unlocked_titles"] else "暂无解锁称号"),
    }

    if total is None:
        remaining = None  # 待核实：不显示任何剩余预算数值
    else:
        remaining = data.get("remaining_fen")
        if remaining is None:
            remaining = budget - total
        if remaining < 0:
            warn("剩余预算为负（超出预算 {} 分），请确认挑战判定".format(-remaining))
    return values, remaining


def render(template, values, items_rows, remaining):
    out = template

    # 1) 剥离模板中的 HTML 注释（使用说明与填充规则；生成卡中已无意义）。
    #    关键原因：注释文本中也引用了 <tbody id="item-rows">，若不剥离，
    #    后续 tbody 正则会从注释内提前匹配，吞掉真实内容。
    out = re.sub(r"<!--.*?-->", "", out, flags=re.DOTALL)

    # 2) 商品行整块替换（此时模板中应只剩真实 tbody）
    out, n = re.subn(
        r'(<tbody id="item-rows">).*?(</tbody>)',
        lambda m: m.group(1) + "\n          " + items_rows + "\n        " + m.group(2),
        out, flags=re.DOTALL)
    if n != 1:
        fail("剥离注释后未找到唯一的 <tbody id=\"item-rows\"> 块（找到 {} 处）".format(n))

    # 3) 剩余预算行追加（必须在数据占位符替换之前，定位串依赖 {{BUDGET}} 原文）
    budget_line = '<div class="status-line"><span class="k">玩家预算</span><span>{{BUDGET}} 元</span></div>'
    if budget_line not in out:
        fail("模板中未找到“玩家预算”状态行，无法追加剩余预算")
    if remaining is None:
        remaining_html = html.escape("待核实")  # 不显示任何数值，避免把未知当 0
    else:
        remaining_html = html.escape(fen_to_yuan(remaining)) + " 元"
    replacement = ('<div class="status-line"><span class="k">玩家预算</span><span>{{BUDGET}} 元</span></div>\n'
                   '      <div class="status-line"><span class="k">剩余预算</span><span>'
                   + remaining_html + '</span></div>')
    out = out.replace(budget_line, replacement)

    # 3b) 总价待核实时，模板中的 "{{TOTAL_PRICE}} 元" 需整体替换，避免出现"待核实 元"
    if values["TOTAL_PRICE"] == "待核实":
        out = out.replace("{{TOTAL_PRICE}} 元", "待核实")

    # 4) CSS 注释中的文档性占位符
    out = out.replace("{{PLACEHOLDER}}", DOC_PLACEHOLDER)

    # 5) 数据占位符替换
    for key in PLACEHOLDER_ORDER:
        out = out.replace("{{" + key + "}}", values[key])

    # 6) 残留占位符检查：任何 {{...}} 残留都视为错误
    leftover = re.findall(r"\{\{[^}]{1,40}\}\}", out)
    if leftover:
        fail("生成结果中仍残留占位符: " + ", ".join(sorted(set(leftover))))
    return out


def main():
    parser = argparse.ArgumentParser(description="McQuest Guild 结算卡本地生成器（只读模板与 JSON，无网络无副作用）")
    parser.add_argument("--data", required=True, help="任务数据 JSON 路径")
    parser.add_argument("--output", required=True, help="输出 HTML 路径（已存在时拒绝覆盖）")
    parser.add_argument("--force", action="store_true", help="允许覆盖输出文件（不建议）")
    args = parser.parse_args()

    if not TEMPLATE_PATH.exists():
        fail("模板不存在: {}".format(TEMPLATE_PATH))
    out_path = Path(args.output)
    if out_path.exists() and not args.force:
        fail("输出文件已存在，拒绝覆盖: {}（如确需覆盖请加 --force）".format(out_path))

    data = load_data(args.data)
    check_required(data)
    check_status_rules(data)
    consistency = check_price_consistency(data)

    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        template = f.read()

    items_rows = build_items_rows(data["items"])
    values, remaining = build_values(data)
    result = render(template, values, items_rows, remaining)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(result)

    print("[完成] 结算卡已生成: {}".format(out_path))
    print("       商品行数: {}；价格一致性: {}；模板与既有文件均未被修改。".format(
        len(data["items"]), {"pass": "通过", "skip": "无法校验（见警告）"}[consistency]))


if __name__ == "__main__":
    main()
