# 正文改写规则与人工复核清单

`convert` 只会改**路径和工具名**这类有明确对应关系的字符串。以下几类必须人工看。

## 脚本自动替换的

| 匹配 | 替换为 | 原因 |
| --- | --- | --- |
| `~/.claude/skills` | `~/.workbuddy/skills` | 用户级技能目录 |
| `~/.claude` | `~/.workbuddy` | 用户级配置目录 |
| `.claude/skills` | `.workbuddy/skills` | 项目级技能目录 |
| `.claude/` | `.workbuddy/` | 项目级配置目录 |
| `Claude Code` | `WorkBuddy` | 产品名 |
| `TodoWrite` | `TaskCreate / TaskUpdate` | 待办工具没有对应物，拆成创建+更新 |
| `NotebookEdit` | `Edit` | 编辑器工具 |

替换会打印明细（「正文替换：用户级技能目录 × 2」），逐条核对是否符合语境。

## 脚本故意不改、需要人工判断的

**1. `CLAUDE.md` / `AGENTS.md` 这类文件名**
目标平台没有同名文件。改了会指向不存在的路径，不改又显得过时。
建议：改成「项目约定文件」这类泛称，或保留原文并在旁注明来源。

**2. 真实 API 标识里的 `claude`**
如 `claude-sonnet-4`、`api.anthropic.com`。这是可执行的技术标识，改写会直接导致调用失败。

**3. 工具能力差异**
来源平台有的工具目标平台可能没有，反之亦然。重点核对：

| 来源常见写法 | 目标平台对应 |
| --- | --- |
| `Bash` | 有（终端） |
| `Read` / `Write` / `Edit` | 有 |
| `WebFetch` / `WebSearch` | 有 |
| `AskUserQuestion` | 有 |
| `TodoWrite` | `TaskCreate` / `TaskUpdate` / `TaskList` |
| `Task`（子代理） | `Agent` |
| `NotebookEdit` | 无，用 `Edit` 改 `.ipynb` 文本 |
| 自定义 slash command | 无，展开成正文步骤 |

**4. 平台的隐式约定**
来源技能常默认自己「被注入到系统提示里」，目标平台是「按需加载」。
凡是写着「你必须在每次对话开始时……」的段落，改成在对应步骤里执行。

**5. 绝对路径与个人信息**
来源包里的 `~/work/xxx`、`/Users/name/...` 这类真实路径，发布前必须换成占位符
（`REPLACE-WITH-YOUR-ID` 之类），否则既泄露信息又在新机器上跑不通。

## 发布前复核清单

- [ ] `validate` 返回 `✓ 通过`，E 开头的一条都没有
- [ ] 双语描述各自独立成句，没混排
- [ ] 描述里至少有 3 个具体触发词（用户原话/文件类型/对象名）
- [ ] `display_name` ≤ 30 字符，`display_name_en` 是纯英文
- [ ] 正文里没有残留 `~/.claude`、`Claude Code`、个人绝对路径
- [ ] 正文引用的每个 `scripts/`、`references/`、`assets/` 文件都存在（E009 会查）
- [ ] 脚本在干净环境里能跑（无第三方依赖，或 `requirements.txt` 写全）
- [ ] 压缩包根目录就是 `SKILL.md`，且全包只有一个 `SKILL.md`
- [ ] 若要收费：`LICENSE` 是否允许买家再分发？是否需要换专有许可；是否开启加密下发
