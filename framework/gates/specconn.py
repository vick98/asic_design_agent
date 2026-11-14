# 作者：vick 邮箱：ykun@yk9811.com

"""规格书端口表与连接表是否闭合、位宽是否一致，以及跨时钟域连接是否经过登记单元。"""

import os
import re

from framework.gates.rtl import leading_width, spec_ports
from framework.paths import project_root


def scan_spec_conn(text, where, state=None, cdc_only=False):
    findings = [] if cdc_only else _conn_width_findings(text, where)
    findings.extend(_cdc_findings(text, where, state))
    return findings


def _conn_width_findings(text, where):
    if "模块连接关系" not in text:
        return []
    if "无内部组成模块" in text:
        return []
    ports = {p["name"]: p for p in spec_ports(text)}
    if not ports:
        return []
    body = text.split("模块连接关系", 1)[-1]
    from framework.mdtable import table_rows
    linked = {}
    findings = []
    for cells in table_rows(body):
        if len(cells) < 3:
            continue
        # 位宽列与端口表同一套取宽：`12（<12,1,t>）` 也是位宽，不再整行跳过。
        width = leading_width(cells[2])
        if width is None:
            continue
        src, dst = cells[0], cells[1]
        for name in (src, dst):
            linked[name] = width
            port = ports.get(name)
            if port and port["width"] is not None and port["width"] != width:
                findings.append({
                    "rule": "C3",
                    "where": where,
                    "detail": "连接 %s 位宽 %d，端口表为 %s" % (name, width, port["width"]),
                })
    missing = [name for name in sorted(ports) if name not in linked]
    if missing:
        findings.append({
            "rule": "C3",
            "where": where,
            "detail": "端口未出现在连接表：%s" % "、".join(missing),
        })
    return findings


def scan_notes(sys_root, state):
    """产物里的裁决注记必须能在裁决表里找到（修改队列已退场，注记直接写〔D…〕）。"""
    import re
    known = set()
    for rows in (state.get("decisions") or {}).values():
        known.update(row["id"] for row in rows)
    findings = []
    for dirpath, _dirs, files in os.walk(sys_root):
        for name in files:
            if not name.endswith(".md") or name.endswith("_status.md") or name.endswith("_decision.md"):
                continue
            with open(os.path.join(dirpath, name), encoding="utf-8") as fh:
                text = fh.read()
            for note in re.findall(r"〔(D\d+(?:-\d+)?)〕", text):
                if note not in known:
                    findings.append({
                        "rule": "W3",
                        "where": os.path.relpath(os.path.join(dirpath, name), sys_root),
                        "detail": "注记 %s 不在裁决表" % note,
                    })
    return findings


def scan_tree(sys_root, state=None):
    findings = []
    spec_dir = os.path.join(sys_root, "spec_doc")
    if not os.path.isdir(spec_dir):
        return findings
    if state is None:
        state = _state_on_disk(sys_root)
    for name in sorted(os.listdir(spec_dir)):
        if not name.endswith("_spec.md"):
            continue
        path = os.path.join(spec_dir, name)
        with open(path, encoding="utf-8") as fh:
            findings.extend(scan_spec_conn(fh.read(), "spec_doc/" + name, state))
    return findings


def scan_cdc_conn(sys_root, state):
    """连接表跨时钟域检查的入口（行 8 conn 闸门只做这一项，不重复 C3）。"""
    findings = []
    spec_dir = os.path.join(sys_root, "spec_doc")
    if not os.path.isdir(spec_dir):
        return findings
    for name in sorted(os.listdir(spec_dir)):
        if not name.endswith("_spec.md"):
            continue
        path = os.path.join(spec_dir, name)
        with open(path, encoding="utf-8") as fh:
            findings.extend(scan_spec_conn(fh.read(), "spec_doc/" + name, state, cdc_only=True))
    return findings


def _state_on_disk(sys_root):
    """调用点没给 state 时，从同一子系统目录读当前状态（裁决表用于 CD1 豁免）。"""
    try:
        import framework.state as state_module
        root = project_root()
        name = os.path.basename(os.path.normpath(sys_root))
        return state_module.load_state(root, name)
    except Exception:
        return {}


# 端口表里"不归属某个时钟域"的占位写法（rules/spec.md：不归属某域的填 `—`）。
CLOCK_NONE = frozenset(("", "—", "-", "–", "－", "n/a", "na"))

# rules/pubip.md 的跨时钟域登记小节与裁决号注记（与产物里的写法同口径）。
CDC_SECTION = "## 跨时钟域公共单元"
DECISION_NOTE = re.compile(r"〔(D\d+(?:-\d+)?)〕")


