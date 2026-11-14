# 作者：vick 邮箱：ykun@yk9811.com

"""产物文档的载体与章节闸门。取材自文档二分和规格书分阶段成文。"""

import os
import re

from framework.flow import cached_yaml
from framework.paths import project_root

H2 = re.compile(r"^##\s+(.+?)\s*$", re.M)
NUM = re.compile(r"^§?\s*\d+\s*[\.、]?\s*(.*)$")
PROCESS = re.compile(r"待裁决|自审记录|变更说明|遗留问题|下一步")
MARK = re.compile(r"mark:|@@")
SECTION1 = re.compile(r"^##\s+§?\s*1(?!\d)", re.M)

# 占位串的唯一来源：new-doc 写 PLACEHOLDER_TEXT，S2 的豁免与 S7 的判定都读
# PLACEHOLDER_MARKERS。别处不要再另写这些字面量。
PLACEHOLDER_TEXT = "待填写。"
PLACEHOLDER_MARKERS = ("待填写", "待设计", "TODO", "TBD")

# 「待确认」标注：同一行要带一个仍打开的问题号，两种括号都认。
CONFIRM_MARK = "待确认"
CONFIRM_REF = re.compile(r"[〔\[]\s*(I\d{3})\s*[〕\]]")

CHAPTERS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "framework", "templates", "chapters.yaml",
)


def chapters_path():
    """chapters.yaml 的绝对路径；与 flow_model.yaml 同口径，优先读 ADF_ROOT 下的那份。

    副本仓库（RepoTest）里改 chapters.yaml 必须让 cached_yaml 的（mtime, 大小）键失效，
    所以有副本就读副本；副本里没有这个文件（ADF_ROOT 不是完整仓库）时退回本仓库，
    即接缓存之前的老行为。
    """
    candidate = os.path.join(project_root(), "framework", "templates", "chapters.yaml")
    if os.path.isfile(candidate):
        return candidate
    return CHAPTERS_PATH


def load_chapter_model():
    return cached_yaml(chapters_path())


def _doc_kind(name, text, sys_name):
    if name == "%s_spec.md" % sys_name:
        return "sys"
    if "模块类型：group" in text:
        return "group"
    if name.endswith("_spec.md"):
        return "leaf"
    return ""


def expected_chapters(rel, stop_id, text="", sys_name=""):
    folder = rel.split("/")[0]
    name = os.path.basename(rel)
    kind = _doc_kind(name, text, sys_name)
    chosen = None
    for doc in load_chapter_model()["documents"]:
        if doc["folder"] != folder:
            continue
        if doc.get("kind") and doc["kind"] != kind:
            continue
        if not doc.get("kind") and kind in ("sys", "leaf", "group"):
            continue
        if stop_id < doc.get("stop_min", 1):
            continue
        if doc.get("stop_max") and stop_id > doc["stop_max"]:
            continue
        chosen = doc["chapters"]
    return list(chosen or [])


def titles(text):
    out = []
    for raw in H2.findall(text):
        raw = raw.strip().strip("*`_ ")
        m = NUM.match(raw)
        if m and m.group(1):
            raw = m.group(1).strip()
        out.append(raw)
    return out


def check_bloat(text, where):
    findings = []
    head = []
    for line in text.split("\n"):
        if line.startswith("## "):
            break
        head.append(line)
    between = head[1:]
    tables = [ln for ln in between if ln.strip().startswith("|")]
    prose = [ln for ln in between if ln.strip() and not ln.strip().startswith("|")]
    if tables:
        findings.append({"rule": "P1", "where": where, "detail": "标题与正文之间有表格"})
    if len(prose) > 2:
        findings.append({"rule": "P1", "where": where, "detail": "标题与正文之间的简介超过一句"})
    if SECTION1.search(text):
        findings.append({"rule": "S3", "where": where, "detail": "产物出现第 1 节，正文应从第 2 节起"})
    if re.search(r"<\s*\d+\s*,\s*\d+\s*,\s*s\s*>", text):
        findings.append({"rule": "P3", "where": where, "detail": "仍使用旧的 s 符号，应改为 t"})
    for i, line in enumerate(text.split("\n"), 1):
        if MARK.search(line):
            findings.append({"rule": "K1", "where": where, "detail": "第 %d 行仍有走查标记" % i})
        elif line.startswith("#") and PROCESS.search(line):
            findings.append({"rule": "P2", "where": where, "detail": "标题含过程字样：%s" % line.strip()[:40]})
    return findings


def _is_placeholder(line):
    """行内出现任一占位标记即算占位；S2 的豁免与 S7 共用这一口径。"""
    return any(marker in line for marker in PLACEHOLDER_MARKERS)


def _lead_lines(text):
    """第 1 个 `##` 标题之前的行（标题行本身不算简介）。"""
    head = []
    for line in text.split("\n"):
        if re.match(r"^##\s+", line):
            break
        head.append(line)
    if head and head[0].lstrip().startswith("#"):
        head = head[1:]
    return head


