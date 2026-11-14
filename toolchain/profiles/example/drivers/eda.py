# 作者：vick 邮箱：ykun@yk9811.com

"""nLint、覆盖率、综合、时序的命令。二进制名只出现在本剖面。"""

import os
import re

EXCLUDES = ("*.vdb", "*.fsdb", "*.vcd", "work", "*.daidir", "*.svf", "*.ddc")

# 版本探针的二进制名与开关都留在本剖面（框架不认识厂商命令）。
VERSION_BIN = {"lint": "nLint", "coverage": "urg", "synth": "dc_shell", "sta": "pt_shell",
               "lec": "yosys"}


def version_line(capability):
    """工具版本探针：脚本开头打一行 `TOOL_VERSION <能力> <版本串>`。

    版本串只取首行（各家 `-version` 之后还有 build 与 license 信息），多行会把
    日志撑乱，也让 expect_versions 的片段比对没法用。工具不在时这一行只剩标记，
    parse 会丢掉，运行记录里就没有这个字段（不阻断运行）。
    """
    return "echo \"TOOL_VERSION %s $(%s -version 2>&1 | head -n 1)\"" % (
        capability, VERSION_BIN[capability])


def _mirror_of(profile, local_path):
    """本地目录 → 镜像目录。"""
    local = (profile.get("local_root") or "").rstrip("/")
    mirror = profile["mirror_root"].rstrip("/")
    absolute = local_path if os.path.isabs(local_path) else os.path.join(local, local_path)
    inside = os.path.relpath(absolute, local)
    if inside.startswith(".."):
        return local_path
    return "%s/%s" % (mirror, inside.replace(os.sep, "/"))


def rsync_line(profile):
    host = profile["ssh_alias"]
    local = profile["local_root"].rstrip("/") + "/"
    mirror = profile["mirror_root"]
    excludes = " ".join("--exclude %s" % item for item in profile.get("sync_excludes") or [])
    return "rsync -avz --delete %s %s %s:%s/" % (excludes, local, host, mirror)


def pull_line(profile, sys_name, capability, scope=None):
    """把远端报告目录拉回本地 <sys>/lint|work|dc|pt。"""
    host = profile["ssh_alias"]
    mirror = profile["mirror_root"].rstrip("/")
    local = (profile.get("local_root") or "").rstrip("/")
    if capability == "coverage":
        scope = scope or {}
        if (scope.get("scenario") or "sys") == "pubip" and scope.get("module"):
            remote = "%s/pub_code/work/%s" % (mirror, scope["module"])
        elif (scope.get("scenario") or "sys") == "module" and scope.get("module"):
            remote = "%s/%s/work/%s" % (mirror, sys_name, scope["module"])
        else:
            remote = "%s/%s/work" % (mirror, sys_name)
        target = "%s/%s/work/" % (local, sys_name)
    elif capability == "lint":
        remote = "%s/%s/lint" % (mirror, sys_name)
        target = "%s/%s/lint/" % (local, sys_name)
    elif capability == "sta":
        remote = "%s/%s/pt" % (mirror, sys_name)
        target = "%s/%s/pt/" % (local, sys_name)
    else:
        remote = "%s/%s/dc" % (mirror, sys_name)
        target = "%s/%s/dc/" % (local, sys_name)
    excludes = " ".join("--exclude '%s'" % item for item in EXCLUDES)
    return "rsync -avz %s %s:%s/ %s || true" % (excludes, host, remote, target)


def lint_incdirs(profile, rtl_rel):
    """lint 的 include 搜索路径：设计目录 + 公共代码目录 + TB 公共目录。

    设计里可以用 `include "xxx.svh"`（大表分离成独立生成物）。nLint 默认不搜索
    被包含文件所在目录，必须显式给路径，否则报 16021「failed to find identifier」。
    目录一律由 lint 的 `target` 推导（target 是文件时取其所在目录），不写死子系统名；
    本地不存在的目录不下发，免得命令行指向镜像里不存在的路径。
    """
    local = (profile.get("local_root") or "").rstrip("/")
    target = os.path.join(local, rtl_rel)
    design = os.path.dirname(target) if rtl_rel.endswith((".v", ".sv")) else target
    candidates = (design, os.path.join(local, "pub_code"), os.path.join(local, "tb_common"))
    return [_mirror_of(profile, path) for path in candidates if os.path.isdir(path)]


