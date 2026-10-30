# 各来源平台的识别特征与映射

## 识别特征

`inspect` 按文件名/目录特征判断来源，可多重命中：

| 标签 | 识别特征 | 通常是什么 |
| --- | --- | --- |
| `skill-md` | 存在 `SKILL.md` | 已经是 agent skill 结构，转换成本最低 |
| `claude-plugin` | `.claude-plugin/plugin.json` | Claude Code 插件包，可能一个包内含多个 skill |
| `claude-agent` | `agents/*.md` | Claude 子代理定义，通常是单个 md + frontmatter |
| `claude-command` | `commands/*.md` | 斜杠命令，本质是提示词模板 |
| `cursor` | `.cursor/rules/*.mdc`、`.cursorrules` | 规则文本，不是 skill，需要重组成「步骤 + 判断」 |
| `windsurf` | `.windsurfrules` | 同上 |
| `cline` | `.clinerules` | 同上 |
| `roo` | `.roo/` | 模式定义，常带自定义指令块 |
| `gemini-cli` | `GEMINI.md` | 单一规则文件 |
| `agents-md` | `AGENTS.md` | 通用约定文件，Codex / 多数 CLI 都认 |
| `mcp` | `mcp.json`、`.mcp.json` | MCP 服务器配置——**不是 skill**，见下方警告 |
| `generic` | 以上都不匹配 | 裸脚本目录，按 README / 文件结构推断 |

## 各类来源的转换要点

### 已经是 SKILL.md 结构

只做三件事：换 frontmatter schema、改写正文里的平台路径/工具名、重新打包。
正文结构、脚本、references 一律不动。

### Claude 插件包（一个包里多个 skill）

平台一个 zip 只认一个技能。遇到多 skill 的包：

1. 先 `inspect` 看 `skills/` 下有几个子目录；
2. 每个子目录单独 `convert` 成独立技能；
3. 如果它们共享脚本/资源，复制一份到各自目录——不要用相对路径跨包引用。

### 规则文件（.cursorrules / GEMINI.md / .windsurfrules）

这类文件是「约束」不是「流程」，直接转会把技能写成一堆祈使句，agent 不知道何时该用。
必须补一层结构后再转：

- 加 `## 什么时候用`（什么输入、什么场景触发）
- 加 `## 步骤`（把散落的规则整理成 3–7 步可执行流程）
- 规则本身降级成 `## 约束` 小节
- description 里写清触发词，别只写「按规则处理」

### MCP 服务器配置（mcp.json）

**这不是技能。** 它描述的是外部工具连接方式，转成 skill 只会得到一个空壳。
正确做法是告诉用户：MCP 走连接器（Connector）配置，WorkBuddy 的 MCP 配置在
`~/.workbuddy/mcp.json`，写入后需要在连接器管理页「信任」该服务器才会生效。
转换器遇到这类输入应当停下并说明，不要硬转。

### 裸脚本目录

按目录结构和 README 推断用途，生成骨架后由 agent 补：什么时候用、步骤、输入输出约定。

## 正文里的平台痕迹对照

| 来源写法 | 目标写法 |
| --- | --- |
| `~/.claude/skills/` | `~/.workbuddy/skills/` |
| `~/.claude/` | `~/.workbuddy/` |
| `.claude/skills/` | `.workbuddy/skills/`（项目级） |
| `Claude Code` | `WorkBuddy` |
| `TodoWrite` | `TaskCreate` / `TaskUpdate` |
| `NotebookEdit` | `Edit` |

不要机械替换以下内容，会让语义变形：

- 代码块里的真实路径字符串（如示例命令里的 `~/.claude/...`，若那是说明来源平台的语境）
- `CLAUDE.md` 文件名——它在目标平台没有对应物，改写会造出不存在的文件引用。
  正确做法是保留原文并加一句说明，或整体替换成「项目约定文件」这种泛称。
- 第三方 API 里含 `claude` 的模型名（如 `claude-sonnet-4`）——那是真实的 API 标识，改了会调用失败。
