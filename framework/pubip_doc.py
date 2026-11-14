# 作者：vick 邮箱：ykun@yk9811.com

"""`rules/pubip.md` 的参数表与端口表由 `pub_code/` 的 RTL 生成。

每个公共模块的 `## <模块名>` 一节里，`### 参数` 与 `### 端口` 下面各有一个生成区：

    <!-- PUBIP_PARAMS -->
    ...生成的参数表...
    <!-- /PUBIP_PARAMS -->

    <!-- PUBIP_PORTS -->
    ...生成的端口表...
    <!-- /PUBIP_PORTS -->

生成区之外（正文、清单、例化示例）手写。`framework/hosts/render.py` 的 `render()`
调 `pubip_markdown()` 把结果写回 `rules/pubip.md`，与 `rules/steps.md` 同类：
`hosts` 是唯一入口，逐字节比对见 `framework/tests/test_pubip_doc.py`。

表格内容：
- 参数名/端口名、方向、位宽、默认值都从 RTL 解析。端口用
  `framework.gates.rtl.module_decl`；参数名与默认值另按 `parameter <名字> = <表达式>`
  扫描（`module_decl` 只收集默认值能算出整数的参数，参数化默认值会漏）。
- `说明` 列优先保留 `rules/pubip.md` 里已有的同名参数/端口说明；新增项取 RTL 行尾
  `//` 注释；没有注释写 `—`。
- 位宽列：端口的 RTL 范围是参数表达式时写参数（如 `CNT_WIDTH`、`[MAX_NUM:0]`），
  否则写解析出的整数。
"""

import os
import re

from framework.gates.rtl import module_decl, strip_comments
from framework.paths import project_root

PARAMS_START = "<!-- PUBIP_PARAMS -->"
PARAMS_END = "<!-- /PUBIP_PARAMS -->"
PORTS_START = "<!-- PUBIP_PORTS -->"
PORTS_END = "<!-- /PUBIP_PORTS -->"
PUBIP_REL = os.path.join("rules", "pubip.md")

SECTION = re.compile(r"(?m)^##\s+`?([^`\n]+?)`?\s*$")
PARAM = re.compile(
    r"\bparameter\s+(?:(?:logic|wire|reg|int|integer|bit)\s+)?"
    r"(?:(?:signed|unsigned)\s+)?(?:\[[^\]]*\]\s*)?([A-Za-z_]\w*)\s*=\s*([^,;\n]+)")
DECL_PORT = re.compile(
    r"\b(input|output|inout)\s+(?:(?:logic|wire|reg)\s+)?(?:(?:signed|unsigned)\s+)?"
    r"((?:\[[^\]]+\]\s*)*)([A-Za-z_]\w*(?:\s*,\s*(?!input\b|output\b|inout\b)[A-Za-z_]\w*)*)")
HEADER_ROW = ("参数名", "端口", "名字")


def pubip_modules(base=None):
    """`pub_code/` 下顶层 RTL 文件对应的模块名（不含 `testbench/` 等目录）。"""
    base = base or project_root()
    folder = os.path.join(base, "pub_code")
    names = []
    try:
        entries = os.listdir(folder)
    except (OSError,):
        return names
    for fn in entries:
        if fn.endswith((".sv", ".v")) and os.path.isfile(os.path.join(folder, fn)):
            names.append(fn.rsplit(".", 1)[0])
    return sorted(names)


def _rtl_path(module, base=None):
    base = base or project_root()
    for ext in (".sv", ".v"):
        path = os.path.join(base, "pub_code", module + ext)
        if os.path.isfile(path):
            return path
    raise ValueError("pub_code/ 里没有 %s 的 RTL 文件" % module)


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _strip_block_comments(src):
    """只去 `/* */`（保留 `//` 行尾注释，说明列要从那里取）。"""
    return re.sub(r"/\*.*?\*/", "", src, flags=re.S)