def check_placeholders(text, where):
    """S7：章节正文仍是占位（开篇简介也纳入）。

    开篇简介指标题与第 1 个 `##` 之间的内容；new-doc 骨架在这两处都写
    PLACEHOLDER_TEXT，所以空骨架整份文档都会被报出来。
    """
    findings = []
    if any(_is_placeholder(line) for line in _lead_lines(text)):
        findings.append({"rule": "S7", "where": where,
                         "detail": "标题与第 1 章之间的简介仍是占位"})
    for name, body in _section_bodies(text):
        if any(_is_placeholder(line) for line in body.split("\n")):
            findings.append({"rule": "S7", "where": where,
                             "detail": "%s 正文仍是占位" % name})
    return findings


def pending_confirmations(text):
    """文本里所有含「待确认」标注的行（原样保留），供引擎在里程碑确认时给原因。"""
    return [line for line in text.splitlines() if CONFIRM_MARK in line]


def _open_problem_ids(state):
    ids = set()
    for item in (state or {}).get("problems") or []:
        if item.get("open", True):
            ids.add(str(item.get("id") or ""))
    return ids


def check_pending_confirmations(text, where, state):
    """U1：每处「待确认」标注的同一行要带一个仍打开的问题号（〔I003〕或 [I003]）。"""
    open_ids = _open_problem_ids(state)
    findings = []
    for lineno, line in enumerate(text.split("\n"), 1):
        if CONFIRM_MARK not in line:
            continue
        if any(pid in open_ids for pid in CONFIRM_REF.findall(line)):
            continue
        findings.append({
            "rule": "U1", "where": where,
            "detail": "第 %d 行待确认标注缺仍打开的问题号（形如 〔I003〕）：%s"
                      % (lineno, line.strip()[:60]),
        })
    return findings


def check_chapters(text, where, stop_id, sys_name=""):
    expected = expected_chapters(where, stop_id, text, sys_name)
    if not expected:
        return []
    found = titles(text)
    findings = []
    missing = [name for name in expected if name not in found]
    if missing:
        findings.append({
            "rule": "S1",
            "where": where,
            "detail": "缺章节：%s" % "、".join(missing),
        })
    want_order = [name for name in expected if name in found]
    got_order = [name for name in found if name in want_order]
    if want_order != got_order:
        findings.append({
            "rule": "S1",
            "where": where,
            "detail": "章节顺序应为 %s" % "、".join(want_order),
        })
    # group 不写模块实现结构/逻辑块/测试要点（rules/spec.md）。多写只提示不阻断。
    if _doc_kind(os.path.basename(where), text, sys_name) == "group":
        forbidden = [name for name in found
                     if name in ("模块实现结构", "模块逻辑块描述", "逻辑块描述", "测试要点")]
        if forbidden:
            findings.append({
                "rule": "S1", "level": "hint", "where": where,
                "detail": "group 不写这些章节（只提示不阻断）：%s" % "、".join(forbidden),
            })
    for name, body in _section_bodies(text):
        real = [ln for ln in body.split("\n") if ln.strip() and not _is_placeholder(ln)]
        if name in expected and not real:
            findings.append({"rule": "S2", "where": where, "detail": "%s 正文为空" % name})
        if len(real) > 80:
            findings.append({"rule": "P4", "where": where, "detail": "%s 超过 80 行" % name})
    findings.extend(check_columns(text, where))
    return findings


def _trace_table_key(cells):
    """追溯锚点表的表头识别：返回 chapters.yaml 的 columns 键，认不出返回空串。

    各表最后一列都是「来源」，trace 沿它逐级向上解析；这里只校验表头列序，
    不要求章节里一定有这张表（可选章节与小规模子系统的免分组都照旧）。
    """
    if cells[0] == "数据节点":
        return "节点表"
    if cells[0] == "大子模块名":
        return "分组表"
    if cells[0] == "所属大子模块":
        return "模块清单"
    if cells[0] == "模块" and "前级模块" in cells:
        return "前后级表"
    if cells[0] == "源模块":
        return "交互表"
    if cells[0] == "编号" and "场景" in cells:
        return "测试要点"
    return ""


def check_columns(text, where):
    columns = load_chapter_model().get("columns") or {}
    findings = []
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not cells or set(cells[0]) <= set("-: "):
            continue
        required = None
        if cells[0] == "名字" and "位宽" in cells:
            required = columns.get("端口表")
        elif cells[0] == "源":
            required = columns.get("连接表")
        else:
            required = columns.get(_trace_table_key(cells))
        if not required:
            continue
        if cells[:len(required)] != required:
            findings.append({
                "rule": "S6",
                "where": where,
                "detail": "表列应为 %s" % "、".join(required),
            })
    return findings


def _section_bodies(text):
    parts = re.split(r"(?m)^##\s+", text)
    out = []
    for part in parts[1:]:
        lines = part.split("\n")
        title = lines[0].strip()
        title = re.sub(r"^§?\s*\d+\s*[\.、]?\s*", "", title)
        out.append((title, "\n".join(lines[1:])))
    return out


