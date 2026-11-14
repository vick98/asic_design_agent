"""``eda-mcp`` 命令行入口。

子命令::

    eda-mcp build-native            编译 FFR 小工具 fsdbq
    eda-mcp info <fsdb>             文件元信息
    eda-mcp signals <fsdb>          信号列表
    eda-mcp scopes <fsdb>           层次列表
    eda-mcp query <fsdb> <name>     按名查信号
    eda-mcp wave <fsdb> -s SIG ...  波形 -> WaveDrom JSON
    eda-mcp wave_extract <fsdb> --clock CLK --node NAME=PATH ... [--valid V]
                                    时钟沿采样导出节点序列（不抽稀，JSON 输出）
    eda-mcp doctor [--deep]         环境自检
    eda-mcp serve                   启动 MCP 服务

子命令按工具组过滤（security.enabled_groups / 环境变量 EDA_MCP_ENABLED_GROUPS），
未启用组的子命令不注册。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import List, Optional

from . import __version__
from .config import enabled_groups, load as load_config


def _print(title: str, payload) -> None:
    print("=== %s ===" % title)
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


# ------------------------------------------------------------------ 子命令


def cmd_build_native(args) -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    native = os.path.join(here, "native")
    if not os.path.isfile(os.path.join(native, "Makefile")):
        print("ERR: 找不到 %s/Makefile" % native, file=sys.stderr)
        return 2
    cmd = ["make", "-C", native]
    if args.verdi_home:
        cmd.append("VERDI_HOME=%s" % args.verdi_home)
    if args.zlib:
        cmd.append("ZLIB=%s" % args.zlib)
    if args.dest:
        try:
            subprocess.check_call(cmd + ["all"])
        except subprocess.CalledProcessError as exc:
            return exc.returncode
        os.makedirs(os.path.dirname(os.path.abspath(args.dest)), exist_ok=True)
        subprocess.check_call(
            ["install", "-m", "0755", os.path.join(native, "fsdbq"), args.dest]
        )
        print("installed: %s" % args.dest)
        return 0
    return subprocess.call(cmd + ["all"])


def cmd_info(args) -> int:
    from .fsdb import open_fsdb

    fs = open_fsdb(args.fsdb, load_config())
    _print("info", fs.info())
    return 0


def cmd_signals(args) -> int:
    from .fsdb import open_fsdb

    fs = open_fsdb(args.fsdb, load_config())
    sigs = fs.signals()
    if args.pattern:
        import fnmatch

        # 与 server.fsdb_signals 同一口径：本地 fnmatch（fsdbq 的 --pattern 语义
        # 与通配预期不一致，实测 *inst* 匹配不到任何信号）
        pat = args.pattern if any(c in args.pattern for c in "*?[") else "*%s*" % args.pattern
        sigs = [s for s in sigs
                if fnmatch.fnmatch(s.hier, pat) or fnmatch.fnmatch(s.name, pat)]
    if args.limit:
        sigs = sigs[: args.limit]
    if args.as_args:
        from .wavedrom import signals_as_args

        print(signals_as_args(sigs))
        return 0
    if args.json:
        _print("signals", [s.to_dict() for s in sigs])
    else:
        from .wavedrom import list_signals_text

        kind = "VCD" if args.fsdb.lower().endswith(".vcd") else "FSDB"
        sys.stdout.write(list_signals_text(sigs, title="%s 中的信号列表" % kind))
    return 0


def cmd_scopes(args) -> int:
    from .fsdb import open_fsdb

    fs = open_fsdb(args.fsdb, load_config())
    scopes = fs.scopes(scope=args.scope, max_depth=args.max_depth)
    for hier, depth in scopes:
        print("%s%s" % ("  " * (depth - 1), hier.rsplit(".", 1)[-1]))
    return 0


def cmd_query(args) -> int:
    from .wavegen import wave_query

    res = wave_query(args.fsdb, args.name)
    if args.json:
        _print("query", res)
    else:
        sys.stdout.write(res["text"])
    return 0 if res["count"] else 1


def cmd_wave(args) -> int:
    from .wavegen import LABEL_BITS, wave_gen

    res = wave_gen(
        args.fsdb,
        signals=args.signal,
        time=args.time,
        cycles=args.cycles,
        start=args.start,
        end=args.end,
        clock=args.clock,
        timescale=args.timescale,
        out=args.output,
        summary=getattr(args, "summary", None),
        cfg=load_config(),
    )
    if args.json:
        _print("wave", res)
    else:
        print("源文件: %s  (timescale=%s)" % (res["source"], res["timescale"]))
        print(
            "时钟: %s [%s]  窗口: %d -> %d  (%d 个周期)"
            % (
                res["clock"],
                res["clock_source"],
                res["window"]["start"],
                res["window"]["end"],
                res["cycles"],
            )
        )
        for s in res["signals"]:
            flag = " (*时钟)" if s["is_clock"] else ""
            print(
                "  %-52s %-9s -> %s%s"
                % (s["requested"], s["match"], s["resolved"], flag)
            )
        for item in res.get("glob_expanded") or []:
            print("  通配: %s -> %s" % (item["requested"], item["resolved"]))
        for hier, segs in (res.get("segments") or {}).items():
            print("  %s 翻转段（%d 段）:" % (hier, len(segs)))
            for (seg_start, seg_end, val) in segs:
                print("    %s -> %s  %s" % (seg_start, seg_end, val))
        if res.get("width_truncated"):
            print(
                "警告: 以下信号超过 %d bit，数据标签只保留低 %d bit（完整值见 -o 写的 "
                "<out>_full_data.log） -> %s"
                % (LABEL_BITS, LABEL_BITS, ", ".join(res["width_truncated"]))
            )
        if res["truncated"]:
            print("警告: 以下信号值变被截断 -> %s" % ", ".join(res["truncated"]))
        if res.get("summary_hint"):
            print("提示: %s" % res["summary_hint"])
        if res["out"]:
            print("已写入: %s" % res["out"])
            print("全量数据: %s" % res["full_data_log"])
        else:
            print(res["json"])
    return 0


def cmd_doctor(args) -> int:
    from .doctor import run_doctor

    return run_doctor(deep=args.deep, as_json=args.json, source=args.fsdb)


def cmd_serve(args) -> int:
    from .server import main as server_main

    return server_main(
        transport=args.transport, host=args.host, port=args.port
    )



# ------------------------------------------------------------------ NPI 设计模型


def cmd_npi(args) -> int:
    from .config import load as load_config
    from .daemon import close_design, designs_root, list_designs
    from .npi import NpiClient, connect

    cfg = load_config()
    act = args.action
    if act == "list":
        for d in list_designs(cfg):
            print("%-24s alive=%-5s pid=%-8s display=%-6s files=%s" % (
                d.design_id, d.alive, d.pid, d.display, len(d.files or [])))
        return 0
    if act == "close":
        ok = close_design(args.design_id, cfg)
        print("closed=%s" % ok)
        return 0 if ok else 1

    if act == "open":
        files = list(args.files or [])
        if args.file:
            files += list(args.file)
        if not files and not args.filelist:
            print("ERR: open 需要 --file <src>... 或 --filelist <.f>", file=sys.stderr)
            return 2
        cli = connect(args.design_id, cfg=cfg, files=files,
                      filelist=args.filelist, top=args.top, sv=not args.no_sv)
        info = cli.daemon.info()
        print("design=%s pid=%s display=%s ping=%s" % (
            info.design_id, info.pid, info.display, cli.ping()))
        return 0

    # 其余动作需要已打开的设计
    from .daemon import DesignDaemon

    d = DesignDaemon(args.design_id, cfg=cfg, root=designs_root(cfg))
    if not d.alive():
        d.start()
    cli = NpiClient(d)

    if act == "hier":
        nodes = cli.hierarchy(root=args.root, max_depth=args.max_depth, pattern=args.pattern)
        for n in nodes:
            print("%s%s  (%s) @%s:%s" % ("  " * n.depth, n.full, n.def_name,
                                         os.path.basename(n.file), n.line))
        print("-- %d 个层次 --" % len(nodes))
        return 0
    if act == "object":
        o = cli.object(args.arg)
        print("%s" % o.to_dict())
        print("  src: %s" % o.source)
        return 0
    if act == "module":
        m = cli.module(args.arg)
        print("counts=%s" % m["counts"])
        for key in ("ports", "params", "nets", "instances"):
            for o in m[key][:args.limit]:
                print("  %-9s %-45s w=%-3s %s" % (
                    key[:-1], o["full"], o["width"], o["direction"] or o["type"]))
        return 0
    if act == "find":
        for o in cli.find(args.arg or "*", limit=args.limit):
            print("  %-52s w=%-3s %s" % (o.full, o.width, o.type))
        return 0
    if act == "trace":
        hits = cli.trace(args.arg, direction=args.direction, limit=args.limit)
        for h in hits:
            print("  %-7s %-14s %s" % (h.direction, h.type, h.full))
        print("-- %d 条 --" % len(hits))
        return 0
    if act == "equiv":
        for h in cli.equivalent(args.arg):
            print("  %-14s %s" % (h.type, h.full))
        return 0
    print("ERR: 未知动作 %s" % act, file=sys.stderr)
    return 2


# ------------------------------------------------------------------ 作业与流程


def _job_reply(args, job, cfg):
    from .jobs import JobManager

    if getattr(args, "wait", 0):
        job = JobManager(cfg).wait(job.id, timeout=args.wait)
    from .server import _verdict  # 复用同一份判定逻辑

    v = _verdict(cfg, job.id)
    print("job_id=%s state=%s rc=%s 耗时=%.1fs" % (
        job.id, job.state, job.rc, job.duration))
    print("日志: %s" % job.log_path)
    if v:
        print("判定: %s" % json.dumps(v, ensure_ascii=False, default=str))
    return 0 if job.state == "completed" or v is None or v.get("verdict") == "PASS" else 1


def cmd_job(args) -> int:
    from .config import load as load_config
    from .jobs import JobManager

    cfg = load_config()
    jm = JobManager(cfg)
    if args.action == "list":
        for j in jm.list(limit=args.limit, state=args.state):
            print("%-24s %-10s rc=%-4s %6.1fs  %s" % (
                j.id, j.state, j.rc, j.duration, j.name))
        return 0
    if args.action == "status":
        from .server import _verdict

        job = jm.get(args.job_id)
        print(json.dumps(job.to_dict(), ensure_ascii=False, indent=2))
        v = _verdict(cfg, args.job_id)
        if v:
            print(json.dumps(v, ensure_ascii=False, indent=2))
        return 0 if job.state == "completed" else 1
    if args.action == "log":
        text = jm.log(args.job_id, tail_lines=args.tail, grep=args.grep)
        sys.stdout.write(text + ("\n" if text and not text.endswith("\n") else ""))
        return 0
    if args.action == "kill":
        print(json.dumps(jm.kill(args.job_id).to_dict(), ensure_ascii=False))
        return 0
    print("ERR: 未知动作 %s" % args.action, file=sys.stderr)
    return 2


def cmd_sim(args) -> int:
    from .config import load as load_config
    from .sim import sim_clean, sim_summary, submit_sim_compile, submit_sim_run

    cfg = load_config()
    if args.action == "compile":
        job = submit_sim_compile(cfg, args.scenario, args.sys_name, args.module,
                                 wave=args.wave, wave_vcd=args.wave_vcd, cov=args.cov,
                                 defines=args.define, extra_args=args.extra)
        return _job_reply(args, job, cfg)
    if args.action == "run":
        job = submit_sim_run(cfg, args.scenario, args.sys_name, args.module, tc=args.tc,
                             seed=args.seed, timeout_us=args.timeout_us, cov=args.cov,
                             wall_timeout_s=args.wall_timeout, extra_args=args.extra)
        return _job_reply(args, job, cfg)
    if args.action == "summary":
        jid = args.job_id or args.scenario   # summary 时位置参数就是 job_id
        print(json.dumps(sim_summary(cfg, jid), ensure_ascii=False, indent=2))
        return 0
    if args.action == "clean":
        print(json.dumps({"removed": sim_clean(cfg, args.scenario, args.sys_name, args.module)},
                         ensure_ascii=False))
        return 0
    print("ERR: 未知动作 %s" % args.action, file=sys.stderr)
    return 2


def cmd_lint(args) -> int:
    from .config import load as load_config
    from .sim import nlint_result, submit_lint

    cfg = load_config()
    job = submit_lint(cfg, list(args.files))
    rc = _job_reply(args, job, cfg)
    print(json.dumps(nlint_result(cfg, job.id), ensure_ascii=False, indent=2))
    return rc


def cmd_syn(args) -> int:
    from .config import load as load_config
    from .syn import submit_syn

    cfg = load_config()
    job = submit_syn(cfg, args.target, top=args.top, lib=args.lib, sdc=args.sdc,
                     tcl=args.tcl, wall_timeout_s=args.wall_timeout)
    return _job_reply(args, job, cfg)


def cmd_sta(args) -> int:
    from .config import load as load_config
    from .syn import submit_sta

    cfg = load_config()
    job = submit_sta(cfg, args.target, top=args.top, corner=args.corner,
                     netlist=args.netlist, sdc=args.sdc, tcl=args.tcl,
                     wall_timeout_s=args.wall_timeout)
    return _job_reply(args, job, cfg)


def cmd_shell(args) -> int:
    from .config import load as load_config
    from .server import shell_run

    sys.stdout.write(shell_run(" ".join(args.command), cwd=args.cwd, timeout_s=args.timeout) + "\n")
    return 0


def cmd_wave_extract(args) -> int:
    from .server import wave_extract

    # 机器可解析：只吐 JSON（每个节点给出文件路径与行数），供 dbg <sys> extract 使用
    print(wave_extract(
        args.fsdb,
        clock=args.clock,
        edge=args.edge,
        valid=args.valid,
        nodes=list(args.node),
        start=args.start,
        end=args.end,
        out_dir=args.out_dir,
    ))
    return 0


def cmd_windows(args) -> int:
    from .server import fsdb_windows

    print(fsdb_windows(args.fsdb, args.expr, start=args.start, end=args.end,
                       min_duration=args.min_duration, limit=args.limit))
    return 0


def cmd_diff(args) -> int:
    from .server import fsdb_diff

    print(fsdb_diff(list(args.fsdb), signals=args.signal, signal_filter=args.filter,
                    after=args.start, before=args.end, clock=args.clock,
                    max_signals=args.max_signals, max_report=args.max_report))
    return 0


def _join_args(args):
    return (args.design, args.fsdb, args.signal, args.time)


def cmd_trace(args) -> int:
    from .server import npi_trace_value

    design, fsdb, signal, time = _join_args(args)
    print(npi_trace_value(design, fsdb, signal, time, depth=args.depth,
                          x_only=args.x, max_nodes=args.max_nodes))
    return 0


def cmd_active(args) -> int:
    from .server import npi_active_drivers

    design, fsdb, signal, time = _join_args(args)
    print(npi_active_drivers(design, fsdb, signal, time, clock=args.clock, edge=args.edge))
    return 0


def cmd_fsm(args) -> int:
    from .server import npi_state_transitions

    print(npi_state_transitions(args.design, args.fsdb, args.signal, clock=args.clock,
                                edge=args.edge, start=args.start, end=args.end,
                                limit=args.limit))
    return 0


# ------------------------------------------------------------------ parser
#
# CLI 子命令按工具组过滤：与 server.TOOL_GROUPS 同一张表；
# serve 是服务本体不分组；未设置 enabled_groups 时全部注册（上游现状）。


CLI_GROUPS = {
    "build-native": "env",
    "info": "fsdb",
    "signals": "fsdb",
    "scopes": "fsdb",
    "query": "wave",
    "wave": "wave",
    "wave_extract": "wave",
    "windows": "wave",
    "diff": "wave",
    "trace": "npi",
    "active": "npi",
    "fsm": "npi",
    "doctor": "env",
    "npi": "npi",
    "job": "flow",
    "sim": "flow",
    "lint": "flow",
    "syn": "flow",
    "sta": "flow",
    "shell": "shell",
    "serve": None,
}


def build_parser(cfg=None) -> argparse.ArgumentParser:
    groups = enabled_groups(cfg or load_config())
    p = argparse.ArgumentParser(
        prog="eda-mcp", description="EDA 工具链 MCP 服务（Verdi NPI / FSDB / VCS / DC·PT）"
    )
    p.add_argument("--version", action="version", version="eda-mcp %s" % __version__)
    sub = p.add_subparsers(dest="cmd")

    def add(name: str, help_text: str):
        """按工具组过滤注册子命令；未启用组直接不注册（而非隐藏报错）。"""
        group = CLI_GROUPS[name]
        if group is not None and group not in groups:
            return None
        return sub.add_parser(name, help=help_text)

    def add_common(sp):
        sp.add_argument("--json", action="store_true", help="以 JSON 输出")

    sp = add("build-native", "编译 FFR 小工具 fsdbq")
    if sp is not None:
        sp.add_argument("--verdi-home", dest="verdi_home", default=None)
        sp.add_argument("--zlib", default=None)
        sp.add_argument("--dest", default=None, help="安装到该路径（如 ~/.local/bin/fsdbq）")
        sp.set_defaults(func=cmd_build_native)

    sp = add("info", "FSDB 元信息")
    if sp is not None:
        sp.add_argument("fsdb")
        add_common(sp)
        sp.set_defaults(func=cmd_info)

    sp = add("signals", "列出波形信号")
    if sp is not None:
        sp.add_argument("fsdb")
        sp.add_argument("--pattern", default=None)
        sp.add_argument("--scope", default=None)
        sp.add_argument("--limit", type=int, default=None)
        sp.add_argument("--as-args", action="store_true", dest="as_args",
                        help="输出可直接粘进 wave -s 的参数串（配合 --pattern 一步取全名）")
        add_common(sp)
        sp.set_defaults(func=cmd_signals)

    sp = add("scopes", "列出波形层次")
    if sp is not None:
        sp.add_argument("fsdb")
        sp.add_argument("--scope", default=None)
        sp.add_argument("--max-depth", dest="max_depth", type=int, default=None)
        sp.set_defaults(func=cmd_scopes)

    sp = add("query", "按名查信号")
    if sp is not None:
        sp.add_argument("fsdb")
        sp.add_argument("name")
        add_common(sp)
        sp.set_defaults(func=cmd_query)

    sp = add("wave", "波形 -> WaveDrom JSON")
    if sp is not None:
        sp.add_argument("fsdb")
        sp.add_argument("-s", "--signal", action="append", default=[], help="可重复")
        sp.add_argument("-t", "--time", default=None, help="中心时间点（如 500ns）")
        sp.add_argument("-c", "--cycles", type=int, default=20)
        sp.add_argument("--start", default=None)
        sp.add_argument("--end", default=None)
        sp.add_argument("--clock", "-clk", dest="clock", default=None)
        sp.add_argument("--timescale", default=None)
        sp.add_argument("-o", "--output", default=None)
        sp.add_argument("--summary", default=None, choices=["flip"],
                        help="附加翻转段摘要（只列翻转时刻+值；长窗口信息密度更高）")
        add_common(sp)
        sp.set_defaults(func=cmd_wave)

    sp = add("wave_extract", "时钟沿采样导出节点序列（不抽稀，每节点一个文本文件）")
    if sp is not None:
        sp.add_argument("fsdb")
        sp.add_argument("--clock", required=True, help="时钟信号（层次路径）")
        sp.add_argument("--edge", default="posedge", choices=["posedge", "negedge"], help="采样沿")
        sp.add_argument("--valid", default=None, help="valid 信号：为 1 的拍才落行")
        sp.add_argument("--node", action="append", default=[], metavar="NAME=PATH",
                        help="节点名=层次路径（可重复）")
        sp.add_argument("--start", type=int, default=None, help="起始时间（含，fsdb 时间单位）")
        sp.add_argument("--end", type=int, default=None, help="结束时间（含）")
        sp.add_argument("--out-dir", dest="out_dir", required=True, help="输出目录")
        sp.set_defaults(func=cmd_wave_extract)

    sp = add("windows", "时间窗搜索：表达式何时成立（区间答案，JSON）")
    if sp is not None:
        sp.add_argument("fsdb")
        sp.add_argument("--expr", required=True,
                        help='布尔表达式，如 "top.u_dut.u_x.valid == 1 && top.u_dut.u_x.cnt > 3"')
        sp.add_argument("--start", default=None, help="窗口起点（fsdb 原值或 100ns 形式）")
        sp.add_argument("--end", default=None)
        sp.add_argument("--min-duration", dest="min_duration", default=None,
                        help="只报至少持续这么长的区间（如 20ns）")
        sp.add_argument("--limit", type=int, default=200)
        sp.set_defaults(func=cmd_windows)

    sp = add("diff", "N 份 FSDB 首分歧定位（首分歧时刻 + 分歧信号排序，JSON）")
    if sp is not None:
        sp.add_argument("fsdb", nargs="+", help="2..N 份 FSDB（第一份的信号表为基准）")
        sp.add_argument("-s", "--signal", action="append", default=[], help="只比这些信号（可重复）")
        sp.add_argument("--filter", default=None, help="信号通配裁剪（默认全量截 512）")
        sp.add_argument("--start", default=None, help="比较窗口起点（fsdb 原值或 100ns）")
        sp.add_argument("--end", default=None)
        sp.add_argument("--clock", default=None, help="只在时钟上升沿比较（滤沿间毛刺）")
        sp.add_argument("--max-signals", dest="max_signals", type=int, default=512)
        sp.add_argument("--max-report", dest="max_report", type=int, default=50)
        sp.set_defaults(func=cmd_diff)

    sp = add("trace", "驱动链带值回溯（NPI 驱动 × FSDB 值；--x 为 X 根因口径，JSON）")
    if sp is not None:
        sp.add_argument("fsdb")
        sp.add_argument("--design", required=True, help="NPI 设计标识（npi open 的 design_id）")
        sp.add_argument("-s", "--signal", required=True, help="目标信号（FSDB 层次路径）")
        sp.add_argument("--time", required=True, help="时刻（fsdb 原值或 85ns）")
        sp.add_argument("--depth", type=int, default=6)
        sp.add_argument("--x", action="store_true", help="X 根因口径：只走 x/z 分支")
        sp.add_argument("--max-nodes", dest="max_nodes", type=int, default=200)
        sp.set_defaults(func=cmd_trace)

    sp = add("active", "某一拍哪条驱动在起作用（值一致分类，JSON）")
    if sp is not None:
        sp.add_argument("fsdb")
        sp.add_argument("--design", required=True)
        sp.add_argument("-s", "--signal", required=True, help="目标信号（FSDB 层次路径）")
        sp.add_argument("--time", required=True)
        sp.add_argument("--clock", default=None, help="时钟（过程驱动的寄存器按采集沿取驱动值）")
        sp.add_argument("--edge", default="posedge", choices=["posedge", "negedge"])
        sp.set_defaults(func=cmd_active)

    sp = add("fsm", "状态寄存器实际转移表（次数/首现/采集沿驱动值，JSON）")
    if sp is not None:
        sp.add_argument("fsdb")
        sp.add_argument("--design", required=True)
        sp.add_argument("-s", "--signal", required=True, help="状态寄存器（FSDB 层次路径）")
        sp.add_argument("--clock", default=None, help="时钟（给采集沿上的驱动值）")
        sp.add_argument("--edge", default="posedge", choices=["posedge", "negedge"])
        sp.add_argument("--start", default=None)
        sp.add_argument("--end", default=None)
        sp.add_argument("--limit", type=int, default=200)
        sp.set_defaults(func=cmd_fsm)

    sp = add("doctor", "环境自检")
    if sp is not None:
        sp.add_argument("fsdb", nargs="?", default=None, help="--deep 时用于波形冒烟的 FSDB 路径")
        sp.add_argument("--deep", action="store_true", help="追加真实波形冒烟")
        add_common(sp)
        sp.set_defaults(func=cmd_doctor)

    sp = add("npi", "Verdi NPI 设计模型查询（温进程 daemon）")
    if sp is not None:
        sp.add_argument("action", choices=["open", "list", "close", "hier", "object",
                                            "module", "find", "trace", "equiv"])
        sp.add_argument("design_id", nargs="?", default="", help="设计标识（daemon 名）")
        sp.add_argument("arg", nargs="?", default="",
                         help="object/module 给对象全路径；find 给通配；trace/equiv 给信号全路径")
        sp.add_argument("-f", "--file", action="append", default=[], help="源码文件（可重复）")
        sp.add_argument("--filelist", default=None, help=".f 编译清单")
        sp.add_argument("--files", nargs="*", default=None, help="源码文件（位置形式）")
        sp.add_argument("--top", default=None)
        sp.add_argument("--no-sv", dest="no_sv", action="store_true", help="按 Verilog 而非 SV 导入")
        sp.add_argument("--root", default=None, help="层次根")
        sp.add_argument("--pattern", default=None, help="层次通配（hier）")
        sp.add_argument("--max-depth", dest="max_depth", type=int, default=None)
        sp.add_argument("--direction", default="both", choices=["driver", "load", "both"])
        sp.add_argument("--limit", type=int, default=200)
        sp.set_defaults(func=cmd_npi)

    sp = add("job", "作业管理")
    if sp is not None:
        sp.add_argument("action", choices=["list", "status", "log", "kill"])
        sp.add_argument("job_id", nargs="?", default="")
        sp.add_argument("--limit", type=int, default=20)
        sp.add_argument("--state", default=None)
        sp.add_argument("--tail", type=int, default=200)
        sp.add_argument("--grep", default=None)
        sp.add_argument("--wait", type=float, default=0)
        sp.set_defaults(func=cmd_job)

    sp = add("sim", "VCS 仿真（作业化）")
    if sp is not None:
        sp.add_argument("action", choices=["compile", "run", "summary", "clean"])
        sp.add_argument("scenario", nargs="?", default="C", help="A|B|C")
        sp.add_argument("--sys", dest="sys_name", default=None)
        sp.add_argument("--module", default=None)
        sp.add_argument("--job-id", dest="job_id", default=None)
        sp.add_argument("--tc", default=None)
        sp.add_argument("--seed", type=int, default=None)
        sp.add_argument("--timeout-us", dest="timeout_us", type=int, default=None)
        sp.add_argument("--wave", action="store_true")
        sp.add_argument("--wave-vcd", dest="wave_vcd", action="store_true")
        sp.add_argument("--cov", action="store_true")
        sp.add_argument("--define", action="append", default=[])
        sp.add_argument("--extra", action="append", default=[])
        sp.add_argument("--wall-timeout", dest="wall_timeout", type=int, default=3600)
        sp.add_argument("--wait", type=float, default=0)
        sp.set_defaults(func=cmd_sim)

    sp = add("lint", "nLint 静态检查")
    if sp is not None:
        sp.add_argument("files", nargs="+")
        sp.add_argument("--wait", type=float, default=120)
        sp.set_defaults(func=cmd_lint)

    sp = add("syn", "DC 逻辑综合")
    if sp is not None:
        sp.add_argument("target", help="子系统名，或 pub_code")
        sp.add_argument("--top", default=None)
        sp.add_argument("--lib", default="std", choices=["std", "stdht"])
        sp.add_argument("--sdc", default=None)
        sp.add_argument("--tcl", default=None)
        sp.add_argument("--wall-timeout", dest="wall_timeout", type=int, default=3600)
        sp.add_argument("--wait", type=float, default=0)
        sp.set_defaults(func=cmd_syn)

    sp = add("sta", "PT 静态时序分析")
    if sp is not None:
        sp.add_argument("target")
        sp.add_argument("--top", default=None)
        sp.add_argument("--corner", default="tt", choices=["tt", "ss", "ff"])
        sp.add_argument("--netlist", default=None)
        sp.add_argument("--sdc", default=None)
        sp.add_argument("--tcl", default=None)
        sp.add_argument("--wall-timeout", dest="wall_timeout", type=int, default=3600)
        sp.add_argument("--wait", type=float, default=0)
        sp.set_defaults(func=cmd_sta)

    sp = add("shell", "逃生舱：执行 shell 命令（默认禁用）")
    if sp is not None:
        sp.add_argument("command", nargs="+")
        sp.add_argument("--cwd", default=None)
        sp.add_argument("--timeout", type=int, default=60)
        sp.set_defaults(func=cmd_shell)

    sp = add("serve", "启动 MCP 服务")
    if sp is not None:
        sp.add_argument("--transport", default=None, choices=[None, "stdio", "streamable-http", "http"])
        sp.add_argument("--host", default=None)
        sp.add_argument("--port", type=int, default=None)
        sp.set_defaults(func=cmd_serve)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "cmd", None):
        parser.print_help()
        return 1
    try:
        return int(args.func(args) or 0)
    except Exception as exc:  # 面向 CLI 的错误要干净，不吐 traceback
        print("ERR: %s" % exc, file=sys.stderr)
        if os.environ.get("EDA_MCP_DEBUG"):
            raise
        return 1


if __name__ == "__main__":
    sys.exit(main())