def lint_script(profile, sys_name, rtl_rel):
    mirror = profile["mirror_root"]
    work = "%s/%s/lint" % (mirror, sys_name)
    target = "%s/%s" % (mirror, rtl_rel)
    incdirs = " ".join("+incdir+'%s'" % item for item in lint_incdirs(profile, rtl_rel))
    rules = "%s/toolchain/profiles/example/nLint_ws.rs" % mirror
    filt = "%s/toolchain/profiles/example/nLint_filter.txt" % mirror
    # 目标给目录时，nLint 不认目录，要展开成源文件清单；本子系统的 rtl 里例化了
    # pub_code/ 下的公共单元，必须一并送入，否则报 16651「view ... is not defined」。
    if rtl_rel.endswith((".v", ".sv")):
        sources = "'%s'" % target
    else:
        sources = ("$(ls '%s'/*.v '%s'/*.sv '%s/pub_code'/*.v '%s/pub_code'/*.sv "
                   "2>/dev/null)") % (target, target, mirror, mirror)
    return "\n".join([
        "set -u",
        version_line("lint"),
        "mkdir -p '%s'" % work,
        "cd '%s'" % work,
        # 旧报告留着会在 nLint 没跑起来时被当成这次的结果。
        "rm -f nlint_report.txt flt_run.txt",
        "sed 's|<MIRROR>|%s|g' '%s' > flt_run.txt" % (mirror, filt),
        "nLint -nologo -sv -rs '%s' -nors install:home:current -filter flt_run.txt %s -out nlint_report.txt" % (
            rules, " ".join(item for item in (incdirs, sources) if item)),
        "if [ ! -s nlint_report.txt ]; then echo NLINT RESULT: NOREPORT; "
        "elif grep -q '^Total 0 Warning' nlint_report.txt && ! grep -q 'Error(s)' nlint_report.txt; "
        "then echo NLINT RESULT: PASS; else echo NLINT RESULT: FAIL; fi",
    ]) + "\n"


def coverage_script(profile, sys_name, module="", scenario="sys"):
    mirror = profile["mirror_root"]
    if scenario == "pubip" and module:
        work = "%s/pub_code/work/%s" % (mirror, module)
        dut = module
    elif scenario == "module" and module:
        work = "%s/%s/work/%s" % (mirror, sys_name, module)
        dut = module
    else:
        work = "%s/%s/work" % (mirror, sys_name)
        dut = "%s_top" % sys_name
    return "\n".join([
        "set -u",
        version_line("coverage"),
        "cd '%s'" % work,
        # 先删旧报告：URG 会往同一个报告目录里累积历史数据，留着会把上一次的结论带进来。
        "rm -rf urgReport",
        "urg -dir simv.vdb -report urgReport -format both",
        "echo 'COV_DUT: %s'" % dut,
        "echo '--- URG_REPORT:dashboard ---'",
        "cat urgReport/dashboard.txt 2>/dev/null || true",
        "echo '--- URG_REPORT:hierarchy ---'",
        "cat urgReport/hierarchy.txt 2>/dev/null || true",
        "echo '--- URG_REPORT:modlist ---'",
        "cat urgReport/modlist.txt 2>/dev/null || true",
    ]) + "\n"


def _rtl_text(rtl_dir):
    """子系统 RTL 的正文（去掉注释，避免把注释里的例化示例当成真的例化）。"""
    text = []
    if os.path.isdir(rtl_dir):
        for fn in sorted(os.listdir(rtl_dir)):
            if fn.endswith((".sv", ".v")):
                with open(os.path.join(rtl_dir, fn), encoding="utf-8", errors="replace") as fh:
                    text.append(_strip_comments(fh.read()))
    return "\n".join(text)


def _strip_comments(text):
    import re
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return re.sub(r"//[^\n]*", " ", text)