def _clean_domain(cell):
    value = (cell or "").strip().strip("`").strip()
    return "" if value.lower() in CLOCK_NONE else value


def _pub_code_modules():
    folder = os.path.join(project_root(), "pub_code")
    try:
        entries = os.listdir(folder)
    except (OSError,):
        return set()
    return {fn.rsplit(".", 1)[0] for fn in entries
            if fn.endswith((".sv", ".v")) and os.path.isfile(os.path.join(folder, fn))}


def registered_cdc_units(text=None):
    """`rules/pubip.md` 跨时钟域小节里登记的单元名（须是 `pub_code/` 里的模块）。"""
    if text is None:
        try:
            with open(os.path.join(project_root(), "rules", "pubip.md"), encoding="utf-8") as fh:
                text = fh.read()
        except (OSError,):
            return []
    if CDC_SECTION not in text:
        return []
    section = text.split(CDC_SECTION, 1)[1].split("\n## ", 1)[0]
    modules = _pub_code_modules()
    from framework.mdtable import table_rows
    units = []
    for cells in table_rows(section):
        if len(cells) < 2:
            continue
        unit = cells[1].strip().strip("`")
        if unit in modules and unit not in units:
            units.append(unit)
    return units


def _live_decisions(state):
    known = set()
    for rows in (state.get("decisions") or {}).values():
        for row in rows:
            if not row.get("withdrawn"):
                known.add(row.get("id"))
    return known


def _endpoint_domain(ports, endpoint, row_clock):
    """端点时钟域：端口表能查到就用端口表的，查不到（子模块端口、胶合）用连接行的。"""
    port = ports.get((endpoint or "").strip().strip("`"))
    if port is not None:
        return _clean_domain(port.get("clock"))
    return row_clock


def _cdc_findings(text, where, state):
    """CD1：连接两端时钟域不同时，要写出已登记的跨域单元名或引用有效裁决号。"""
    if "模块连接关系" not in text:
        return []
    if "无内部组成模块" in text:
        return []
    ports = {p["name"]: p for p in spec_ports(text)}
    if not ports:
        return []
    body = text.split("模块连接关系", 1)[-1]
    from framework.mdtable import table_rows
    units = registered_cdc_units()
    known = _live_decisions(state or {})
    findings = []
    for cells in table_rows(body):
        if len(cells) < 4 or leading_width(cells[2]) is None:
            continue
        src, dst = cells[0], cells[1]
        row_clock = _clean_domain(cells[3])
        src_clock = _endpoint_domain(ports, src, row_clock)
        dst_clock = _endpoint_domain(ports, dst, row_clock)
        if not src_clock or not dst_clock or src_clock == dst_clock:
            continue
        desc = cells[4] if len(cells) > 4 else ""
        if any(re.search(r"\b%s\b" % re.escape(unit), desc) for unit in units):
            continue
        notes = DECISION_NOTE.findall(desc)
        if any(note in known for note in notes):
            continue
        detail = ("连接 %s → %s 跨时钟域（%s → %s），说明列要写出已登记的跨域单元名"
                  "（%s）或引用有效裁决号〔D…〕"
                  % (src, dst, src_clock, dst_clock,
                     "、".join(units) if units else "见 rules/pubip.md"))
        invalid = [note for note in notes if note not in known]
        if invalid:
            detail += "；说明列引用的 %s 不在有效裁决表" % "、".join(invalid)
        findings.append({"rule": "CD1", "where": where, "detail": detail})
    return findings


def spec_clock_domains(text):
    """端口表里出现的时钟域：去空白与反引号、去占位符，按出现顺序去重。"""
    domains = []
    for port in spec_ports(text):
        name = (port.get("clock") or "").strip().strip("`").strip()
        if not name or name.lower() in CLOCK_NONE:
            continue
        if name not in domains:
            domains.append(name)
    return domains


def scan_clock_domains(sys_root):
    """`spec_doc/` 各份规格书端口表的时钟域并集（按文件名排序、出现顺序去重）。

    行 8 的跨时钟域闸门用：只要有一份端口表写出两个以上时钟域，设计里就有跨域
    接口，需要 cdc 证据或点选入库的裁决豁免。
    """
    spec_dir = os.path.join(sys_root, "spec_doc")
    if not os.path.isdir(spec_dir):
        return []
    domains = []
    for name in sorted(os.listdir(spec_dir)):
        if not name.endswith("_spec.md"):
            continue
        with open(os.path.join(spec_dir, name), encoding="utf-8") as fh:
            for item in spec_clock_domains(fh.read()):
                if item not in domains:
                    domains.append(item)
    return domains
