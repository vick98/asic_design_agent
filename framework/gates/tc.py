# 作者：vick 邮箱：ykun@yk9811.com

"""用例文件、factory、tc_all 三方双向一致。命名为 <dut>_tc_<name>。"""

import os
import re

from framework.tbgen import SKELETON_MARKS


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def strip_line_comments(text):
    out = []
    for line in text.splitlines():
        idx = line.find("//")
        out.append(line if idx < 0 else line[:idx])
    return "\n".join(out)


def ifdef_regions(text):
    lines = text.splitlines()
    guard_open = set()
    for i in range(len(lines) - 1):
        matched = re.match(r"`ifndef\s+(\w+)", lines[i].strip())
        if matched and re.match(r"`define\s+" + re.escape(matched.group(1)) + r"\b", lines[i + 1].strip()):
            guard_open.add(i)
    region = set()
    depth = 0
    for i, raw in enumerate(lines):
        if i in guard_open:
            continue
        stripped = raw.strip()
        if re.match(r"`ifdef\s", stripped):
            if depth > 0:
                region.add(i)
            depth += 1
        elif re.match(r"`endif\b", stripped):
            if depth > 0:
                depth -= 1
        elif depth > 0:
            region.add(i)
    return region


def _platforms(sys_root):
    tb = os.path.join(sys_root, "testbench")
    if not os.path.isdir(tb):
        return []
    if os.path.isdir(os.path.join(tb, "tc")):
        return [tb]
    found = []
    for name in sorted(os.listdir(tb)):
        sub = os.path.join(tb, name)
        if os.path.isdir(os.path.join(sub, "tc")):
            found.append(sub)
    return found


def platform_names(sys_root):
    """TB 平台的登记名：testbench/tc 叫 tb，其余用子目录名。"""
    names = []
    for platform in _platforms(sys_root):
        if os.path.basename(platform) == "testbench":
            names.append("tb")
        else:
            names.append(os.path.basename(platform))
    return names


def _dut_of(platform):
    tc_dir = os.path.join(platform, "tc")
    if not os.path.isdir(tc_dir):
        return ""
    all_files = [name for name in os.listdir(tc_dir) if name.endswith("_tc_all.sv")]
    if not all_files:
        return ""
    return sorted(all_files)[0][: -len("_tc_all.sv")]


def case_count(sys_root, dut="", only=None):
    """tc_all 枚举的用例数；行 10 的全量回归按它核对 RESULT 条数。

    `only` 是允许计入的平台名集合（T3：sys 场景只数 `testbench/<sys>_tb.f`
    实际引用的那个平台）；None 表示不按平台名过滤。
    """
    total = 0
    for platform in _platforms(sys_root):
        name = _dut_of(platform)
        if not name or (dut and name != dut):
            continue
        if only is not None and name not in only:
            continue
        enumerated, _cond, _missing = _tcall(
            os.path.join(platform, "tc", name + "_tc_all.sv"), name)
        total += len(enumerated)
    return total


