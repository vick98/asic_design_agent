"""VCS 仿真与 nLint 静态检查（作业化）。

命令与框架 `script/framework.py run` 的剖面驱动对齐（上游旧脚本 `run_sim.sh` 不在本仓库；**改一处必须同步**）：

* 编译：``vcs -sverilog -full64 -j 4 -f <.f> <YDIRS> +libext+.v+.sv <opts> -l compile.log``
* 运行：``timeout <wall> ./simv <runargs>``（退出码不可靠，按 log 里 ``RESULT`` 行判定）
* FSDB 档必须带 ``+nolibcell``（否则波形丢 DUT）与完整的 PLI/``-LDFLAGS``

长任务一律走 :mod:`eda_mcp.jobs`，不阻塞 MCP 调用。
"""

from __future__ import annotations

import os
import re
import shlex
from typing import Any, Dict, List, Optional

from .config import Config
from .jobs import Job, JobManager
from .workspace import Scenario, WorkspaceError, resolve_scenario

__all__ = [
    "SimError",
    "compile_command",
    "run_command",
    "submit_sim_compile",
    "submit_sim_run",
    "sim_summary",
    "sim_clean",
    "submit_lint",
    "nlint_result",
]


class SimError(RuntimeError):
    pass


def _verdi_pli(cfg: Config) -> str:
    home = cfg.verdi_home()
    if not home:
        raise SimError("未定位 VERDI_HOME（配置 verdi.verdi_home 或设置环境变量）")
    return os.path.join(home, "share", "PLI", "VCS", "LINUX64")


def compile_command(
    cfg: Config,
    sc: Scenario,
    wave: bool = False,
    wave_vcd: bool = False,
    cov: bool = False,
    defines: Optional[List[str]] = None,
    extra_args: Optional[List[str]] = None,
    jobs: int = 4,
) -> str:
    parts: List[str] = [
        "vcs", "-sverilog", "-full64", "-j", str(int(jobs)),
        "-f", sc.filelist, *sc.ydirs, "+libext+.v+.sv",
    ]
    if wave:
        parts.append("+define+DEBUG_CODE_EN")
        if not wave_vcd:
            pli = _verdi_pli(cfg)
            if not os.path.isfile(os.path.join(pli, "pli.a")):
                raise SimError("FSDB PLI 不存在: %s（或用 wave_vcd=True 退回 VCD）" % pli)
            parts += [
                "+nolibcell",                       # 不加会丢掉 -y 库里的 DUT
                "+define+TB_DUMP_FSDB",
                "-debug_access+all",
                "-P", os.path.join(pli, "novas.tab"),
                os.path.join(pli, "pli.a"),
                "-LDFLAGS", '"-no-pie -Wl,--no-as-needed -fno-lto"',
            ]
    if cov:
        parts += ["+define+TB_COV_EN", "-cm", "line+cond+fsm+tgl"]
    for d in defines or []:
        parts.append(d if d.startswith("+") else "+define+" + d)
    parts += list(extra_args or [])
    parts += ["-l", "compile.log"]
    return " ".join(parts)


def run_command(
    cfg: Config,
    tc: Optional[str] = None,
    seed: Optional[int] = None,
    timeout_us: Optional[int] = None,
    cov: bool = False,
    wall_timeout_s: int = 3600,
    extra_args: Optional[List[str]] = None,
) -> str:
    args: List[str] = []
    if tc:
        args.append("+TC=%s" % tc)
    if timeout_us:
        args.append("+TB_TIMEOUT_US=%d" % int(timeout_us))
    if seed is not None:
        args.append("+SEED=%d" % int(seed))
    if cov:
        args += ["-cm", "line+cond+fsm+tgl"]
    args += list(extra_args or [])
    return "timeout %d ./simv %s 2>&1 | tee sim.log" % (
        int(wall_timeout_s), " ".join(args)
    )


