# 作者：vick 邮箱：ykun@yk9811.com

"""停点闸门的唯一入口。advance 与 gate 都调用这里。

一次进程内按（停点号, state 内容摘要, 相关磁盘输入的 mtime 集合）备忘：同一条
命令里 advance / tick / 简报渲染会把同一份 state 的闸门反复跑好几遍（实测一次
tick 15 次、一次写命令 6 次），这里同一份（state, 磁盘输入）只跑一遍。
磁盘输入取闸门与运行摘要真正会读的东西——子系统目录整棵树、子系统外的
tb_common 与 pub_code、运行记录里的 SDC/网表路径，外加 flow_model.yaml；
任一 mtime/大小变化即重跑，不靠"闸门都读同一批文件"的假设。
"""

import collections
import copy
import hashlib
import json
import os

from framework import flow
from framework.flow import DONE, PENDING, load, milestone_done_stops, product_path
from framework.gates.docs import scan_docs
from framework.gates.numeric import scan_tree
from framework.gates.rtl import scan_conn, scan_rtl
from framework.gates.specconn import scan_cdc_conn
from framework.gates.specconn import scan_clock_domains, scan_notes
from framework.gates.specconn import scan_tree as scan_spec_conn
from framework.gates.tc import platform_names, scan_tc
from framework.state import stop_row, sys_dir

# 闸门备忘：key -> 深拷贝后的 findings。上限兜住长时间 selftest 里不断新增的
# 副本仓库路径（每个 RepoTest 类是独立根目录）。
_GATE_CACHE = collections.OrderedDict()
_GATE_CACHE_MAX = 256

# 带违例送审时给失败运行记录打的备注（写在 state 的 runs 里，随事务落库）。
_ALLOW_VIOLATION_NOTE = "有违例仍提交审核"


def run_gates(root, name, stop_id, state, allow_violation=False):
    key = _gate_cache_key(root, name, stop_id, state, allow_violation)
    if key is not None:
        hit = _GATE_CACHE.get(key)
        if hit is not None:
            _GATE_CACHE.move_to_end(key)
            # 命中也要补上闸门对 state 的写入（带违例送审的运行记录备注），
            # 否则同一条命令里第二次调用不再往 state 里写备注，落库内容就变了。
            _note_allow_violation(state, stop_id, allow_violation)
            return copy.deepcopy(hit)
    findings = _run_gates(root, name, stop_id, state, allow_violation)
    if key is not None:
        _GATE_CACHE[key] = copy.deepcopy(findings)
        _GATE_CACHE.move_to_end(key)
        while len(_GATE_CACHE) > _GATE_CACHE_MAX:
            _GATE_CACHE.popitem(last=False)
    return findings


def _gate_cache_key(root, name, stop_id, state, allow_violation):
    """备忘键；算不出（stop 号不是整数、state 不是 JSON 数据）时返回 None（不备忘）。"""
    try:
        sid = int(stop_id)
    except (TypeError, ValueError):
        return None
    digest = _state_digest(state)
    if digest is None:
        return None
    return (os.path.abspath(root), name, sid, bool(allow_violation), digest,
            flow.model_stamp(), _tree_stamp(sys_dir(root, name)), _root_input_stamp(root, state))


