#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wb-skill-converter — 把其他平台的 skill 包转成 WorkBuddy 技能市场可发布的技能包。

四个子命令：
    inspect   看一眼来源是什么平台、有哪些字段、有哪些坑
    convert   转换（生成符合平台 schema 的 SKILL.md）
    validate  按平台规则体检（不通过就不该上传）
    pack      打包成 SKILL.md 位于根目录的 zip

只依赖标准库：目标机器上缺 PyYAML 也能跑。装有 PyYAML 时会额外做一次严格解析。
"""

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import time
import zipfile
from pathlib import Path

try:  # 让 Windows 控制台也能输出中文
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# ---------------------------------------------------------------- 平台 schema

# 平台必填字段（缺一个就会被驳回）
REQUIRED_FIELDS = [
    "name",
    "display_name",
    "display_name_en",
    "description",
    "description_zh",
    "description_en",
    "version",
]

# 市场已有的分类取值，超集见 references/workbuddy-schema.md
CATEGORIES = [
    "productivity", "education", "media", "design", "data", "writing",
    "research", "finance", "automation", "developer", "business",
    "marketing", "collaboration", "content-creation",
]

# 来源 frontmatter 里对目标平台无意义、需要丢弃的键
DROP_KEYS = {
    "allowed-tools", "allowed_tools", "argument-hint", "allowedTools",
    "disable-model-invocation", "user-invocable", "model", "tools", "triggers",
}

# 需要原样透传的嵌套块（权限声明等）
PASSTHROUGH_NESTED = ["permissions"]

# 平台也认、有就保留的附加字段
EXTRA_KEYS = ["author", "license", "icon", "homepage", "repository", "tags",
              "contributors", "changelog"]

PLACEHOLDER_ZH = "[TODO 待补] 一句中文说明：这个技能做什么、用户说什么话时该用它。"
PLACEHOLDER_EN = "[TODO] One English sentence: what this skill does and when to use it."

CATEGORY_HINTS = {
    "education": ["课程", "教学", "作业", "考试", "讲义", "实验", "学习", "课堂",
                  "讲稿", "education", "course", "lab", "teaching",
                  "student", "tutor", "lecture"],
    "data": ["数据", "分析", "统计", "表格", "csv", "excel", "data", "analytics",
             "spreadsheet", "sql", "pandas"],
    "writing": ["写作", "文案", "润色", "文档", "writing", "copywriting", "edit",
                "proofread", "docx", "论文", "笔记", "周报", "摘要"],
    "design": ["设计", "配色", "海报", "ui", "ux", "figma", "design", "logo",
               "banner", "layout"],
    "media": ["视频", "音频", "图片", "剪辑", "video", "audio", "image", "photo",
              "subtitle", "封面"],
    "research": ["调研", "检索", "文献", "论文", "research", "literature", "survey",
                 "patent"],
    "finance": ["财务", "财报", "投资", "股票", "估值", "finance", "stock",
                "valuation", "invoice"],
    "developer": ["代码", "重构", "调试", "测试", "code", "debug", "refactor",
                  "test", "api", "git", "deploy"],
    "automation": ["自动化", "批量", "定时", "automation", "batch", "cron",
                   "workflow", "pipeline"],
    "marketing": ["营销", "投放", "增长", "marketing", "seo", "ads", "campaign"],
    "collaboration": ["协作", "会议", "日程", "collaboration", "meeting",
                      "calendar", "kanban"],
    "content-creation": ["生成内容", "创作", "content", "generate", "creative"],
}

# 正文里的平台痕迹替换规则：(正则, 替换, 说明)
BODY_REWRITES = [
    (r"~/\.claude/skills", "~/.workbuddy/skills", "用户级技能目录"),
    (r"~/\.claude", "~/.workbuddy", "用户级配置目录"),
    (r"(?<![\w./])\.claude/skills", ".workbuddy/skills", "项目级技能目录"),
    (r"(?<![\w./])\.claude/", ".workbuddy/", "项目级配置目录"),
    (r"\bClaude Code\b", "WorkBuddy", "产品名"),
    (r"\bclaude-code\b", "workbuddy", "产品名"),
    (r"\bTodoWrite\b", "TaskCreate / TaskUpdate", "待办工具"),
    (r"\bNotebookEdit\b", "Edit", "编辑器工具"),
]

JUNK_NAMES = {"__pycache__", ".git", ".ds_store", ".idea", ".vscode",
              "node_modules", ".pytest_cache"}
JUNK_SUFFIX = {".pyc", ".pyo", ".DS_Store"}


# ---------------------------------------------------------------- 极简 YAML

def _unquote(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        if v[0] == '"':
            return v[1:-1].replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")
        return v[1:-1].replace("''", "'")
    return v


def parse_frontmatter(text):
    """解析 SKILL.md 的 frontmatter，返回 (data, body, meta)。

    meta['plain'] 记录哪些键是未加引号的裸标量——它们最容易被 YAML 解析器拒绝。
    不追求完整 YAML 语义，只覆盖 frontmatter 常见写法。
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, text, {"found": False, "plain": set(), "raw": {}}

    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() in ("---", "..."):
            end = i
            break
    if end is None:
        return {}, text, {"found": False, "plain": set(), "raw": {}}

    fm = lines[1:end]
    data, raw, plain = {}, {}, set()
    i = 0
    while i < len(fm):
        line = fm[i]
        if not line.strip() or line.lstrip().startswith("#") or line[0] in " \t":
            i += 1
            continue
        m = re.match(r"^([A-Za-z0-9_.\-]+)\s*:\s*(.*)$", line)
        if not m:
            i += 1
            continue
        key, rest = m.group(1), m.group(2)
        block = [line]

        if rest[:1] in ("|", ">"):
            style = rest[0]
            i += 1
            buf = []
            while i < len(fm) and (not fm[i].strip() or fm[i][0] in " \t"):
                buf.append(fm[i])
                block.append(fm[i])
                i += 1
            ind = min((len(b) - len(b.lstrip()) for b in buf if b.strip()), default=0)
            ded = [b[ind:] for b in buf]
            if style == ">":
                data[key] = " ".join(b.strip() for b in ded if b.strip()).strip()
            else:
                data[key] = "\n".join(ded).strip("\n")
        elif rest.strip() == "":
            i += 1
            buf = []
            while i < len(fm) and (not fm[i].strip() or fm[i][0] in " \t"
                                   or fm[i].lstrip().startswith("- ")):
                buf.append(fm[i])
                block.append(fm[i])
                i += 1
            data[key] = None
        else:
            val = rest
            i += 1
            while (i < len(fm) and fm[i][:1] in " \t" and fm[i].strip()
                   and not re.match(r"^\s+[A-Za-z0-9_.\-]+\s*:", fm[i])):
                val += " " + fm[i].strip()
                block.append(fm[i])
                i += 1
            if not (len(rest.strip()) >= 2 and rest.strip()[0] == rest.strip()[-1]
                    and rest.strip()[0] in "\"'"):
                plain.add(key)
            data[key] = _unquote(val)

        raw[key] = "\n".join(block)

    return data, "\n".join(lines[end + 1:]), {"found": True, "plain": plain, "raw": raw}