def pubip_reads(profile, rtl_dir, mirror):
    """只读子系统 RTL 真正例化的 `pub_code` 模块，公共 IP 内部再例化的也逐层读入。

    全量读 `pub_code/` 会把别的 IP 一起卷进 elaboration（实测把只有几百门的计数器
    综合成 17 万门、时钟扇出 2080），而且与子系统同名的文件会把 DUT 覆盖掉。
    """
    import re
    local = (profile.get("local_root") or "").rstrip("/")
    pub = os.path.join(local, "pub_code")
    if not os.path.isdir(pub):
        return []
    own = set()
    if os.path.isdir(rtl_dir):
        for fn in sorted(os.listdir(rtl_dir)):
            if fn.endswith((".sv", ".v")):
                own.add(fn.rsplit(".", 1)[0])
    library = {fn.rsplit(".", 1)[0]: fn for fn in sorted(os.listdir(pub)) if fn.endswith((".sv", ".v"))}
    pending = [_rtl_text(rtl_dir)]
    used = set()
    while pending:
        text = pending.pop()
        for name, fn in library.items():
            if name in own or name in used:
                continue
            if re.search(r"\b" + re.escape(name) + r"\s*(#\s*\(|[A-Za-z_]\w*\s*\()", text):
                used.add(name)
                with open(os.path.join(pub, fn), encoding="utf-8", errors="replace") as fh:
                    pending.append(_strip_comments(fh.read()))
    return ["read_file -format sverilog %s/pub_code/%s" % (mirror, library[name]) for name in sorted(used)]


def synth_top(sys_name, top=""):
    return top or ("%s_top" % sys_name)


def synth_products(sys_name, top=""):
    """本次综合写出的网表与 SDC 文件名。命名是本剖面的事，框架按名字取。"""
    name = synth_top(sys_name, top)
    return {"netlist": "%s_syn.v" % name, "sdc": "%s_syn.sdc" % name}


def synth_script(profile, sys_name, lib="default", top="", rtl_dir="", sdc=""):
    mirror = profile["mirror_root"].rstrip("/")
    local = (profile.get("local_root") or "").rstrip("/")
    work = "%s/%s/dc" % (mirror, sys_name)
    lib_dir = "HVT" if lib == "hvt" else "STD"
    db = "yourtechHT_tt.db" if lib == "hvt" else "yourtech_tt.db"
    top = synth_top(sys_name, top)
    # --rtl-dir 可能是相对路径，必须相对数据根解析，不能依赖进程的当前目录。
    rtl_dir = rtl_dir or os.path.join(sys_name, "rtl")
    rtl_local = rtl_dir if os.path.isabs(rtl_dir) else os.path.join(local, rtl_dir)
    if not os.path.isdir(rtl_local):
        rtl_local = os.path.join(local, sys_name, "rtl")
    rtl_mirror = _mirror_of(profile, rtl_local)
    search = "%s/tech_lib/yourtech/%s/Synopsys" % (profile.get("tool_root", "/opt/synopsys"), lib_dir)
    reads = []
    if os.path.isdir(rtl_local):
        for fn in sorted(os.listdir(rtl_local)):
            if fn.endswith((".sv", ".v")):
                reads.append("read_file -format sverilog %s/%s" % (rtl_mirror, fn))
    if not reads:
        reads.append("read_file -format sverilog %s/%s.sv" % (rtl_mirror, top))
    reads.extend(pubip_reads(profile, rtl_local, mirror))
    tcl = [
        "set search_path [list . %s]" % search,
        "set target_library %s" % db,
        "set link_library [list * $target_library]",
    ] + reads + [
        "current_design %s" % top,
        "link",
        "read_sdc %s" % (sdc or "constraints.sdc"),
        "check_design > check_design.rpt",
        "compile_ultra",
        # 约束与 latch 的检查写进报告文件：文件内容不会被 dc_shell 回显，
        # 而写成 puts 的标记会随命令一起回显，解析时会把命令当成结果（曾经的假 no_clock）。
        "set adf_fp [open adf_checks.rpt w]",
        "puts $adf_fp \"Clock Count: [sizeof_collection [all_clocks]]\"",
        "if {[catch {sizeof_collection [all_registers -level_sensitive]} adf_latch_n]} "
        "{ set adf_latch_n UNKNOWN }",
        "puts $adf_fp \"Latch Count: $adf_latch_n\"",
        "close $adf_fp",
        "report_area > %s_syn_area.rpt" % top,
        "report_qor > %s_syn_qor.rpt" % top,
        "report_timing -max_paths 10 > %s_syn_timing.rpt" % top,
        "write -format ddc -output %s_syn.ddc" % top,
        "write -format verilog -output %s_syn.v" % top,
        "write_sdc %s_syn.sdc" % top,
        "exit",
    ]
    body = "\n".join(tcl)
    return "\n".join([
        "set -u",
        version_line("synth"),
        "mkdir -p '%s'" % work,
        "cd '%s'" % work,
        # dc_shell 中途失败时，留下的旧报告会被 cat 出来当成这次的结果。
        "rm -f adf_checks.rpt check_design.rpt %s_syn_area.rpt %s_syn_qor.rpt %s_syn_timing.rpt "
        "%s_syn.ddc %s_syn.v %s_syn.sdc dc.log" % (top, top, top, top, top, top),
        "cat > %s_syn.tcl <<'TCL'\n%s\nTCL" % (top, body),
        "dc_shell -f %s_syn.tcl -output_log_file dc.log < /dev/null" % top,
        "cat adf_checks.rpt check_design.rpt %s_syn_area.rpt %s_syn_qor.rpt "
        "%s_syn_timing.rpt dc.log 2>/dev/null" % (top, top, top),
    ]) + "\n"


