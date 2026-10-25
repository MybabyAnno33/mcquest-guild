# McQuest Guild 项目说明

《从麦麦冒险者公会开始的异世界探索》——以冒险者公会与悬赏任务闯关为主题、结合 McDonald's China MCP 的游戏化 WorkBuddy Skill 项目：玩家在冒险者公会领取悬赏，通过真实的门店、菜单、价格、优惠券与营养数据完成探索，按实际核验结果结算游戏内称号。

## 目录结构

```
mcquest-guild/
├── SKILL.md                      # Skill 入口：流程、工具分级、硬性规则
├── references/
│   ├── mcp-api-notes.md          # 已实测的 MCP 工具行为与单位/异常记录
│   └── quest-001.md              # 悬赏 No.001「失落的金色补给」剧本
├── assets/
│   └── settlement-card.html      # 像素风结算卡模板（占位符 {{...}} 填充）
└── scripts/
    ├── build_settlement.py       # 结算卡本地生成脚本（仅标准库，无网络/MCP）
    ├── test-data-No001.json      # 悬赏 No.001 实测样例数据（脚本输入）
    └── test_build_settlement_exceptions.py  # 脚本异常输入测试 harness（17 项独立检查）
```

注：工作目录中的 `assets/settlement-card-test-No001.html` 与 `assets/settlement-card-generated-No001.html` 为开发测试产物，已通过 `.gitignore` 排除出公开仓库，但仍保留在本地工作目录中，不会被删除。

## 依赖

- WorkBuddy Skill 运行环境
- 用户自行配置的 McDonald's China MCP 连接（由 WorkBuddy 连接器托管）。本 Skill 只调用只读工具，**不要假设所有读写工具均可用**——工具可用性分级与禁用清单见 SKILL.md。

## 安装方式

- **项目级**：将整个 `mcquest-guild/` 复制到目标项目的 `.workbuddy/skills/mcquest-guild/`
- **用户级**：将整个 `mcquest-guild/` 复制到 `~/.workbuddy/skills/mcquest-guild/`
- 注意：项目级 Skill 的自动加载能力依赖运行环境，**当前尚未验证**；如未自动触发，请以手动方式参照 SKILL.md 规则使用。

## 测试状态

| 项目 | 状态 |
| --- | --- |
| `quick_validate.py` 规范校验（针对安装副本） | ✅ 通过，退出码 0 |
| `build_settlement.py` 手动运行（测试数据副本 → 全新输出路径） | ✅ 成功，结算卡内容检查通过（价格/预算/剩余/状态/称号/无残留占位符） |
| `test_build_settlement_exceptions.py` 异常输入 harness | ✅ 17 项独立检查全部通过（输入异常/状态矛盾/价格一致性/待核实状态/防覆盖/HTML 转义） |
| 项目级 Skill 自动加载 | ⬜ 未验证或当前环境不支持 |
| Skill 运行时自动调用 `build_settlement.py` | ⬜ 未验证（当前为手动调用） |

## MCP 实测范围

实测范围与未验证范围的**权威记录**见 `references/mcp-api-notes.md`；SKILL.md 的「工具可用性分级」表为现行摘要。未取得真实成功返回并核对结果的能力一律标注"未验证"，本项目不将其描述为已实现。

## 结算卡展示方式

`settlement-card.html` 为静态独立模板，无脚本、无远程依赖。两条已界定的路径：

- **已验证（手动）**：用 `python scripts/build_settlement.py --data <任务.json> --output <输出.html>` 从本地任务数据生成结算卡副本（输出文件已存在时拒绝覆盖）。
- **未验证**：Skill 运行时自动生成并展示结算卡的交互路径尚未验证；`present_files` 面板可展示静态 HTML，但自动触发机制未经验证。

## 使用示例

一个已验证的完整任务流程（悬赏 No.001「失落的金色补给」，预算挑战）：

1. 进入公会大厅，领取悬赏并确认预算（示例：40 元）与城市（示例：深圳）
2. Skill 调用 `query-nearby-stores` 列出门店供玩家选择，`query-meals` 展示真实菜单
3. 玩家选择巨无霸（code=1100）×1，`calculate-price` 核验实际价格 29 元（2900 分）
4. 结算：29 元 ≤ 40 元预算，解锁「初入公会 · 寻宝学徒 · 任务全勘」称号，用 `scripts/build_settlement.py` 生成本地结算卡

配置连接器的 JSON 结构见 `mcp-config.example.json`（鉴权值请替换为你自己的 MCP Token 环境变量）。

## 目标用户

- 使用 WorkBuddy、想要娱乐化点餐决策体验的普通用户
- 对"AI Agent 调用真实业务数据"的最佳实践与安全边界感兴趣的开发者
- 希望参考只读工具白名单、诚实呈现数据等模式构建自己 Skill 的参赛者

## GitHub 项目使用说明

- 本项目已发布于 GitHub 公开仓库，并作为麦当劳程序员节创意开发大赛参赛作品提交报名
- 浏览或克隆本仓库后，按上文「安装方式」将 Skill 复制到对应目录即可使用
- 正式发行包（精简 ZIP）计划通过 GitHub Release 附件提供，不随仓库源码提交

## 安全边界

- 只使用只读 MCP 工具；不创建订单、不绑定优惠券、不抽奖
- 不要求也不存储任何 MCP_TOKEN / Cookie / Authorization 凭证
- 游戏内称号均为虚构成就，非麦当劳官方奖励