def _submit(
    cfg: Config, sc: Scenario, name: str, cmd: str, extra: Optional[Dict[str, Any]] = None
) -> Job:
    os.makedirs(sc.work, exist_ok=True)
    jm = JobManager(cfg)
    return jm.submit(name, cmd, cwd=sc.work, extra=dict(extra or {}, platform=sc.platform, scenario=sc.kind))


def submit_sim_compile(
    cfg: Config,
    scenario: str,
    sys_name: Optional[str] = None,
    module: Optional[str] = None,
    wave: bool = False,
    wave_vcd: bool = False,
    cov: bool = False,
    defines: Optional[List[str]] = None,
    extra_args: Optional[List[str]] = None,
    no_fix_prefix: bool = False,
) -> Job:
    from .workspace import fix_filelist_prefixes

    if not no_fix_prefix:
        fix_filelist_prefixes(cfg)
    sc = resolve_scenario(cfg, scenario, sys_name, module)
    cmd = compile_command(cfg, sc, wave=wave, wave_vcd=wave_vcd, cov=cov,
                          defines=defines, extra_args=extra_args)
    return _submit(cfg, sc, "sim_compile", cmd,
                   {"step": "compile", "wave": bool(wave), "wave_vcd": bool(wave_vcd)})


def submit_sim_run(
    cfg: Config,
    scenario: str,
    sys_name: Optional[str] = None,
    module: Optional[str] = None,
    tc: Optional[str] = None,
    seed: Optional[int] = None,
    timeout_us: Optional[int] = None,
    cov: bool = False,
    wall_timeout_s: int = 3600,
    extra_args: Optional[List[str]] = None,
) -> Job:
    sc = resolve_scenario(cfg, scenario, sys_name, module)
    simv = os.path.join(sc.work, "simv")
    if not os.path.isfile(simv):
        raise WorkspaceError("找不到 %s，请先 sim_compile" % simv)
    cmd = run_command(cfg, tc=tc, seed=seed, timeout_us=timeout_us, cov=cov,
                      wall_timeout_s=wall_timeout_s, extra_args=extra_args)
    return _submit(cfg, sc, "sim_run", cmd, {"step": "run", "tc": tc or "tc_all", "seed": seed})


_RESULT_RE = re.compile(r"RESULT\s*[:=]\s*(PASS|FAIL)", re.IGNORECASE)
_FINAL_RE = re.compile(r"FINAL[^:]*:\s*(PASS|FAIL)", re.IGNORECASE)
_SUMMARY_RE = re.compile(
    r"Total checks\s*:\s*(\d+).*?PASS\s*:\s*(\d+).*?FAIL\s*:\s*(\d+)",
    re.IGNORECASE | re.DOTALL,
)


def sim_summary(cfg: Config, job_id: str) -> Dict[str, Any]:
    """解析仿真日志（**退出码不可靠**，按 log 判定）。"""
    jm = JobManager(cfg)
    job = jm.get(job_id)
    text = jm.log(job_id, tail_lines=0)
    passes = len(_RESULT_RE.findall(text)) and sum(
        1 for m in _RESULT_RE.finditer(text) if m.group(1).upper() == "PASS")
    fails = sum(1 for m in _RESULT_RE.finditer(text) if m.group(1).upper() == "FAIL")
    final = None
    for m in _FINAL_RE.finditer(text):
        final = m.group(1).upper()
    checks = None
    m = _SUMMARY_RE.search(text)
    if m:
        checks = {"total": int(m.group(1)), "pass": int(m.group(2)), "fail": int(m.group(3))}
    first_fail = None
    for line in text.splitlines():
        if _RESULT_RE.search(line) and "FAIL" in line.upper():
            first_fail = line.strip()
            break
    ok = (final == "PASS") or (fails == 0 and passes > 0)
    return {
        "job_id": job_id,
        "state": job.state,
        "rc": job.rc,
        "pass_count": passes,
        "fail_count": fails,
        "checks": checks,
        "final": final,
        "verdict": "PASS" if ok else "FAIL",
        "first_failure": first_fail,
        "duration_s": round(job.duration, 1),
    }