def sta_script(profile, sys_name, corner="typical", netlist="", sdc=""):
    mirror = profile["mirror_root"]
    work = "%s/%s/pt" % (mirror, sys_name)
    db = {"typical": "yourtech_tt.db", "slow": "yourtech_ss.db", "fast": "yourtech_ff.db"}[corner]
    search = "%s/tech_lib/yourtech/STD/Synopsys" % profile.get("tool_root", "/opt/synopsys")
    net = netlist or ("%s/%s/dc/%s_syn.v" % (mirror, sys_name, "%s_top" % sys_name))
    top = os.path.splitext(os.path.basename(net))[0]
    if top.endswith("_syn"):
        top = top[:-4]
    if not top:
        top = "%s_top" % sys_name
    constraint = sdc or ("%s/%s/dc/%s_syn.sdc" % (mirror, sys_name, top))
    tcl = [
        "set search_path [list . %s]" % search,
        "set link_path [list * %s]" % db,
        "read_verilog %s" % net,
        "link_design %s" % top,
        "read_sdc %s" % constraint,
        "update_timing -full",
        "report_timing -delay_type max -max_paths 10 > %s_sta_setup.rpt" % top,
        "report_timing -delay_type min -max_paths 10 > %s_sta_hold.rpt" % top,
        "report_qor > %s_sta_qor.rpt" % top,
        "check_timing -verbose > %s_sta_check.rpt" % top,
        "exit",
    ]
    body = "\n".join(tcl)
    return "\n".join([
        "set -u",
        version_line("sta"),
        "mkdir -p '%s'" % work,
        "cd '%s'" % work,
        # pt_shell 在 link 阶段失败时，留下的旧报告会被当成这次的结果。
        "rm -f %s_sta_setup.rpt %s_sta_hold.rpt %s_sta_qor.rpt %s_sta_check.rpt pt.log"
        % (top, top, top, top),
        "cat > %s_sta.tcl <<'TCL'\n%s\nTCL" % (top, body),
        "pt_shell -f %s_sta.tcl -output_log_file pt.log < /dev/null" % top,
        "echo '--- PT_REPORT:setup ---'",
        "cat %s_sta_setup.rpt 2>/dev/null" % top,
        "echo '--- PT_REPORT:hold ---'",
        "cat %s_sta_hold.rpt 2>/dev/null" % top,
        "echo '--- PT_REPORT:check ---'",
        "cat %s_sta_check.rpt 2>/dev/null" % top,
        "echo '--- PT_REPORT:qor ---'",
        "cat %s_sta_qor.rpt pt.log 2>/dev/null" % top,
    ]) + "\n"