def _parameter_decls(stripped, module):
    """模块体里的参数名与默认值表达式（按声明顺序）。"""
    body = stripped.split("module %s" % module, 1)[-1].split("endmodule", 1)[0]
    names, defaults = [], {}
    for matched in PARAM.finditer(body):
        name = matched.group(1)
        if name in defaults:
            continue
        names.append(name)
        defaults[name] = matched.group(2).strip()
    return names, defaults


def _declared_ranges(stripped, names):
    """端口声明里的范围表达式原文（按端口名）。"""
    ranges = {}
    wanted = set(names)
    for matched in DECL_PORT.finditer(stripped):
        rng = (matched.group(2) or "").strip()
        for name in re.findall(r"[A-Za-z_]\w*", matched.group(3)):
            if name in wanted and name not in ranges:
                ranges[name] = rng
    return ranges


def _line_comments(raw, names, keyword):
    """声明行尾 `//` 注释：parameter 行按 `parameter`，端口行按方向关键字识别。"""
    wanted = set(names)
    found = {}
    for line in _strip_block_comments(raw).split("\n"):
        code, _sep, note = line.partition("//")
        if keyword == "parameter":
            if not re.search(r"\bparameter\b", code):
                continue
        elif not re.search(r"\b(?:input|output|inout)\b", code):
            continue
        for name in wanted:
            if name in found:
                continue
            if re.search(r"\b%s\b" % re.escape(name), code):
                found[name] = note.strip()
    return found


def _mentions_param(text, params):
    return any(re.search(r"\b%s\b" % re.escape(name), text) for name in params)


def _width_cell(rng, width, params):
    """位宽列：参数表达式写参数名，能算成整数的裸范围写整数。"""
    rng = (rng or "").strip()
    if not rng:
        return "1"
    single = re.fullmatch(r"\[\s*(.+?)\s*\]", rng, re.S)
    expr = single.group(1).strip() if single else rng
    matched = re.fullmatch(r"(.+?)\s*-\s*1\s*:\s*0", expr, re.S)
    if matched:
        base = matched.group(1).strip()
        if width is None or _mentions_param(base, params):
            return base
    matched = re.fullmatch(r"(.+?)\s*:\s*0", expr, re.S)
    if matched:
        base = matched.group(1).strip()
        if width is None or _mentions_param(base, params):
            return "[%s:0]" % base
    if width is not None:
        return str(width)
    return rng


def _default_cell(default):
    text = re.sub(r"\s+", " ", (default or "").strip())
    if re.fullmatch(r"\d+", text):
        return text
    return "`%s`" % text


def module_tables(module, base=None):
    """`pub_code/<module>` 的参数与端口：名字、默认值/方向/位宽、RTL 行尾注释。"""
    raw = _read(_rtl_path(module, base))
    decl = module_decl(raw, module)
    if decl is None:
        raise ValueError("pub_code/%s 里解析不到 module %s 的声明" % (module, module))
    _decl_params, ports = decl
    stripped = strip_comments(raw)
    param_names, defaults = _parameter_decls(stripped, module)
    port_names = [port["name"] for port in ports]
    param_comments = _line_comments(raw, param_names, "parameter")
    port_comments = _line_comments(raw, port_names, "port")
    port_ranges = _declared_ranges(stripped, port_names)
    params = [{
        "name": name,
        "default": defaults.get(name, ""),
        "comment": param_comments.get(name, ""),
    } for name in param_names]
    rows = [{
        "name": port["name"],
        "direction": port["direction"],
        "width": _width_cell(port_ranges.get(port["name"], ""),
                             port["width"], param_names),
        "comment": port_comments.get(port["name"], ""),
    } for port in ports]
    return params, rows


def _section_text(text, module):
    matched = re.search(r"^##\s+`?%s`?\s*$(.*?)(?=^##\s|\Z)" % re.escape(module),
                        text, re.M | re.S)
    return matched.group(1) if matched else ""


