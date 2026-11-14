# 作者：vick 邮箱：ykun@yk9811.com

"""规格书端口对 RTL，以及顶层例化是否盖住模块端口。"""

import os
import re

COMMENT = re.compile(r"//.*")
PORT = re.compile(
    r"\b(input|output|inout)\s+(?:(?:logic|wire|reg)\s+)?(?:(?:signed|unsigned)\s+)?"
    r"(?:\[([^\]]*)\]\s*)?([A-Za-z_]\w*)\s*[,)]"
)
PARAM = re.compile(
    r"parameter\s+(?:logic\s+\[[^\]]*\]\s+|logic\s+|int\s+|integer\s+|bit\s+|"
    r"\[[^\]]*\]\s+)?([A-Za-z_]\w*)\s*="
)
LEADING_NUM = re.compile(r"^\s*(\d+)")


def leading_width(cell):
    """位宽列取宽：单元格以十进制数字开头就取前导整数，否则 None。

    端口表与连接表共用这一套：`12`、`12（<12,1,t>）`、`8 bit` 都取到 12/8；
    装饰过的位宽列不再被连接表整行跳过，连接表位宽列也不必限成纯数字。
    """
    m = LEADING_NUM.match(cell or "")
    return int(m.group(1)) if m else None


def strip_comments(src):
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return COMMENT.sub("", src)


def _eval_expr(expr, params):
    expr = (expr or "").strip()
    if not expr:
        return None

    def repl(match):
        name = match.group(0)
        if name not in params:
            raise ValueError(name)
        return str(params[name])

    try:
        replaced = re.sub(r"[A-Za-z_]\w*", repl, expr)
    except ValueError as exc:
        return None
    if not re.fullmatch(r"[0-9+\-*/()\s]+", replaced):
        return None
    try:
        return int(eval(replaced, {"__builtins__": {}}, {}))
    except Exception:
        return None


def _range_width(expr, params):
    expr = expr.strip()
    matched = re.match(r"\s*(.+)\s*:\s*(.+)\s*$", expr)
    if not matched:
        return None
    hi = _eval_expr(matched.group(1), params)
    lo = _eval_expr(matched.group(2), params)
    if hi is None or lo is None:
        return None
    return abs(hi - lo) + 1


def _packed_width(ranges, params):
    if not ranges:
        return 1
    total = 1
    for rng in ranges:
        width = _range_width(rng, params)
        if width is None:
            return None
        total *= width
    return total


def _param_defaults(text):
    params = {}
    for matched in re.finditer(
        r"parameter\s+(?:logic\s+\[[^\]]*\]\s+|logic\s+|int\s+|integer\s+|bit\s+|"
        r"\[[^\]]*\]\s+)?([A-Za-z_]\w*)\s*=\s*([^,);\n]+)",
        text or "",
    ):
        value = _eval_expr(matched.group(2), params)
        if value is not None:
            params[matched.group(1)] = value
    return params


def _decl_ports(text, params):
    ports = []
    unsupported = []
    for matched in re.finditer(
        r"\b([A-Za-z_]\w*\.[A-Za-z_]\w*)\s+([A-Za-z_]\w*)",
        text,
    ):
        unsupported.append(matched.group(2))
    for matched in re.finditer(
        r"\b(input|output|inout)\s+(?:(?:logic|wire|reg)\s+)?(?:(?:signed|unsigned)\s+)?"
        r"((?:\[[^\]]+\]\s*)*)([A-Za-z_]\w*(?:\s*,\s*(?!input\b|output\b|inout\b)[A-Za-z_]\w*)*)",
        text,
    ):
        direction = matched.group(1).lower()
        ranges = re.findall(r"\[([^\]]+)\]", matched.group(2) or "")
        width = _packed_width(ranges, params)
        for name in re.findall(r"[A-Za-z_]\w*", matched.group(3)):
            if name in unsupported:
                continue
            ports.append({"name": name, "direction": direction, "width": width})
    return ports, unsupported


