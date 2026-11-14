"""DC 综合 / PT STA（作业化）。

TCL 模板**按框架 profile driver 移植**（上游旧脚本 `dc_flow.sh` / `pt_flow.sh` 不在本仓库；改一处必须同步另一处）：

* DC：``read_file -format sverilog`` 逐文件 → ``current_design`` → ``link`` →
  ``check_design`` → ``read_sdc`` → ``compile_ultra`` → ``report_*`` → ``write``
* PT：``read_verilog <netlist>`` → ``link_design`` → ``read_sdc`` →
  ``update_timing -full`` → ``report_timing``（setup/hold）

**判定一律读报告，不看退出码**：``dc.log``/``pt.log`` 有 ``^Error`` → 运行错误；
``slack (VIOLATED)`` → 时序违例。两工具都需 ``< /dev/null``（会吞 heredoc 剩余行）。
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from .config import Config
from .jobs import Job, JobManager
from .workspace import WorkspaceError, guard_path

__all__ = [
    "SynError",
    "LIB_CHOICES",
    "render_dc_tcl",
    "render_pt_tcl",
    "submit_syn",
    "submit_sta",
    "report_verdict",
]

LIB_CHOICES = {
    "std": ("STD", "yourtech_tt.db"),
    "stdht": ("STDHT", "yourtechHT_tt.db"),
}
TECH_ROOT = "/opt/synopsys/tech_lib/yourtech"


class SynError(RuntimeError):
    pass


def _root(cfg: Config) -> str:
    root = cfg.path("eda.workspace_root")
    if not root or not os.path.isdir(root):
        raise WorkspaceError("未配置/不存在 eda.workspace_root")
    return os.path.abspath(root)


def _positions(cfg: Config, target: str, top: Optional[str]) -> Dict[str, str]:
    """归属目录 → (顶层名, RTL 目录, dc 目录, pt 目录)。"""
    root = _root(cfg)
    if target == "pub_code":
        rtl = os.path.join(root, "pub_code")
        if not top:
            raise SynError("归属为 pub_code 时必须给 top（单模块综合冒烟）")
        name = top
        pos = os.path.join(root, "pub_code")
    else:
        rtl = os.path.join(root, target, "rtl")
        name = top or ("%s_top" % target)
        pos = os.path.join(root, target)
    return {
        "root": root,
        "top": name,
        "rtl": rtl,
        "pos": pos,
        "dc": os.path.join(pos, "dc"),
        "pt": os.path.join(pos, "pt"),
    }


def _rtl_files(rtl_dir: str) -> List[str]:
    if not os.path.isdir(rtl_dir):
        raise SynError("RTL 目录不存在: %s" % rtl_dir)
    out = []
    for fn in sorted(os.listdir(rtl_dir)):
        if fn.endswith((".v", ".sv")):
            out.append(os.path.join(rtl_dir, fn))
    if not out:
        raise SynError("RTL 目录里没有 .v/.sv: %s" % rtl_dir)
    return out


# ------------------------------------------------------------------ TCL 生成


def render_dc_tcl(
    top: str, rtl_files: List[str], lib: str = "std", sdc: Optional[str] = None
) -> str:
    libdir, dbfile = LIB_CHOICES.get(lib, LIB_CHOICES["std"])
    lines = [
        "#=========== %s_syn.tcl（由 eda-mcp 生成，模板依据框架 profile driver）============" % top,
        "#----------- 工艺库（read_lib）------------",
        "set search_path  [list . %s/%s/Synopsys]" % (TECH_ROOT, libdir),
        "set target_library %s" % dbfile,
        "set link_library [list * $target_library]",
        "#----------- 设计读入（read_design：逐文件，统一按 sverilog 解析）------------",
    ]
    for f in rtl_files:
        lines.append("read_file -format sverilog %s" % f)
    lines += [
        "current_design %s" % top,
        "link",
        "#----------- 结构检查（compile 前）------------",
        "check_design > check_design.rpt",
        "#----------- 时序约束（constraints）------------",
        ("read_sdc %s" % sdc) if sdc else "# （无 SDC：无时钟约束冒烟）",
        "#----------- 综合（compile）------------",
        "compile_ultra",
        "#----------- 报告（report）------------",
        "report_area   > %s_syn_area.rpt" % top,
        "report_qor    > %s_syn_qor.rpt" % top,
        "report_timing -max_paths 10 > %s_syn_timing.rpt" % top,
        "#----------- 产出（write）------------",
        "write -format ddc     -output %s_syn.ddc" % top,
        "write -format verilog -output %s_syn.v" % top,
        "write_sdc             %s_syn.sdc" % top,
        "exit",
    ]
    return "\n".join(lines) + "\n"


def render_pt_tcl(top: str, netlist: str, sdc: str, corner: str = "tt") -> str:
    return "\n".join([
        "#=========== %s_sta.tcl（由 eda-mcp 生成，模板依据框架 profile driver）============" % top,
        "#----------- 工艺库（read_lib）------------",
        "set search_path [list . %s/STD/Synopsys]" % TECH_ROOT,
        "set link_path   [list * yourtech_%s.db]" % corner,
        "#----------- 网表读入（read_verilog）------------",
        "read_verilog %s" % netlist,
        "link_design %s" % top,
        "#----------- 约束（read_sdc）------------",
        "read_sdc %s" % sdc,
        "#----------- 时序分析（report）------------",
        "update_timing -full",
        "report_timing -delay_type max -max_paths 10 -slack_lesser_than 1000000 > %s_sta_setup.rpt" % top,
        "report_timing -delay_type min -max_paths 10 -slack_lesser_than 1000000 > %s_sta_hold.rpt" % top,
        "report_qor > %s_sta_qor.rpt" % top,
        "exit",
    ]) + "\n"


# ------------------------------------------------------------------ 提交


def _write(path: str, text: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(text)
    return path


def submit_syn(
    cfg: Config,
    target: str,
    top: Optional[str] = None,
    lib: str = "std",
    sdc: Optional[str] = None,
    tcl: Optional[str] = None,
    wall_timeout_s: int = 3600,
) -> Job:
    p = _positions(cfg, target, top)
    rtl_files = _rtl_files(p["rtl"])
    os.makedirs(p["dc"], exist_ok=True)

    sdc_abs = None
    if sdc:
        sdc_abs = guard_path(cfg, sdc if os.path.isabs(sdc) else os.path.join(p["root"], sdc), True)
    else:
        default = os.path.join(p["dc"], "constraints.sdc")
        if os.path.isfile(default):
            sdc_abs = default

    if tcl:
        tcl_abs = guard_path(cfg, tcl if os.path.isabs(tcl) else os.path.join(p["root"], tcl), True)
        tcl_name = os.path.basename(tcl_abs)
    else:
        tcl_name = "%s_syn.tcl" % p["top"]
        tcl_abs = _write(os.path.join(p["dc"], tcl_name),
                         render_dc_tcl(p["top"], rtl_files, lib=lib, sdc=sdc_abs))

    dc_bin = cfg.which("eda.dc_bin") or "dc_shell"
    cmd = "timeout %d %s -f %s -output_log_file dc.log < /dev/null; echo '（判定读报告，不看退出码）'" % (
        int(wall_timeout_s), dc_bin, os.path.basename(tcl_abs))
    jm = JobManager(cfg)
    job = jm.submit(
        "syn_run", cmd, cwd=p["dc"],
        extra={"step": "syn", "top": p["top"], "target": target, "lib": lib,
               "tcl": tcl_abs, "sdc": sdc_abs, "rtl_files": rtl_files},
    )
    # 报告路径一并记入作业元信息，便于 job_status 直接给出
    job.extra["reports"] = {
        "log": os.path.join(p["dc"], "dc.log"),
        "timing": os.path.join(p["dc"], "%s_syn_timing.rpt" % p["top"]),
        "qor": os.path.join(p["dc"], "%s_syn_qor.rpt" % p["top"]),
        "area": os.path.join(p["dc"], "%s_syn_area.rpt" % p["top"]),
        "netlist": os.path.join(p["dc"], "%s_syn.v" % p["top"]),
    }
    jm._save(job)  # noqa: SLF001 - 补写报告路径
    return job


def submit_sta(
    cfg: Config,
    target: str,
    top: Optional[str] = None,
    corner: str = "tt",
    netlist: Optional[str] = None,
    sdc: Optional[str] = None,
    tcl: Optional[str] = None,
    wall_timeout_s: int = 3600,
) -> Job:
    if corner not in ("tt", "ss", "ff"):
        raise SynError("corner 仅支持 tt|ss|ff，收到 %r" % corner)
    p = _positions(cfg, target, top)

    net = netlist or os.path.join(p["dc"], "%s_syn.v" % p["top"])
    net_abs = guard_path(cfg, net if os.path.isabs(net) else os.path.join(p["root"], net))
    if sdc:
        sdc_abs = guard_path(cfg, sdc if os.path.isabs(sdc) else os.path.join(p["root"], sdc))
    else:
        sdc_abs = os.path.join(p["dc"], "%s_syn.sdc" % p["top"])
    if not os.path.isfile(net_abs):
        raise SynError("网表不存在: %s（先运行 syn_run）" % net_abs)
    if not os.path.isfile(sdc_abs):
        raise SynError("SDC 不存在: %s（先运行 syn_run）" % sdc_abs)

    os.makedirs(p["pt"], exist_ok=True)
    if tcl:
        tcl_abs = guard_path(cfg, tcl if os.path.isabs(tcl) else os.path.join(p["root"], tcl), True)
    else:
        tcl_abs = _write(os.path.join(p["pt"], "%s_sta.tcl" % p["top"]),
                         render_pt_tcl(p["top"], net_abs, sdc_abs, corner=corner))

    pt_bin = cfg.which("eda.pt_bin") or "pt_shell"
    cmd = "timeout %d %s -f %s -output_log_file pt.log < /dev/null; echo '（判定读报告，不看退出码）'" % (
        int(wall_timeout_s), pt_bin, os.path.basename(tcl_abs))
    jm = JobManager(cfg)
    job = jm.submit(
        "sta_run", cmd, cwd=p["pt"],
        extra={"step": "sta", "top": p["top"], "target": target, "corner": corner,
               "tcl": tcl_abs, "netlist": net_abs, "sdc": sdc_abs},
    )
    job.extra["reports"] = {
        "log": os.path.join(p["pt"], "pt.log"),
        "setup": os.path.join(p["pt"], "%s_sta_setup.rpt" % p["top"]),
        "hold": os.path.join(p["pt"], "%s_sta_hold.rpt" % p["top"]),
        "qor": os.path.join(p["pt"], "%s_sta_qor.rpt" % p["top"]),
    }
    jm._save(job)  # noqa: SLF001
    return job


# ------------------------------------------------------------------ 判定


def report_verdict(cfg: Config, job_id: str) -> Dict[str, Any]:
    """按 `rules/syn.md` 准出标准读报告判定（**不看退出码**）。"""
    jm = JobManager(cfg)
    job = jm.get(job_id)
    step = job.extra.get("step")
    reports: Dict[str, str] = dict(job.extra.get("reports") or {})
    log_path = reports.get("log") or os.path.join(job.cwd, "dc.log" if step == "syn" else "pt.log")

    errors: List[str] = []
    violations: List[str] = []
    missing: List[str] = []
    warnings: List[str] = []

    try:
        with open(log_path, errors="replace") as fh:
            for line in fh:
                if line.startswith("Error"):
                    errors.append(line.strip())
                    if len(errors) >= 10:
                        break
    except OSError:
        missing.append(log_path)

    check = [reports.get("timing")] if step == "syn" else [reports.get("setup"), reports.get("hold")]
    constrained = False
    for rpt in [r for r in check if r]:
        if not os.path.isfile(rpt):
            missing.append(rpt)
            continue
        with open(rpt, errors="replace") as fh:
            text = fh.read()
        if "No constrained paths" in text:
            # 千万别把「没有受约束路径」当成时序达标——那多半是缺 SDC 时钟约束
            warnings.append("%s: No constrained paths（无受约束路径）" % os.path.basename(rpt))
            continue
        constrained = True
        for line in text.splitlines():
            if "slack (VIOLATED)" in line:
                violations.append("%s: %s" % (os.path.basename(rpt), line.strip()))
                break

    if errors:
        verdict, reason = "FAIL", "运行错误（日志有 Error 行）"
    elif missing:
        verdict, reason = "FAIL", "报告缺失"
    elif violations:
        verdict, reason = "FAIL", "时序违例（slack VIOLATED）"
    elif job.state != "completed":
        verdict, reason = "FAIL", "作业未正常结束（state=%s）" % job.state
    else:
        verdict, reason = "PASS", "达标"
    if verdict == "PASS" and not constrained:
        reason = "达标，但无受约束路径（检查 SDC 是否给了时钟约束）"

    return {
        "job_id": job_id,
        "step": step,
        "state": job.state,
        "rc": job.rc,
        "verdict": verdict,
        "reason": reason,
        "errors": errors,
        "violations": violations,
        "constrained": constrained,
        "warnings": warnings,
        "missing_reports": missing,
        "reports": reports,
        "duration_s": round(job.duration, 1),
    }
