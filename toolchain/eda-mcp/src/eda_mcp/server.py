"""MCP 服务装配：注册工具、选择 transport。

兼容两代 MCP Python SDK：

* v2（``mcp>=2.0``）：``from mcp.server import MCPServer``
* v1.x：``from mcp.server.fastmcp import FastMCP``

核心波形通路（FFR/FSDB/WaveDrom）不依赖 MCP SDK；未安装 SDK 时
``eda-mcp`` 的 CLI 子命令照常可用，``serve`` 子命令会给出明确提示。
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from .config import Config, enabled_groups, load as load_config

__all__ = ["make_server", "main"]


def _sdk():
    """返回 (类, 名称)。v2 优先；都没装则返回 (None, "builtin")。"""
    try:
        from mcp.server import MCPServer  # type: ignore

        return MCPServer, "MCPServer"
    except Exception:
        pass
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore

        return FastMCP, "FastMCP"
    except Exception:
        return None, "builtin"


def _json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


# ------------------------------------------------------------------ 工具实现


def eda_env_info() -> str:
    """EDA 环境总览：工具路径与版本、VERDI_HOME、fsdbq、配置来源与逐项自检结果。"""
    from . import __version__
    from .fsdb import open_fsdb  # noqa: F401
    from .doctor import build_report

    cfg = load_config()
    rep = build_report(cfg)
    return _json(
        {
            "version": __version__,
            "config_sources": cfg.sources,
            "workspace_root": cfg.path("eda.workspace_root"),
            "verdi_home": cfg.verdi_home(),
            "fsdbq": cfg.fsdbq(),
            "tools": {
                k: cfg.which("eda." + k)
                for k in (
                    "vcs_bin",
                    "verdi_bin",
                    "vcd2fsdb_bin",
                    "nlint_bin",
                    "dc_bin",
                    "pt_bin",
                )
            },
            "checks": rep.items,
            "conclusion": rep.conclusion(),
        }
    )


def eda_doctor(deep: bool = False, fsdb: Optional[str] = None) -> str:
    """一键环境自检（工具存在性/Verdi FFR/Xvfb/可写性/MCP SDK）；deep=True 时追加一次真实波形冒烟，需同时给 fsdb 路径。"""
    from .doctor import build_report

    cfg = load_config()
    rep = build_report(cfg, deep=deep, source=fsdb)
    return _json({"conclusion": rep.conclusion(), "items": rep.items})


def fsdb_info(path: str) -> str:
    """FSDB 文件元信息：scale unit、仿真器版本与日期、min/max time。"""
    from .fsdb import open_fsdb

    fs = open_fsdb(path, load_config())
    info = fs.info()
    return _json(
        {
            "path": fs.path,
            "scale_unit": info.get("scale_unit"),
            "sim_version": info.get("sim_version"),
            "sim_date": info.get("sim_date"),
            "min_time": info.get("min_time_int"),
            "max_time": info.get("max_time_int"),
        }
    )


def fsdb_scopes(
    path: str, root: Optional[str] = None, max_depth: Optional[int] = None
) -> str:
    """列出波形内的层次（scope），可用 root 按前缀裁剪、max_depth 限深。"""
    from .fsdb import open_fsdb

    fs = open_fsdb(path, load_config())
    scopes = fs.scopes(scope=root, max_depth=max_depth)
    return _json(
        {
            "path": fs.path,
            "count": len(scopes),
            "scopes": [{"hier": h, "depth": d} for h, d in scopes],
        }
    )


def fsdb_signals(
    path: str,
    scope: Optional[str] = None,
    pattern: Optional[str] = None,
    max_depth: Optional[int] = None,
    limit: int = 500,
) -> str:
    """列出波形内信号（全名/位宽/类型）；scope 按前缀过滤，pattern 支持通配或子串，limit 截断。"""
    from .fsdb import open_fsdb

    fs = open_fsdb(path, load_config())
    all_sigs = fs.signals(scope=scope, max_depth=max_depth)
    if pattern:
        import fnmatch

        pat = pattern if any(c in pattern for c in "*?[") else "*%s*" % pattern
        all_sigs = [
            s for s in all_sigs if fnmatch.fnmatch(s.hier, pat) or fnmatch.fnmatch(s.name, pat)
        ]
    total = len(all_sigs)
    shown = all_sigs[: max(0, int(limit))]
    return _json(
        {
            "path": fs.path,
            "total": total,
            "returned": len(shown),
            "truncated": total > len(shown),
            "signals": [s.to_dict() for s in shown],
        }
    )


def fsdb_find(path: str, pattern: str, limit: int = 200) -> str:
    """按名字搜索信号，返回全路径与位宽（等价 fsdb_signals 的 pattern 用法）。"""
    return fsdb_signals(path, pattern=pattern, limit=limit)


def fsdb_value(path: str, signal: str, time: int, fmt: str = "bin") -> str:
    """取单个信号在 time 时刻的值（自动取 <= time 的最近值变）；fmt 取 bin|hex|dec。"""
    from .fsdb import open_fsdb

    fs = open_fsdb(path, load_config())
    res = fs.wave([signal], clock="none", t0=0, t1=int(time), max_changes=0)
    ws = res.signals[0] if res.signals else None
    if ws is None or not ws.found:
        return _json({"error": "signal not found", "signal": signal})
    val = ws.value_at(int(time))
    return _json(
        {
            "path": fs.path,
            "signal": ws.resolved,
            "time": int(time),
            "value": _format_value(val, ws.width, fmt),
            "raw": val,
            "width": ws.width,
        }
    )


def _format_value(val: str, width: int, fmt: str) -> Optional[str]:
    if not val:
        return None
    if fmt in ("bin", "raw"):
        return val
    v = val.lower()
    if v.startswith("r"):
        return v[1:]
    bits = v[1:] if v.startswith("b") else v
    if any(c not in "01" for c in bits):
        return val  # 含 x/z，保持原样
    n = int(bits, 2) if bits else 0
    if fmt == "hex":
        return "0x%x" % n
    if fmt == "dec":
        return str(n)
    return val


def fsdb_wave(
    path: str,
    signals: List[str],
    t0: Optional[int] = None,
    t1: Optional[int] = None,
    max_changes: int = 2000,
    fmt: str = "bin",
) -> str:
    """取一组信号的值变序列（时间+值）；超过 max_changes 会自动抽稀并在 truncated 中标记。"""
    from .fsdb import open_fsdb

    fs = open_fsdb(path, load_config())
    res = fs.wave(
        list(signals), clock="none", t0=t0, t1=t1, max_changes=int(max_changes)
    )
    out = []
    for ws in res.signals:
        out.append(
            {
                "requested": ws.requested,
                "resolved": ws.resolved,
                "width": ws.width,
                "total_changes": ws.total,
                "truncated": ws.truncated,
                "changes": [
                    [t, _format_value(v, ws.width, fmt)] for t, v in ws.changes
                ],
            }
        )
    return _json({"path": fs.path, "signals": out})


def fsdb_check(path: str) -> str:
    """检查给定文件是否为合法且可读的 FSDB。"""
    from .fsdb import open_fsdb

    try:
        fs = open_fsdb(path, load_config())
        info = fs.info()
        n = len(fs.signals(limit=1))
        return _json(
            {
                "path": fs.path,
                "ok": True,
                "scale_unit": info.get("scale_unit"),
                "time_range": [info.get("min_time_int"), info.get("max_time_int")],
                "has_signals": bool(info),
            }
        )
    except Exception as exc:  # noqa: BLE001
        return _json({"path": path, "ok": False, "error": str(exc)})


def wave_gen(
    source: str,
    signals: Optional[List[str]] = None,
    time: Optional[str] = None,
    cycles: int = 20,
    start: Optional[str] = None,
    end: Optional[str] = None,
    clock: Optional[str] = None,
    timescale: Optional[str] = None,
    out: Optional[str] = None,
    summary: Optional[str] = None,
) -> str:
    """VCD/FSDB -> WaveDrom 时序图 JSON。time+cycles 以该时刻为中心截取，或 start+end 取区间（二者互斥）；clock 缺省先在信号表里找 *clk* 再自动检测。输出与原 aic_tool_trace 逐字节一致。summary='flip' 时每个信号额外给 segments（窗口内 [t0,t1,值] 翻转段，段内恒定）——长窗口做恒值判读/翻转定位用它，别读巨长的 wave 串。signals 里含 * ? [ 的项按信号名通配展开。"""
    from .wavegen import wave_gen as _impl

    res = _impl(
        source,
        signals=signals,
        time=time,
        cycles=cycles,
        start=start,
        end=end,
        clock=clock,
        timescale=timescale,
        out=out,
        summary=summary,
        cfg=load_config(),
    )
    # json 原样内联返回，便于直接贴进规格书
    return _json(res)


def wave_list_signals(source: str, limit: int = 2000) -> str:
    """列出波形内全部信号（等价原工具 --list-signals）。"""
    from .wavegen import wave_list_signals as _impl

    res = _impl(source, cfg=load_config())
    sigs = res["signals"]
    if limit and len(sigs) > int(limit):
        res = dict(res, signals=sigs[: int(limit)], truncated=True)
    return _json(res)


def wave_query(source: str, name: str) -> str:
    """按名查信号（等价原工具 --query）：带点则精确匹配，否则列出全部同名信号（层次由浅到深）。"""
    from .wavegen import wave_query as _impl

    return _json(_impl(source, name, cfg=load_config()))


def wave_extract(
    path: str,
    clock: str,
    edge: str = "posedge",
    valid: Optional[str] = None,
    nodes: Optional[List[str]] = None,
    start: Optional[int] = None,
    end: Optional[int] = None,
    out_dir: Optional[str] = None,
    cfg: Optional[Config] = None,
) -> str:
    """时钟沿采样导出节点序列：valid 为 1 的拍才落行，**不抽稀**。

    nodes 为 ``NAME=层次路径`` 列表；每个节点写一个文本文件
    ``<out_dir>/<安全化名>.txt``，每行 ``拍号 时间 值``（拍号从 0 起，
    按"已被 valid 放行的拍"顺序编号；值为 fsdbq 原始值，如 b0001 / r3.14）。
    返回 JSON：每个节点的文件路径与行数，供 ``dbg <sys> extract`` 使用。
    """
    from .fsdb import FsdbError, open_fsdb

    if edge not in ("posedge", "negedge"):
        raise FsdbError("edge 取 posedge|negedge，得到: %r" % edge)
    pairs: List[tuple] = []
    for item in nodes or []:
        if "=" not in item:
            raise FsdbError("node 需要 NAME=层次路径 形式: %r" % item)
        name, hier = item.split("=", 1)
        name, hier = name.strip(), hier.strip()
        if not name or not hier:
            raise FsdbError("node 需要 NAME=层次路径 形式: %r" % item)
        pairs.append((name, hier))
    if not pairs:
        raise FsdbError("至少要给一个 node（NAME=层次路径，可重复）")
    if not out_dir:
        raise FsdbError("需要输出目录 out_dir")
    if valid and valid == clock:
        raise FsdbError("valid 信号不能与时钟相同: %s" % valid)

    fs = open_fsdb(path, cfg or load_config())
    wanted: List[str] = [clock]
    if valid:
        wanted.append(valid)
    wanted += [hier for _, hier in pairs]
    seen = set()
    wanted = [s for s in wanted if not (s in seen or seen.add(s))]  # 去重保序
    # max_changes=0：不做抽稀（fsdb_wave 的默认 2000 上限在这里不适用）
    res = fs.wave(wanted, clock=clock, clock_pattern=clock, t0=start, t1=end, max_changes=0)

    edges = res.rising if edge == "posedge" else res.falling
    if not edges:
        raise FsdbError(
            "窗口内没有 %s 的 %s 沿（clock=%s, start=%s, end=%s）"
            % (res.clock or clock, edge, res.clock or clock, start, end)
        )

    slots = {ws.requested: ws for ws in res.signals}
    valid_ws = slots.get(valid) if valid else None
    if valid and valid_ws is None:
        raise FsdbError("valid 信号未找到: %s" % valid)

    def _is_high(val: str) -> bool:
        v = (val or "").strip().lower()
        return v[1:] == "1" if v.startswith("b") else v == "1"

    sampled = [
        t for t in edges
        if not valid or _is_high(valid_ws.value_at(t))
    ]
    if not sampled:
        raise FsdbError("valid 门控后没有任何拍（检查 valid=%s 与时间窗口）" % valid)

    os.makedirs(out_dir, exist_ok=True)

    def _safe(name: str) -> str:
        cleaned = "".join(c if (c.isalnum() or c in "._-") else "_" for c in name)
        return cleaned or "node"

    out_nodes = []
    for name, hier in pairs:
        ws = slots.get(hier)
        if ws is None or not ws.found:
            raise FsdbError("节点未找到: %s" % hier)
        fpath = os.path.join(out_dir, _safe(name) + ".txt")
        lines = ["%d %d %s" % (beat, t, ws.value_at(t)) for beat, t in enumerate(sampled)]
        with open(fpath, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        out_nodes.append(
            {
                "name": name,
                "path": hier,
                "resolved": ws.resolved,
                "width": ws.width,
                "file": fpath,
                "lines": len(lines),
            }
        )
    return _json(
        {
            "fsdb": fs.path,
            "out_dir": os.path.abspath(out_dir),
            "clock": res.clock or clock,
            "edge": edge,
            "valid": valid,
            "start": int(start) if start is not None else None,
            "end": int(end) if end is not None else None,
            "clock_edges": len(edges),
            "beats": len(sampled),
            "format": "<beat> <time> <value>（拍号按 valid 放行的拍从 0 编号；值为 fsdbq 原始值）",
            "nodes": out_nodes,
        }
    )


# ------------------------------------------------------------------ 时间窗 / 波形对比


def _time_to_int(fsdb_path: str, value, cfg: Optional[Config] = None) -> Optional[int]:
    """时间参数：纯数字按 fsdb 原值；带单位（``100ns``）按该文件 timescale 换算。"""
    if value is None:
        return None
    s = str(value).strip()
    try:
        return int(s)
    except ValueError:
        pass
    from .fsdb import open_fsdb
    from .wavedrom import parse_time_with_timescale

    fs = open_fsdb(fsdb_path, cfg or load_config())
    unit = fs.info().get("scale_unit") or "1ps"
    return int(parse_time_with_timescale(s, unit))


def _dur_to_int(fsdb_path: str, value) -> int:
    v = _time_to_int(fsdb_path, value)
    if v is None:
        return 0
    return max(0, int(v))


def fsdb_windows(
    path: str,
    expr: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    min_duration: Optional[str] = None,
    limit: int = 200,
) -> str:
    """时间窗搜索：布尔表达式在波形里何时成立，返回**区间**而不是值流。

    表达式口径见 ``eda_mcp/predicate.py``：信号用层次全路径，支持
    ``== != === !== < <= > >= && || ! & | ^``、位选 ``sig[3]``、
    部分选择 ``sig[7:4]``、三元 ``c ? a : b`` 与 SV 字面量（``8'hFF``）。
    含 x/z 的时段记为 undecidable 并单列时长，**绝不计入命中**——
    "没找到"与"全程不可决"可区分。start/end 缺省为全波形；
    ``100ns`` 形式按文件 timescale 换算，纯数字按 fsdb 原值。
    """
    from .fsdb import open_fsdb
    from .timequery import find_time_windows

    fs = open_fsdb(path, load_config())
    t0 = _time_to_int(path, start)
    t1 = _time_to_int(path, end)
    if t0 is None or t1 is None:
        lo, hi = fs.time_range()
        t0 = lo if t0 is None else t0
        t1 = hi if t1 is None else t1
    res = find_time_windows(
        fs, expr, int(t0), int(t1),
        min_duration=_dur_to_int(path, min_duration),
        max_hits=max(1, int(limit)),
    )
    return _json(res)


def fsdb_diff(
    paths: List[str],
    signals: Optional[List[str]] = None,
    signal_filter: Optional[str] = None,
    after: Optional[str] = None,
    before: Optional[str] = None,
    clock: Optional[str] = None,
    max_signals: int = 512,
    max_report: int = 50,
) -> str:
    """N 份 FSDB 的**首分歧定位**：第一处不一致的时刻 + 按分歧时间排序的信号。

    回归调试第一入口：pass/fail 两份波形一比，最早分歧者才是嫌疑人，其后的
    差异多半是下游传染。>2 份时给分歧簇（按值把文件分组：3 份一致 + 1 份独走
    → 嫌疑在独走那份的激励）。给 ``clock`` 时只在时钟沿比较（滤沿间毛刺）。
    分歧信号可直接接 ``npi trace`` / ``dbg trace`` 做因果回溯。
    """
    from .diffwave import first_divergence

    cfg = load_config()
    a = _time_to_int(paths[0], after, cfg) if after is not None else 0
    b = _time_to_int(paths[0], before, cfg)
    res = first_divergence(
        [str(p) for p in paths],
        signals=[str(s) for s in signals] if signals else None,
        signal_filter=signal_filter,
        after=int(a or 0),
        before=b,
        clock=clock,
        max_signals=max(1, int(max_signals)),
        max_report=max(1, int(max_report)),
        fsdbq=cfg.fsdbq(),
    )
    return _json(res)


def npi_trace_value(
    design_id: str,
    fsdb: str,
    signal: str,
    time: str,
    depth: int = 6,
    x_only: bool = False,
    max_nodes: int = 200,
) -> str:
    """沿驱动链反向遍历，**每个节点带该时刻真实波形值**（静态×动态联立）。

    signal 给 FSDB 层次路径（调试器命名空间），自动映射进设计命名空间。
    x_only=True 是 X 根因口径：只沿值为 x/z 的分支走，``x_roots`` 是值为
    x/z 且不再有信号驱动的叶子候选。连续赋值驱动的节点附语句语境
    （file:line + 反编译）；**过程驱动（always）没有语句语境**——Verdi NPI
    无头模式拿不到语句体，如实缺省，不装作有。
    """
    from .fsdb import open_fsdb
    from .join import JoinError, map_target, trace_value

    cfg = load_config()
    cli = _design(design_id)
    fs = open_fsdb(fsdb, cfg)
    t = _time_to_int(fsdb, time, cfg)
    if t is None:
        return _json({"status": "error", "error_type": "invalid_argument",
                      "error": "缺少 time（如 85000 或 85ns）"})
    try:
        mapping = map_target(fs, cli, signal)
    except JoinError as exc:
        return _json({"status": "error", "error_type": "map_failed", "error": str(exc)})
    res = trace_value(fs, cli, mapping, signal, int(t), depth=int(depth),
                      x_only=bool(x_only), max_nodes=int(max_nodes))
    return _json(res)


def npi_active_drivers(
    design_id: str,
    fsdb: str,
    signal: str,
    time: str,
    clock: Optional[str] = None,
    edge: str = "posedge",
) -> str:
    """某一拍哪条驱动在起作用：驱动值与目标值逐条分类。

    match=与目标值一致（活跃候选）；differ=不一致；undecidable=x/z；
    constant=常量驱动；missing=波形里查不到。目标是过程驱动的寄存器时
    **强烈建议给 clock**：寄存器在沿上采集，不给 clock 只能按 t 时刻
    组合值评估，回复里的 ``capture_note`` 会说明采用了哪种口径。
    """
    from .fsdb import open_fsdb
    from .join import JoinError, active_drivers, map_target

    cfg = load_config()
    cli = _design(design_id)
    fs = open_fsdb(fsdb, cfg)
    t = _time_to_int(fsdb, time, cfg)
    if t is None:
        return _json({"status": "error", "error_type": "invalid_argument",
                      "error": "缺少 time（如 81500 或 81.5ns）"})
    try:
        mapping = map_target(fs, cli, signal)
    except JoinError as exc:
        return _json({"status": "error", "error_type": "map_failed", "error": str(exc)})
    res = active_drivers(fs, cli, mapping, signal, int(t),
                         clock=clock, edge=edge)
    return _json(res)


def npi_state_transitions(
    design_id: str,
    fsdb: str,
    signal: str,
    clock: Optional[str] = None,
    edge: str = "posedge",
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = 200,
) -> str:
    """状态寄存器的**实际转移表**：发生过的 (from→to)、次数、首现时刻。

    这不是覆盖率：没有"应该有"的分母，没出现的状态可能是不可达、可能是
    激励缺口，一次波形区分不了——只报事实。给 ``clock`` 时附每个转移首现
    **采集沿**上的驱动值（诊断"谁把它推进这个状态"的第一手数据）。
    """
    from .fsdb import open_fsdb
    from .join import JoinError, map_target, state_transitions

    cfg = load_config()
    cli = _design(design_id)
    fs = open_fsdb(fsdb, cfg)
    s = _time_to_int(fsdb, start, cfg)
    e = _time_to_int(fsdb, end, cfg)
    if s is None or e is None:
        lo, hi = fs.time_range()
        s = lo if s is None else s
        e = hi if e is None else e
    try:
        mapping = map_target(fs, cli, signal)
    except JoinError as exc:
        return _json({"status": "error", "error_type": "map_failed", "error": str(exc)})
    res = state_transitions(fs, cli, mapping, signal, clock=clock, edge=edge,
                            start=int(s), end=int(e), limit=int(limit))
    return _json(res)


# ------------------------------------------------------------------ NPI 设计模型


def _design(design_id: str):
    """取已存在的设计 daemon（未启动则按 state 里的元信息重启）。"""
    from .daemon import DesignDaemon, designs_root
    from .npi import NpiClient

    d = DesignDaemon(design_id, cfg=load_config(), root=designs_root(load_config()))
    if not d.alive():
        d.start()
    return NpiClient(d)


def npi_open_design(
    design_id: str,
    files: Optional[List[str]] = None,
    filelist: Optional[str] = None,
    top: Optional[str] = None,
    sv: bool = True,
) -> str:
    """打开（或复用）一个设计模型温进程：debImport 一次、长期服务。

    冷启动约 2~30 s（随设计规模），之后每次查询约 10 ms。
    files 给源码文件列表，或 filelist 给 .f 文件清单，二者至少一个。
    """
    from .npi import connect

    cli = connect(design_id, cfg=load_config(), files=files, filelist=filelist, top=top, sv=sv)
    return _json({"design": cli.daemon.info().to_dict(), "ping": cli.ping()})


def npi_list_designs() -> str:
    """列出本机全部设计 daemon（含是否存活、display、文件清单）。"""
    from .daemon import list_designs

    return _json([d.to_dict() for d in list_designs(load_config())])


def npi_close_design(design_id: str) -> str:
    """关闭并回收一个设计 daemon。"""
    from .daemon import close_design

    return _json({"design_id": design_id, "closed": close_design(design_id, load_config())})


def npi_hierarchy(
    design_id: str,
    root: Optional[str] = None,
    max_depth: Optional[int] = None,
    pattern: Optional[str] = None,
) -> str:
    """RTL 层次树（模块/实例，含定义名与源文件行号）。

    root 缺省从顶层模块开始；max_depth 限深；pattern 为通配裁剪。
    一次返回整棵树，避免逐节点往返。
    """
    cli = _design(design_id)
    nodes = cli.hierarchy(root=root, max_depth=max_depth, pattern=pattern)
    return _json({"design_id": design_id, "count": len(nodes),
                  "nodes": [n.to_dict() for n in nodes]})


def npi_object(design_id: str, path: str) -> str:
    """按全路径查一个对象（模块/实例/端口/网络/寄存器/参数）的属性。

    返回类型、位宽与左右界、方向、网络类型、源文件与行号、源码原文。
    """
    cli = _design(design_id)
    return _json(cli.object(path).to_dict())


def npi_module(design_id: str, path: str) -> str:
    """模块/实例详情：端口、内部网络与寄存器、参数、子实例（按类分组去重）。"""
    cli = _design(design_id)
    return _json(cli.module(path))


def npi_find(design_id: str, pattern: str, limit: int = 200) -> str:
    """按通配搜索信号/参数（如 "*cnt*"、"o_*"），返回全路径与位宽。"""
    cli = _design(design_id)
    objs = cli.find(pattern, limit=limit)
    return _json({"design_id": design_id, "count": len(objs),
                  "objects": [o.to_dict() for o in objs]})


def npi_trace(design_id: str, signal: str, direction: str = "both", limit: int = 200) -> str:
    """elaboration 后的真实驱动/负载追踪（NPI L1，零编译）。

    direction 取 driver|load|both。结果为完整层次路径；
    常量类句柄以 [unnamed:<type>] 标注（无层次名）。
    """
    cli = _design(design_id)
    hits = cli.trace(signal, direction=direction, limit=limit)
    return _json({"design_id": design_id, "signal": signal, "count": len(hits),
                  "hits": [h.to_dict() for h in hits]})


def npi_equivalent(design_id: str, signal: str) -> str:
    """等价信号查询（电气等价的一组信号）。"""
    cli = _design(design_id)
    hits = cli.equivalent(signal)
    return _json({"design_id": design_id, "signal": signal,
                  "hits": [h.to_dict() for h in hits]})



# ------------------------------------------------------------------ 作业管理


def _jobs(cfg=None):
    from .jobs import JobManager

    return JobManager(cfg or load_config())


def _verdict(cfg, job_id: str):
    """对 sim/syn/sta/lint 作业附上流程判定。"""
    try:
        job = _jobs(cfg).get(job_id)
    except Exception:  # noqa: BLE001
        return None
    step = (job.extra or {}).get("step")
    try:
        if step == "run":
            from .sim import sim_summary

            return sim_summary(cfg, job_id)
        if step in ("syn", "sta"):
            from .syn import report_verdict

            return report_verdict(cfg, job_id)
        if step == "lint":
            from .sim import nlint_result

            return nlint_result(cfg, job_id)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
    return None


def job_list(limit: int = 20, state: Optional[str] = None) -> str:
    """近期作业列表（state 取 running|completed|failed|killed）。"""
    jobs = _jobs().list(limit=limit, state=state)
    return _json({"count": len(jobs), "jobs": [j.to_dict() for j in jobs]})


def job_status(job_id: str) -> str:
    """作业状态：state/退出码/耗时，并附流程判定（仿真 RESULT、综合 STA 报告）。"""
    cfg = load_config()
    job = _jobs(cfg).get(job_id)
    out = job.to_dict()
    v = _verdict(cfg, job_id)
    if v is not None:
        out["verdict_detail"] = v
    return _json(out)


def job_log(job_id: str, tail_lines: int = 200, grep: Optional[str] = None) -> str:
    """日志切片（**避免把整份编译日志塞进上下文**）；grep 为正则。"""
    text = _jobs().log(job_id, tail_lines=tail_lines, grep=grep)
    return _json({"job_id": job_id, "lines": len(text.splitlines()), "text": text})


def job_kill(job_id: str) -> str:
    """终止作业（含整个进程组）。"""
    return _json(_jobs().kill(job_id).to_dict())


def _job_reply(job, cfg, wait_seconds: float):
    from .jobs import JobManager

    if wait_seconds and wait_seconds > 0:
        job = JobManager(cfg).wait(job.id, timeout=wait_seconds)
    out = job.to_dict()
    v = _verdict(cfg, job.id)
    if v is not None:
        out["verdict_detail"] = v
    return _json(out)


# ------------------------------------------------------------------ VCS 仿真


def sim_compile(
    scenario: str,
    sys_name: Optional[str] = None,
    module: Optional[str] = None,
    wave: bool = False,
    wave_vcd: bool = False,
    cov: bool = False,
    defines: Optional[List[str]] = None,
    extra_args: Optional[List[str]] = None,
    wait_seconds: float = 0,
) -> str:
    """VCS 编译（对齐框架 `run sim` 场景 A/B/C）。

    scenario: A 子系统级（sys_name）/ B 子系统内模块级（sys_name+module）/
    C 公共 IP 模块级（module）。wave=True 走 FSDB（自动带 +nolibcell 与 PLI），
    wave_vcd=True 退回 VCD。wait_seconds>0 时同步等待。
    """
    from .sim import submit_sim_compile

    cfg = load_config()
    job = submit_sim_compile(cfg, scenario, sys_name=sys_name, module=module,
                             wave=wave, wave_vcd=wave_vcd, cov=cov,
                             defines=defines, extra_args=extra_args)
    return _job_reply(job, cfg, wait_seconds)


def sim_run(
    scenario: str,
    sys_name: Optional[str] = None,
    module: Optional[str] = None,
    tc: Optional[str] = None,
    seed: Optional[int] = None,
    timeout_us: Optional[int] = None,
    cov: bool = False,
    wall_timeout_s: int = 3600,
    extra_args: Optional[List[str]] = None,
    wait_seconds: float = 0,
) -> str:
    """运行 simv（需先 sim_compile）；退出码不可靠，用 sim_summary 判 PASS/FAIL。"""
    from .sim import submit_sim_run

    cfg = load_config()
    job = submit_sim_run(cfg, scenario, sys_name=sys_name, module=module, tc=tc,
                         seed=seed, timeout_us=timeout_us, cov=cov,
                         wall_timeout_s=wall_timeout_s, extra_args=extra_args)
    return _job_reply(job, cfg, wait_seconds)


def sim_summary(job_id: str) -> str:
    """解析仿真日志给出 PASS/FAIL（按 log 里的 RESULT 行，不看退出码）。"""
    from .sim import sim_summary as _impl

    return _json(_impl(load_config(), job_id))


def sim_clean(scenario: str, sys_name: Optional[str] = None, module: Optional[str] = None) -> str:
    """清理编译产物（保留日志与波形）。"""
    from .sim import sim_clean as _impl

    return _json({"removed": _impl(load_config(), scenario, sys_name, module)})


# ------------------------------------------------------------------ nLint


def lint_run(files: List[str], wait_seconds: float = 60) -> str:
    """nLint 静态检查（仅可综合 RTL；TB 代码不做 lint 工具检查）。"""
    from .sim import submit_lint

    cfg = load_config()
    job = submit_lint(cfg, list(files))
    return _job_reply(job, cfg, wait_seconds)


# ------------------------------------------------------------------ DC / PT


def syn_run(
    target: str,
    top: Optional[str] = None,
    lib: str = "std",
    sdc: Optional[str] = None,
    tcl: Optional[str] = None,
    wall_timeout_s: int = 3600,
    wait_seconds: float = 0,
) -> str:
    """DC 逻辑综合。target 为子系统名（RTL 取 <sys>/rtl/）或 pub_code（须给 top）。

    lib 取 std|stdht（对应 yourtech_tt.db / yourtechHT_tt.db）。判定读报告不看退出码。
    """
    from .syn import submit_syn

    cfg = load_config()
    job = submit_syn(cfg, target, top=top, lib=lib, sdc=sdc, tcl=tcl,
                     wall_timeout_s=wall_timeout_s)
    return _job_reply(job, cfg, wait_seconds)


def sta_run(
    target: str,
    top: Optional[str] = None,
    corner: str = "tt",
    netlist: Optional[str] = None,
    sdc: Optional[str] = None,
    tcl: Optional[str] = None,
    wall_timeout_s: int = 3600,
    wait_seconds: float = 0,
) -> str:
    """PT 静态时序分析（需先 syn_run 产出网表与 SDC）。corner 取 tt|ss|ff。"""
    from .syn import submit_sta

    cfg = load_config()
    job = submit_sta(cfg, target, top=top, corner=corner, netlist=netlist, sdc=sdc,
                     tcl=tcl, wall_timeout_s=wall_timeout_s)
    return _job_reply(job, cfg, wait_seconds)


# ------------------------------------------------------------------ 逃生舱


def shell_run(command: str, cwd: Optional[str] = None, timeout_s: int = 60) -> str:
    """逃生舱：直接在服务器上执行 shell 命令。

    **默认关闭**（security.allow_shell=false）；开启后仍受路径白名单与超时约束。
    """
    import subprocess

    from .workspace import WorkspaceError, guard_path

    cfg = load_config()
    if not cfg.get("security.allow_shell"):
        return _json({
            "error": "shell_run 已禁用",
            "how_to_enable": "在 ~/.config/eda-mcp/config.toml 写 [security] allow_shell = true",
        })
    try:
        workdir = guard_path(cfg, cwd, True) if cwd else (cfg.path("eda.workspace_root") or os.getcwd())
    except WorkspaceError as exc:
        return _json({"error": str(exc)})
    try:
        proc = subprocess.run(
            ["bash", "-lc", command], cwd=workdir, timeout=int(timeout_s),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            universal_newlines=True,
        )
    except subprocess.TimeoutExpired:
        return _json({"error": "超时（%ss）" % timeout_s, "cwd": workdir})
    return _json({
        "rc": proc.returncode, "cwd": workdir,
        "output": (proc.stdout or "")[-20000:],
    })


# ------------------------------------------------------------------ 工具组
#
# 哪个工具属于哪一组。未启用组的工具不注册（MCP 工具列表与 CLI 子命令都按此过滤）；
# ``security.enabled_groups`` 未设置时全部启用，与上游现状等价。
TOOL_GROUPS = {
    "eda_env_info": "env",
    "eda_doctor": "env",
    "fsdb_info": "fsdb",
    "fsdb_scopes": "fsdb",
    "fsdb_signals": "fsdb",
    "fsdb_find": "fsdb",
    "fsdb_value": "fsdb",
    "fsdb_wave": "fsdb",
    "fsdb_check": "fsdb",
    "wave_gen": "wave",
    "wave_list_signals": "wave",
    "wave_query": "wave",
    "wave_extract": "wave",
    "fsdb_windows": "wave",
    "fsdb_diff": "wave",
    "npi_trace_value": "npi",
    "npi_active_drivers": "npi",
    "npi_state_transitions": "npi",
    "npi_open_design": "npi",
    "npi_close_design": "npi",
    "npi_list_designs": "npi",
    "npi_hierarchy": "npi",
    "npi_object": "npi",
    "npi_module": "npi",
    "npi_find": "npi",
    "npi_trace": "npi",
    "npi_equivalent": "npi",
    "job_list": "flow",
    "job_status": "flow",
    "job_log": "flow",
    "job_kill": "flow",
    "sim_compile": "flow",
    "sim_run": "flow",
    "sim_summary": "flow",
    "sim_clean": "flow",
    "lint_run": "flow",
    "syn_run": "flow",
    "sta_run": "flow",
    "shell_run": "shell",
}


def tool_functions(cfg: Optional[Config] = None) -> List[Any]:
    """启用的 MCP 工具（两种后端共用同一份实现）；未启用组的工具不注册。"""
    groups = enabled_groups(cfg)
    return [
        fn for fn in (
            eda_env_info,
            eda_doctor,
            fsdb_info,
            fsdb_scopes,
            fsdb_signals,
            fsdb_find,
            fsdb_value,
            fsdb_wave,
            fsdb_check,
            wave_gen,
            wave_list_signals,
            wave_query,
            wave_extract,
            fsdb_windows,
            fsdb_diff,
            npi_open_design,
            npi_close_design,
            npi_list_designs,
            npi_hierarchy,
            npi_object,
            npi_module,
            npi_find,
            npi_trace,
            npi_equivalent,
            npi_trace_value,
            npi_active_drivers,
            npi_state_transitions,
            # 作业与流程（二期）
            job_list,
            job_status,
            job_log,
            job_kill,
            sim_compile,
            sim_run,
            sim_summary,
            sim_clean,
            lint_run,
            syn_run,
            sta_run,
            shell_run,
        )
        if TOOL_GROUPS.get(fn.__name__) in groups
    ]


def make_server(cfg: Optional[Config] = None):
    cls, kind = _sdk()
    if kind == "builtin":
        # 零依赖回落：EDA 服务器常常没有 pip 也不能联网
        from . import __version__
        from .mcp_stdio import StdioServer

        srv = StdioServer("eda-mcp", __version__)
        for fn in tool_functions(cfg):
            srv.add_tool(fn)
        return srv, kind

    try:
        srv = cls("eda-mcp")
    except TypeError:  # 某些版本只接受关键字
        srv = cls(name="eda-mcp")
    for fn in tool_functions(cfg):
        srv.tool(fn)
    return srv, kind


def main(
    transport: Optional[str] = None,
    host: Optional[str] = None,
    port: Optional[int] = None,
) -> int:
    cfg = load_config()
    srv, kind = make_server(cfg)
    t = (transport or cfg.get("server.transport", "stdio") or "stdio").lower()
    if t in ("http", "streamable-http", "streamable_http"):
        if kind == "builtin":
            raise SystemExit(
                "HTTP 传输需要官方 MCP SDK（内置零依赖实现只支持 stdio）。\n"
                "  pip install 'eda-mcp[server]'   或   bash install/install.sh --vendor"
            )
        h = host or cfg.get("server.host", "127.0.0.1")
        p = int(port or cfg.get("server.port", 8710))
        settings = getattr(srv, "settings", None)
        if settings is not None:
            settings.host = h
            settings.port = p
        srv.run(transport="streamable-http")
    else:
        srv.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