def scan_docs(sys_root, stop_id, state=None):
    """docs 闸门全部检查。传 state 时做 U1（「待确认」标注要带仍打开的问题号）。"""
    from framework.gates.products import doc_texts, sys_name_of
    findings = []
    docs = doc_texts(sys_root)
    for rel, text in sorted(docs.items()):
        findings.extend(check_bloat(text, rel))
        findings.extend(check_placeholders(text, rel))
        if state is not None:
            findings.extend(check_pending_confirmations(text, rel, state))
        findings.extend(check_chapters(text, rel, stop_id, sys_name_of(sys_root)))
        findings.extend(_refs(text, rel, sys_root))
    findings.extend(_dupes(docs))
    findings.extend(_index(sys_root))
    return findings


def _refs(text, where, sys_root):
    findings = []
    for mod, num in re.findall(r"见\s*`?([A-Za-z_][\w]*)_spec`?\s*§\s*(\d+)", text):
        path = os.path.join(sys_root, "spec_doc", mod + "_spec.md")
        if not os.path.isfile(path):
            findings.append({"rule": "S4", "where": where, "detail": "引用 %s_spec 不存在" % mod})
            continue
        with open(path, encoding="utf-8") as fh:
            heads = re.findall(r"(?m)^##\s+[^\n]*?(\d+)", fh.read())
        if num not in heads:
            findings.append({"rule": "S4", "where": where, "detail": "%s_spec 没有第 %s 节" % (mod, num)})
    return findings


def _dupes(docs):
    seen = {}
    findings = []
    for rel, text in sorted(docs.items()):
        local = {}
        for line in text.split("\n"):
            s = line.strip()
            if len(s) < 24 or s.startswith("|") or s.startswith("#"):
                continue
            local[s] = local.get(s, 0) + 1
            prev = seen.get(s)
            if prev and prev != rel:
                findings.append({"rule": "P6", "where": rel, "detail": "与 %s 重复：%s" % (prev, s[:40])})
            elif s not in seen:
                seen[s] = rel
        for s, n in local.items():
            if n > 1:
                findings.append({"rule": "P5", "where": rel, "detail": "档内重复：%s" % s[:40]})
    return findings


_TYPE_WORDS = ("leaf", "group", "外部模块", "嵌套子系统")


def _type_of_cell(cell):
    """类型单元格先剥离括号注记再判断：`leaf（寄存器配置模块）` → `leaf`。

    改前要求类型格恰好是 `leaf`/`group`，于是分批产出时写的注记会让这些行**永久逃过
    S5 检查**；若某批全部带注记，`_index()` 还会返回空集 → S5 静默关闭且不报错。
    """
    text = re.sub(r"[（(].*?[)）]", "", cell.strip().strip("*` ")).strip()
    for word in _TYPE_WORDS:
        if text == word or text.startswith(word + " ") or text.startswith(word + "("):
            return word
    return ""


def _module_rows(spec):
    """模块摘要表的 (模块名, 类型)；类型列允许带括号注记。"""
    rows = []
    for line in spec.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        name = cells[0].strip().strip("`")
        kind = _type_of_cell(cells[1])
        if not kind or not re.match(r"^[A-Za-z_]\w*$", name):
            continue
        rows.append((name, kind))
    return rows


_TABLE_HEAD = re.compile(r"\|\s*(?:模块|名字|name)\s*\|\s*(?:类型|kind)\s*\|")


def _has_module_table(text):
    """文件里是否出现"模块/类型"表头（用来区分"没有这张表"与"表在但类型列认不出"）。"""
    return bool(_TABLE_HEAD.search(text))


def _index(sys_root):
    spec_dir = os.path.join(sys_root, "spec_doc")
    if not os.path.isdir(spec_dir):
        return []
    names = sorted(os.listdir(spec_dir))
    spec = ""
    spec_name = ""
    table_name = ""
    for name in names:
        if not name.endswith("_spec.md"):
            continue
        with open(os.path.join(spec_dir, name), encoding="utf-8") as fh:
            text = fh.read()
        if _module_rows(text):
            spec = text
            spec_name = name
            break
        if not table_name and _has_module_table(text):
            table_name = name
    if not spec:
        if table_name:
            # 表在、类型列认不出：这是 S5 静默失效的入口，必须报出来。
            return [{"rule": "S5", "where": "spec_doc",
                     "detail": "%s 的模块摘要表类型列认不出（须为 %s）" % (table_name, "/".join(_TYPE_WORDS))}]
        return []
    findings = []
    for mod, kind in _module_rows(spec):
        if kind in ("leaf", "group"):
            if not os.path.isfile(os.path.join(spec_dir, mod + "_spec.md")):
                findings.append({"rule": "S5", "where": "spec_doc",
                                 "detail": "模块表有 %s 但没有规格书" % mod})
            continue
        # 外部模块/嵌套子系统：契约或规格文件里须提到它
        mentioned = False
        for name in names:
            if not name.endswith(".md") or name == spec_name:
                continue  # 摘要表自己提到模块名不算契约提及
            with open(os.path.join(spec_dir, name), encoding="utf-8") as fh:
                if mod in fh.read():
                    mentioned = True
                    break
        if not mentioned:
            findings.append({"rule": "S5", "where": "spec_doc",
                             "detail": "%s（%s）在 spec_doc 里找不到契约或规格提及" % (mod, kind)})
    return findings