def yaml_scalar(v):
    """输出成一定不会被解析器误判的形式：单引号包裹，或块标量。"""
    v = str(v)
    if "\n" in v:
        return "|-\n" + "\n".join(("  " + ln) if ln else "" for ln in v.split("\n"))
    return "'" + v.replace("'", "''") + "'"


SAFE_BARE = {"name", "version", "category"}  # 取值天然安全，不加引号（部分加载器不脱引号）


def emit_frontmatter(fields, nested_raw):
    out = ["---"]
    for k, v in fields.items():
        if v is None:
            continue
        if isinstance(v, bool):
            out.append(f"{k}: {'true' if v else 'false'}")
        elif k in nested_raw and nested_raw[k]:
            head = nested_raw[k].split("\n")[0]
            if head.split(":", 1)[1].strip():  # 行内写法，整块原样输出
                out.append(nested_raw[k])
            else:
                out.append(f"{k}:")
                out.extend(nested_raw[k].split("\n")[1:])
        elif k in SAFE_BARE and re.fullmatch(r"[A-Za-z0-9._-]+", str(v)):
            out.append(f"{k}: {v}")
        else:
            out.append(f"{k}: {yaml_scalar(v)}")
    out.append("---")
    return "\n".join(out)


# ---------------------------------------------------------------- 工具函数

