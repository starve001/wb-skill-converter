# WorkBuddy 技能市场 frontmatter schema

平台用的不是 Claude 的 `name + description` 两字段规范，而是技能市场自己的一套。
下面这张表来自实际已上架技能的 `SKILL.md` 与市场接口数据。

## 字段全解

| 字段 | 必填 | 类型 | 说明 |
| --- | --- | --- | --- |
| `name` | 是 | string | 技能标识。`^[a-z0-9][a-z0-9-]{0,39}$`：小写字母/数字/连字符，≤40 字符，不能以连字符开头。建议与目录名一致 |
| `display_name` | 是 | string | 市场展示名（中文）。可含英文品牌词，如「Canva可画」「Seedream 专家」 |
| `display_name_en` | 是 | string | 英文展示名。纯英文，如「Seedream Expert」 |
| `description` | 是 | string | 主描述。市场列表与技能召回都用它，**约定与 `description_zh` 同值** |
| `description_zh` | 是 | string | 中文描述。写清「做什么 + 什么时候用 + 触发词」 |
| `description_en` | 是 | string | 英文描述。不要混中文，`Use when ...` 起手最自然 |
| `version` | 是 | string | 严格 `x.y.z`。`1.0.0`，不带 `v` 前缀 |
| `category` | 建议 | string | 见下方取值表。缺失时市场分类可能错 |
| `author` | 可选 | string | 作者或团队名 |
| `license` | 可选 | string | 许可标识。注意 Apache-2.0 / MIT 都允许买家再分发 |
| `icon` | 可选 | string | 图标地址，或上传时用默认头像 |
| `permissions` | 可选 | mapping | 权限声明，嵌套块原样透传。常见键：`provisional`、`read`、`write` |
| `agent_created` | 建议 | bool | `true`。标记由 agent 创建，后续 `skill_manage` 改这个技能才不会受限 |
| `homepage` / `repository` / `tags` / `contributors` / `changelog` | 可选 | — | 有就保留 |

**不要写**（对平台无意义，写了也不报错但属于噪音）：`allowed-tools`、`allowed_tools`、
`argument-hint`、`model`、`tools`、`disable-model-invocation`、`user-invocable`、`triggers`。

## category 取值

市场里出现过的值（取小写连字符风格）：

```
productivity  education  media  design  data  writing  research
finance  automation  developer  business  marketing  collaboration  content-creation
```

另有细分值偶尔出现：`productivity-tools`、`image-video`、`ecommerce-analytics`、
`bioinformatics`、`legal`、`manufacturing`。

选不准时的判断顺序：技能产出什么（文档→`writing`，数据→`data`，代码→`developer`）→
服务谁（学生/教学→`education`，企业运营→`business`）→ 都说不清就 `productivity`。

## 打包与上传规则

- `name` 在**全平台唯一**，被占用会直接驳回（「技能名称已被占用」）。`workbuddy-` 前缀疑似官方保留，
  自定义技能避免使用；撞名时换一个前缀（如 `wb-`、`my-`）改 `name` 和目录名后重新打包即可，
  `display_name` 不受唯一性限制，可以照旧。
- 压缩包**根目录**必须是 `SKILL.md`。多套一层目录（GitHub 下载的 `repo-main/`）会导致解析异常。
- 目录里只能有**一个** `SKILL.md`；嵌套的子目录另有 SKILL.md 会让解析器抓错。
- 编码 UTF-8 **无 BOM**；换行统一 LF（CRLF 一般能用，但不建议）。
- 排除：`__pycache__`、`.git`、`.DS_Store`、`node_modules`、`*.pyc`。
- 上传后平台会生成技能 ID（形如 `os_xxxxxxxxxxxx`），并解析出「市场展示名称 / 分类 / 版本号 / 价格 / 类目 / 介绍」。
  这一页是只读预览，**改任何东西都要回到编辑态重新提交**。
- 改动（含改价、改文案）通常要重新过审。已安装用户不受影响。

## 付费技能的数据结构

价格**不能写进 SKILL.md**，是运营后台的表单字段。接口侧的形态：

```json
{
  "need_pay": 1,
  "pay_detail": {
    "resourceType": "skill",
    "payMode": 2,
    "needEncrypt": 0,
    "goods": [
      { "goodsId": "PRO-XXXX", "durationDays": 30, "amount": 29900,
        "canRefund": false, "canRenew": false }
    ]
  }
}
```

要点：

- `payMode: 2` = 按周期订阅，**没有买断/永久档**。想做长期授权只能把 `durationDays` 填大（如 3650）。
- `amount` 单位是**分**：`29900` = ¥299。
- `needEncrypt` = 是否加密下发。付费技能建议开，否则买家能直接读到全部源码与提示词。
- 付费前置条件：实名认证 + 结算收款账户。缺任一项，价格项通常点不动。

## 两个真实驳回案例

**案例 1：YAML 语法**

```
SKILL.md 格式错误 - frontmatter 无法解析: yaml: line 2: mapping values are not allowed in this context
```

原因：`description` 是裸标量，且内含 `..., or in English: reproduce ...`。
YAML 把 `: ` 当成新的键值对起始。
修法：整条值加单引号（内部单引号写成 `''`），或改成 `>-` 块标量。最省事是把冒号改成逗号。

**案例 2：缺字段**

```
缺少 Skill 版本号 / 缺少中文展示名 / 缺少英文展示名 / 缺少中文描述 / 缺少英文描述
```

原因：按 Claude 规范只写了 `name` + `description`。
修法：补齐七个必填字段，`description` 与 `description_zh` 同值。

两次都不是内容问题，都是 schema 问题。所以**上传前先跑 `port.py validate`**，
本地能过再传，别把平台当测试环境（每次驳回都要重新走一遍解析流程）。
