"""``wave_gen`` / ``wave_list_signals`` / ``wave_query`` —— 波形转 WaveDrom。

入口参数语义与原 `aic_tool_trace` 完全一致（便于 `rules/waveform.md`
的渲染约定与既有规格书图无需改动）：

======================  ==========================================
``time`` + ``cycles``   以 ``time`` 为**中心**截取 ``cycles`` 个周期
``start`` + ``end``     截取区间（自动对齐到时钟上升沿）
``clock``               指定时钟；缺省先在信号表里找 ``*clk*``，再自动检测
``timescale``           手动指定；FSDB 缺省取文件的 ``scale_unit``
======================  ==========================================
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from typing import Dict, List, Optional, Sequence, Tuple

from .config import Config, load as load_config
from .fsdb import Fsdb, FsdbError, missing_path_message, open_fsdb
from .wavedrom import (
    SignalTable,
    WaveDrom,
    _value_at,
    align_time_window,
    format_data_label,
    list_signals_text,
    parse_time_with_timescale,
    query_signal_text,
)

__all__ = ["ensure_fsdb", "flip_segments", "wave_gen", "wave_list_signals", "wave_query"]

# 多 bit 数据标签只保留低 32 bit（见 wavedrom.format_data_label）；超过就丢了高位
LABEL_BITS = 32
# 翻转次数到这条线就在返回值里提示可用 `--summary flip`（默认不改变返回形状）
SUMMARY_HINT_FLIPS = 64


def _cfg(cfg: Optional[Config]) -> Config:
    return cfg if cfg is not None else load_config()


# ------------------------------------------------------------------ `-s` 通配与翻转段


def _is_glob(name: str) -> bool:
    """**只有显式通配才模糊**：出现 ``*`` ``?`` ``[`` 之一才算通配。"""
    return any(ch in name for ch in "*?[")


def _expand_globs(fs: Fsdb, names: Sequence[str]):
    """把 ``-s`` 里的显式通配按信号名展开；非通配名字原样保留。

    复用 ``Fsdb.signals(pattern=...)``——与 ``eda-mcp signals --pattern`` 同一口径，
    避免两套匹配语义。命中为空时原样保留，交给后面的精确解析报 not-found，不静默吞掉。
    返回 ``(展开后的名字列表, 展开明细)``。
    """
    out: List[str] = []
    expanded: List[Dict[str, str]] = []
    for name in names:
        if not _is_glob(name):
            if name not in out:
                out.append(name)
            continue
        try:
            hits = [sig.hier for sig in fs.signals(pattern=name)]
        except FsdbError:
            # 通配命中为空时 fsdbq 可能一行都不输出，_run 会当成错误——这里按"无命中"处理，
            # 名字原样保留交给精确解析报 not-found，报错信息才指向真正的原因。
            hits = []
        if not hits:
            if name not in out:
                out.append(name)
            continue
        for hier in hits:
            if hier not in out:
                out.append(hier)
            expanded.append({"requested": name, "resolved": hier})
    return out, expanded


def flip_segments(
    changes: Sequence[Tuple[int, str]],
    t0: int,
    t1: int,
    label: bool = True,
) -> List[List[object]]:
    """把窗口内的值变序列压成 ``[t0, t1, 值]`` 段——段内恒定，只列翻转时刻。

    对"恒值判读 / 翻转定位"类任务，这比每周期一个字符的 wavedrom ``wave`` 串
    信息密度高得多（长窗口尤甚）。``label=True`` 时值与 wave 里的数据标签同款。
    """
    segs: List[List[object]] = []
    cursor = t0
    value = _value_at(changes, t0)

    def emit(end: int) -> None:
        text = format_data_label(value) if label else value
        if segs and segs[-1][2] == text and segs[-1][1] == cursor:
            segs[-1][1] = end          # 值没变：并进上一段，不产生同值相邻段
        else:
            segs.append([cursor, end, text])

    for (when, val) in changes:
        if when <= t0:
            continue
        if when > t1:
            break
        emit(when)
        cursor, value = when, val
    if cursor < t1 or not segs:
        emit(t1)
    return segs


# ------------------------------------------------------------------ 源文件


def ensure_fsdb(source: str, cfg: Optional[Config] = None, cache_dir: Optional[str] = None) -> str:
    """FSDB 直接返回；VCD 用 ``vcd2fsdb`` 转成 FSDB 后返回其路径。"""
    src = os.path.abspath(os.path.expanduser(source))
    if not os.path.isfile(src):
        raise FsdbError(missing_path_message("波形文件不存在", source))
    if src.lower().endswith(".fsdb"):
        return src
    if not src.lower().endswith(".vcd"):
        # 不认识的扩展名交给 FFR 自己判
        return src

    c = _cfg(cfg)
    vcd2fsdb = c.which("eda.vcd2fsdb_bin")
    if not vcd2fsdb:
        raise FsdbError(
            "源文件是 VCD，但找不到 vcd2fsdb（请设置 eda.vcd2fsdb_bin 或改用 .fsdb）"
        )
    cache = os.path.expanduser(cache_dir or c.cache_dir())
    os.makedirs(cache, exist_ok=True)
    base = os.path.basename(src)[:-4] + ".fsdb"
    out = os.path.join(cache, base)
    if os.path.isfile(out) and os.path.getmtime(out) >= os.path.getmtime(src):
        return out
    proc = subprocess.run(
        [vcd2fsdb, src, "-o", out],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    if proc.returncode != 0 or not os.path.isfile(out):
        raise FsdbError("vcd2fsdb 失败 (rc=%d): %s" % (proc.returncode, proc.stdout.strip()))
    return out


# ------------------------------------------------------------------ wave_gen


def wave_gen(
    source: str,
    signals: Optional[Sequence[str]] = None,
    time: Optional[str] = None,
    cycles: int = 20,
    start: Optional[str] = None,
    end: Optional[str] = None,
    clock: Optional[str] = None,
    timescale: Optional[str] = None,
    out: Optional[str] = None,
    max_changes: Optional[int] = None,
    summary: Optional[str] = None,
    cfg: Optional[Config] = None,
) -> Dict[str, object]:
    """VCD/FSDB -> WaveDrom JSON。返回值含 ``json`` 文本与过程信息。

    ``summary='flip'`` 时每个信号额外给 ``segments``——窗口内的 ``[t0, t1, 值]``
    翻转段（段内恒定），用于长窗口的恒值判读与翻转定位。
    """
    c = _cfg(cfg)
    if summary not in (None, "", "flip"):
        raise ValueError("--summary 只支持 flip")
    if time and (start or end):
        raise ValueError("--time 与 --start/--end 互斥，请只使用一种方式")
    if (start is None) != (end is None):
        raise ValueError("--start 和 --end 必须同时指定")
    sig_list = list(signals or [])
    if not sig_list and not time and not (start and end):
        # 无信号、无时间窗也可以：退化为「自动检测时钟 + 空信号表」
        pass

    fsdb_path = ensure_fsdb(source, c)
    fs = open_fsdb(fsdb_path, c)
    info = fs.info()
    ts = timescale or info.get("scale_unit") or "1ns"

    table = SignalTable(fs.signals())

    # ---- `-s` 里的显式通配按信号名展开；非通配名字行为不变
    sig_list, glob_expanded = _expand_globs(fs, sig_list)

    # ---- 时钟：显式 > 信号表里的 clk > 自动检测
    clock_path: Optional[str] = None
    clock_id: Optional[int] = None
    clock_source = ""
    if clock:
        match, csig = table.resolve(clock)
        if not csig or not csig.is_single_bit:
            raise ValueError("指定时钟 '%s' 无效或非单 bit 信号" % clock)
        clock_path, clock_id, clock_source = clock, csig.idcode, "explicit"
    else:
        for p in sig_list:
            leaf = p.rsplit(".", 1)[-1].lower()
            if "clk" in leaf:
                match, s = table.resolve(p)
                if s and s.is_single_bit:
                    clock_path, clock_id, clock_source = p, s.idcode, "from-signals"
                    break
        if clock_path is None:
            probe = fs.wave([], clock="auto")
            if not probe.clock:
                raise ValueError("未检测到时钟信号，请用 clock= 手动指定")
            match, csig = table.resolve(probe.clock)
            clock_path = probe.clock
            clock_id = csig.idcode if csig else None
            clock_source = "auto-detected"

    # ---- 时钟沿（R/F 由 fsdbq 在 clock 模式下全时间段给出，不受窗口限制）
    clock_wave = fs.wave([], clock=clock_path)
    rising, falling = clock_wave.rising, clock_wave.falling
    if not rising:
        raise ValueError("时钟 '%s' 无上升沿" % clock_path)

    # ---- 时间窗
    if time:
        center = parse_time_with_timescale(time, ts)
        a_start, a_end = align_time_window(rising, -1, -1, center, int(cycles))
    elif start and end:
        s = parse_time_with_timescale(start, ts)
        e = parse_time_with_timescale(end, ts)
        if s > e:
            s, e = e, s
        a_start, a_end = align_time_window(rising, s, e, -1, int(cycles))
    else:
        a_start, a_end = align_time_window(rising, -1, -1, -1, int(cycles))

    # ---- 需要取值的信号（时钟恒渲染为 "p"，不需要它的值变）
    signal_order = [clock_path] + [p for p in sig_list if p != clock_path]
    resolved: List[Tuple[str, str, Optional[object]]] = []
    wanted: List[str] = []
    for p in signal_order:
        match, s = table.resolve(p)
        resolved.append((p, match, s))
        if s is not None and s.hier not in wanted:
            wanted.append(s.hier)

    limit = int(max_changes or c.get("fsdb.max_changes", 2000) or 2000)
    limit = max(limit, 2000000) if max_changes is None else int(max_changes)
    wave_res = fs.wave(
        wanted, clock=clock_path, t0=a_start, t1=a_end, max_changes=limit
    )
    changes_of: Dict[str, Sequence[Tuple[int, str]]] = {}
    truncated: List[str] = []
    for ws in wave_res.signals:
        if ws.resolved:
            changes_of[ws.resolved] = ws.changes
            if ws.truncated:
                truncated.append(ws.resolved)

    # ---- 生成
    full_log_path = None
    full_log = None
    if out:
        root, _ext = os.path.splitext(out)
        full_log_path = root + "_full_data.log"
        full_log = open(full_log_path, "w")
    try:
        gen = WaveDrom(table, clock_path, clock_id, rising, falling, changes_of.__getitem__)
        text = gen.generate(signal_order, a_start, a_end, full_log=full_log)
        n_cycles = gen.cycle_count(a_start, a_end)
    finally:
        if full_log is not None:
            full_log.close()

    if out:
        with open(out, "w") as fh:
            fh.write(text)

    detail = []
    width_truncated: List[str] = []
    max_flips = 0
    for (p, match, s) in resolved:
        width = s.width if s else None
        over = bool(width and width > LABEL_BITS)
        if over and s.hier not in width_truncated:
            width_truncated.append(s.hier)
        if s is not None:
            max_flips = max(max_flips, len(changes_of.get(s.hier) or []))
        detail.append(
            {
                "requested": p,
                "match": match or "not-found",
                "resolved": s.hier if s else None,
                "width": width,
                "label_bits": (min(width, LABEL_BITS) if width else None),
                "label_truncated": over,
                "is_clock": bool(s and clock_id is not None and s.idcode == clock_id),
            }
        )

    segments: Dict[str, List[List[object]]] = {}
    if summary == "flip":
        for (_p, _match, s) in resolved:
            if s is None or (clock_id is not None and s.idcode == clock_id):
                continue
            segments[s.hier] = flip_segments(changes_of.get(s.hier) or [], a_start, a_end)

    result: Dict[str, object] = {
        "json": text,
        "out": out,
        "full_data_log": full_log_path,
        "source": fsdb_path,
        "timescale": ts,
        "clock": clock_path,
        "clock_source": clock_source,
        "window": {"start": a_start, "end": a_end},
        "cycles": n_cycles,
        "signals": detail,
        "truncated": truncated,
        "bytes": len(text.encode("utf-8")),
        "glob_expanded": glob_expanded,
        "width_truncated": width_truncated,
        "summary": summary or "",
        "segments": segments,
    }
    if not summary and max_flips >= SUMMARY_HINT_FLIPS:
        result["summary_hint"] = (
            "有信号翻转 %d 次，wavedrom 的 wave 串会很长；"
            "做恒值判读或翻转定位可加 --summary flip 只取翻转段" % max_flips
        )
    return result


# ------------------------------------------------------------------ 列表 / 查询


def wave_list_signals(source: str, cfg: Optional[Config] = None) -> Dict[str, object]:
    """列出波形内全部信号（等价 ``aic_tool_trace --list-signals``）。"""
    c = _cfg(cfg)
    fsdb_path = ensure_fsdb(source, c)
    fs = open_fsdb(fsdb_path, c)
    info = fs.info()
    signals = fs.signals()
    kind = "VCD" if fsdb_path.lower().endswith(".vcd") else "FSDB"
    return {
        "source": fsdb_path,
        "timescale": info.get("scale_unit", ""),
        "sim_version": info.get("sim_version", ""),
        "sim_date": info.get("sim_date", ""),
        "min_time": info.get("min_time_int", 0),
        "max_time": info.get("max_time_int", 0),
        "count": len(signals),
        "signals": [s.to_dict() for s in signals],
        "text": list_signals_text(signals, title="%s 中的信号列表" % kind),
    }


def wave_query(source: str, name: str, cfg: Optional[Config] = None) -> Dict[str, object]:
    """查信号（等价 ``aic_tool_trace --query``）。"""
    c = _cfg(cfg)
    fsdb_path = ensure_fsdb(source, c)
    fs = open_fsdb(fsdb_path, c)
    table = SignalTable(fs.signals())
    results = table.query(name)
    return {
        "source": fsdb_path,
        "query": name,
        "match_type": "exact" if "." in name else "fuzzy",
        "count": len(results),
        "signals": [s.to_dict() for s in results],
        "text": query_signal_text(results, name),
    }