def slugify(s, fallback="skill"):
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    s = re.sub(r"-{2,}", "-", s)
    if not s:
        s = fallback
    if s[0].isdigit():
        s = "skill-" + s
    return s[:40].strip("-")


def normalize_version(v, fallback="1.0.0"):
    """v2.1 / 2.1 / 2.1.3 / 2.1.0-beta → x.y.z，认不出就用 fallback。"""
    s = str(v or "").strip().lstrip("vV")
    m = re.match(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?", s)
    if not m:
        return fallback
    return f"{m.group(1)}.{m.group(2) or '0'}.{m.group(3) or '0'}"


def cjk_ratio(s):
    if not s:
        return 0.0
    cjk = len(re.findall(r"[\u4e00-\u9fff]", s))
    letters = len(re.findall(r"[A-Za-z]", s))
    return cjk / max(1, cjk + letters)


def split_bilingual(text):
    """把中英混写的描述拆成 (中文, 英文)。

    典型来源是「一句中文 + Use when the user ...」这种混排：整段塞给哪个字段都不对，
    按句子判定语种后分桶。只有一侧有内容时返回 None，交给调用方走单语分支。
    """
    if not text:
        return None
    parts = [p.strip() for p in re.split(r"(?<=[。！？!?])\s*|(?<=\.)\s+", text) if p.strip()]
    zh, en = [], []
    for p in parts:
        (zh if cjk_ratio(p) >= 0.3 else en).append(p)
    if zh and en:
        return " ".join(zh).strip(), " ".join(en).strip()
    return None


def first_heading(body):
    for line in body.split("\n"):
        m = re.match(r"^#\s+(.+?)\s*$", line)
        if m:
            return m.group(1).strip()
    return ""


def title_case_slug(slug):
    return " ".join(w.capitalize() for w in slug.split("-") if w)


def guess_category(*texts):
    blob = " ".join(t for t in texts if t).lower()
    best, best_hits = "productivity", 0
    for cat, words in CATEGORY_HINTS.items():
        hits = sum(blob.count(w.lower()) for w in words)
        if hits > best_hits:
            best, best_hits = cat, hits
    return best


def read_text(p):
    return Path(p).read_text(encoding="utf-8", errors="replace")


def is_junk(name):
    low = name.lower()
    return low in JUNK_NAMES or name in JUNK_SUFFIX


# ---------------------------------------------------------------- 来源处理

STRAY_TOP = {"commands", "agents", ".claude-plugin", ".cursor", ".roo"}
STRAY_FILES = {".cursorrules", ".windsurfrules", ".clinerules", "GEMINI.md",
               "gemini.md", "CLAUDE.md", "AGENTS.md", "agents.md"}


def is_stray(rel):
    """来源平台的残留文件，发布前建议删掉。"""
    return rel.split("/")[0] in STRAY_TOP or rel in STRAY_FILES


PLATFORM_SIGNATURES = [
    ("claude-plugin", [".claude-plugin/plugin.json"]),
    ("cursor", [".cursor/rules", ".cursorrules"]),
    ("windsurf", [".windsurfrules"]),
    ("cline", [".clinerules"]),
    ("roo", [".roo/"]),
    ("gemini-cli", ["GEMINI.md", "gemini.md"]),
    ("agents-md", ["AGENTS.md", "agents.md"]),
    ("mcp", ["mcp.json", ".mcp.json"]),
    ("claude-command", ["commands/"]),
    ("claude-agent", ["agents/"]),
]


def detect_platform(names):
    """names: 相对路径列表。"""
    joined = "\n".join(names)
    hits = []
    for label, sigs in PLATFORM_SIGNATURES:
        for s in sigs:
            if (s.endswith("/") and s in joined + "/") or (not s.endswith("/") and s in names):
                hits.append(label)
                break
    if "SKILL.md" in names or any(n.endswith("SKILL.md") for n in names):
        hits.insert(0, "skill-md")
    return hits or ["generic"]


def materialize(src):
    """把 zip / 目录 / 单个文件统一变成 (根目录, 临时目录或None)。"""
    src = Path(src)
    if src.is_file() and src.suffix.lower() == ".zip":
        tmp = Path(tempfile.mkdtemp(prefix="porter-"))
        with zipfile.ZipFile(src) as z:
            z.extractall(tmp)
        entries = [p for p in tmp.iterdir() if not p.name.startswith("__MACOSX")]
        if len(entries) == 1 and entries[0].is_dir():
            return entries[0], tmp
        return tmp, tmp
    if src.is_file():
        return src.parent, None
    return src, None


def list_files(root):
    out = []
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if not is_junk(d)]
        for f in fns:
            if is_junk(f):
                continue
            out.append(str(Path(dp, f).relative_to(root)).replace(os.sep, "/"))
    return sorted(out)