def referenced_platforms(filelist):
    """`<sys>_tb.f` 里引用的平台目录名。清单不存在时返回 None（不限制）。"""
    if not filelist or not os.path.isfile(filelist):
        return None
    names = set()
    with open(filelist, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            for matched in re.finditer(r"testbench/([A-Za-z_]\w*)/", line):
                names.add(matched.group(1))
    return names or None


def _cases(tc_dir, dut):
    names = set()
    if not os.path.isdir(tc_dir):
        return names
    prefix = dut + "_tc_"
    for name in sorted(os.listdir(tc_dir)):
        if not (name.startswith(prefix) and name.endswith(".sv")):
            continue
        stem = name[:-3][len(dut):]
        matched = re.fullmatch(r"_tc_(.+)", stem)
        if not matched:
            continue
        case = matched.group(1)
        if case not in ("base", "all"):
            names.add(case)
    return names


def _factory(path):
    text = strip_line_comments(_read(path))
    regions = ifdef_regions(text)
    plain, cond = set(), set()
    for i, line in enumerate(text.splitlines()):
        matched = re.search(r'"tc_([A-Za-z0-9_]+)"\s*:', line)
        if matched and matched.group(1) not in ("base", "all"):
            (cond if i in regions else plain).add(matched.group(1))
    return plain, cond


def _tcall(path, dut):
    text = strip_line_comments(_read(path))
    regions = ifdef_regions(text)
    enumerated, cond, var2name = set(), set(), {}
    pattern = re.compile(r"%s_tc_(?!base\b|all\b)(\w+)\s+(\w+)\s*=\s*new\s*\(" % re.escape(dut))
    for i, line in enumerate(text.splitlines()):
        matched = pattern.search(line)
        if not matched:
            continue
        name, var = matched.group(1), matched.group(2)
        enumerated.add(name)
        var2name[var] = name
        if i in regions:
            cond.add(name)
    called = set(re.findall(r"(\w+)\.body\(\s*\)", text))
    missing = sorted(var2name[var] for var in var2name if var not in called)
    return enumerated, cond, missing


def _class_ok(path, class_name):
    text = _read(path)
    return re.search(r"\bclass\s+%s\b" % re.escape(class_name), text) is not None


def _testpoints(spec_path):
    """测试要点条数：有表格时按表格数据行算，无表格时按列表项算（与 trace 一致）。"""
    table_count = 0
    list_count = 0
    table_found = False
    level = None
    data_row = False
    for line in _read(spec_path).splitlines():
        matched = re.match(r"^(#{1,6})\s", line)
        if matched:
            depth = len(matched.group(1))
            if level is not None and depth <= level:
                level = None
            if level is None and "测试要点" in line:
                level = depth
            data_row = False
            continue
        if level is None:
            continue
        if re.match(r"^\s*-\s+\S", line):
            list_count += 1
            data_row = False
            continue
        stripped = line.strip()
        if not stripped.startswith("|"):
            data_row = False
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if cells and set("".join(cells)) <= set("-: "):
            data_row = True
            continue
        if cells and cells[0] in ("编号", "名字", "序号"):
            table_found = True
            data_row = True
            continue
        if data_row:
            table_count += 1
    return table_count if table_found else list_count


def _covered_testpoints(tc_dir, dut, cases):
    """用例覆盖的测试要点序号（T5 逐条映射）。

    两条声明途径：用例名 `tc_tp<N>`；或用例文件头注释里写 `testpoint: N`
    （手写用例不按 tp 命名时用，声明后这个用例就算覆盖了第 N 条）。
    """
    covered = set()
    for case in cases:
        matched = re.fullmatch(r"tp(\d+)", case)
        if matched:
            covered.add(int(matched.group(1)))
        path = os.path.join(tc_dir, "%s_tc_%s.sv" % (dut, case))
        if os.path.isfile(path):
            covered.update(int(num) for num in re.findall(r"testpoint\s*[:=]\s*(\d+)", _read(path)))
    return covered


def _skeleton_findings(platform, where, dut, tc_dir, cases):
    """T6：平台任用例文件或参考模型文件仍含 tb-gen 骨架标记即阻断。

    标记常量由 tbgen.py 导出（SKELETON_MARKS），用例文件与参考模型文件共用一套，
    避免闸门与生成器各写一份字面量后走偏。
    """
    targets = [("%s_tc_%s.sv" % (dut, case), os.path.join(tc_dir, "%s_tc_%s.sv" % (dut, case)))
               for case in sorted(cases)]
    if os.path.isdir(platform):
        targets += [(name, os.path.join(platform, name))
                    for name in sorted(os.listdir(platform)) if name.endswith("_tb_refm.svh")]
    findings = []
    for name, path in targets:
        if not os.path.isfile(path):
            continue
        text = _read(path)
        for mark in SKELETON_MARKS:
            if mark in text:
                findings.append({
                    "rule": "T6", "where": where,
                    "detail": "%s 仍是 tb-gen 骨架（含标记「%s」），按规格书填写后才能准出"
                              % (name, mark.split("：", 1)[0]),
                })
                break
    return findings


def _spec_path(platform, dut):
    """框架产物规格书的位置：只在 `spec_doc/`（rules/spec.md）。

    这里不回退到 `<sys_root>/<dut>_spec.md`：那条路径命中的是外部输入材料
    （如 `pub_code/pubip_mseq_cal_spec.md`，正文自己写明"供模块级 TB 参考"），
    拿它当模块规格做 T5 逐条映射是错的语义；docs.py 的章节与 S5 检查也只认 `spec_doc/`。
    """
    parent = os.path.dirname(platform)
    sys_root = os.path.dirname(parent) if os.path.basename(parent) == "testbench" else parent
    path = os.path.join(sys_root, "spec_doc", dut + "_spec.md")
    return path if os.path.isfile(path) else ""


def _check_platform(platform):
    tc_dir = os.path.join(platform, "tc")
    findings = []
    where = os.path.relpath(platform, os.path.dirname(os.path.dirname(platform)))
    all_files = [name for name in os.listdir(tc_dir) if name.endswith("_tc_all.sv")] if os.path.isdir(tc_dir) else []
    if not all_files:
        return [{"rule": "T1", "where": where, "detail": "没有 <dut>_tc_all.sv"}]
    dut = sorted(all_files)[0][: -len("_tc_all.sv")]
    files = _cases(tc_dir, dut)
    if not files:
        return [{"rule": "T0", "where": where, "detail": "没有 %s_tc_*.sv 用例" % dut}]
    factory = os.path.join(tc_dir, dut + "_tc_factory.svh")
    tcall = os.path.join(tc_dir, dut + "_tc_all.sv")
    if not os.path.isfile(factory):
        return [{"rule": "T1", "where": where, "detail": "缺少 %s" % os.path.basename(factory)}]
    unc, cond = _factory(factory)
    enumerated, _cond_all, missing_body = _tcall(tcall, dut)
    for case in sorted(files - unc - cond):
        findings.append({"rule": "T2", "where": where, "detail": "用例 tc_%s 有文件但未在 factory 注册" % case})
    for case in sorted((unc | cond) - files):
        findings.append({"rule": "T2", "where": where, "detail": "factory 注册了 tc_%s 但无对应用例文件" % case})
    for case in sorted(files - enumerated):
        if case in cond:
            findings.append({
                "rule": "T3", "level": "hint", "where": where,
                "detail": "用例 tc_%s 由 ifdef 包裹，未纳入 tc_all" % case,
            })
        else:
            findings.append({"rule": "T2", "where": where, "detail": "用例 tc_%s 未被 tc_all 枚举" % case})
    for case in sorted(enumerated - files):
        findings.append({"rule": "T2", "where": where, "detail": "tc_all 枚举了 tc_%s 但无对应用例文件" % case})
    for case in missing_body:
        findings.append({"rule": "T2", "where": where, "detail": "tc_all 中 tc_%s 未调用 body()" % case})
    for case in sorted(files):
        class_name = "%s_tc_%s" % (dut, case)
        path = os.path.join(tc_dir, class_name + ".sv")
        if os.path.isfile(path) and not _class_ok(path, class_name):
            findings.append({"rule": "T4", "where": where, "detail": "类名与文件名不一致：%s" % class_name})
    findings.extend(_skeleton_findings(platform, where, dut, tc_dir, files))
    spec = _spec_path(platform, dut)
    if spec:
        points = _testpoints(spec)
        covered = _covered_testpoints(tc_dir, dut, files)
        missing = [num for num in range(1, points + 1) if num not in covered]
        if missing:
            findings.append({
                "rule": "T5", "where": where,
                "detail": "测试要点缺对应用例：第 %s 条（用例名用 tc_tp<N>，"
                          "或用例文件头注释声明 testpoint: N）" % "、".join(str(num) for num in missing),
            })
    return findings


def scan_tc(sys_root):
    platforms = _platforms(sys_root)
    if not platforms:
        return [{"rule": "T0", "detail": "没有 testbench/tc"}]
    findings = []
    for platform in platforms:
        findings.extend(_check_platform(platform))
    return findings


def platform_path(sys_root, platform_name):
    """平台登记名 → 平台目录（与 _platforms/platform_names 同一套口径）。

    旧布局 `testbench/tc` 的登记名是 "tb"（对应 `<sys>/testbench`）；其余是
    `<sys>/testbench/<名字>`。按名字拼路径会漏掉旧布局，所以统一走这里。
    """
    for platform in _platforms(sys_root):
        name = "tb" if os.path.basename(platform) == "testbench" else os.path.basename(platform)
        if name == platform_name:
            return platform
    return ""


def platform_state(base, platform_name):
    """行 9 平台状态由文件与用例核对推导（不再手工登记 modules[9]）。

    - 平台目录找不到 → "未开始"；
    - 用例/参考模型仍含 tb-gen 骨架标记（T6）→ "骨架"；
    - `_check_platform` 无阻断发现 → "tc_check 通过"；
    - 其余（用例装配对不上）→ "用例已装配"。
    """
    platform = platform_path(base, platform_name)
    if not platform:
        return "未开始"
    findings = _check_platform(platform)
    if any(item.get("rule") == "T6" for item in findings):
        return "骨架"
    if any(item.get("level") != "hint" for item in findings):
        return "用例已装配"
    return "tc_check 通过"
