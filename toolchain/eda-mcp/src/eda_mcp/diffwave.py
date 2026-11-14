"""N 份 FSDB 波形的首分歧定位。

回归调试的第一入口：给同一设计的多份波形（典型是 pass/fail 两份），找出
**第一个不再一致的时刻**与**最早分歧的信号**——最早分歧者才是嫌疑人，
其后的差异多半是下游传染。

口径：

* **信号对齐**：默认以第一份文件的信号表为准（可加 filter 通配/显式 signals）；
  某信号在 ≥2 份文件里存在即参与比较，缺失的文件在该信号上记 null。
* **值比较**：按 4 值位串字面比较（x/z 参与比较，x≠1；两份都 x 视为一致），
  实数按数值比较。编码口径不同的文件（不同仿真器版本）可能整片"假分歧"，
  结果里以 ``value_encoding_note`` 提示。
* **时钟对齐采样**（可选 ``clock``）：只在时钟上升沿比较，滤掉沿间毛刺与
  非采样时刻的传输延迟差；不给 clock 则按事件时刻全量比较。
* **分歧簇**（>2 份时）：在首分歧时刻，按"各文件的值"把文件分成几簇
  （如 3 份一致 + 1 份独走 → 嫌疑在那 1 份的激励；2-2 分裂 → 配置差异）。

分歧信号可直接接 ``npi trace``（驱动链）与 ``dbg trace``（带值回溯）做因果回溯。
"""

from __future__ import annotations

import fnmatch
from typing import Dict, List, Optional, Sequence, Tuple

from .fsdb import Fsdb

__all__ = ["first_divergence"]

_MAX_SIGNALS_DEFAULT = 512
_MAX_REPORT_DEFAULT = 50


def _norm(raw: Optional[str]) -> Tuple[str, object]:
    """把 fsdbq 原始值归一成可比较的键：("b", bits) 或 ("r", float) 或 ("n", None)。"""
    if raw is None:
        return ("n", None)
    s = str(raw).strip().lower()
    if not s:
        return ("n", None)
    if s[0] == "r":
        try:
            return ("r", float(s[1:]))
        except ValueError:
            return ("b", s)
    if s[0] == "b":
        return ("b", s[1:].replace("_", ""))
    if set(s) <= set("01xz"):
        return ("b", s)
    try:
        return ("r", float(s))
    except ValueError:
        return ("b", s)


def _first_diff(changes_per_file: List[Optional[List[Tuple[int, str]]]],
                times: List[int]) -> Optional[int]:
    """在合并事件时刻序列上找第一份"值不一致"的时刻。

    changes_per_file[i] 为第 i 份文件该信号的值变序列（None = 该文件没有此信号）。
    """
    ptrs = [0] * len(changes_per_file)

    def value_at(i: int, t: int) -> Optional[str]:
        ch = changes_per_file[i]
        if ch is None:
            return None
        best = None
        lo, hi = 0, len(ch) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            if ch[mid][0] <= t:
                best = ch[mid][1]
                lo = mid + 1
            else:
                hi = mid - 1
        return best  # 无种子值 → None → 归一为 ("n", None)

    for t in times:
        vals = [value_at(i, t) for i in range(len(changes_per_file))]
        keys = [_norm(v) for v in vals]
        first = keys[0]
        if any(k != first for k in keys[1:]):
            return t
    return None


def _events_of(changes_per_file) -> List[int]:
    times = set()
    for ch in changes_per_file:
        if ch:
            times.update(t for t, _v in ch)
    return sorted(times)


def _clock_edges(fs: Fsdb, clock: str, after: int, before: int) -> List[int]:
    res = fs.wave([clock], clock=clock, clock_pattern=clock, t0=after, t1=before, max_changes=0)
    return sorted(set(res.rising or []))