def find_skill_root(root):
    """优先找 SKILL.md 所在目录；没有就把来源目录本身当技能根。"""
    root = Path(root)
    if (root / "SKILL.md").exists():
        return root, True
    for p in sorted(root.rglob("SKILL.md")):
        return p.parent, False
    return root, False


# ---------------------------------------------------------------- 转换

def rewrite_body(body):
    """把正文里的平台专属路径/工具名换成 WorkBuddy 的写法，返回 (新正文, 改动明细)。"""
    changes = []
    new = body
    for pat, rep, desc in BODY_REWRITES:
        n = len(re.findall(pat, new))
        if n:
            new = re.sub(pat, rep, new)
            changes.append((desc, n))
    return new, changes


def convert(src, out_dir=None, overrides=None, force=False):
    overrides = overrides or {}
    root, is_skill_dir = materialize(src)
    tmp_holder = root
    skill_root, at_root = find_skill_root(root)

    skill_md = skill_root / "SKILL.md"
    if skill_md.exists():
        text = read_text(skill_md)
    else:
        # 没有 SKILL.md：用 README / AGENTS.md 当正文素材
        for cand in ("AGENTS.md", "README.md", "readme.md", "CLAUDE.md"):
            if (skill_root / cand).exists():
                text = "# " + skill_root.name + "\n\n" + read_text(skill_root / cand)
                break
        else:
            text = "# " + skill_root.name + "\n"

    data, body, meta = parse_frontmatter(text)
    if not meta["found"]:
        body = text
        data = {}

    names = list_files(skill_root)
    platforms = detect_platform(names)

    # ---- name
    raw_name = overrides.get("name") or data.get("name") or skill_root.name
    name = slugify(raw_name)

    # ---- display names
    heading = first_heading(body)
    if heading and raw_name:
        # 「my-skill — 中文副标题」这种 H1，展示名只要副标题
        heading = re.sub(rf"^{re.escape(str(raw_name))}\s*[—\-–:|]\s*", "", heading,
                         flags=re.I).strip() or heading
    display_zh = (overrides.get("display_name") or data.get("display_name")
                  or data.get("displayName") or data.get("title")
                  or heading or name)
    display_zh = re.sub(r"\s+", " ", str(display_zh)).strip()[:60]
    display_en = (overrides.get("display_name_en") or data.get("display_name_en")
                  or data.get("displayNameEn") or "")
    if not display_en:
        display_en = display_zh if cjk_ratio(display_zh) < 0.2 else title_case_slug(name)
    display_en = re.sub(r"\s+", " ", str(display_en)).strip()[:60]

    # ---- descriptions
    src_desc = (overrides.get("description") or data.get("description")
                or data.get("summary") or data.get("when_to_use") or "")
    src_desc = re.sub(r"\s+", " ", str(src_desc)).strip()

    split = split_bilingual(src_desc)
    if split:
        zh_part, en_part = split
    elif cjk_ratio(src_desc) >= 0.25:
        zh_part, en_part = src_desc, ""
    else:
        zh_part, en_part = "", src_desc

    desc_zh = (overrides.get("description_zh") or data.get("description_zh")
               or zh_part or PLACEHOLDER_ZH)
    desc_en = (overrides.get("description_en") or data.get("description_en")
               or en_part or PLACEHOLDER_EN)

    # ---- category / version
    category = overrides.get("category") or data.get("category") or ""
    if not category:
        category = guess_category(src_desc, display_zh, " ".join(names))
    category = str(category).strip().lower()
    if category not in CATEGORIES:
        category = guess_category(src_desc, display_zh, " ".join(names))

    version = normalize_version(overrides.get("version") or data.get("version") or "1.0.0")

    # ---- 正文重写
    new_body, body_changes = rewrite_body(body)

    # ---- 组装 frontmatter
    nested_raw = {}
    for k in PASSTHROUGH_NESTED:
        if k in meta["raw"]:
            nested_raw[k] = meta["raw"][k]

    fields = {
        "name": name,
        "display_name": display_zh,
        "display_name_en": display_en,
        "description": desc_zh,
        "description_zh": desc_zh,
        "description_en": desc_en,
        "category": category,
        "version": version,
        "agent_created": True,
    }
    for k, v in nested_raw.items():
        fields[k] = v
    for k in EXTRA_KEYS:
        if data.get(k) and k not in fields:
            fields[k] = data[k]

    new_text = emit_frontmatter(fields, nested_raw) + "\n" + new_body.lstrip("\n")

    # ---- 落盘
    dest = Path(out_dir) if out_dir else Path.cwd() / name
    if dest.exists():
        if not force:
            raise SystemExit(f"目标已存在：{dest}（加 --force 覆盖）")
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    if at_root:
        for item in skill_root.iterdir():
            if item.name in ("SKILL.md",) or is_junk(item.name):
                continue
            target = dest / item.name
            if item.is_dir():
                shutil.copytree(item, target,
                                ignore=shutil.ignore_patterns(*JUNK_NAMES, "*.pyc"))
            else:
                shutil.copy2(item, target)
    else:
        for item in skill_root.iterdir():
            if is_junk(item.name):
                continue
            target = dest / item.name
            if item.is_dir():
                shutil.copytree(item, target,
                                ignore=shutil.ignore_patterns(*JUNK_NAMES, "*.pyc"))
            else:
                shutil.copy2(item, target)

    (dest / "SKILL.md").write_text(new_text, encoding="utf-8", newline="\n")

    strays = [n for n in list_files(dest) if is_stray(n)]
    report = {
        "source": str(src),
        "strays": strays,
        "platforms": platforms,
        "output": str(dest),
        "name": name,
        "renamed_from": raw_name if str(raw_name) != name else None,
        "category": category,
        "version": version,
        "dropped_keys": sorted([k for k in data if k in DROP_KEYS]),
        "kept_keys": sorted([k for k in data if k not in DROP_KEYS]),
        "body_rewrites": body_changes,
        "todo": [k for k, v in (("description_zh", desc_zh), ("description_en", desc_en))
                 if "TODO" in str(v)],
    }
    if tmp_holder and tmp_holder != Path(src) and str(tmp_holder).startswith(tempfile.gettempdir()):
        shutil.rmtree(tmp_holder, ignore_errors=True)
    return report, dest


