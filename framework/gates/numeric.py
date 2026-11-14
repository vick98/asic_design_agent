# 作者：vick 邮箱：ykun@yk9811.com

"""核对文档里的定点算式、戳记、位域合计、区段容量和同名格式。"""

import os
import re

from framework.toolbox.fx import (
    finish,
    FxError, add, addr_capacity, cmul, fmt_s, latency, lift, line, mul, obs16,
    parse_fmt, round_shr, sac_shift, sat_bounds, shift, sub,
)

FMT = r"<\s*(\d+)\s*,\s*(\d+)\s*,\s*([tu])\s*>"
FORMULA = re.compile(
    r"%s\s*(\*\*|\*|×|\+|-|−)\s*%s\s*(?:→|->)\s*%s" % (FMT, FMT, FMT)
)
STAMP = re.compile(r"stamp:\s*([0-9a-f]{12})")
NAMED = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`\s*" + FMT)
PORT_FMT = re.compile(r"(\d+)\s*[（(]\s*" + FMT)
TOTAL_WORDS = re.compile(r"合计\s*(\d+)\s*字")
ADDR_BITS = re.compile(r"地址位宽\s*(\d+)")
PACK_TOTAL = re.compile(r"(?:合计|打包总线)\s*(\d+)\b")

# 带数值的 fx 文本行：戳记不变，数值由闸门按同样的运算复核。
SAT_NOTE = re.compile(r"sat\s+" + FMT + r"\s+(asymmetric|symmetric)\s+范围\s*(-?\d+)\.\.(-?\d+)")
PACK_NOTE = re.compile(r"pack\s+((?:\d+\s*\+\s*)+\d+)\s+合计位宽\s*(\d+)")
ADDR_NOTE = re.compile(
    r"addr\s+\[([^\]]*)\]\s*bits=(\d+)\s+总字数\s*(\d+)\s+容量\s*(\d+)\s*(放得下|放不下)")
ROUND_NOTE = re.compile(r"round\s+(-?\d+)\s*>>\s*(\d+)\s*(trunc|half_up|even)\s+结果\s*(-?\d+)")
LATENCY_NOTE = re.compile(r"latency\s+\[([^\]]*)\]\s+拍数合计\s*(\d+)")
SAC_NOTE = re.compile(r"sac\s+" + FMT + r"\s*->\s*" + FMT + r"\s+移位\s*(\d+)")
TOL_NOTE = re.compile(r"GOLDEN_TOL\s+(\d+)\s+k=(\d+)\s+参考刻度\s+2\^(-?\d+)=(\S+)")


SHIFT = re.compile(
    r"%s\s*>>\s*(\d+)(\s+shrink)?\s*(?:→|->)\s*%s" % (FMT, FMT)
)
LIFT = re.compile(r"lift\s+%s\s*(?:→|->)\s*%s" % (FMT, FMT))
OBS = re.compile(r"obs16\s+%s\s*(?:→|->)\s*%s" % (FMT, FMT))
SAT = re.compile(r"sat\s+%s\s+(asymmetric|symmetric)" % FMT)
SAC = re.compile(r"sac\s+%s\s*(?:→|->)\s*%s" % (FMT, FMT))
FINISH = re.compile(
    r"finish\s+" + FMT + r"\s*>>\s*(\d+)\s*half-up\s*\+\s*sat\s*(?:→|->)\s*" + FMT)
CHAIN = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s+(.*?)->\s*([A-Za-z_][A-Za-z0-9_]*)\s*$")
FACTOR = re.compile(r"^\s*(\d+(?:\s*×\s*\d+)+)\s*=\s*(\d+)\s*$")
PARAM_ROW = re.compile(r"^\|\s*([A-Z][A-Z0-9_]{2,})\s*\|\s*(\d+)\s*\|")
PARAM_ASSIGN = re.compile(r"\b([A-Z][A-Z0-9_]{2,})\b\s*(?:=|取|为)\s*(\d+)")
PARAM_KW = ("位宽", "宽度", "深度", "参数", "常数", "上限", "个数", "档位", "固定为")


def _eval(op, f1, f2):
    if op == "**":
        return cmul(f1, f2)
    if op in ("*", "×"):
        return mul(f1, f2)
    if op in ("-", "−"):
        return sub(f1, f2)
    return add(f1, f2)


def _op_word(op):
    if op == "**":
        return "**"
    if op in ("*", "×"):
        return "*"
    if op in ("-", "−"):
        return "-"
    return "+"


def _kind(op):
    if op == "**":
        return "cmul"
    if op in ("*", "×"):
        return "mul"
    if op in ("-", "−"):
        return "sub"
    return "add"


def _window(lines, idx):
    nxt = lines[idx + 1] if idx + 1 < len(lines) else ""
    return lines[idx] + "\n" + nxt


# 会带戳记的定点表达式；窗口内的表达式区间用来划清"这枚戳记归谁"。
EXPR_PATTERNS = (FORMULA, SHIFT, FINISH, LIFT, OBS, SAT, SAC)


def _expr_spans(window):
    """窗口内所有定点表达式的 [起, 止) 区间，按出现位置排序。"""
    spans = []
    for pattern in EXPR_PATTERNS:
        for m in pattern.finditer(window):
            spans.append((m.start(), m.end()))
    spans.sort()
    return spans


def _stamp_after(window, end, spans):
    """取本表达式结束之后、下一条表达式之前的第一枚戳记。

    一行里写多条表达式时，戳记按距离归属；取不到就是缺戳记，
    不退化到"窗口内任一戳记"，否则这条表达式会拿别人的戳记过关。
    """
    limit = len(window)
    for start, _ in spans:
        if start >= end:
            limit = start
            break
    return STAMP.search(window, end, limit)


def scan_text(text, where):
    findings = []
    lines = text.split("\n")
    for idx, raw in enumerate(lines):
        window = _window(lines, idx)
        spans = _expr_spans(window)
        for m in FORMULA.finditer(raw):
            f1 = (int(m.group(1)), int(m.group(2)), m.group(3))
            op = m.group(4)
            f2 = (int(m.group(5)), int(m.group(6)), m.group(7))
            declared = (int(m.group(8)), int(m.group(9)), m.group(10))
            try:
                parse_fmt("<%d,%d,%s>" % f1)
                parse_fmt("<%d,%d,%s>" % f2)
                expected = _eval(op, f1, f2)
            except ValueError as exc:
                findings.append({"rule": "fx", "where": where, "detail": str(exc)})
                continue
            expr = "%s %s %s" % (fmt_s(f1), _op_word(op), fmt_s(f2))
            kind = _kind(op)
            expect_stamp = line(kind, expr, expected)["stamp"]
            got = _stamp_after(window, m.end(), spans)
            if expected != declared:
                findings.append({
                    "rule": "fx",
                    "where": where,
                    "detail": "%s 应按工具得 %s，文档写 %s" % (expr, fmt_s(expected), fmt_s(declared)),
                })
            elif not got:
                findings.append({
                    "rule": "fx-stamp",
                    "where": where,
                    "detail": "%s 的结果缺少工具戳记 stamp: %s" % (expr, expect_stamp),
                })
            elif got.group(1) != expect_stamp:
                findings.append({
                    "rule": "fx-stamp",
                    "where": where,
                    "detail": "%s 的戳记与工具不一致" % expr,
                })
        for pm in PORT_FMT.finditer(raw):
            width = int(pm.group(1))
            fmt_w = int(pm.group(2))
            if width != fmt_w:
                findings.append({
                    "rule": "D4",
                    "where": where,
                    "detail": "端口位宽 %d 与定点总位宽 %d 不一致" % (width, fmt_w),
                })
        findings.extend(_check_shift(raw, window, spans, where))
        findings.extend(_check_finish(raw, window, spans, where))
        findings.extend(_check_lift(raw, window, spans, where))
        findings.extend(_check_obs(raw, window, spans, where))
        findings.extend(_check_sat(raw, window, spans, where))
        findings.extend(_check_sac(raw, window, spans, where))
    findings.extend(_pack(text, where))
    findings.extend(_segments(text, where))
    findings.extend(_factors(text, where))
    findings.extend(_bare_formats(text, where))
    findings.extend(_legal_formats(text, where))
    findings.extend(_chain(text, where))
    findings.extend(_obs16(text, where))
    findings.extend(_latency_missing(text, where))
    findings.extend(_fx_notes(text, where))
    return findings


def _fx_note(bad):
    return {"rule": "fx", "detail": bad}


def _fx_notes(text, where):
    """复核 fx 文本行里显示的数值；旧文档没有这些数值时不报。"""
    findings = []
    for raw in text.split("\n"):
        for m in SAT_NOTE.finditer(raw):
            src = (int(m.group(1)), int(m.group(2)), m.group(3))
            bounds = sat_bounds(src, symmetric=(m.group(4) == "symmetric"))
            if (int(m.group(5)), int(m.group(6))) != (bounds["min"], bounds["max"]):
                findings.append(dict(_fx_note(
                    "sat %s 显示范围 %s..%s，工具为 %d..%d" % (
                        fmt_s(src), m.group(5), m.group(6), bounds["min"], bounds["max"])),
                    where=where))
        for m in PACK_NOTE.finditer(raw):
            widths = [int(n) for n in re.findall(r"\d+", m.group(1))]
            if sum(widths) != int(m.group(2)):
                findings.append(dict(_fx_note(
                    "pack %s 显示合计位宽 %s，实为 %d" % (m.group(1), m.group(2), sum(widths))),
                    where=where))
        for m in ADDR_NOTE.finditer(raw):
            depths = [int(n) for n in re.findall(r"\d+", m.group(1))]
            got = addr_capacity(depths, int(m.group(2)))
            if (int(m.group(3)), int(m.group(4)), m.group(5)) != (
                    got["total_words"], got["capacity"], "放得下" if got["fits"] else "放不下"):
                findings.append(dict(_fx_note(
                    "addr %s bits=%s 的显示数值与工具不符" % (m.group(1), m.group(2))), where=where))
        for m in ROUND_NOTE.finditer(raw):
            got = round_shr(int(m.group(1)), int(m.group(2)), m.group(3))
            if got != int(m.group(4)):
                findings.append(dict(_fx_note(
                    "round %s >> %s %s 显示结果 %s，工具为 %d" % (
                        m.group(1), m.group(2), m.group(3), m.group(4), got)), where=where))
        for m in LATENCY_NOTE.finditer(raw):
            cycles = [int(n) for n in re.findall(r"\d+", m.group(1))]
            if latency(cycles) != int(m.group(2)):
                findings.append(dict(_fx_note(
                    "latency %s 显示拍数合计 %s，实为 %d" % (
                        m.group(1), m.group(2), latency(cycles))), where=where))
        for m in SAC_NOTE.finditer(raw):
            src = (int(m.group(1)), int(m.group(2)), m.group(3))
            dst = (int(m.group(4)), int(m.group(5)), m.group(6))
            if sac_shift(src, dst) != int(m.group(7)):
                findings.append(dict(_fx_note(
                    "sac %s -> %s 显示移位 %s，工具为 %d" % (
                        fmt_s(src), fmt_s(dst), m.group(7), sac_shift(src, dst))), where=where))
        for m in TOL_NOTE.finditer(raw):
            if m.group(1) != m.group(2):
                findings.append(dict(_fx_note(
                    "GOLDEN_TOL %s 与 k=%s 不一致" % (m.group(1), m.group(2))), where=where))
                continue
            exp = int(m.group(3))
            expect = 2.0 ** exp
            try:
                shown = float(m.group(4))
            except ValueError as exc:
                del exc
                shown = None
            if shown is None or abs(shown - expect) > abs(expect) * 1e-6:
                findings.append(dict(_fx_note(
                    "参考刻度 2^%d 应为 %.6g，文档写 %s" % (exp, expect, m.group(4))), where=where))
    return findings


def _stamp_ok(kind, expr, result, window, spans=(), end=0, extra=None):
    expect = line(kind, expr, result, extra)["stamp"]
    got = _stamp_after(window, end, spans)
    if not got:
        return {"rule": "fx-stamp", "detail": "%s 的结果缺少工具戳记 stamp: %s" % (expr, expect)}
    if got.group(1) != expect:
        return {"rule": "fx-stamp", "detail": "%s 的戳记与工具不一致" % expr}
    return None


def _check_shift(raw, window, spans, where):
    findings = []
    for m in SHIFT.finditer(raw):
        src = (int(m.group(1)), int(m.group(2)), m.group(3))
        n = int(m.group(4))
        shrink = bool(m.group(5))
        declared = (int(m.group(6)), int(m.group(7)), m.group(8))
        expr = "%s >> %d%s" % (fmt_s(src), n, " shrink" if shrink else "")
        try:
            expected = shift(src, n, shrink=shrink)
        except FxError as exc:
            findings.append({"rule": "fx", "where": where, "detail": str(exc)})
            continue
        if expected != declared:
            findings.append({
                "rule": "fx", "where": where,
                "detail": "%s 应按工具得 %s，文档写 %s" % (expr, fmt_s(expected), fmt_s(declared)),
            })
            continue
        bad = _stamp_ok("shift", expr, expected, window, spans, m.end())
        if bad:
            bad["where"] = where
            findings.append(bad)
    return findings


def _check_finish(raw, window, spans, where):
    findings = []
    for m in FINISH.finditer(raw):
        src = (int(m.group(1)), int(m.group(2)), m.group(3))
        n = int(m.group(4))
        dst = (int(m.group(5)), int(m.group(6)), m.group(7))
        expr = "finish %s >> %d half-up + sat -> %s" % (fmt_s(src), n, fmt_s(dst))
        try:
            got = finish(src, dst, n)
        except FxError as exc:
            findings.append({"rule": "fx", "where": where, "detail": str(exc)})
            continue
        bad = _stamp_ok("finish", expr, None, window, spans, m.end(),
                        extra={"shift": got["shift"], "sat": got["sat"]})
        if bad:
            bad["where"] = where
            findings.append(bad)
    return findings


def _check_lift(raw, window, spans, where):
    findings = []
    for m in LIFT.finditer(raw):
        src = (int(m.group(1)), int(m.group(2)), m.group(3))
        declared = (int(m.group(4)), int(m.group(5)), m.group(6))
        expr = "lift %s" % fmt_s(src)
        expected = lift(src)
        if expected != declared:
            findings.append({
                "rule": "fx", "where": where,
                "detail": "%s 应按工具得 %s，文档写 %s" % (expr, fmt_s(expected), fmt_s(declared)),
            })
            continue
        bad = _stamp_ok("lift", expr, expected, window, spans, m.end())
        if bad:
            bad["where"] = where
            findings.append(bad)
    return findings


def _check_obs(raw, window, spans, where):
    findings = []
    for m in OBS.finditer(raw):
        src = (int(m.group(1)), int(m.group(2)), m.group(3))
        declared = (int(m.group(4)), int(m.group(5)), m.group(6))
        expr = "obs16 %s" % fmt_s(src)
        try:
            got = obs16(src)
        except FxError as exc:
            findings.append({"rule": "fx", "where": where, "detail": str(exc)})
            continue
        expected = got["format"]
        extra = {"shift": got["shift"], "pad_low": got["pad_low"]}
        if expected != declared:
            findings.append({
                "rule": "fx", "where": where,
                "detail": "%s 应按工具得 %s，文档写 %s" % (expr, fmt_s(expected), fmt_s(declared)),
            })
            continue
        bad = _stamp_ok("obs16", expr, expected, window, spans, m.end(), extra)
        if bad:
            bad["where"] = where
            findings.append(bad)
    return findings


def _check_sat(raw, window, spans, where):
    findings = []
    for m in SAT.finditer(raw):
        src = (int(m.group(1)), int(m.group(2)), m.group(3))
        mode = m.group(4)
        bounds = sat_bounds(src, symmetric=(mode == "symmetric"))
        expr = "sat %s %s" % (fmt_s(src), bounds["mode"])
        bad = _stamp_ok("sat", expr, None, window, spans, m.end(), bounds)
        if bad:
            bad["where"] = where
            findings.append(bad)
    return findings


def _check_sac(raw, window, spans, where):
    findings = []
    for m in SAC.finditer(raw):
        src = (int(m.group(1)), int(m.group(2)), m.group(3))
        dst = (int(m.group(4)), int(m.group(5)), m.group(6))
        expr = "sac %s -> %s" % (fmt_s(src), fmt_s(dst))
        try:
            n = sac_shift(src, dst)
        except FxError as exc:
            findings.append({"rule": "fx", "where": where, "detail": str(exc)})
            continue
        bad = _stamp_ok("sac", expr, None, window, spans, m.end(), {"shift": n})
        if bad:
            bad["where"] = where
            findings.append(bad)
    return findings


def _bare_formats(text, where):
    findings = []
    lines = text.split("\n")
    for idx, raw in enumerate(lines):
        if not re.search(FMT, raw):
            continue
        window = _window(lines, idx)
        if (FORMULA.search(window) or SHIFT.search(window) or LIFT.search(window)
                or OBS.search(window) or SAT.search(window) or SAC.search(window)
                or STAMP.search(window) or NAMED.search(window) or PORT_FMT.search(raw)):
            continue
        findings.append({
            "rule": "fx-bare",
            "where": where,
            "detail": "定点格式没有算式、命名节点或戳记：%s" % raw.strip()[:80],
        })
    return findings


def _legal_formats(text, where):
    findings = []
    seen = set()
    for m in re.finditer(FMT, text):
        fmt = (int(m.group(1)), int(m.group(2)), m.group(3))
        if fmt in seen:
            continue
        seen.add(fmt)
        try:
            parse_fmt("<%d,%d,%s>" % fmt)
        except FxError as exc:
            findings.append({"rule": "D6b", "where": where, "detail": str(exc)})
    return findings


def _obs16(text, where):
    if "o_obs_node" not in text:
        return []
    widths = [int(n) for n in re.findall(r"o_obs_node[^\n]{0,60}?(\d+)\s*bit", text)]
    widths += [int(m.group(1)) for m in re.finditer(r"o_obs_node[^\n]{0,40}" + FMT, text)]
    bad = [w for w in widths if w != 16]
    if bad:
        return [{"rule": "D8", "where": where, "detail": "观测口位宽须为 16，文档写 %s" % bad}]
    if not widths:
        return [{"rule": "D8", "where": where, "detail": "写了 o_obs_node 但没有 16 bit 位宽"}]
    return []


def _latency_missing(text, where):
    m = re.search(r"模块逻辑块描述\s*\n(.*?)(?=^##\s|\Z)", text, re.S | re.M)
    if not m:
        return []
    if not re.search(r"\d+\s*拍", m.group(1)):
        return [{"rule": "latency", "where": where, "detail": "逻辑块描述没有拍数"}]
    return []


def _pack(text, where):
    if "位域" not in text and "打包" not in text:
        return []
    from framework.mdtable import table_rows
    widths = []
    for cells in table_rows(text):
        if len(cells) >= 2 and cells[-1].isdigit() and cells[0] not in ("名字", "字段"):
            widths.append(int(cells[-1]))
    declared = PACK_TOTAL.search(text)
    if not declared or not widths:
        return []
    total = sum(widths)
    if int(declared.group(1)) != total:
        return [{"rule": "D2", "where": where, "detail": "位域合计 %d，文档写 %s" % (total, declared.group(1))}]
    return []


def _segments(text, where):
    if "区段" not in text:
        return []
    depths = []
    for raw in text.split("\n"):
        if not raw.strip().startswith("|"):
            continue
        cells = [c.strip() for c in raw.strip().strip("|").split("|")]
        if len(cells) >= 3 and cells[2].isdigit():
            depths.append(int(cells[2]))
    if not depths:
        return []
    findings = []
    words = TOTAL_WORDS.search(text)
    if words and int(words.group(1)) != sum(depths):
        findings.append({
            "rule": "D3",
            "where": where,
            "detail": "区段合计 %d 字，文档写 %s" % (sum(depths), words.group(1)),
        })
    bits = ADDR_BITS.search(text)
    if bits:
        got = addr_capacity(depths, int(bits.group(1)))
        if not got["fits"]:
            findings.append({
                "rule": "D6",
                "where": where,
                "detail": "区段 %d 字超过 2^%d" % (got["total_words"], got["addr_bits"]),
            })
    return findings


def _factors(text, where):
    if "区段" not in text:
        return []
    findings = []
    for raw in text.split("\n"):
        if not raw.strip().startswith("|") or "SEG_" not in raw:
            continue
        cells = [c.strip() for c in raw.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        matched = FACTOR.match(cells[2])
        if not matched:
            continue
        factors = [int(n) for n in re.findall(r"\d+", matched.group(1))]
        prod = 1
        for n in factors:
            prod *= n
        declared = int(matched.group(2))
        if prod != declared:
            findings.append({
                "rule": "D6a",
                "where": where,
                "detail": "区段深度因子乘积不符：%s = %d（声明 %d 字）" % (
                    "×".join(str(n) for n in factors), prod, declared),
            })
    return findings


def _nodes(text):
    nodes = {}
    for raw in text.split("\n"):
        if not raw.startswith("|"):
            continue
        cells = [c.strip() for c in raw.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        found = re.search(FMT, cells[3])
        if not found or cells[0].startswith("数据节点") or set(cells[0]) <= set("-: "):
            continue
        name = re.sub(r"^`|`$", "", cells[0].strip())
        name = re.sub(r"[（(].*$", "", name).strip()
        nodes[name] = (int(found.group(1)), int(found.group(2)), found.group(3))
    return nodes


def _chain(text, where):
    if "->" not in text:
        return []
    nodes = _nodes(text)
    findings = []
    for raw in text.split("\n"):
        matched = CHAIN.match(raw.strip())
        if not matched:
            continue
        src, mid, dst = matched.group(1), matched.group(2), matched.group(3)
        opm = re.match(r"\s*(\*\*|\*|×|\+|-|−)", mid)
        if not opm or src not in nodes or dst not in nodes:
            continue
        if "sac" in mid:
            continue
        operand = None
        for tok in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", mid):
            if tok in nodes:
                operand = nodes[tok]
                break
        if operand is None:
            continue
        try:
            expected = _eval(opm.group(1), nodes[src], operand)
        except FxError as exc:
            findings.append({"rule": "D1b", "where": where, "detail": str(exc)})
            continue
        if expected != nodes[dst]:
            findings.append({
                "rule": "D1b",
                "where": where,
                "detail": "运算链 %s %s -> %s：按规则应为 %s，节点表写 %s" % (
                    src, _op_word(opm.group(1)), dst, fmt_s(expected), fmt_s(nodes[dst])),
            })
    return findings


def scan_params(docs, sys_name=""):
    """D7 的作用域是同一份规格书；跨文档同名不同值降为提示，
    除非该参数出现在子系统规格书的全局参数表里。"""
    findings = []
    per_doc = {}
    for rel, text in sorted(docs.items()):
        local = {}
        for index, raw in enumerate(text.split("\n"), 1):
            row = PARAM_ROW.search(raw)
            if row:
                local.setdefault(row.group(1), {}).setdefault(
                    int(row.group(2)), []).append("%s:%d" % (rel, index))
            if not any(k in raw for k in PARAM_KW):
                continue
            for m in PARAM_ASSIGN.finditer(raw):
                local.setdefault(m.group(1), {}).setdefault(
                    int(m.group(2)), []).append("%s:%d" % (rel, index))
        per_doc[rel] = local
    across = {}
    for rel, local in per_doc.items():
        for name, byval in sorted(local.items()):
            if len(byval) > 1:
                findings.append({
                    "rule": "D7", "where": rel,
                    "detail": "参数「%s」在同一份文档里取值不唯一：%s" % (
                        name, "；".join("= %d" % v for v in sorted(byval))),
                })
            for value in byval:
                across.setdefault(name, {}).setdefault(value, []).append(rel)
    sys_spec = "spec_doc/%s_spec.md" % sys_name
    global_names = set()
    for raw in (docs.get(sys_spec) or "").split("\n"):
        row = PARAM_ROW.search(raw)
        if row:
            global_names.add(row.group(1))
    for name, byval in sorted(across.items()):
        if len(byval) <= 1:
            continue
        detail = "；".join("%s：%s" % ("/".join(sorted(set(where))), value)
                           for value, where in sorted(byval.items()))
        if name in global_names:
            findings.append({
                "rule": "D7", "where": name,
                "detail": "全局参数「%s」跨文档取值不唯一：%s" % (name, detail),
            })
        else:
            findings.append({
                "rule": "D7", "level": "hint", "where": name,
                "detail": "参数「%s」跨文档取值不同，按实例取值可不同则无需处理：%s" % (name, detail),
            })
    return findings


def scan_named_formats(docs):
    seen = {}
    findings = []
    for rel, text in docs.items():
        for m in NAMED.finditer(text):
            name = m.group(1)
            fmt = (int(m.group(2)), int(m.group(3)), m.group(4))
            prev = seen.get(name)
            if prev and prev[0] != fmt:
                findings.append({
                    "rule": "D5",
                    "where": rel,
                    "detail": "%s 在 %s 为 %s，这里为 %s" % (name, prev[1], fmt_s(prev[0]), fmt_s(fmt)),
                })
            elif not prev:
                seen[name] = (fmt, rel)
    return findings


def _product_texts(sys_root):
    """产物正文列表：与 docs 闸门共用同一个函数，info_input/ 只认总览。"""
    from framework.gates.products import doc_texts
    return doc_texts(sys_root)


def scan_tree(sys_root):
    import os
    docs = _product_texts(sys_root)
    findings = []
    for rel, text in sorted(docs.items()):
        findings.extend(scan_text(text, rel))
    findings.extend(scan_named_formats(docs))
    findings.extend(scan_params(docs, os.path.basename(os.path.abspath(sys_root))))
    return findings