def _tool_versions(text):
    """日志里的 `TOOL_VERSION <能力> <版本串>` 行。

    版本为空的探针行（工具不在 PATH 上）不记：宁缺勿错，运行记录里要么是实测版本、
    要么没有这个字段。同一能力出现多行时取最后一行。
    """
    return dict(re.findall(r"(?m)^TOOL_VERSION\s+(\S+)[ \t]+(.+?)[ \t]*$", text or ""))


def lec_script(profile, sys_name, module="", gold=""):
    """CEC 等价性检查脚本（yosys，厂商中立）。

    候选 = rtl/<module>.sv|.v；黄金参考 gold 是同一模块名的参考实现（上一版
    或独立参考设计）。先读黄金文件并 rename 成 gold_ref，再读候选（两者同名
    模块不能一次 read，会报重复定义），建 miter 后 sat 求证：yosys 退出码 0
    且日志有 `SAT proof finished` 记 EQUIV；求证跑过但失败记 DIFF；其余
    （没有 yosys、没跑到求证）记 NOTOOL/NOREPORT，框架判 unavailable/error，
    不判不等价。
    """
    mirror = profile["mirror_root"]
    work = "%s/%s/work" % (mirror, sys_name)
    script = (
        "read_verilog -sv '%(gold)s'; rename %(mod)s gold_ref;"
        "read_verilog -sv $CAND;"
        "miter -equiv -flatten -make_assert gold_ref %(mod)s miter;"
        "hierarchy -top miter;"
        "sat -verify -prove-asserts -seq 1 -show-ports miter"
    ) % {"gold": gold, "mod": module}
    return "\n".join([
        "set -u",
        version_line("lec"),
        "mkdir -p '%s'" % work,
        "cd '%s'" % work,
        "rm -f lec.log",
        "CAND=$(ls '%(mirror)s/%(sys)s/rtl/%(mod)s.sv' '%(mirror)s/%(sys)s/rtl/%(mod)s.v' "
        "2>/dev/null | head -n 1)" % {"mirror": mirror, "sys": sys_name, "mod": module},
        "if [ -z \"$CAND\" ]; then echo 'CEC RESULT: NOCAND'; exit 0; fi",
        "if ! command -v yosys >/dev/null 2>&1; then echo 'CEC RESULT: NOTOOL'; exit 0; fi",
        "if yosys -p \"%s\" > lec.log 2>&1; then echo 'CEC RESULT: EQUIV';" % script,
        "elif grep -q 'SAT proof finished' lec.log; then echo 'CEC RESULT: DIFF';",
        "else echo 'CEC RESULT: NOREPORT'; fi",
    ]) + "\n"


def _parse_lec(text):
    if "CEC RESULT: EQUIV" in text:
        return {"equiv": 1, "diff": 0, "no_report": 0}
    if "CEC RESULT: DIFF" in text:
        return {"equiv": 0, "diff": 1, "no_report": 0}
    if "CEC RESULT: NOTOOL" in text:
        return {"tool_error": 1}
    return {"no_report": 1}


def parse(capability, log_text, artifact_dir=""):
    text = log_text or ""
    if artifact_dir and os.path.isdir(artifact_dir):
        for name in sorted(os.listdir(artifact_dir)):
            path = os.path.join(artifact_dir, name)
            if os.path.isfile(path):
                with open(path, encoding="utf-8", errors="replace") as fh:
                    text += "\n" + fh.read()
    if capability == "lint":
        checks = _parse_lint(text)
    elif capability == "coverage":
        checks = _parse_coverage(text)
    elif capability == "synth":
        checks = _parse_synth(text)
    elif capability == "sta":
        checks = _parse_sta(text)
    elif capability == "lec":
        checks = _parse_lec(text)
    else:
        checks = {}
    versions = _tool_versions(text)
    if versions:
        checks["tool_versions"] = versions
    return checks