def sim_clean(cfg: Config, scenario: str, sys_name: Optional[str] = None,
              module: Optional[str] = None) -> List[str]:
    """清理编译产物（保留日志与波形）。"""
    sc = resolve_scenario(cfg, scenario, sys_name, module)
    removed: List[str] = []
    if not os.path.isdir(sc.work):
        return removed
    for name in ("simv", "simv.daidir", "csrc", "ucli.key", "simv.vdb", "AN.DB"):
        path = os.path.join(sc.work, name)
        if os.path.isdir(path):
            import shutil

            shutil.rmtree(path, ignore_errors=True)
            removed.append(name)
        elif os.path.exists(path):
            try:
                os.remove(path)
                removed.append(name)
            except OSError:
                pass
    return removed


# ------------------------------------------------------------------ nLint


def submit_lint(cfg: Config, files: List[str], rule_set: Optional[str] = None,
                wait_seconds: float = 0.0) -> Job:
    """nLint 静态检查（仅适用可综合 RTL，TB 不做 lint）。"""
    from .workspace import _root, guard_path  # noqa: PLC2701

    root = _root(cfg)
    if not files:
        raise SimError("lint_run 需要至少一个 RTL 文件")
    rels: List[str] = []
    for f in files:
        p = guard_path(cfg, f if os.path.isabs(f) else os.path.join(root, f))
        if not os.path.isfile(p):
            raise SimError("文件不存在: %s" % p)
        rels.append(os.path.relpath(p, root))

    top = rels[0].split(os.sep)[0]
    ldir = os.path.join(root, top, "lint")
    os.makedirs(ldir, exist_ok=True)

    rs = rule_set or os.path.join(root, "script", "nLint_ws.rs")
    flt_src = os.path.join(root, "script", "nLint_filter.txt")
    flt = os.path.join(ldir, "flt_run.txt")
    if os.path.isfile(flt_src):
        with open(flt_src, errors="replace") as fh:
            text = fh.read().replace("<MIRROR>", root)
        with open(flt, "w") as fh:
            fh.write(text)

    paths = " ".join(shlex.quote(os.path.join(root, r)) for r in rels)
    cmd = (
        "rm -rf nLintDB nLintLog nlint_report.txt; "
        "nLint -nologo -sv -rs %s -nors install:home:current -filter %s %s "
        "-out nlint_report.txt > /dev/null 2>&1; "
        "if [ -f nLintLog/compiler.log ] && grep -q '^\\*Error\\*' nLintLog/compiler.log; then "
        "  echo 'NLINT PARSE FAIL'; grep '^\\*Error\\*' nLintLog/compiler.log | head -10; exit 2; fi; "
        "if [ -f nlint_report.txt ]; then grep -vE 'for loop might' nlint_report.txt; fi"
    ) % (shlex.quote(rs), shlex.quote(flt), paths)

    jm = JobManager(cfg)
    job = jm.submit("lint_run", cmd, cwd=ldir, extra={"step": "lint", "files": rels, "top": top})
    if wait_seconds and wait_seconds > 0:
        job = jm.wait(job.id, timeout=wait_seconds)
    return job


def nlint_result(cfg: Config, job_id: str) -> Dict[str, Any]:
    jm = JobManager(cfg)
    job = jm.get(job_id)
    text = jm.log(job_id, tail_lines=0)
    warn = err = 0
    total = None
    for line in text.splitlines():
        m = re.match(r"^Total\s+(\d+)\s+Warning", line)
        if m:
            warn = int(m.group(1))
            e = re.search(r"(\d+)\s+Error", line)
            err = int(e.group(1)) if e else 0
            total = line.strip()
    parse_fail = "NLINT PARSE FAIL" in text
    if parse_fail:
        verdict = "ERROR"
    elif total is None:
        verdict = "UNKNOWN"
    elif warn == 0 and err == 0:
        verdict = "PASS"
    else:
        verdict = "FAIL"
    return {
        "job_id": job_id,
        "state": job.state,
        "rc": job.rc,
        "verdict": verdict,
        "warning": warn,
        "error": err,
        "total_line": total,
    }