# ---------------------------------------------------------------- 校验

def _in_temp(p):
    """判断路径是否落在临时目录里（zip 解包后的位置），用于跳过目录名比对。"""
    try:
        return str(Path(p).resolve()).lower().startswith(
            str(Path(tempfile.gettempdir()).resolve()).lower())
    except Exception:
        return False


def validate(path):
    """按平台规则体检。返回 (errors, warnings, info)。"""
    errors, warns, info = [], [], {}
    root, at_root = find_skill_root(materialize(path)[0])
    root = Path(root).resolve()
    skill_md = Path(root) / "SKILL.md"

    if not skill_md.exists():
        errors.append(("E001", "根目录没有 SKILL.md"))
        return errors, warns, info
    if not at_root:
        warns.append(("W001", "SKILL.md 不在压缩包根目录，平台可能找不到（用 pack 重新打包）"))

    raw = skill_md.read_bytes()
    if raw[:3] == b"\xef\xbb\xbf":
        errors.append(("E002", "SKILL.md 带 UTF-8 BOM，frontmatter 会解析失败"))
    if b"\r\n" in raw:
        warns.append(("W002", "存在 CRLF 换行，建议统一成 LF"))

    text = raw.decode("utf-8", errors="replace")
    data, body, meta = parse_frontmatter(text)

    if not meta["found"]:
        errors.append(("E003", "文件开头不是 --- 包裹的 frontmatter"))
        return errors, warns, info

    # YAML 裸标量里出现 ": " 是最常见的上传失败原因
    for k in sorted(meta["plain"]):
        v = data.get(k)
        if isinstance(v, str) and (": " in v or v.rstrip().endswith(":")):
            errors.append(("E004", f"`{k}` 是裸标量且含「冒号+空格」，YAML 会报 "
                                   f"mapping values are not allowed in this context；"
                                   f"用 convert 重写或整体加引号"))

    for f in REQUIRED_FIELDS:
        if not data.get(f):
            errors.append(("E005", f"缺少必填字段 `{f}`"))

    name = str(data.get("name") or "")
    if name:
        if not re.match(r"^[a-z0-9][a-z0-9-]{0,39}$", name):
            errors.append(("E006", f"name「{name}」不合规：只能小写字母/数字/连字符，"
                                   f"不超过 40 字符，不能以连字符开头"))
        if Path(root).name != name and at_root and not _in_temp(root):
            warns.append(("W003", f"name「{name}」与目录名「{Path(root).name}」不一致"))

    ver = str(data.get("version") or "")
    if ver and not re.match(r"^\d+\.\d+\.\d+$", ver):
        errors.append(("E007", f"version「{ver}」不是 x.y.z 形式"))

    cat = str(data.get("category") or "")
    if cat and cat not in CATEGORIES:
        warns.append(("W004", f"category「{cat}」不在常见取值内：{', '.join(CATEGORIES)}"))

    for k in ("display_name", "display_name_en"):
        v = str(data.get(k) or "")
        if v and len(v) > 60:
            warns.append(("W005", f"{k} 超过 60 字符，市场列表里会被截断"))

    d_en = str(data.get("description_en") or "")
    d_zh = str(data.get("description_zh") or "")
    if d_en and cjk_ratio(d_en) > 0.35:
        warns.append(("W006", "description_en 里中文占比过高，像是没翻译"))
    if d_zh and cjk_ratio(d_zh) < 0.1:
        warns.append(("W007", "description_zh 里几乎没有中文，像是没翻译"))

    blob = " ".join([d_zh, d_en, str(data.get("description") or "")])
    if "TODO" in blob:
        errors.append(("E008", "描述里还留着 TODO 占位，补完再发布"))

    if not data.get("category"):
        warns.append(("W008", "没有 category，市场分类可能不准"))

    if not data.get("agent_created"):
        warns.append(("W009", "缺少 agent_created: true，后续用 skill_manage 改这个技能会受限"))

    # 正文里引用的资源是否真的存在
    for kind in ("scripts", "references", "assets"):
        for ref in set(re.findall(rf"{kind}/([A-Za-z0-9_.\-/]+)", body)):
            if re.match(r"^(x+|your[-_])", ref) or any(c in ref for c in "<>*{}"):
                continue  # 文档里的占位写法，不是真实文件
            target = Path(root) / kind / ref
            if not target.exists():
                errors.append(("E009", f"正文引用了 {kind}/{ref}，但文件不存在"))

    extra = [p for p in Path(root).rglob("SKILL.md")
             if p.parent != Path(root)]
    if extra:
        warns.append(("W010", f"存在嵌套 SKILL.md：{extra[0]}，平台可能解析到错误的那一个"))

    body_len = len(body)
    if body_len > 15000:
        warns.append(("W011", f"正文 {body_len} 字符偏长，建议把细节挪到 references/"))

    info = {"name": name, "version": ver, "category": cat,
            "body_chars": body_len, "files": len(list_files(root))}
    return errors, warns, info