def _parse_lint(text):
    if "NLINT RESULT: PASS" in text:
        return {"errors": 0, "warnings": 0, "compiler_error": 0}
    if "NLINT RESULT: FAIL" in text:
        return {"errors": 1, "warnings": 0, "compiler_error": 0}
    return {"compiler_error": 1}


def _score_row(tokens):
    """一行覆盖率数字。`--` 记成 na，由框架决定是否按 100 计。"""
    cleaned = []
    for token in tokens:
        if token in ("--", "N.A.", "n.a."):
            cleaned.append("na")
            continue
        try:
            cleaned.append(float(token))
        except ValueError:
            return None
    if len(cleaned) >= 5:
        return {"line": cleaned[1], "cond": cleaned[2], "tgl": cleaned[3], "fsm": cleaned[4]}
    if len(cleaned) >= 4:
        return {"line": cleaned[0], "cond": cleaned[1], "tgl": cleaned[2], "fsm": cleaned[3]}
    return None


def _worst(rows):
    """逐项取最差，避免以最好者代表整体。"""
    out = {}
    for key in ("line", "cond", "tgl", "fsm"):
        values = [float(row[key]) for row in rows if isinstance(row.get(key), (int, float))]
        out[key] = min(values) if values else "na"
    return out


def _urg_sections(text):
    """按驱动的分隔标记切出 dashboard / hierarchy / modlist 三段。"""
    parts, current = {}, None
    for line in (text or "").splitlines():
        marker = line.strip()
        if marker.startswith("--- URG_REPORT:") and marker.endswith("---"):
            current = marker[len("--- URG_REPORT:"):-len("---")].strip()
            parts.setdefault(current, [])
            continue
        if current:
            parts[current].append(line)
    return {key: "\n".join(value) for key, value in parts.items()}


def _hierarchy_rows(text):
    """层次报告里的一行：缩进 + SCORE LINE COND TOGGLE FSM + 实例名。"""
    rows = []
    for line in (text or "").splitlines():
        indent = len(line) - len(line.lstrip())
        tokens = line.split()
        if len(tokens) != 6:
            continue
        scores = _score_row(tokens[:5])
        if not scores:
            continue
        rows.append({"indent": indent, "name": tokens[5], "scores": scores})
    return rows


def _has_metric(scores):
    return any(isinstance(value, (int, float)) for value in (scores or {}).values())


def _pick_dut_rows(rows, subject):
    """取 DUT 实例那一行。

    层次报告给的是实例名，实例名不一定等于模块名，所以先按名字精确找；
    找不到就取 TB 顶层下面第一层实例 —— 那些就是 DUT 与它的接口实例。
    """
    if not rows:
        return []
    exact = [row for row in rows if subject and row["name"] == subject]
    if exact:
        least = min(row["indent"] for row in exact)
        return [row for row in exact if row["indent"] == least]
    top = min(row["indent"] for row in rows)
    deeper = sorted({row["indent"] for row in rows if row["indent"] > top})
    if not deeper:
        return []
    return [row for row in rows if row["indent"] == deeper[0]]