def module_decl(src, modname):
    src = strip_comments(src)
    matched = re.search(
        r"module\s+" + re.escape(modname) + r"\s*(?:#\((.*?)\))?\s*\((.*?)\)\s*;",
        src, re.S)
    if not matched:
        return None
    header = matched.group(2) or ""
    body = src[matched.end():].split("endmodule", 1)[0]
    params = _param_defaults((matched.group(1) or "") + "\n" + body)
    if re.search(r"\b(input|output|inout)\b", header) or re.search(r"\w+\.\w+", header):
        ports, unsupported = _decl_ports(header, params)
    else:
        ports, unsupported = _decl_ports(body, params)
    module_decl.last_unsupported = unsupported
    return list(params), ports


def rtl_width(range_s):
    if not range_s:
        return 1
    m = re.match(r"\s*(\d+)\s*:\s*(\d+)\s*$", range_s.strip())
    if not m:
        return None
    return abs(int(m.group(1)) - int(m.group(2))) + 1


def spec_ports(text):
    """端口表：名字、方向、可解析的整数位宽。"""
    from framework.mdtable import table_rows
    ports = []
    chunk = []
    capture = False
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith("#") and ("端口" in s or "接口" in s):
            capture = True
            continue
        if capture and s.startswith("## "):
            break
        if capture:
            chunk.append(line)
    for cells in table_rows("\n".join(chunk)):
        if len(cells) < 3 or cells[1].lower() not in ("input", "output", "inout"):
            continue
        width = leading_width(cells[2])
        port = {"name": cells[0], "direction": cells[1].lower(), "width": width,
                "clock": cells[3] if len(cells) > 3 else "",
                "description": cells[4] if len(cells) > 4 else ""}
        ports.append(port)
    return ports


def compare_ports(spec_text, rtl_src, modname):
    parsed = module_decl(rtl_src, modname)
    if parsed is None:
        return [{"rule": "M0", "detail": "%s 的 RTL 没有解析到 module 声明" % modname}]
    unsupported = getattr(module_decl, "last_unsupported", [])
    if unsupported:
        return [{"rule": "M0", "detail": "interface 端口未支持：%s" % "、".join(unsupported)}]
    _params, rtl = parsed
    spec = spec_ports(spec_text)
    smap = {p["name"]: p for p in spec}
    rmap = {p["name"]: p for p in rtl}
    out = []
    for name in sorted(set(smap) - set(rmap)):
        out.append({"rule": "M2", "detail": "规格书端口 %s 在 RTL 中没有" % name})
    for name in sorted(set(rmap) - set(smap)):
        out.append({"rule": "M2", "detail": "RTL 端口 %s 不在规格书端口表" % name})
    for name in sorted(set(smap) & set(rmap)):
        if smap[name]["direction"] != rmap[name]["direction"]:
            out.append({"rule": "M3", "detail": "%s 方向不一致" % name})
        sw, rw = smap[name]["width"], rmap[name]["width"]
        if sw is not None and rw is not None and sw != rw:
            out.append({"rule": "M4", "detail": "%s 位宽规格 %s / RTL %s" % (name, sw, rw)})
    spec_params = re.findall(r"(?ms)^#{2,3}\s[^\n]*参数[^\n]*\n(.*?)(?=^#{2,3}\s|\Z)", spec_text)
    if spec_params:
        spec_p = [n for n in re.findall(r"\|\s*`?([A-Za-z_]\w*)`?\s*\|", spec_params[0])
                  if n not in ("参数名", "名字")]
        for n in sorted(set(spec_p) - set(_params)):
            out.append({"rule": "M1", "detail": "规格书参数 %s 在 RTL 中没有" % n})
        for n in sorted(set(_params) - set(spec_p)):
            out.append({"rule": "M1", "detail": "RTL 参数 %s 不在规格书" % n})
    return out


