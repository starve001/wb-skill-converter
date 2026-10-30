---
name: wb-skill-converter
display_name: 'WorkBuddy 转换格式 Skill'
display_name_en: 'WorkBuddy Skill Converter'
description: '把其他平台（Claude Code、Cursor、Codex、Gemini CLI、Dify、Coze、通用 AGENTS.md 仓库）的 Skill 包转换成 WorkBuddy 技能市场可发布格式：重写 frontmatter 为平台 schema、替换平台专属路径与工具名、补中英双语展示名与描述、按上传规则体检、打包成 SKILL.md 位于根目录的 zip。当用户要给 WorkBuddy 上架一个别处拿来的技能、上传报 frontmatter 或字段错误、或想把本地技能整理成能发布的包时使用。'
description_zh: '把其他平台（Claude Code、Cursor、Codex、Gemini CLI、Dify、Coze、通用 AGENTS.md 仓库）的 Skill 包转换成 WorkBuddy 技能市场可发布格式：重写 frontmatter 为平台 schema、替换平台专属路径与工具名、补中英双语展示名与描述、按上传规则体检、打包成 SKILL.md 位于根目录的 zip。当用户要给 WorkBuddy 上架一个别处拿来的技能、上传报 frontmatter 或字段错误、或想把本地技能整理成能发布的包时使用。'
description_en: 'Convert Skill packages from other platforms (Claude Code, Cursor, Codex, Gemini CLI, Dify, Coze, plain AGENTS.md repos) into WorkBuddy-marketplace-ready skills: rewrite frontmatter to the platform schema, replace platform-specific paths and tool names, fill in bilingual display names and descriptions, validate against upload rules, and package a zip with SKILL.md at the root. Use when a skill from elsewhere must be published on WorkBuddy, when an upload fails on frontmatter or missing fields, or when a local skill needs to be tidied into a publishable package.'
category: developer
version: 1.0.0
agent_created: true
---

# WorkBuddy 转换格式 Skill

把「别处能跑的 skill」变成「WorkBuddy 能上架的 skill」。转换是机械活，交给脚本；
唯一需要判断力的是**双语描述和展示名**——脚本会留 `[TODO]` 占位，由 agent 补。

## 什么时候用

- 用户拿来一个 Claude Code / Cursor / Codex / Gemini CLI / Dify / Coze 的 skill，要上架到 WorkBuddy。
- 上传报 `frontmatter 无法解析`，或 `缺少 Skill 版本号 / 中文展示名 / 英文描述`。
- 本地有一堆散装规则文件（`AGENTS.md`、`.cursorrules`、`README.md`），想整理成一个正规技能包。

不适用：技能已经在 WorkBuddy 里跑通、只想改文案——直接编辑那个 `SKILL.md`，别走转换。

## 三条硬规则

踩中任意一条，上传必失败：

1. **frontmatter 的每个值都加引号**。裸标量里出现「冒号+空格」（`, or in English: reproduce ...`）
   会被 YAML 当成嵌套 mapping 起始，报 `mapping values are not allowed in this context`。
2. **`SKILL.md` 必须在压缩包根目录**。GitHub 下载的包常多套一层 `repo-main/`，平台找不到就报缺字段。
3. **七个必填字段一个都不能少**：`name`、`display_name`、`display_name_en`、`description`、
   `description_zh`、`description_en`、`version`。少哪个报哪个。

## 标准流程

<!-- S 指本技能脚本路径，按实际安装位置替换 -->

```bash
python <skill>/scripts/port.py inspect  <来源目录或zip>     # 先看平台、字段、有没有冒号坑
python <skill>/scripts/port.py convert  <来源> -o <输出目录> # 转换，打印丢弃字段与正文替换明细
python <skill>/scripts/port.py validate <输出目录>           # 单独体检，退出码非 0 就别打包
python <skill>/scripts/port.py pack     <输出目录> -o dist   # 打包成 <name>.zip，SKILL.md 在根目录
```

`convert` 结束会自动体检。若报 `E008 描述里还留着 TODO`，说明脚本没拿到双语描述——
按下一节补上即可，这是设计如此，不是 bug。

## 补双语描述与展示名

来源只有中文时 `description_en` 是占位，只有英文时反过来。补的时候：

- **两种语言各写各的**，不要一边写中文一边夹英文触发词。英文侧写 `Use when the user ...`，
  中文侧写「当用户……时使用」。
- **触发词要具体**：把用户可能说的原话、文件类型、对象名词都写进去，这是技能被召回的唯依据。
  写「处理文档」等于没写；写「把课程实验课件（PDF / 截图）复刻成 .ipynb 并出 A4 PDF」才有效。
- **长度 100–300 字**。超过 500 字市场列表会截断，且每次对话都占上下文。
- `display_name` 是市场里给人看的中文名（可含英文品牌词，如「Canva可画」），
  `display_name_en` 是纯英文名，两者都别超过 30 字符。

补写最省事的方式是带参数重跑 `convert`，而不是手工改文件：

```bash
python <skill>/scripts/port.py convert <来源> -o <输出> --force \
    --display-name "Jupyter 实验报告生成" --display-name-en "Jupyter Lab Report" \
    --description-zh "……" --description-en "……" --category education
```

## 常见驳回与对应错误码

| 错误码 | 含义 | 处理 |
| --- | --- | --- |
| E001 | 根目录没有 SKILL.md | 用 `pack` 重打包（会把内容提到根层） |
| E002 | 文件带 BOM | 用 `convert` 重写；或另存为「UTF-8 无 BOM」 |
| E004 | 裸标量含「冒号+空格」 | 跑一次 `convert`，它统一加引号 |
| E005 | 缺必填字段 | `convert` 自动补齐，双语描述需人工写 |
| E006 | `name` 不合规 | 只能小写字母/数字/连字符，≤40 字符 |
| E007 | `version` 不是 x.y.z | `convert` 会把 `v2.1` 归一成 `2.1.0` |
| E008 | 描述还留着 TODO | 补双语描述 |
| E009 | 正文引用了不存在的 `references/x.md` | 补文件或删引用 |

`W` 开头的警告不阻塞上传，但值得看一眼：`W006`「英文描述里中文占比过高」通常意味着
源里的英文段其实是中英混排，最好人工重写。

## 资源

- `scripts/port.py` — 转换 / 体检 / 打包，纯标准库，无第三方依赖。
- `references/workbuddy-schema.md` — 平台字段全解、分类取值、付费技能数据结构、真实驳回案例。
- `references/platforms.md` — 各来源平台的识别特征、保留什么、丢弃什么。
- `references/rewrite-rules.md` — 正文改写规则表与人工复核清单。

改完描述后用 `validate` 再跑一次，`✓ 通过` 再上传，别拿平台当测试环境。