def _parse_coverage(text):
    sections = _urg_sections(text)
    matched = re.search(r"COV_DUT:\s*(\S+)", text)
    subject = matched.group(1) if matched else None
    # 先看层次报告里 DUT 实例那一行（它已经汇总理面各模块）。
    if "hierarchy" in sections:
        picked = _pick_dut_rows(_hierarchy_rows(sections["hierarchy"]), subject)
        scores = _worst([row["scores"] for row in picked])
        if _has_metric(scores):
            return scores
    # 没有层次报告（或那一行没有数值）时退回 modlist：优先 DUT 行，否则逐项取最差。
    body = sections.get("modlist", text)
    skip = re.compile(r"(?:_sim_top|_if)$|^tb_", re.I)
    rows = []
    for row in re.finditer(r"^\s*((?:\S+\s+){3,4}\S+)\s+([A-Za-z_][\w$]*)\s*$", body, re.M):
        name = row.group(2)
        scores = _score_row(row.group(1).split())
        if not scores or skip.search(name):
            continue
        rows.append((name, scores))
    if subject:
        for name, scores in rows:
            if name == subject or name.startswith(subject):
                return scores
    if rows:
        return _worst([scores for _name, scores in rows])
    dashboard = {}
    head = sections.get("dashboard", text)
    header = re.search(r"LINE\s+COND(?:ITION)?\s+TOGGLE\s+FSM\s*\n\s*((?:\S+\s+){3,4}\S+)", head)
    if header:
        scores = _score_row(header.group(1).split())
        if scores:
            dashboard = scores
    if not dashboard:
        found = {}
        for key, label in (("line", "LINE"), ("cond", "COND"), ("fsm", "FSM"), ("tgl", "TGL")):
            value = re.search(r"%s\s+(\d+(?:\.\d+)?)" % label, head)
            if value:
                found[key] = float(value.group(1))
        if len(found) == 4:
            dashboard = found
    return dashboard


def _num(text, pattern):
    import re
    match = re.search(pattern, text)
    if not match:
        return None
    return float(match.group(1))


def _parse_synth(text):
    import re
    area = _num(text, r"Design Area:\s+(-?\d+(?:\.\d+)?)")
    if area is None:
        area = _num(text, r"Total cell area:\s+(-?\d+(?:\.\d+)?)")
    wns = _num(text, r"Design\s+WNS:\s+(-?\d+(?:\.\d+)?)")
    viol = _num(text, r"Design\s+WNS:.*?Number of Violating Paths:\s+(\d+)")
    # 时钟与 latch 都取自 adf_checks.rpt 的正文（文件内容不会被命令回显污染）。
    clocks = _num(text, r"Clock Count:\s*(\d+)")
    latches = _num(text, r"Latch Count:\s*(\d+)")
    if latches is None:
        latches = _num(text, r"Number of latch(?:es)?\s*[:=]\s*(\d+)")
    if latches is None:
        inferred = len(re.findall(r"(?i)latch(?:es)?\s+(?:inferred|is inferred)", text))
        if inferred:
            latches = float(inferred)
    errors = 1.0 if re_error(text) else 0.0
    checks = {}
    if clocks is not None and int(clocks) == 0:
        checks["no_clock"] = 1
    if area is not None:
        checks["area"] = area
    if wns is not None:
        checks["setup_wns"] = wns
    if viol is not None:
        checks["setup_violations"] = int(viol)
    if latches is not None:
        checks["latches"] = int(latches)
    if area is not None and wns is not None:
        checks["errors"] = int(errors)
    return checks


def re_error(text):
    import re
    return re.search(r"(?m)^Error:", text) is not None


def _split_sections(text):
    """按驱动的分隔标记切出 setup / hold / qor 三段。"""
    parts = {}
    current = None
    for line in text.splitlines():
        marker = line.strip()
        if marker.startswith("--- PT_REPORT:") and marker.endswith("---"):
            current = marker[len("--- PT_REPORT:"):-len("---")].strip()
            parts.setdefault(current, [])
            continue
        if current:
            parts[current].append(line)
    return {key: "\n".join(value) for key, value in parts.items()}


def _split_by_delay(text):
    """没有标记时按 report_timing 头部里的 delay_type 切段。"""
    import re
    setup, hold = [], []
    for part in re.split(r"(?m)^(?=\s*Report\s*:\s*timing\b)", text):
        matched = re.search(r"-delay_type\s+(\w+)", part[:400])
        if not matched:
            continue
        (setup if matched.group(1) == "max" else hold).append(part)
    return "\n".join(setup), "\n".join(hold)


