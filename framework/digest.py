# 作者：vick 邮箱：ykun@yk9811.com

"""交付 IR，schema_version=2。"""

import json
import os
import re

from framework.gates.rtl import spec_ports

FMT = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`\s*<\s*(\d+)\s*,\s*(\d+)\s*,\s*([tu])\s*>")
# rules/dsp.md 的写法 3「端口位宽带格式」——`12（<12,1,t>）`，数字须等于格式总位宽。
FMT_PORT = re.compile(r"(\d+)\s*[（(]\s*<\s*(\d+)\s*,\s*(\d+)\s*,\s*([tu])\s*>\s*[)）]")
PARAM = re.compile(r"^\|\s*`?([A-Za-z_][\w]*)`?\s*\|\s*([^|]+)\|", re.M)
TEST = re.compile(r"^[-*]\s+(.+)$", re.M)
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _section(text, title):
    m = re.search(r"^#{2,3}\s+[^\n]*%s[^\n]*\n(.*?)(?=^##\s|\Z)" % re.escape(title), text, re.M | re.S)
    return m.group(1) if m else ""


def _params(text):
    body = _section(text, "参数")
    out = []
    for m in PARAM.finditer(body):
        name, value = m.group(1), m.group(2).strip()
        if name in ("参数名", "名字") or set(name) <= set("-:"):
            continue
        out.append({"name": name, "value": value})
    return out


def _registers(text):
    from framework.mdtable import table_rows
    body = _section(text, "寄存器")
    rows = []
    for cells in table_rows(body):
        if len(cells) < 2 or not re.match(r"[A-Za-z_]", cells[0]):
            continue
        width = int(cells[1]) if cells[1].isdigit() else None
        rows.append({"name": cells[0], "width": width})
    return rows


def _connections(text):
    from framework.mdtable import table_rows
    body = _section(text, "模块连接关系")
    rows = []
    for cells in table_rows(body):
        if len(cells) < 3 or cells[0] in ("源", "名字"):
            continue
        width = int(cells[2]) if cells[2].isdigit() else None
        rows.append({
            "src": cells[0], "dst": cells[1], "width": width,
            "clock": cells[3] if len(cells) > 3 else "",
            "description": cells[4] if len(cells) > 4 else "",
        })
    return rows


def _logic_blocks(text):
    body = _section(text, "模块逻辑块描述")
    return [line.strip() for line in body.splitlines() if line.strip() and not line.strip().startswith("|")]


def _structured_tests(text):
    from framework.mdtable import table_rows
    body = _section(text, "测试要点")
    table_present = any(line.strip().startswith("|") for line in body.splitlines())
    rows = []
    for cells in table_rows(body):
        if len(cells) < 4 or cells[0] in ("编号", "名字", "序号"):
            continue
        rows.append({
            "id": cells[0], "scene": cells[1], "stimulus": cells[2], "expect": cells[3],
        })
    if rows:
        return rows
    if table_present:
        return []
    return [{"id": str(i + 1), "scene": item, "stimulus": "", "expect": ""}
            for i, item in enumerate(_tests(text))]


def _memory(text):
    from framework.mdtable import table_rows
    body = _section(text, "区段")
    depths = []
    for cells in table_rows(body):
        if len(cells) >= 3 and cells[2].isdigit():
            depths.append({"name": cells[0], "depth": int(cells[2])})
    peak = sum(item["depth"] for item in depths)
    bits = None
    matched = re.search(r"地址位宽\s*(\d+)", text)
    if matched:
        bits = int(matched.group(1))
    return {"segments": depths, "total_words": peak, "peak_words": peak, "addr_bits": bits}


def _tests(text):
    body = _section(text, "测试要点")
    return [m.group(1).strip() for m in TEST.finditer(body)]


def _formats(text):
    """三种合法写法都要产出 fixed_point。

    改前只认写法 2（`` `name` <W,I,t> ``），写法 3（`12（<12,1,t>）`）会被整个漏掉，
    于是 IR 的 fixed_point 静默为空——而 rules/roles/spec2rtl.md 把 IR 当编码真值。
    """
    out = [{"name": m.group(1), "format": "<%s,%s,%s>" % (m.group(2), m.group(3), m.group(4))}
           for m in FMT.finditer(text)]
    for m in FMT_PORT.finditer(text):
        width, w, i, signed = m.group(1), m.group(2), m.group(3), m.group(4)
        if int(width) != int(w):
            continue  # 写法 3 要求数字等于格式总位宽
        start = text.rfind("\n", 0, m.start()) + 1
        end = text.find("\n", m.end())
        line = text[start:end if end != -1 else len(text)]
        found = _IDENT.search(line)
        name = found.group(0) if found else "line%d" % (text.count("\n", 0, m.start()) + 1)
        out.append({"name": name, "format": "<%s,%s,%s>" % (w, i, signed)})
    return out


def digest(sys_root, sys_name=""):
    spec_dir = os.path.join(sys_root, "spec_doc")
    details = []
    if os.path.isdir(spec_dir):
        for name in sorted(os.listdir(spec_dir)):
            if not name.endswith("_spec.md") or name.endswith("_signoff.md"):
                continue
            mod = name[: -len("_spec.md")]
            with open(os.path.join(spec_dir, name), encoding="utf-8") as fh:
                text = fh.read()
            kind = "group" if "模块类型：group" in text else "leaf"
            ports = spec_ports(text)
            details.append({
                "name": mod,
                "kind": kind,
                "spec_path": os.path.join("spec_doc", name),
                "ports": ports,
                "params": _params(text),
                "registers": _registers(text),
                "connections": _connections(text),
                "logic_blocks": _logic_blocks(text),
                "memory": _memory(text),
                "fixed_point": _formats(text),
                "tests": _structured_tests(text),
            })
    sys_file = os.path.join(spec_dir, (sys_name or "") + "_spec.md")
    top_text = ""
    if sys_name and os.path.isfile(sys_file):
        with open(sys_file, encoding="utf-8") as fh:
            top_text = fh.read()
    return {
        "schema_version": "2",
        "sys_name": sys_name or os.path.basename(sys_root.rstrip(os.sep)),
        "params": _params(top_text),
        "ports": spec_ports(top_text),
        "registers": _registers(top_text),
        "memory": _memory(top_text),
        "modules": [{"name": item["name"], "kind": item["kind"], "spec_path": item["spec_path"]}
                    for item in details if item["name"] != sys_name],
        "module_details": [item for item in details if item["name"] != sys_name],
        "flow_nodes": _formats(top_text),
    }


def dump(sys_root, sys_name=""):
    from framework.ircheck import validate_ir
    data = digest(sys_root, sys_name)
    errors = validate_ir(data)
    if errors:
        raise ValueError("交付 IR 未通过校验：%s" % errors[0])
    return json.dumps(data, ensure_ascii=False, indent=2)