def _documented_descriptions(section):
    """规则文件里已有的 `说明` 列：参数名/端口名 → 文本（说明原样保留，含反引号）。"""
    docs = {"params": {}, "ports": {}}
    capture = None
    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            if "参数" in stripped:
                capture = "params"
            elif "端口" in stripped:
                capture = "ports"
            else:
                capture = None
            continue
        if capture is None or not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 3:
            continue
        name = cells[0].strip("`")
        if name in HEADER_ROW:
            continue
        if set("".join(cells)) <= set("-: "):
            continue
        docs[capture][name] = cells[-1]
    return docs


def _params_table(params, old):
    rows = ["| 参数名 | 默认值 | 说明 |", "|--------|--------|------|"]
    for item in params:
        desc = old[item["name"]] if item["name"] in old else (item["comment"] or "—")
        rows.append("| `%s` | %s | %s |" % (
            item["name"], _default_cell(item["default"]), desc))
    return "\n".join(rows)


def _ports_table(ports, old):
    rows = ["| 端口 | 方向 | 位宽 | 说明 |", "|------|------|------|------|"]
    for item in ports:
        desc = old[item["name"]] if item["name"] in old else (item["comment"] or "—")
        width = item["width"]
        if not re.fullmatch(r"\d+", width):
            width = "`%s`" % width
        rows.append("| `%s` | %s | %s | %s |" % (
            item["name"], item["direction"], width, desc))
    return "\n".join(rows)


def _fill_block(body, kind, table, module):
    start, end = {
        "PUBIP_PARAMS": (PARAMS_START, PARAMS_END),
        "PUBIP_PORTS": (PORTS_START, PORTS_END),
    }[kind]
    if body.count(start) != 1 or body.count(end) != 1:
        raise ValueError("%s 的 %s 生成区标记必须恰好各一个（%s / %s）"
                         % (module, kind, start, end))
    pre, rest = body.split(start, 1)
    _inner, post = rest.split(end, 1)
    return pre + start + "\n" + table + "\n" + end + post


def _ensure_no_markers(body, name):
    for marker in (PARAMS_START, PARAMS_END, PORTS_START, PORTS_END):
        if marker in body:
            raise ValueError("%s 一节不是 pub_code/ 里的模块，不能有参数/端口生成标记 %s"
                             % (name, marker))


def render_pubip(text, base=None):
    """把 text 里每个公共模块的参数/端口生成区渲染成当前 RTL 的表格。

    每个 `pub_code/` 顶层模块都要有 `## <模块名>` 一节且两处标记齐备；标记放在
    非模块小节里、模块缺一节、或标记重复都直接报错，不静默跳过。
    """
    base = base or project_root()
    modules = set(pubip_modules(base))
    heads = list(SECTION.finditer(text))
    chunks, pos, registered = [], 0, set()
    for index, head in enumerate(heads):
        body_start = head.end()
        body_end = heads[index + 1].start() if index + 1 < len(heads) else len(text)
        name = head.group(1).strip()
        body = text[body_start:body_end]
        if name in modules:
            if name in registered:
                raise ValueError("rules/pubip.md 里 %s 出现了多节，模块名必须唯一" % name)
            registered.add(name)
            section = text[head.start():body_end]
            old = _documented_descriptions(section)
            params, ports = module_tables(name, base)
            body = _fill_block(body, "PUBIP_PARAMS", _params_table(params, old["params"]), name)
            body = _fill_block(body, "PUBIP_PORTS", _ports_table(ports, old["ports"]), name)
        else:
            _ensure_no_markers(body, name)
        chunks.append(text[pos:body_start])
        chunks.append(body)
        pos = body_end
    chunks.append(text[pos:])
    missing = sorted(modules - registered)
    if missing:
        raise ValueError(
            "rules/pubip.md 缺模块一节（pub_code/ 有 RTL 就要登记参数与端口）：%s"
            % "、".join(missing))
    return "".join(chunks)


def pubip_markdown(base=None):
    """`rules/pubip.md` 的当前生成结果（读入、渲染、返回文本；写盘由 hosts 入口做）。"""
    base = base or project_root()
    path = os.path.join(base, PUBIP_REL)
    with open(path, encoding="utf-8") as fh:
        return render_pubip(fh.read(), base)