def _timing_section(text):
    """一段时序报告：最差 slack 与违例条数；无约束路径单独标出。"""
    import re
    if not (text or "").strip():
        return None
    if "No constrained paths" in text:
        return {"wns": None, "violations": 0, "unconstrained": True}
    slacks = [float(value) for value in
              re.findall(r"slack\s*\((?:MET|VIOLATED)\)\s*(-?\d+(?:\.\d+)?)", text, re.I)]
    if slacks:
        violations = len(re.findall(r"slack\s*\(VIOLATED\)", text, re.I))
        return {"wns": min(slacks), "violations": violations, "unconstrained": False}
    # 「没有 slack 小于 X 的路径」= 有约束、零违例；最差 slack 只在 X 以上，
    # 取 X 当保守下界并标出来，不算编造。
    floor = re.search(r"No paths with slack less than\s*(-?\d+(?:\.\d+)?)", text)
    if floor:
        return {"wns": float(floor.group(1)), "violations": 0, "unconstrained": False,
                "bound": True}
    return None


QOR_GROUP = re.compile(
    r"Timing Path Group\s+'?([^'\n(]+?)'?\s*\((max_delay|min_delay)/(setup|hold)\)(.*?)"
    r"(?=Timing Path Group|\Z)", re.S)
QOR_SLACK = re.compile(r"Critical Path Slack:\s*(-?\d+(?:\.\d+)?)")
QOR_VIOL = re.compile(r"No\. of Violating Paths:\s*(\d+)")


def _qor_groups(text):
    """从 qor 报告按路径组取最差 slack 与违例条数（工具自己的汇总）。
    多个时钟组时 slack 取最差、违例条数相加，不能让后一个组盖掉前一个。"""
    setup = hold = None
    for matched in QOR_GROUP.finditer(text or ""):
        body = matched.group(4)
        slack = QOR_SLACK.search(body)
        violations = QOR_VIOL.search(body)
        if slack is None or violations is None:
            continue
        item = {"wns": float(slack.group(1)), "violations": int(violations.group(1)),
                "unconstrained": False}
        prev = setup if matched.group(2) == "max_delay" else hold
        if prev is not None:
            item = {"wns": min(prev["wns"], item["wns"]),
                    "violations": prev["violations"] + item["violations"],
                    "unconstrained": False}
        if matched.group(2) == "max_delay":
            setup = item
        else:
            hold = item
    return setup, hold


UNCONSTRAINED_COUNT = re.compile(
    r"There\s+(?:are|is)\s+(\d+)\s+end-?points?\s+(?:which|that)\s+(?:are|is)\s+not\s+constrained", re.I)
UNCONSTRAINED_LIST = re.compile(r"end-?points?\s+(?:are|is)\s+not\s+constrained", re.I)


def _unconstrained_endpoints(text):
    """check_timing 报的未约束端点数。按计数句取；只有列表句时至少记 1。"""
    counts = [int(value) for value in UNCONSTRAINED_COUNT.findall(text or "")]
    if counts:
        return sum(counts)
    return 1 if UNCONSTRAINED_LIST.search(text or "") else 0


def _parse_sta(text):
    sections = _split_sections(text)
    if sections:
        setup_text = sections.get("setup", "")
        hold_text = sections.get("hold", "")
        qor_text = sections.get("qor", "")
        check_text = sections.get("check", "")
    else:
        setup_text, hold_text = _split_by_delay(text)
        qor_text = text
        check_text = text
    checks = {}
    if re_error(text):
        checks["tool_error"] = 1
    loose = _unconstrained_endpoints(check_text)
    if loose:
        checks["unconstrained_endpoints"] = loose
    report_setup = _timing_section(setup_text)
    report_hold = _timing_section(hold_text)
    setup, hold = _qor_groups(qor_text)
    if setup is None:
        setup = report_setup
    if hold is None:
        hold = report_hold
    if ((setup and setup["unconstrained"]) or (hold and hold["unconstrained"])
            or (report_setup and report_setup["unconstrained"])
            or (report_hold and report_hold["unconstrained"])):
        checks["unconstrained"] = 1
    if setup and hold and not setup["unconstrained"] and not hold["unconstrained"]:
        corner = {
            "setup_wns": setup["wns"],
            "hold_wns": hold["wns"],
            "setup_violations": setup["violations"],
            "hold_violations": hold["violations"],
        }
        if setup.get("bound") or hold.get("bound"):
            corner["wns_is_bound"] = 1
        checks["corners"] = [corner]
    return checks
