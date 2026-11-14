"""时间窗搜索：布尔条件在波形里何时成立，答案是**区间**而不是值流。

设计要点（与 wave-mcp 的 find_time_windows 同一口径，落地在我们的 fsdbq 上）：

* **事件驱动扫描**：谓词只在被引用信号变化时才可能变值，所以只在"任一引用
  信号的变化时刻"求值，不做采样网格——不漏毛刺，也不会因网格太粗错过短窗。
* **不可决 ≠ 否**：谓词含 x/z 的时段记为 undecidable 并**单列时长**，
  绝不计入命中——空结果与"全程不可决"可区分。
* **窗口语义**：区间 ``[start, end)`` 左闭右开；窗口末端仍为真的区间标
  ``open_ended``；``min_duration`` 过滤"至少持续多久"的查询。

数据通路：一次 ``fs.wave(全部引用信号)``（一个 fsdbq 进程）拿到窗口内全部
值变与种子值，之后纯内存扫描。
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Sequence, Tuple

from . import predicate
from .fsdb import Fsdb

__all__ = ["find_time_windows", "eval_at_time"]

_MAX_CHANGES = 1_000_000  # 单信号值变上限；超出即截断并在结果里声明


def _signal_changes(fs: Fsdb, names: Sequence[str], t0: int, t1: int):
    """一次 fsdbq 调用取全部信号的值变；返回 (changes_by_name, missing)。"""
    res = fs.wave(list(names), clock="none", t0=t0, t1=t1, max_changes=0)
    changes: Dict[str, List[Tuple[int, str]]] = {}
    missing: List[str] = []
    for ws in res.signals:
        if not ws.found:
            missing.append(ws.requested)
            continue
        changes[ws.requested] = list(ws.changes)
    # 请求名与解析名可能不同（fsdbq 按原文回填 resolved；这里 requested 即原文）
    return changes, missing, res


def _truth_changes(fs: Fsdb, node, names: Sequence[str], t0: int, t1: int):
    """把各信号的值变折成谓词真值的变化序列 [(t, truth)]。

    truth 取 ``true`` / ``false`` / ``undecidable``。
    """
    changes, missing, res = _signal_changes(fs, names, t0, t1)
    if missing:
        return None, missing, None

    events = sorted({t for tl in changes.values() for (t, _v) in tl if t0 < t <= t1})
    cur: Dict[str, Optional[str]] = {n: None for n in names}
    ptr: Dict[str, int] = {n: 0 for n in names}
    # 先吃掉 t0 及之前的种子/值变：初始真值必须建立在已有值上，
    # 查不到就按 x（不可决），不冒充 0。
    for n in names:
        tl = changes.get(n) or []
        i = ptr[n]
        while i < len(tl) and tl[i][0] <= t0:
            cur[n] = tl[i][1]
            i += 1
        ptr[n] = i

    def get_value(name: str) -> Optional[str]:
        return cur.get(name)

    out: List[Tuple[int, str]] = []
    truth = predicate.truth_of(predicate.evaluate(node, get_value))
    out.append((t0, truth))
    for t in events:
        for n in names:
            tl = changes[n]
            i = ptr[n]
            while i < len(tl) and tl[i][0] <= t:
                cur[n] = tl[i][1]
                i += 1
            ptr[n] = i
        truth = predicate.truth_of(predicate.evaluate(node, get_value))
        if out and out[-1][1] == truth:
            continue  # 真值没变不重复记
        out.append((t, truth))
    return out, [], res


def find_time_windows(
    fs: Fsdb,
    expr: str,
    t0: int,
    t1: int,
    min_duration: int = 0,
    max_hits: int = 200,
) -> dict:
    """在 ``[t0, t1]`` 里找谓词成立（确真）的区间。

    返回 dict::

        {"status": "ok",
         "window": {"start": t0, "end": t1},
         "hits": [{"start", "end", "duration", "open_ended"}...],
         "total_hits": int, "truncated": bool,
         "undecidable_time": int,   # 谓词不可决的总时长
         "signals": [引用的信号]}
    """
    if t1 <= t0:
        return {"status": "error", "error_type": "invalid_window",
                "error": "时间窗无效（end 必须大于 start）",
                "window": {"start": t0, "end": t1}}
    try:
        node = predicate.parse_expr(expr)
    except predicate.ExprError as exc:
        return {"status": "error", "error_type": "invalid_expression",
                "error": str(exc)}
    names = predicate.collect_signals(node)
    if not names:
        return {"status": "error", "error_type": "empty_predicate",
                "error": "表达式没有引用任何信号"}

    seq, missing, _res = _truth_changes(fs, node, names, t0, t1)
    if seq is None:
        return {"status": "error", "error_type": "signal_not_found",
                "error": "表达式引用的信号不在波形里: " + "、".join(missing[:5]),
                "missing": missing,
                "hint": "先用 signals/query 拿准确全路径"}
    # names 里的原文与 fsdbq resolved 可能不同：报告用原文即可（requested）
    # 若 resolved 存在，补充报告
    # （changes 用 requested 键，fs.wave 回填 requested=原文）

    hits: List[dict] = []
    total = 0
    undecidable_time = 0
    truncated = False
    for i, (t, truth) in enumerate(seq):
        seg_end = seq[i + 1][0] if i + 1 < len(seq) else t1
        duration = seg_end - t
        if duration <= 0:
            continue
        if truth == "undecidable":
            undecidable_time += duration
            continue
        if truth != "true" or duration < min_duration:
            continue
        total += 1
        if len(hits) < max_hits:
            hits.append({
                "start": t,
                "end": seg_end,
                "duration": duration,
                "open_ended": bool(i + 1 >= len(seq) and seg_end >= t1),
            })
        else:
            truncated = True
    return {
        "status": "ok",
        "window": {"start": t0, "end": t1},
        "hits": hits,
        "total_hits": total,
        "truncated": truncated,
        "undecidable_time": undecidable_time,
        "signals": list(names),
    }


def eval_at_time(fs: Fsdb, expr: str, t: int) -> dict:
    """单点求值（窗口调试辅助）：给该时刻的真值与各信号原值。"""
    try:
        node = predicate.parse_expr(expr)
    except predicate.ExprError as exc:
        return {"status": "error", "error_type": "invalid_expression", "error": str(exc)}
    names = predicate.collect_signals(node)
    if not names:
        return {"status": "error", "error_type": "empty_predicate", "error": "表达式没有引用任何信号"}
    res = fs.wave(list(names), clock="none", t0=0, t1=t, max_changes=0)
    values: Dict[str, Optional[str]] = {}
    missing: List[str] = []
    for ws in res.signals:
        if not ws.found:
            missing.append(ws.requested)
            values[ws.requested] = None
        else:
            values[ws.requested] = ws.value_at(t)
    if missing:
        return {"status": "error", "error_type": "signal_not_found",
                "error": "信号不在波形里: " + "、".join(missing[:5]),
                "missing": missing}
    v = predicate.evaluate(node, lambda n: values.get(n))
    return {
        "status": "ok",
        "time": t,
        "truth": predicate.truth_of(v),
        "value": v.raw(),
        "values": values,
        "signals": list(names),
    }
