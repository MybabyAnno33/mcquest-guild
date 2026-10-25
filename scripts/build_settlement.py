#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
McQuest Guild 结算卡本地生成脚本（仅标准库，无网络、无 MCP、无副作用）。

用途：读取本地 JSON 任务数据与 assets/settlement-card.html 模板，生成一份新的
HTML 结算卡副本。不修改模板本身，不覆盖任何已存在的文件。

用法：
    python build_settlement.py --data <task.json> --output <out.html>

数据约定（单位）：
    - 所有价格字段以「分」为单位（整数），展示时由本脚本 ÷100 转为「元」。
    - 缺失的优惠/营养数据用 "未查询" 表示；未核验的价格显示 "待核实"，绝不填 0。

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
from pathlib import Path

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "assets" / "settlement-card.html"

# 模板中位于 CSS 注释里的文档性占位符（非数据字段），统一替换为说明文字
DOC_PLACEHOLDER = "当次任务的真实核验数据"

REQUIRED_FIELDS = [
    "quest_no", "quest_name", "quest_result", "challenge_type",
    "store_name", "store_code", "quest_time",
    "items", "total_price_fen", "budget_fen",
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


def check_required(data):
    missing = [k for k in REQUIRED_FIELDS if k not in data]
    if missing:
        fail("缺少必需字段: " + ", ".join(missing))
    for k in ("quest_no", "quest_name", "quest_result", "challenge_type",
              "store_name", "store_code", "quest_time",
              "price_status", "coupon_status", "nutrition_status"):
        if not isinstance(data[k], str) or not data[k].strip():
            fail("字段 {} 必须是非空字符串".format(k))
    if not isinstance(data["total_price_fen"], int) or data["total_price_fen"] < 0:
        fail("total_price_fen 必须是非负整数（单位：分）；价格未核验时不要提供该字段，脚本会显示“待核实”")
    if not isinstance(data["budget_fen"], int) or data["budget_fen"] < 0:
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
    if ("未完成" in result or "退出" in result) and ("通关" in result or result.strip().startswith("已完成")):
        fail("quest_result 同时包含“未完成/退出”与“已完成/通关”，状态矛盾")
    if "退出" in result and "任务全勘" in titles:
        warn("玩家主动退出的任务中保留了“任务全勘”：请确认其解锁条件（核验成功且满足目标）在退出前已满足")
    if "未查询" in data["coupon_status"] and "无券勇者" in titles:
        fail("优惠券未查询时不得授予“无券勇者”")
    if "待核实" in data["price_status"] and "任务全勘" in titles:
        fail("价格待核实时不得授予“任务全勘”")


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
    total = data["total_price_fen"]
    budget = data["budget_fen"]
    discount = data.get("discount_fen", OPTIONAL_DEFAULTS["discount_fen"])
    remaining = data.get("remaining_fen", OPTIONAL_DEFAULTS["remaining_fen"])

    values = {
        "QUEST_NO": html.escape(data["quest_no"]),
        "QUEST_NAME": html.escape(data["quest_name"]),
        "QUEST_RESULT": html.escape(data["quest_result"]),
        "CHALLENGE_TYPE": html.escape(data["challenge_type"]),
        "STORE_NAME": html.escape(data["store_name"]),
        "STORE_CODE": html.escape(data["store_code"]),
        "QUEST_TIME": html.escape(data["quest_time"]),
        "TOTAL_PRICE": fen_to_yuan(total),
        "BUDGET": fen_to_yuan(budget),
        "PRICE_STATUS": html.escape(data["price_status"]),
        "COUPON_STATUS": html.escape(data["coupon_status"]),
        "NUTRITION_STATUS": html.escape(data["nutrition_status"]),
        "UNLOCKED_TITLES": html.escape(" · ".join(data["unlocked_titles"]) if data["unlocked_titles"] else "暂无解锁称号"),
    }

    if remaining is None:
        remaining = budget - total
    if remaining < 0:
        warn("剩余预算为负（超出预算 {} 分），请确认挑战判定".format(-remaining))
    return values, remaining, discount


def render(template, values, items_rows, remaining, discount):
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
    remaining_yuan = fen_to_yuan(remaining) if remaining is not None else "待核实"
    replacement = ('<div class="status-line"><span class="k">玩家预算</span><span>{{BUDGET}} 元</span></div>\n'
                   '      <div class="status-line"><span class="k">剩余预算</span><span>'
                   + html.escape(remaining_yuan) + ' 元</span></div>')
    out = out.replace(budget_line, replacement)

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

    # 4) 数据占位符替换
    for key in PLACEHOLDER_ORDER:
        out = out.replace("{{" + key + "}}", values[key])

    # 5) 残留占位符检查：任何 {{...}} 残留都视为错误
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

    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        template = f.read()

    items_rows = build_items_rows(data["items"])
    values, remaining, discount = build_values(data)
    result = render(template, values, items_rows, remaining, discount)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(result)

    print("[完成] 结算卡已生成: {}".format(out_path))
    print("       商品行数: {}；模板与既有文件均未被修改。".format(len(data["items"])))


if __name__ == "__main__":
    main()