def _state_digest(state):
    """state 的内容摘要。旧 state 每次都重算闸门，所以判据里凡是读 state 的字段
    （runs/waivers/decisions/problems/items/modules/stops）都必须进这个摘要。"""
    try:
        text = json.dumps(state, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return None  # 序列化不了就不备忘，宁可慢也不能读旧结果
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _stamp(path):
    """(mtime_ns, size)；路径不存在（含走查途中刚被删掉）时 None。"""
    if not os.path.exists(path):
        return None
    st = os.stat(path)
    return (st.st_mtime_ns, st.st_size)


def _tree_stamp(base):
    """目录树的（相对路径, mtime_ns, 大小）摘要：只 stat，不读文件内容。

    目录本身与子目录的 mtime 也收：文件删掉、空目录出现这类变化同样会让闸门
    结果变（例如 rtl/ 下没有模块文件的判定）。
    """
    if not os.path.isdir(base):
        return "-"
    base_hit = _stamp(base)
    if base_hit is None:
        return "-"
    parts = [".|%d" % base_hit[0]]
    for dirpath, dirnames, files in os.walk(base):
        dirnames[:] = sorted(dirnames)
        for fn in dirnames:
            path = os.path.join(dirpath, fn)
            hit = _stamp(path)
            if hit is None:
                continue
            parts.append("%s|%d" % (os.path.relpath(path, base), hit[0]))
        for fn in sorted(files):
            path = os.path.join(dirpath, fn)
            hit = _stamp(path)
            if hit is None:
                continue
            parts.append("%s|%d|%d" % (os.path.relpath(path, base), hit[0], hit[1]))
    return hashlib.sha1("\n".join(parts).encode("utf-8")).hexdigest()[:16]


def _file_stamp(path):
    """单个文件的（绝对路径, mtime_ns, 大小）；缺失记 "|-"（出现/消失都要让键变）。"""
    full = os.path.abspath(path)
    hit = _stamp(full)
    if hit is None:
        return "%s|-" % full
    return "%s|%d|%d" % (full, hit[0], hit[1])


def _root_input_stamp(root, state):
    """子系统目录之外、闸门仍会读的输入：tb_common、pub_code 与运行记录里的 SDC/网表。

    _fresh 走 inputs_digest，这些文件在子系统目录之外；漏收一处就会把陈旧判成新鲜。
    SDC 路径按原样与相对 root 两种解释各收一次（记录里两种写法都出现过）。
    """
    parts = [_tree_stamp(os.path.join(root, "tb_common")),
             _tree_stamp(os.path.join(root, "pub_code"))]
    for run in state.get("runs") or []:
        scope = run.get("scope") or {}
        paths = list(run.get("sdc_paths") or [])
        if scope.get("netlist"):
            paths.append(scope["netlist"])
        for raw in paths:
            if not raw:
                continue
            for candidate in sorted({raw, os.path.join(root, raw)}):
                parts.append(_file_stamp(candidate))
    return hashlib.sha1("\n".join(parts).encode("utf-8")).hexdigest()[:16]


def _note_allow_violation(state, stop_id, allow_violation):
    """带违例送审：把失败的综合/时序运行记录标一句，state 落库时带着它。"""
    if not allow_violation:
        return
    stop = load()["by_id"].get(int(stop_id)) or {}
    gates = stop.get("gates") or []
    for cap in ("synth", "sta"):
        if cap not in gates:
            continue
        run = _latest(state, cap)
        if run and run.get("status") == "fail":
            run["note"] = _ALLOW_VIOLATION_NOTE


def _run_gates(root, name, stop_id, state, allow_violation=False):
    model = load()
    stop = model["by_id"].get(int(stop_id))
    if stop is None:
        return [_finding("stop", "", "没有停点 %s" % stop_id)]
    gates = stop.get("gates") or []
    base = sys_dir(root, name)
    findings = []
    if "numeric" in gates:
        findings.extend(scan_tree(base))
    if "docs" in gates:
        rel = product_path(stop, name)
        if rel.endswith(".md") and not os.path.isfile(os.path.join(base, rel)):
            findings.append(_finding("docs", rel, "缺少产出 %s" % rel))
        findings.extend(scan_docs(base, stop["id"], state))
        findings.extend(scan_spec_conn(base))
        findings.extend(scan_notes(base, state))
    if "rtl" in gates:
        findings.extend(scan_rtl(base))
        findings.extend(_rtl_module_findings(state, base))
    if "conn" in gates:
        findings.extend(scan_conn(base, name))
        # 连接表跨时钟域：两端域不同要经已登记跨域单元或引用有效裁决号（CD1）。
        findings.extend(scan_cdc_conn(base, state))
        # 行 8 的通过态由证据推导（顶层文件的 rtl_review 记录 + 连接核对），
        # 不再要求手工登记 modules[8]。
        findings.extend(_cdc_findings(base, state))
    if "tc" in gates:
        findings.extend(scan_tc(base))
        findings.extend(_tc_module_findings(state, base))
    if "lint" in gates:
        findings.extend(_lint_findings(root, name, state))
    if "sim" in gates:
        findings.extend(_sim_findings(root, name, state))
        # 行 10 的参考数据要已登记且新鲜（挂点在 sim：行 10 的闸门是 sim+coverage）。
        findings.extend(_golden_findings(root, name, state))
        findings.extend(_lec_hint_findings(state))
    if "coverage" in gates:
        findings.extend(_coverage_findings(root, name, state))
    if "synth" in gates or "sta" in gates:
        for cap in ("synth", "sta"):
            if cap not in gates:
                continue
            run = _latest(state, cap)
            if not run:
                findings.append(_finding("run", cap, "行 11 缺少 %s 运行记录" % cap))
            elif run.get("status") == "pass":
                if not _fresh(root, name, run):
                    findings.append(_finding("run", cap, "输入已变更，需重跑"))
                findings.extend(_output_findings(root, name, run))
                loose = int((run.get("checks") or {}).get("unconstrained_endpoints") or 0)
                if cap == "sta" and loose:
                    findings.append(_finding(
                        "sta-unconstrained", "sta",
                        "时序检查报 %d 个端点未约束；补约束后重跑，或经人确认登记豁免" % loose))
            elif allow_violation and run.get("status") == "fail":
                run["note"] = _ALLOW_VIOLATION_NOTE
            else:
                findings.append(_finding(
                    "run", cap,
                    "行 11 的 %s 未通过；有违例仍要送审时加 --allow-violation%s" % (cap, _diag_suffix(run)),
                ))
    if "signoff" in gates:
        # 签核停点的前置停点：遍历它自己的 depends_on（不写死行 11）。每个前置停点
        # 要么已完成，要么属"由里程碑完成"（动作表 stop_done_milestone）且已送审待
        # M3 确认——否则行 11 只能由 M3 置完成、而 M3 又要求签核停点先送审，两边互等。
        milestone_stops = milestone_done_stops()
        bad = []
        for dep in flow.depends_on(stop["id"]):
            row = stop_row(state, dep)
            if row["state"] == DONE:
                continue
            if row["state"] == PENDING and dep in milestone_stops:
                continue
            bad.append(dep)
        if bad:
            findings.append(_finding(
                "signoff", ",".join(str(dep) for dep in bad),
                "行 %s 要求前置停点 %s 已完成（或已送审待里程碑确认）"
                % (stop["id"], "、".join("行 %d" % dep for dep in bad))))
    if stop["id"] >= 6:
        findings.extend(_trace_findings(base, state))
    findings = _without_waivers(findings, state)
    # 已确认产物被改动不走豁免：唯一出路是退回该停点重新送审。
    from framework.engine import stale_message, stale_stops
    stale = stale_stops(root, name, state, skip=stop["id"])
    if stale:
        findings.append(_finding("fingerprint", ",".join(str(sid) for sid in stale),
                                 stale_message(name, stale)))
    return findings


def _without_waivers(findings, state):
    known = set()
    for rows in (state.get("decisions") or {}).values():
        for row in rows:
            # 撤回的裁决只标 withdrawn、不再从表里删掉——豁免引用的裁决必须**有效**。
            if not row.get("withdrawn"):
                known.add(row.get("id"))
    kept = []
    for item in findings:
        if any(w.get("rule") == item.get("rule") and w.get("where") == item.get("where")
               and w.get("decision") in known for w in state.get("waivers") or []):
            continue
        kept.append(item)
    return kept


def _trace_findings(base, state):
    """TR1：输入要点的测试要点追溯缺口（行 6 起检查）。

    口径：矩阵逐条看「来源」列能否把输入要点接到测试要点。强约束输入要点没有
    任何测试要点追溯 → 阻断；权威/参考档只提示（level=hint），不影响自动完成。
    追溯读不动文档时不在这里报错——缺产物与章节问题由 docs 闸门负责。
    """
    from framework.trace import trace_matrix
    try:
        result = trace_matrix(base, state)
    except Exception:  # 提示性检查：文档读不动时由 docs 闸门报，不让整个闸门炸掉
        return []
    findings = []
    for item in result.get("uncovered") or []:
        if item.get("strong"):
            findings.append({
                "rule": "TR1", "where": "行 6",
                "detail": "输入要点 %s（强约束）没有测试要点追溯：补测试要点，"
                          "并在测试要点表的「来源」列写该输入编号或上游模块名"
                          % item.get("input", "?"),
            })
        else:
            findings.append({
                "rule": "TR1", "level": "hint", "where": "行 6",
                "detail": "输入要点 %s（%s）没有测试要点追溯（只提示，不阻断）"
                          % (item.get("input", "?"), item.get("credibility") or "未定级"),
            })
    return findings


def _finding(rule, where, detail):
    return {"rule": rule, "where": where, "detail": detail}


def _latest(state, cap):
    for run in reversed(state.get("runs") or []):
        if run.get("capability") != cap:
            continue
        if cap == "sim":
            # 「最近一次仿真」跳过 scenario 不是 sys 的记录——pubip 变体回归
            # 不得顶掉行 10 的 sys 全量回归，也不得成为覆盖率的绑定对象。
            if (run.get("scope") or {}).get("scenario", "sys") != "sys":
                continue
        return run
    return None


def _fresh(root, name, run):
    from framework.engine import run_inputs_digest
    return run.get("inputs_digest") == run_inputs_digest(root, name, run)


def _output_findings(root, name, run):
    """输出侧证据复核（agreement gate）：日志文件摘要与登记值不一致即结论不可信。

    输入摘要把"改了输入要重跑"咬住；这里把"改了输出"咬住——agent 与开发者
    同一系统用户，事后改 work/ 下的日志可以让陈旧记录装新鲜，运行记录里的
    log_digest 是 record_run 落库时的内容摘要，闸门复算文件比对。旧记录没有
    这个字段则跳过（向后兼容）。
    """
    log_rel = run.get("log") or ""
    digest = run.get("log_digest") or ""
    if not log_rel or not digest:
        return []
    import hashlib
    path = os.path.join(root, log_rel)
    if not os.path.isfile(path):
        return [_finding("run-log", run.get("id") or "",
                         "运行记录 %s 的日志 %s 不存在，结论不可信，需重跑"
                         % (run.get("id") or "", log_rel))]
    with open(path, "rb") as fh:
        actual = hashlib.sha256(fh.read()).hexdigest()
    if actual != digest:
        return [_finding("run-log", run.get("id") or "",
                         "运行记录 %s 的日志 %s 与登记摘要不一致（日志被改动），结论不可信，需重跑"
                         % (run.get("id") or "", log_rel))]
    return []


def _diag_suffix(run):
    """失败信息附首条结构化诊断；没有诊断清单返回空串。"""
    from framework.diagnostics import first_note
    note = first_note(run)
    if not note:
        return ""
    return "；%s（详见运行记录 %s）" % (note, run.get("id") or "")



def _lint_findings(root, name, state):
    run = _latest(state, "lint")
    if not run or run.get("status") != "pass":
        return [_finding("run", "lint",
                         "行 7 需要最近一次 lint 为 pass%s"
                         % (_diag_suffix(run) if run else ""))]
    if not _fresh(root, name, run):
        return [_finding("run", "lint", "输入已变更，需重跑")]
    return _output_findings(root, name, run)


def _lec_hint_findings(state):
    """行 10 的 CEC 提示（hint 级，不阻断）。

    登记了黄金参考数据却从未有过 lec（等价性检查）通过记录时提示：仿真对
    数据负责，等价性对设计负责，两者不互替。需要剖面提供 lec 能力
    （toolchain/profiles 的 tools.lec.available，配远端 yosys）后才能跑：
    `run lec --sys <sys> --module <模块> --gold <黄金 RTL 文件>`。
    """
    if not (state.get("golden") or []):
        return []
    for run in state.get("runs") or []:
        if run.get("capability") == "lec" and run.get("status") == "pass":
            return []
    return [{"rule": "lec", "level": "hint", "where": "行 10",
             "detail": "已登记黄金参考数据但无等价性检查（lec）通过记录；有黄金 RTL"
                       "（参考实现/上一版）时按 run lec --gold <文件> 核对（需要剖面提供"
                       " lec 能力；无则保持提示，不影响自动完成）"}]


def _data_files(base):
    """TB 用到的参考数据文件（`testbench/**/data/**` 下的文件，相对路径）。"""
    root = os.path.join(base, "testbench")
    found = []
    for dirpath, dirnames, files in os.walk(root):
        dirnames[:] = [item for item in dirnames if item != "__pycache__"]
        if os.path.basename(dirpath) != "data":
            continue
        for fn in sorted(files):
            found.append(os.path.relpath(os.path.join(dirpath, fn), base).replace(os.sep, "/"))
    return sorted(found)


def _golden_stale_by(base, record):
    """登记的参考数据"生成脚本或输入改过"的元凶路径；新鲜返回空串。

    不新增字段：登记时间记在 `time`，生成脚本与输入各自的 mtime 比它晚即需重新生成。
    """
    import datetime
    stamp = str(record.get("time") or "")
    try:
        registered = datetime.datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S").timestamp()
    except (ValueError,):
        return ""
    watched = [str(record.get("gen") or "")] + list(record.get("inputs") or [])
    for rel in watched:
        path = os.path.join(base, rel)
        # 登记时间是秒粒度，mtime 是纳秒：同一秒内刚落盘的脚本不算"改过"，
        # 因此留 1 秒余量，只有确实晚于登记时刻的改动才判需重新生成。
        if rel and os.path.exists(path) and os.path.getmtime(path) > registered + 1.0:
            return rel
    return ""


def _golden_findings(root, name, state):
    """行 10：参考数据必须已登记且新鲜。

    - 被 TB 用到的数据文件（`testbench/**/data/**`）都要有 golden 登记记录，
      否则旧黄金数据会被当作有效期望；
    - 已登记的数据若"生成脚本或输入在登记之后改过"，报需重新生成。
    """
    base = sys_dir(root, name)
    registered = {row.get("data"): row for row in (state.get("golden") or [])}
    findings = []
    for rel in _data_files(base):
        record = registered.get(rel)
        if record is None:
            findings.append(_finding(
                "golden", rel,
                "参考数据未登记：用 golden %s register --data %s --gen <生成脚本> "
                "--inputs <输入…> 登记生成器" % (name, rel)))
            continue
        stale = _golden_stale_by(base, record)
        if stale:
            findings.append(_finding(
                "golden", rel,
                "参考数据需重新生成：%s 在登记（%s）之后改过" % (stale, record.get("time", ""))))
    return findings


def _sim_findings(root, name, state):
    run = _latest(state, "sim")
    if not run or run.get("status") != "pass":
        return [_finding("run", "sim",
                         "行 10 需要最近一次仿真 pass%s" % (_diag_suffix(run) if run else ""))]
    if not _fresh(root, name, run):
        return [_finding("run", "sim", "输入已变更，需重跑")]
    output_bad = _output_findings(root, name, run)
    if output_bad:
        return output_bad
    scope = run.get("scope") or {}
    if scope.get("scenario") != "sys" or scope.get("tc"):
        return [_finding("run", "sim", "行 10 只认 scenario=sys 且不带 --tc 的全量回归")]
    checks = run.get("checks") or {}
    if not checks.get("full_regression"):
        observed = checks.get("observed_cases")
        if observed is None:
            # 记录里没写用例数时说清楚，别只显示一个问号。
            got = "记录里没有用例数"
        else:
            got = "%s=%s" % ("用例数" if checks.get("cases_source") == "cases" else "RESULT 条数",
                             observed)
        return [_finding(
            "run", "sim",
            "行 10 的用例覆盖数与 tc_all 枚举用例数 × seed 数不符"
            "（期望 %s，实得 %s；PASS %s / FAIL %s）"
            % (checks.get("expected_results", "?"), got,
               checks.get("result_pass", "?"), checks.get("result_fail", "?")),
        )]
    return []


def _coverage_findings(root, name, state):
    run = _latest(state, "coverage")
    if not run or run.get("status") != "pass":
        return [_finding("run", "coverage", "行 10 需要覆盖率 pass")]
    if not _fresh(root, name, run):
        return [_finding("run", "coverage", "输入已变更，需重跑")]
    output_bad = _output_findings(root, name, run)
    if output_bad:
        return output_bad
    # 覆盖率记录的 vdb 来自某一次仿真，必须就是行 10 认可的那一次全量回归，
    # 且那次仿真仍然新鲜、覆盖率是在它之后跑的。
    sim = _latest(state, "sim")
    if not sim:
        return [_finding("run", "coverage", "还没有可依据的仿真记录，先跑全量回归再跑覆盖率")]
    bound = (run.get("scope") or {}).get("based_on_sim") or ""
    if not bound:
        return [_finding("run", "coverage", "覆盖率记录没有绑定仿真记录号，重跑 run coverage")]
    if bound != sim.get("id"):
        return [_finding("run", "coverage",
                         "覆盖率记录依据的是仿真 %s，最近一次仿真已是 %s，需重跑覆盖率"
                         % (bound, sim.get("id")))]
    if not _fresh(root, name, sim):
        return [_finding("run", "coverage",
                         "覆盖率依据的仿真 %s 输入已变更，需重跑仿真与覆盖率" % bound)]
    return []


def _cdc_findings(base, state):
    """行 8：端口表出现两个以上时钟域时，要一条 cdc 通过记录或点选入库的裁决豁免。

    本机与远端都没有 CDC 工具许可（剖面 cdc 能力位 available: false），闸门只认
    证据或豁免，不自动跑工具。豁免不在这里判：阻断项用固定的 (rule, where) 交给
    末尾的 _without_waivers 收割。
    """
    domains = scan_clock_domains(base)
    if len(domains) < 2:
        return []
    run = _latest(state, "cdc")
    if run and run.get("status") == "pass":
        return []
    if run:
        note = "最近一条 cdc 运行记录是 %s，不是 pass" % run.get("status")
    else:
        note = "没有 cdc 运行记录"
    return [_finding(
        "cdc", "行 8",
        "端口表出现 %d 个时钟域（%s）；%s。需要一条 cdc 通过记录，"
        "或引用点选入库的裁决登记豁免" % (len(domains), "、".join(domains), note))]


def _rtl_names(base):
    rtl = os.path.join(base, "rtl")
    if not os.path.isdir(rtl):
        return []
    names = []
    for fn in sorted(os.listdir(rtl)):
        if fn.endswith(("_top.sv", "_top.v")):
            continue
        if fn.endswith((".sv", ".v")):
            names.append(fn.rsplit(".", 1)[0])
    return names


def _rtl_module_findings(state, base):
    """行 7 逐模块判据（模块清单由文件推导，状态由证据推导）。

    - 模块清单 = rtl/ 下的非顶层 HDL 文件（模块清单由文件推导，没有"未登记的模块"这一说）；
    - 每个模块都要有对当前文件的 lint 通过记录；
    - 有过 rtl_review 记录但摘要对不上当前文件的模块，报"文件已改动，需重新审查"；
    - 显式"退回"的模块报缺证据。
    """
    from framework.engine import _lint_ok, _module_entry, module_digest
    names = _rtl_names(base)
    if not names:
        return [_finding("mod", "行 7", "rtl/ 下没有模块文件")]
    missing, edited = [], []
    for mod in names:
        entry = _module_entry(state, "7", mod) or {}
        has_review = entry.get("kind") == "rtl_review"
        if entry.get("state") == "退回":
            missing.append(mod)
            continue
        if has_review and entry.get("digest") != module_digest(base, mod):
            edited.append(mod)
        elif not _lint_ok(state, mod, base):
            missing.append(mod)
    findings = []
    if missing:
        findings.append(_finding("mod", "行 7", "行 7 缺 lint 记录（或记录早于当前文件）：%s"
                                 % "、".join(missing)))
    if edited:
        findings.append(_finding("mod", "行 7", "行 7 审查通过后文件已改动，需重新 lint 与审查：%s"
                                 % "、".join(edited)))
    return findings


def _tc_module_findings(state, base):
    """行 9 的 TB 平台是否完成（平台清单由 testbench/ 推导，状态由用例核对推导）。

    不再接受手工登记的"骨架即合格"：骨架里还有"骨架未填写"标记（T6），
    用例并没有真正装配；装配对不上只算"用例已装配"，三方一致才"tc_check 通过"。
    """
    from framework.gates.tc import platform_state
    names = platform_names(base)
    if not names:
        return [_finding("mod", "行 9", "没有 testbench/<dut>/tc 平台")]
    bad = [mod for mod in names if platform_state(base, mod) != "tc_check 通过"]
    if bad:
        return [_finding("mod", "行 9", "行 9 平台未完成：%s" % "、".join(bad))]
    return []
