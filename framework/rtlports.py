# 作者：vick 邮箱：ykun@yk9811.com

"""RTL 端口真值解析：pyslang AST 求值优先，回退 gates.rtl 的正则解析。

tb-gen 以交付 IR 为端口来源（framework/tbgen.py 的 dut_ports）：IR 陈旧或
RTL 改过端口时，骨架会照着旧端口生成。生成前先用这里解析 rtl/<模块>.sv 的
实际端口与 IR 对表，对不上即拒绝生成并列出差异。行 7 闸门的"规格书↔RTL"
比对已有独立实现（framework/gates/rtl.py 的 compare_ports，规则号 M0–M3），
这里不重复，也不进闸门——tb-gen 是生成器，校验挡在生成前。

pyslang 是可选依赖（requirements.txt 注明可选）：装了走 AST 编译求值，位宽
按参数实际值展开（`[W-1:0]`、`[15:0]` 都能算）；没装回退正则（module_decl），
解析结果标 parser="regex"——参数化位宽此时可能为 None，调用方据此降级提示。
解析不出（文件缺失、语法错误）返回 errors，调用方决定提示或拒绝。
"""

import os

_PORT_FILES = (".sv", ".v")


def _find_rtl_file(sys_root, modname):
    rtl = os.path.join(sys_root, "rtl")
    for ext in _PORT_FILES:
        path = os.path.join(rtl, modname + ext)
        if os.path.isfile(path):
            return path
    return ""


def _parse_pyslang(text):
    """pyslang AST 编译求值；返回 (端口表, None) 或 (None, 错误一句话)。"""
    import pyslang.ast as ast
    import pyslang.syntax as syntax
    tree = syntax.SyntaxTree.fromText(text)
    comp = ast.Compilation()
    comp.addSyntaxTree(tree)
    diags = comp.getParseDiagnostics()
    for diag in diags:
        if str(getattr(diag, "severity", "")).lower() in ("fatal", "error"):
            return None, "RTL 解析报错：%s" % diag
    fatal = comp.hasFatalErrors
    if callable(fatal):
        fatal = fatal()
    if fatal:
        return None, "RTL 解析报错（fatal）"
    directions = {ast.ArgumentDirection.In: "input",
                  ast.ArgumentDirection.Out: "output",
                  ast.ArgumentDirection.InOut: "inout"}
    tops = list(comp.getRoot().topInstances)
    if not tops:
        return None, "没有顶层模块"
    ports = []
    for port in tops[0].body.portList:
        width = None
        try:
            width = int(port.type.bitstreamWidth)
        except Exception:
            width = None
        ports.append({
            "name": str(port.name),
            "direction": directions.get(port.direction, ""),
            "width": width,
        })
    return ports, None


def _parse_regex(sys_root, path, modname):
    """回退路径：framework/gates/rtl.py 的 module_decl 正则（行 7 同款）。"""
    from framework.gates.rtl import module_decl
    with open(path, encoding="utf-8") as fh:
        parsed = module_decl(fh.read(), modname)
    if parsed is None:
        return None, "没有解析到 module %s 声明" % modname
    unsupported = list(getattr(module_decl, "last_unsupported", []))
    if unsupported:
        return None, "端口声明未支持（正则解析）：%s" % "、".join(unsupported)
    ports = []
    for row in parsed[1]:
        item = {"name": row.get("name"), "direction": row.get("direction"),
                "width": row.get("width")}
        if item["width"] is None:
            item["width_unparsed"] = True
        ports.append(item)
    return ports, None


def parse_ports(sys_root, modname):
    """解析 rtl/<modname>.sv|.v 的实际端口。

    返回 (ports, parser, errors)：ports 是 [{"name","direction","width"}]
    （width 求不出时为 None 并带 width_unparsed 标记），parser 是
    "pyslang" | "regex" | ""，errors 是失败原因一句话列表。
    """
    path = _find_rtl_file(sys_root, modname)
    if not path:
        return [], "", ["rtl/ 下没有 %s.sv 或 %s.v" % (modname, modname)]
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    # 用 find_spec 探测可选依赖，不用 try import——框架目录禁出现厂商异常字面量
    # （framework/tests/test_profile.py 的禁用清单）。
    import importlib.util
    if importlib.util.find_spec("pyslang") is not None:
        ports, error = _parse_pyslang(text)
        if error is None:
            return ports, "pyslang", []
        return [], "", ["pyslang：%s" % error]
    ports, error = _parse_regex(sys_root, path, modname)
    if error is not None:
        return [], "", [error]
    return ports, "regex", []


def diff_ports(ir_ports, rtl_ports):
    """IR 端口表与 RTL 实际端口的差异清单；空清单即一致。

    口径与 compare_ports 一致：互相缺的端口、方向不一致、位宽不一致
    （IR 位宽必然是数字；RTL 位宽求不出时不比位宽，只比名字与方向）。
    """
    diffs = []
    smap = {p.get("name"): p for p in ir_ports or []}
    rmap = {p.get("name"): p for p in rtl_ports or []}
    for name in sorted(set(smap) - set(rmap)):
        diffs.append("IR 端口 %s 在 RTL 中没有" % name)
    for name in sorted(set(rmap) - set(smap)):
        diffs.append("RTL 端口 %s 不在 IR 端口表" % name)
    for name in sorted(set(smap) & set(rmap)):
        if smap[name].get("direction") != rmap[name].get("direction"):
            diffs.append("%s 方向不一致：IR %s / RTL %s"
                         % (name, smap[name].get("direction"), rmap[name].get("direction")))
        ir_w, rtl_w = smap[name].get("width"), rmap[name].get("width")
        if ir_w is not None and rtl_w is not None and int(ir_w) != int(rtl_w):
            diffs.append("%s 位宽不一致：IR %s / RTL %s" % (name, ir_w, rtl_w))
    return diffs