def instance_ports(top_src, modname, instname):
    src = strip_comments(top_src)
    m = re.search(
        re.escape(modname) + r"\s*(?:#\((.*?)\)\s*)?" + re.escape(instname) + r"\s*\((.*?)\)\s*;",
        src, re.S)
    if not m:
        return None
    params = re.findall(r"\.\s*([A-Za-z_]\w*)\s*\(", m.group(1) or "")
    ports = re.findall(r"\.\s*([A-Za-z_]\w*)\s*\(", (m.group(2) or "") + ")")
    return params, ports


def check_instance(mod_src, top_src, modname, instname):
    decl = module_decl(mod_src, modname)
    inst = instance_ports(top_src, modname, instname)
    if decl is None:
        return [{"rule": "C0", "detail": "解析不到模块 %s" % modname}]
    if inst is None:
        return [{"rule": "C0", "detail": "顶层没有例化 %s %s" % (modname, instname)}]
    dparams, dport_rows = decl
    iparams, iports = inst
    dports = [row["name"] for row in dport_rows]
    out = []
    for name in sorted(set(dports) - set(iports)):
        out.append({"rule": "C1", "detail": "例化 %s 未连接端口 %s" % (instname, name)})
    for name in sorted(set(iports) - set(dports)):
        out.append({"rule": "C1", "detail": "例化 %s 多连了端口 %s" % (instname, name)})
    for name in sorted(set(dparams) - set(iparams)):
        out.append({"rule": "C2", "detail": "例化 %s 未传参数 %s" % (instname, name)})
    return out


def scan_rtl(sys_root):
    spec_dir = os.path.join(sys_root, "spec_doc")
    rtl_dir = os.path.join(sys_root, "rtl")
    findings = []
    if not os.path.isdir(rtl_dir):
        return [{"rule": "M0", "detail": "没有 rtl 目录"}]
    rtl_files = [f for f in os.listdir(rtl_dir) if f.endswith((".sv", ".v"))]
    if not rtl_files:
        return [{"rule": "M0", "detail": "rtl 目录里没有模块文件"}]
    for fn in sorted(rtl_files):
        if fn.endswith("_top.sv") or fn.endswith("_top.v"):
            continue
        mod = fn.rsplit(".", 1)[0]
        spec = os.path.join(spec_dir, mod + "_spec.md")
        rtl_path = os.path.join(rtl_dir, fn)
        with open(rtl_path, encoding="utf-8") as fh:
            rtl_src = fh.read()
        if not os.path.isfile(spec):
            findings.append({"rule": "M0", "detail": "%s 有 RTL 但没有规格书" % mod})
            continue
        with open(spec, encoding="utf-8") as fh:
            findings.extend(compare_ports(fh.read(), rtl_src, mod))
    return findings


def scan_conn(sys_root, sys_name):
    rtl_dir = os.path.join(sys_root, "rtl")
    top = os.path.join(rtl_dir, sys_name + "_top.sv")
    if not os.path.isfile(top):
        return [{"rule": "C0", "detail": "没有 %s_top.sv" % sys_name}]
    with open(top, encoding="utf-8") as fh:
        top_src = fh.read()
    findings = []
    for fn in sorted(os.listdir(rtl_dir)):
        if not fn.endswith((".sv", ".v")) or fn.startswith(sys_name + "_top."):
            continue
        mod = fn.rsplit(".", 1)[0]
        with open(os.path.join(rtl_dir, fn), encoding="utf-8") as fh:
            mod_src = fh.read()
        if re.search(r"\b" + re.escape(mod) + r"\b", strip_comments(top_src)) is None:
            continue
        insts = re.findall(
            r"\b" + re.escape(mod) + r"\s+(?:#\([^;]*?\)\s*)?([A-Za-z_]\w*)\s*\(",
            strip_comments(top_src))
        for inst in insts:
            findings.extend(check_instance(mod_src, top_src, mod, inst))
    return findings
