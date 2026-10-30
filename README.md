# wb-skill-converter

把「别处能跑的 skill」变成「WorkBuddy 能上架的 skill」。

支持的来源：Claude Code、Cursor、Codex、Gemini CLI、Dify、Coze、通用 `AGENTS.md` 仓库、`.cursorrules` / `GEMINI.md` 规则文件、`mcp.json` 配置、裸脚本目录，以及已经是 `SKILL.md` 结构的包。

转换是机械活，全部交给脚本；唯一需要人（或 agent）判断的是**中英双语描述与展示名**——脚本拿不到时会留 `[TODO]` 占位。

## 能做什么

| 子命令 | 作用 |
| --- | --- |
| `inspect` | 看一眼来源是什么平台、有哪些 frontmatter 字段、有没有踩冒号坑，不写任何文件 |
| `convert` | 转成平台 schema：重写 frontmatter、替换平台专属路径与工具名、补齐缺失字段，结束时自动体检 |
| `validate` | 只按平台规则体检，退出码非 0 就不该打包 |
| `pack` | 打包成 `<name>.zip`，保证 `SKILL.md` 位于压缩包根目录 |

## 快速开始

```bash
python scripts/port.py inspect  <来源目录或zip>       # 先侦察
python scripts/port.py convert  <来源> -o <输出目录>   # 转换 + 自动体检
python scripts/port.py validate <输出目录>             # 单独体检
python scripts/port.py pack     <输出目录> -o dist     # 打包成可上传的 zip
```

来源只有中文时 `description_en` 会是占位，体检报 `E008 描述里还留着 TODO`——这是设计如此。最省事的补法是带参数重跑，而不是手工改文件：

```bash
python scripts/port.py convert <来源> -o <输出> --force \
    --display-name "Jupyter 实验报告生成" --display-name-en "Jupyter Lab Report" \
    --description-zh "……" --description-en "……" --category education
```

体检通过长这样（拿本仓库自己当输入实测的）：

```
$ python scripts/port.py inspect .
来源平台 : skill-md
技能根   : .（SKILL.md 在根目录）
文件数   : 6
frontmatter 字段: name, display_name, display_name_en, description, description_zh, description_en, category, version, agent_created
正文长度: 2650 字符

$ python scripts/port.py validate .
✓ 通过
```

## 目录结构

```
wb-skill-converter/
├── SKILL.md                        # 技能主文档：流程、硬规则、错误码对照表（93 行）
├── scripts/
│   └── port.py                     # 转换 / 体检 / 打包四个子命令（810 行，纯标准库）
└── references/
    ├── workbuddy-schema.md         # 平台 frontmatter 字段全解、category 取值、打包上传规则、付费技能数据结构、真实驳回案例
    ├── platforms.md                # 各来源平台的识别特征、保留什么、丢弃什么、正文里的平台痕迹对照
    └── rewrite-rules.md            # 正文改写规则表（脚本自动改的 / 故意留给人工的）与发布前复核清单
```

## 三条硬规则

踩中任意一条，上传必失败：

1. **frontmatter 的每个值都加引号**。裸标量里出现「冒号 + 空格」会被 YAML 当成嵌套 mapping 起始，报 `mapping values are not allowed in this context`。
2. **`SKILL.md` 必须在压缩包根目录**。从 GitHub 下载的包常多套一层 `repo-main/`，平台找不到就报缺字段。
3. **七个必填字段一个都不能少**：`name`、`display_name`、`display_name_en`、`description`、`description_zh`、`description_en`、`version`。

完整错误码表（`E001`–`E009`、`W006`）在 [SKILL.md](SKILL.md) 里。

## 依赖

Python 3，只用标准库——目标机器上缺 PyYAML 也能跑。装了 PyYAML 时 `validate` 会额外做一次严格解析。本机实测环境为 Python 3.12.4。

## 什么时候不要用

技能已经在 WorkBuddy 里跑通、你只想改文案——直接编辑那个 `SKILL.md`，别走转换。
