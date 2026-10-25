#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_settlement.py 异常输入测试 harness（独立测试文件，不修改被测脚本/模板/既有数据）。

在系统临时目录搭建独立沙箱（复制被测脚本与模板），逐场景运行并输出证据。
只使用标准库；不访问网络、不调用 MCP。
"""

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
SCRIPT_SRC = Path(__file__).resolve().parent / "build_settlement.py"
TEMPLATE_SRC = PROJECT / "assets" / "settlement-card.html"
DATA_SRC = Path(__file__).resolve().parent / "test-data-No001.json"
PY = sys.executable

results = []


def record(name, ok, detail):
    results.append((name, ok, detail))
    print(("PASS " if ok else "FAIL ") + name)
    print("      " + detail.replace("\n", "\n      "))


def sandbox(base, template_text=None):
    """在 base 下搭建 scripts/ 与 assets/ 结构，返回可执行脚本路径。"""
    (base / "scripts").mkdir(parents=True)
    (base / "assets").mkdir(parents=True)
    shutil.copy(SCRIPT_SRC, base / "scripts" / "build_settlement.py")
    tpl = template_text if template_text is not None else TEMPLATE_SRC.read_text(encoding="utf-8")
    (base / "assets" / "settlement-card.html").write_text(tpl, encoding="utf-8")
    return base / "scripts" / "build_settlement.py"


def run(script, data_path, out_path):
    return subprocess.run([PY, str(script), "--data", str(data_path), "--output", str(out_path)],
                          capture_output=True, text=True)


def load_base_data():
    return json.loads(DATA_SRC.read_text(encoding="utf-8"))


def main():
    root = Path(tempfile.mkdtemp(prefix="mcquest-exc-"))
    print("临时沙箱:", root)
    base_data = load_base_data()
    out = root / "out.html"

    # ── 场景 1：缺失必需字段 ──
    sb = root / "s1"
    sb.mkdir()
    script = sandbox(sb)
    d = dict(base_data)
    del d["store_code"]
    dp = sb / "d.json"
    dp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    r = run(script, dp, out)
    ok = r.returncode != 0 and "缺少必需字段" in (r.stdout + r.stderr) and not out.exists()
    record("1 缺失必需字段", ok,
           "退出码={}，错误信息含'缺少必需字段'={}，输出文件未产生={}".format(
               r.returncode, "缺少必需字段" in (r.stdout + r.stderr), not out.exists()))

    # ── 场景 2：未知占位符（模板中注入 {{UNKNOWN_X}}）──
    sb = root / "s2"
    sb.mkdir()
    tpl = TEMPLATE_SRC.read_text(encoding="utf-8").replace(
        "<h2>任务结果</h2>", "<h2>任务结果</h2>\n      <p>{{UNKNOWN_X}}</p>")
    script = sandbox(sb, tpl)
    dp = sb / "d.json"
    dp.write_text(json.dumps(base_data, ensure_ascii=False), encoding="utf-8")
    out2 = sb / "out.html"
    r = run(script, dp, out2)
    ok = r.returncode != 0 and "UNKNOWN_X" in (r.stdout + r.stderr) and not out2.exists()
    record("2 未知占位符", ok,
           "退出码={}，错误信息含'UNKNOWN_X'={}，输出文件未产生={}".format(
               r.returncode, "UNKNOWN_X" in (r.stdout + r.stderr), not out2.exists()))

    # ── 场景 3：任务状态矛盾（未完成 + 通关）──
    sb = root / "s3"
    sb.mkdir()
    script = sandbox(sb)
    d = dict(base_data)
    d["quest_result"] = "未完成（玩家主动退出），但补给已通关"
    dp = sb / "d.json"
    dp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    out3 = sb / "out.html"
    r = run(script, dp, out3)
    ok = r.returncode != 0 and "状态矛盾" in (r.stdout + r.stderr) and not out3.exists()
    record("3 任务状态矛盾", ok,
           "退出码={}，错误信息含'状态矛盾'={}，输出文件未产生={}".format(
               r.returncode, "状态矛盾" in (r.stdout + r.stderr), not out3.exists()))

    # ── 场景 4：券未查询 + 无券勇者 ──
    sb = root / "s4"
    sb.mkdir()
    script = sandbox(sb)
    d = dict(base_data)
    d["coupon_status"] = "未查询"
    d["unlocked_titles"] = ["初入公会", "无券勇者"]
    dp = sb / "d.json"
    dp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    out4 = sb / "out.html"
    r = run(script, dp, out4)
    ok = r.returncode != 0 and "无券勇者" in (r.stdout + r.stderr) and not out4.exists()
    record("4 称号与查询状态矛盾", ok,
           "退出码={}，错误信息含'无券勇者'={}，输出文件未产生={}".format(
               r.returncode, "无券勇者" in (r.stdout + r.stderr), not out4.exists()))

    # ── 场景 5：输出文件已存在，拒绝覆盖 ──
    sb = root / "s5"
    sb.mkdir()
    script = sandbox(sb)
    dp = sb / "d.json"
    dp.write_text(json.dumps(base_data, ensure_ascii=False), encoding="utf-8")
    out5 = sb / "existing.html"
    sentinel = "SENTINEL-原内容指纹-9f8e7d6c"
    out5.write_text(sentinel, encoding="utf-8")
    before = hashlib.md5(out5.read_bytes()).hexdigest()
    r = run(script, dp, out5)
    after = hashlib.md5(out5.read_bytes()).hexdigest()
    ok = r.returncode != 0 and "拒绝覆盖" in (r.stdout + r.stderr) and before == after and sentinel in out5.read_text(encoding="utf-8")
    record("5 输出文件已存在拒绝覆盖", ok,
           "退出码={}，错误信息含'拒绝覆盖'={}，文件 MD5 前后一致={}（{}）".format(
               r.returncode, "拒绝覆盖" in (r.stdout + r.stderr), before == after, before[:8]))

    # ── 场景 6：HTML 特殊字符转义 ──
    sb = root / "s6"
    sb.mkdir()
    script = sandbox(sb)
    d = json.loads(json.dumps(base_data))
    d["items"] = [{"name": "<script>alert(1)</script> & \"引号\"", "code": "1100",
                   "menu_price": "29.0", "verified_price": "29.0"}]
    d["store_name"] = '门店"引号" & <b>标签</b>'
    dp = sb / "d.json"
    dp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    out6 = sb / "out.html"
    r = run(script, dp, out6)
    text = out6.read_text(encoding="utf-8") if out6.exists() else ""
    no_raw_script = "<script>alert(1)</script>" not in text
    escaped = "&lt;script&gt;alert(1)&lt;/script&gt;" in text and "&amp;" in text
    ok = r.returncode == 0 and out6.exists() and no_raw_script and escaped
    record("6 HTML 特殊字符转义", ok,
           "退出码={}，输出存在={}，原始 <script>alert 未出现={}，已转义实体出现={}".format(
               r.returncode, out6.exists(), no_raw_script, escaped))

    # ── 场景 7：金额边界 ──
    sb = root / "s7a"
    sb.mkdir()
    script = sandbox(sb)
    # 7a 负数金额 → 拒绝
    d = dict(base_data)
    d["total_price_fen"] = -5
    dp = sb / "d.json"
    dp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    out7a = sb / "out.html"
    r = run(script, dp, out7a)
    ok7a = r.returncode != 0 and "非负整数" in (r.stdout + r.stderr) and not out7a.exists()
    record("7a 负数核验价拒绝", ok7a,
           "退出码={}，错误信息含'非负整数'={}，输出文件未产生={}".format(
               r.returncode, "非负整数" in (r.stdout + r.stderr), not out7a.exists()))

    # 7b 预算 < 核验价（超预算）→ 允许生成但必须出现明确警告，不得静默
    sb = root / "s7b"
    sb.mkdir()
    script = sandbox(sb)
    d = dict(base_data)
    d["total_price_fen"] = 5000
    d["budget_fen"] = 4000
    dp = sb / "d.json"
    dp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    out7b = sb / "out.html"
    r = run(script, dp, out7b)
    warned = "警告" in (r.stdout + r.stderr) and "超出预算" in (r.stdout + r.stderr)
    text = out7b.read_text(encoding="utf-8") if out7b.exists() else ""
    ok7b = r.returncode == 0 and warned and text.count("50.00 元") >= 1 and "-10.00" in text
    record("7b 超预算明确提示不静默", ok7b,
           "退出码={}，含'超出预算'警告={}，输出含核验价 50.00 与剩余 -10.00={}".format(
               r.returncode, warned, "50.00" in text and "-10.00" in text))

    shutil.rmtree(root, ignore_errors=True)

    print("\n══ 汇总 ══")
    bad = [n for n, ok, _ in results if not ok]
    for n, ok, _ in results:
        print(("PASS" if ok else "FAIL"), n)
    print("总结:", "全部通过" if not bad else "失败: " + ", ".join(bad))
    sys.exit(0 if not bad else 1)


if __name__ == "__main__":
    main()