def first_divergence(
    paths: Sequence[str],
    signals: Optional[Sequence[str]] = None,
    signal_filter: Optional[str] = None,
    after: int = 0,
    before: Optional[int] = None,
    clock: Optional[str] = None,
    max_signals: int = _MAX_SIGNALS_DEFAULT,
    max_report: int = _MAX_REPORT_DEFAULT,
    fsdbq: Optional[str] = None,
) -> dict:
    """比较 2..N 份 FSDB，返回首分歧时刻与按分歧时间排序的信号。

    **时间对齐口径**：回归里同一用例的多份波形各占自己的绝对时间窗
    （按用例接续落盘），所以先把每份波形按**自身 min_time** 平移到相对
    时间轴再比较；``after``/``before`` 是相对量（相对各自波形起点）。
    """
    paths = [str(p) for p in paths]
    if len(paths) < 2:
        return {"status": "error", "error_type": "need_two_files",
                "error": "至少要给两份 FSDB（pass/fail 或同设计多份运行）"}
    try:
        files = [Fsdb(p, fsdbq=fsdbq) for p in paths]
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error_type": "open_failed", "error": str(exc)}
    # 各文件自身的起点：绝对时间 → 相对时间（t - min_i）
    mins: List[int] = []
    for fs in files:
        try:
            lo, _hi = fs.time_range()
        except Exception:  # noqa: BLE001
            lo = 0
        mins.append(int(lo or 0))

    # 信号清单：显式 > 通配 > 第一份文件全量（截断）
    if signals:
        candidates = [str(s) for s in signals]
    else:
        base = files[0].signals()
        candidates = [s.hier for s in base]
        if signal_filter:
            pat = signal_filter if any(c in signal_filter for c in "*?[") else "*%s*" % signal_filter
            candidates = [s for s in candidates
                          if fnmatch.fnmatch(s, pat) or fnmatch.fnmatch(s.rsplit(".", 1)[-1], pat)]
        if len(candidates) > max_signals:
            candidates = sorted(candidates)[:max_signals]
    if clock and clock not in candidates:
        candidates = [clock] + candidates

    # 每份文件**一次** fsdbq 调用取全部候选信号（512 信号 × N 文件也不爆进程数）；
    # 取数窗口按各文件绝对时间换算（min_i + after .. min_i + before），取回后平移到相对轴
    changes_by_file: List[Dict[str, List[Tuple[int, str]]]] = []
    for i, fs in enumerate(files):
        t0 = mins[i] + max(0, int(after))
        t1 = (mins[i] + int(before)) if before is not None else None
        try:
            res = fs.wave(list(candidates), clock="none", t0=t0, t1=t1, max_changes=0)
        except Exception:  # noqa: BLE001
            res = None
        cmap: Dict[str, List[Tuple[int, str]]] = {}
        if res is not None:
            for ws in res.signals:
                if ws.found:
                    cmap[ws.requested] = [(t - mins[i], v) for (t, v) in ws.changes]
        changes_by_file.append(cmap)

    compared = 0
    skipped = 0
    rows: List[dict] = []
    edges: List[int] = []
    if clock:
        edges = [t - mins[0] for t in _clock_edges(files[0], clock,
                                                   mins[0] + max(0, int(after)),
                                                   (mins[0] + int(before)) if before is not None else None)]
    for hier in candidates:
        changes_per_file = [cmap.get(hier) for cmap in changes_by_file]
        have = sum(1 for ch in changes_per_file if ch is not None)
        if have < 2:
            skipped += 1
            continue
        compared += 1
        times = edges if clock else _events_of(changes_per_file)
        t_diff = _first_diff(changes_per_file, times)
        if t_diff is None:
            continue
        # 取首分歧时刻各文件的值（给证据）
        vals: List[Optional[str]] = []
        for ch in changes_per_file:
            if ch is None:
                vals.append(None)
                continue
            best = None
            for (t, v) in ch:
                if t <= t_diff:
                    best = v
                else:
                    break
            vals.append(best)
        rows.append({"hier": hier, "time": t_diff, "values": vals})

    if not rows:
        return {
            "status": "ok",
            "files": [f.path for f in files],
            "window": {"after": after, "before": before},
            "clock": clock,
            "compared": compared,
            "skipped": skipped,
            "first_divergence": None,
            "signals": [],
            "note": "没有发现分歧（或信号不在 ≥2 份文件里）",
        }
    rows.sort(key=lambda r: r["time"])
    first_t = rows[0]["time"]

    out_rows = rows[:max_report]

    # 分歧簇：>2 份文件时，按首分歧时刻的值把文件分组（取首分歧信号）
    groups = None
    if len(paths) > 2:
        top = rows[0]
        clusters: Dict[object, List[int]] = {}
        for i, v in enumerate(top["values"]):
            clusters.setdefault(_norm(v), []).append(i)
        if len(clusters) > 1:
            groups = {
                "signal": top["hier"],
                "time": top["time"],
                "clusters": [
                    {"files": idxs, "value": top["values"][idxs[0]]}
                    for idxs in clusters.values()
                ],
            }

    return {
        "status": "ok",
        "files": [f.path for f in files],
        "window": {"after": after, "before": before},
        "clock": clock,
        "compared": compared,
        "skipped": skipped,
        "first_divergence": first_t,
        "diverging_signals": len(rows),
        "signals": out_rows,
        "truncated_report": len(rows) > max_report,
        "groups": groups,
    }