# ---------------------------------------------------------------- 打包

def pack(path, out_dir=None):
    errors, warns, info = validate(path)
    if errors:
        return None, errors, warns
    root, _ = find_skill_root(materialize(path)[0])
    name = info.get("name") or Path(root).name
    out_dir = Path(out_dir or Path.cwd())
    out_dir.mkdir(parents=True, exist_ok=True)
    zp = out_dir / f"{name}.zip"
    if zp.exists():
        zp.unlink()
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in list_files(root):
            full = Path(root) / rel
            zi = zipfile.ZipInfo(rel, date_time=time.localtime(full.stat().st_mtime)[:6])
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            z.writestr(zi, full.read_bytes())
    return zp, [], warns


# ---------------------------------------------------------------- CLI

def print_report(rep):
    print(f"来源平台   : {', '.join(rep['platforms'])}")
    print(f"输出目录   : {rep['output']}")
    print(f"技能标识   : {rep['name']}" +
          (f"（原名 {rep['renamed_from']} 已规范化）" if rep["renamed_from"] else ""))
    print(f"分类 / 版本: {rep['category']} / {rep['version']}")
    if rep["dropped_keys"]:
        print(f"丢弃字段   : {', '.join(rep['dropped_keys'])}（对目标平台无意义）")
    if rep["body_rewrites"]:
        for desc, n in rep["body_rewrites"]:
            print(f"正文替换   : {desc} × {n}")
    if rep.get("strays"):
        print(f"残留平台文件: {', '.join(rep['strays'])}（发布前建议删除）")
    if rep["todo"]:
        print(f"待补写     : {', '.join(rep['todo'])} —— 这是唯一需要动脑的地方")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="port.py", description="跨平台 skill 转换器")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_i = sub.add_parser("inspect", help="检查来源")
    p_i.add_argument("src")

    p_c = sub.add_parser("convert", help="转换")
    p_c.add_argument("src")
    p_c.add_argument("-o", "--out")
    p_c.add_argument("--name")
    p_c.add_argument("--display-name")
    p_c.add_argument("--display-name-en")
    p_c.add_argument("--description")
    p_c.add_argument("--description-zh")
    p_c.add_argument("--description-en")
    p_c.add_argument("--category")
    p_c.add_argument("--version")
    p_c.add_argument("--force", action="store_true")

    p_v = sub.add_parser("validate", help="按平台规则体检")
    p_v.add_argument("src")
    p_v.add_argument("--json", action="store_true")

    p_p = sub.add_parser("pack", help="打包成可上传的 zip")
    p_p.add_argument("src")
    p_p.add_argument("-o", "--out")

    args = ap.parse_args(argv)

    if args.cmd == "inspect":
        root, _ = materialize(args.src)
        skill_root, at_root = find_skill_root(root)
        names = list_files(skill_root)
        platforms = detect_platform(names)
        print(f"来源平台 : {', '.join(platforms)}")
        print(f"技能根   : {skill_root}（SKILL.md {'在' if at_root else '不在'}根目录）")
        print(f"文件数   : {len(names)}")
        for n in names[:30]:
            print(f"  - {n}")
        sm = skill_root / "SKILL.md"
        if sm.exists():
            data, body, meta = parse_frontmatter(read_text(sm))
            print(f"frontmatter 字段: {', '.join(data.keys()) or '（无）'}")
            risky = [k for k in meta["plain"]
                     if isinstance(data.get(k), str) and ": " in (data.get(k) or "")]
            if risky:
                print(f"⚠ 裸标量含冒号+空格（上传必炸）：{', '.join(risky)}")
            if not meta["found"]:
                print("⚠ 没有可解析的 frontmatter")
            print(f"正文长度: {len(body)} 字符")
        return 0

    if args.cmd == "convert":
        ov = {k: v for k, v in {
            "name": args.name, "display_name": args.display_name,
            "display_name_en": args.display_name_en, "description": args.description,
            "description_zh": args.description_zh, "description_en": args.description_en,
            "category": args.category, "version": args.version,
        }.items() if v}
        rep, dest = convert(args.src, args.out, ov, args.force)
        print_report(rep)
        errors, warns, _ = validate(dest)
        print()
        if errors:
            print(f"✗ 体检未通过（{len(errors)} 项）：")
            for code, msg in errors:
                print(f"  [{code}] {msg}")
            return 1
        for code, msg in warns:
            print(f"  ⚠ [{code}] {msg}")
        print("✓ 体检通过，可以打包上传")
        return 0

    if args.cmd == "validate":
        errors, warns, info = validate(args.src)
        if args.json:
            print(json.dumps({"errors": errors, "warnings": warns, "info": info},
                             ensure_ascii=False, indent=2))
        else:
            for code, msg in errors:
                print(f"✗ [{code}] {msg}")
            for code, msg in warns:
                print(f"⚠ [{code}] {msg}")
            if not errors:
                print("✓ 通过" + ("（有警告）" if warns else ""))
        return 1 if errors else 0

    if args.cmd == "pack":
        zp, errors, warns = pack(args.src, args.out)
        if errors:
            for code, msg in errors:
                print(f"✗ [{code}] {msg}")
            print("先修完再打包。")
            return 1
        for code, msg in warns:
            print(f"⚠ [{code}] {msg}")
        print(f"✓ 已打包：{zp}")
        with zipfile.ZipFile(zp) as z:
            print(f"  根目录 SKILL.md: {'SKILL.md' in z.namelist()}")
            print(f"  文件数: {len(z.namelist())}")
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
