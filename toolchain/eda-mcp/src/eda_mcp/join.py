"""FSDB × NPI 联立层：静态驱动关系 × 波形真实值。

回答 wave-mcp 式的因果问题，落在我们的底座上（Verdi NPI 温进程 + fsdbq）：

* :func:`map_target`   —— FSDB 层次路径 → NPI 命名空间映射（最短可解析后缀 + 位宽核对）。
* :func:`trace_value`  —— 沿驱动链反向遍历，每个节点带该时刻真实 FSDB 值；
  ``x_only=True`` 退化为 :func:`trace_x`（只走 x/z 分支，找 X 根因）。
* :func:`active_drivers` —— 某一拍哪条驱动在起作用：按值一致分类
  （match/differ/undecidable/constant/missing）；寄存器给 ``clock`` 时按
  **采样沿时刻**取驱动值（过程赋值是沿上采集，不是 t 时刻组合值）。
* :func:`state_transitions` —— 状态寄存器的实际转移表（次数/首现时刻），
  给 ``clock`` 时附每个转移首现沿上的驱动值。

**已知边界（如实声明，不装作没有）**：Verdi NPI 无头模式（V-2023.12 实测）
拿不到 always/initial 的过程赋值语句体，所以过程驱动只有"驱动信号 + 采集沿
上的值"，没有 wave-mcp 那样的门控条件树求值；连续赋值语句语境（file:line、
语句反编译）由 :meth:`NpiClient.stmtmap` 提供并自动挂到对应节点上。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from .fsdb import Fsdb
from .npi import NpiClient, NpiError
from .predicate import value_from_fsdb

__all__ = [
    "Mapping",
    "map_target",
    "trace_value",
    "active_drivers",
    "state_transitions",
]


class JoinError(RuntimeError):
    pass


def has_xz_raw(raw: Optional[str]) -> bool:
    v = value_from_fsdb(raw)
    return v.has_xz()


def _same_value(a: Optional[str], b: Optional[str]) -> bool:
    """两个 fsdbq 原始值是否等值：可决时按数值（跨位宽补齐），否则按字面。"""
    va, vb = value_from_fsdb(a), value_from_fsdb(b)
    if va.has_xz() or vb.has_xz():
        return va.raw() == vb.raw()
    ia, ib = va.int_or_none(), vb.int_or_none()
    if ia is None or ib is None:
        return va.raw() == vb.raw()
    return ia == ib


# ------------------------------------------------------------------ 路径映射

class Mapping:
    """FSDB 前缀 ↔ NPI 命名空间的单向映射。

    FSDB 路径 = ``fsdb_prefix + 子树路径``；当 DUT 子树**不含**设计顶层模块
    名段时（实测 ``tb.u_dut.gen_w08`` ↔ ``demo_sys_top.gen_w08``），
    ``top_segment`` 记录需要插拔的那一段：FSDB→NPI 时补上，NPI→FSDB 时剥掉。
    ``fsdb_prefix`` 以 "." 结尾；目标在 DUT 顶层之上时 prefix 可为 ""。
    """

    def __init__(self, fsdb_prefix: str, fsdb_target: str, npi_target: str,
                 top_segment: str = ""):
        self.fsdb_prefix = fsdb_prefix
        self.fsdb_target = fsdb_target
        self.npi_target = npi_target
        self.top_segment = top_segment

    def fsdb(self, npi_path: str) -> str:
        body = npi_path
        if self.top_segment and body.startswith(self.top_segment + "."):
            body = body[len(self.top_segment) + 1:]
        elif self.top_segment and body == self.top_segment:
            body = ""
        if not self.fsdb_prefix:
            return body
        return self.fsdb_prefix + body

    def npi(self, fsdb_path: str) -> str:
        body = fsdb_path
        if self.fsdb_prefix and fsdb_path.startswith(self.fsdb_prefix):
            body = fsdb_path[len(self.fsdb_prefix):]
        if (self.top_segment and body
                and not body.startswith(self.top_segment + ".")
                and body != self.top_segment):
            return self.top_segment + "." + body
        return body

    def to_dict(self) -> Dict[str, Any]:
        return {"fsdb_prefix": self.fsdb_prefix, "fsdb_target": self.fsdb_target,
                "npi_target": self.npi_target, "top_segment": self.top_segment}


def map_target(fs: Fsdb, npi: NpiClient, fsdb_path: str) -> Mapping:
    """把一个 FSDB 层次路径映射进 NPI 命名空间。

    FSDB 的 DUT 子树**不一定**含设计顶层模块名段（实测：``tb.u_dut.gen_w08``
    ↔ NPI ``demo_sys_top.gen_w08``），所以对每级后缀试两种形式：
    ``<后缀>`` 与 ``<设计顶层>.<后缀>``；能解析且位宽与 FSDB 一致（或一边
    未知）即锁定——最短可解析后缀对应的映射才能覆盖整个 DUT 子树。
    """
    parts = [p for p in str(fsdb_path).split(".") if p]
    if not parts:
        raise JoinError("空的目标路径")
    top = _design_top(npi)
    fsdb_width = _fsdb_width(fs, fsdb_path)
    tried: List[Dict[str, Any]] = []
    fallback: Optional[Mapping] = None
    # 两遍策略：第一遍要求位宽一致（排除同名浅层信号的误配）；NPI 的位宽推断
    # 对参数化声明（源码行无字面量 [msb:lsb]）可能差 1（range_of 用 npiSize 当
    # 左界，实测 [WIDTH:0] 报成 [9:0]），所以第二遍放宽为"能解析即取"，仍按
    # 最短 k 优先，同一 k 里"补顶层名"的形式优先于裸后缀。
    for strict in (True, False):
        for k in range(1, len(parts) + 1):
            suffix = ".".join(parts[k:])
            if not suffix:
                continue
            cands = [top + "." + suffix] if top else []
            if suffix not in cands:
                cands.append(suffix)
            for cand in cands:
                try:
                    obj = npi.object(cand)
                except NpiError:
                    tried.append({"suffix": cand, "ok": False, "reason": "NPI 无此对象"})
                    continue
                npi_w = int(obj.width or 0)
                width_match = (not fsdb_width or not npi_w
                               or npi_w == fsdb_width
                               or npi_w == 1 and fsdb_width == 1)
                tried.append({"suffix": cand, "ok": width_match,
                              "width": {"fsdb": fsdb_width, "npi": npi_w}})
                if not strict and fallback is None:
                    prefix = ".".join(parts[:k])
                    fallback = Mapping(prefix + "." if prefix else "", fsdb_path, cand,
                                       top_segment=_seg_for(cand, suffix, top))
                if strict and width_match:
                    prefix = ".".join(parts[:k])
                    return Mapping(prefix + "." if prefix else "", fsdb_path, cand,
                                   top_segment=_seg_for(cand, suffix, top))
        if strict and fallback is not None:
            return fallback
    if fallback is not None:
        return fallback
    raise JoinError(
        "无法把 FSDB 路径映射进设计命名空间: %s（尝试：%s）"
        % (fsdb_path, "；".join(t["suffix"] for t in tried[-3:])))


def _design_top(npi: NpiClient) -> str:
    """设计顶层模块名（NPI 命名空间根）；取不到时返回空串。"""
    try:
        nodes = npi.hierarchy(max_depth=0)
    except NpiError:
        return ""
    return nodes[0].full if nodes else ""


def _seg_for(cand: str, suffix: str, top: str) -> str:
    """候选是"补了顶层名"的形式且子树本身不含该段时，返回需插拔的段。"""
    if top and cand.startswith(top + ".") and not suffix.startswith(top + "."):
        return top
    return ""


def _fsdb_width(fs: Fsdb, fsdb_path: str) -> int:
    try:
        res = fs.wave([fsdb_path], clock="none", max_changes=0)
        ws = res.signals[0] if res.signals else None
        return ws.width if ws is not None and ws.found else 0
    except Exception:  # noqa: BLE001
        return 0


# ------------------------------------------------------------------ 值批量取

def _values_at(fs: Fsdb, paths: Sequence[str], t: int) -> Dict[str, Optional[str]]:
    """一次 fsdbq 调用取多条路径在 t 时刻的值；查不到的路径记 None。"""
    out: Dict[str, Optional[str]] = {}
    if not paths:
        return out
    try:
        res = fs.wave(list(paths), clock="none", t0=0, t1=t, max_changes=0)
        for ws in res.signals:
            out[ws.requested] = ws.value_at(t) if ws.found else None
    except Exception:  # noqa: BLE001
        pass
    for p in paths:
        out.setdefault(p, None)
    return out


def _stmt_lookup(npi: NpiClient, mapping: Mapping) -> Dict[str, Dict[str, Any]]:
    """整个设计的连续赋值语句图，按 LHS 全路径（NPI 命名）索引。"""
    try:
        stmts = npi.stmtmap(root="", max_depth=8, limit=5000)
    except NpiError:
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for st in stmts:
        lhs = st.get("lhs") or ""
        if lhs and lhs not in out:
            out[lhs] = st
    return out


# ------------------------------------------------------------------ 驱动链

def _walk_drivers(
    fs: Fsdb,
    npi: NpiClient,
    mapping: Mapping,
    target_fsdb: str,
    t: int,
    depth: int,
    max_nodes: int,
    x_only: bool,
) -> Dict[str, Any]:
    """BFS 反向驱动链。``x_only`` 时只展开值为 x/z 的节点（trace_x 口径）。"""
    stmt_by_lhs = _stmt_lookup(npi, mapping)
    nodes: List[Dict[str, Any]] = []
    by_path: Dict[str, int] = {}
    queue: List[Tuple[str, int, Optional[int]]] = [(target_fsdb, 0, None)]
    expanded = 0
    truncated = False
    while queue:
        path, dep, parent = queue.pop(0)
        if path in by_path:
            continue
        if len(nodes) >= max_nodes:
            truncated = True
            break
        npi_path = mapping.npi(path)
        vals = _values_at(fs, [path], t)
        raw = vals.get(path)
        node = {
            "id": len(nodes),
            "parent": parent,
            "depth": dep,
            "path": path,
            "npi_path": npi_path,
            "value": raw,
            "kind": "",
            "stmt": None,
            "drivers": [],
        }
        by_path[path] = len(nodes)
        nodes.append(node)
        if dep >= depth:
            continue
        if x_only and not has_xz_raw(raw):
            continue  # 只沿 x/z 分支走
        try:
            hits = npi.trace(npi_path, direction="driver", limit=100)
        except NpiError as exc:
            node["drivers"] = [{"error": str(exc)}]
            continue
        child_paths: List[str] = []
        for hit in hits:
            dtype = hit.type
            full = hit.full
            if dtype == "npiConstant" or full.startswith("[unnamed:"):
                node["drivers"].append({"kind": "constant", "type": dtype, "path": full})
                continue
            child = mapping.fsdb(full)
            node["drivers"].append({"kind": "signal", "type": dtype,
                                    "path": child, "npi_path": full})
            child_paths.append(child)
        # 语句语境：连续赋值 LHS 挂 file:line + 反编译文本
        st = stmt_by_lhs.get(npi_path)
        if st:
            node["stmt"] = {"file": st.get("file"), "line": st.get("line"),
                            "lhs_text": st.get("lhs_text"), "rhs": st.get("rhs")}
        node["kind"] = _kind_of(npi, npi_path)
        # 一次性取本层全部子节点的值并入队（fsdbq 进程数 = 层数，不是节点数）
        if child_paths:
            uniq = [p for p in dict.fromkeys(child_paths) if p not in by_path]
            _values_at(fs, uniq, t)
            for child in node["drivers"]:
                if child.get("kind") == "signal" and child["path"] not in by_path:
                    queue.append((child["path"], dep + 1, node["id"]))
        expanded += 1
    return {"nodes": nodes, "truncated": truncated, "expanded": expanded}


def _kind_of(npi: NpiClient, npi_path: str) -> str:
    try:
        obj = npi.object(npi_path)
        return obj.type or ""
    except NpiError:
        return ""


def _x_roots(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """x/z 值且没有继续展开的信号驱动（或深度截断）——X 根因候选。

    口径：walk 在 ``x_only`` 下只展开值为 x/z 的节点，所以"值为 x/z 且
    drivers 里没有 signal 类子项"即叶子候选；常量驱动不算根因证据。
    """
    out: List[Dict[str, Any]] = []
    seen = set()
    for n in nodes:
        if not has_xz_raw(n.get("value")):
            continue
        signal_children = [d for d in n.get("drivers") or [] if d.get("kind") == "signal"]
        if signal_children:
            continue
        if n["path"] in seen:
            continue
        seen.add(n["path"])
        out.append({"path": n["path"], "value": n.get("value"),
                    "depth": n["depth"],
                    "driver": [d for d in (n.get("drivers") or [])
                               if d.get("kind") == "constant"]})
    return out


def trace_value(fs: Fsdb, npi: NpiClient, mapping: Mapping, target_fsdb: str,
                t: int, depth: int = 6, max_nodes: int = 200,
                x_only: bool = False) -> Dict[str, Any]:
    """沿驱动链反向遍历，每个节点带 t 时刻真实值。"""
    root_vals = _values_at(fs, [target_fsdb], t)
    if root_vals.get(target_fsdb) is None:
        try:
            res = fs.wave([target_fsdb], clock="none", max_changes=0)
            found = bool(res.signals) and res.signals[0].found
        except Exception:  # noqa: BLE001
            found = False
        if not found:
            return {"status": "error", "error_type": "signal_not_found",
                    "error": "目标信号不在波形里: %s" % target_fsdb,
                    "hint": "先用 dbg signals/query 拿准确全路径"}
    walk = _walk_drivers(fs, npi, mapping, target_fsdb, t, max(0, int(depth)),
                         max(1, int(max_nodes)), bool(x_only))
    out = {
        "status": "ok",
        "target": {"path": target_fsdb, "time": t},
        "mapping": mapping.to_dict(),
        "mode": "trace_x" if x_only else "trace_value",
        "nodes": walk["nodes"],
        "truncated": walk["truncated"],
        "note": None,
    }
    if x_only:
        out["x_roots"] = _x_roots(walk["nodes"])
        out["note"] = ("x_roots 是值为 x/z 且不再有信号驱动的节点；"
                       "驱动为常量或深度截断的按候选看待，不是定论")
    return out


# ------------------------------------------------------------------ 活跃驱动

def _clock_edge_before(fs: Fsdb, clock: str, t: int, edge: str) -> Optional[int]:
    res = fs.wave([clock], clock=clock, clock_pattern=clock, t0=0, t1=t, max_changes=0)
    edges = res.falling if edge == "negedge" else res.rising
    if not edges:
        return None
    return max(e for e in edges if e <= t) if any(e <= t for e in edges) else None


def active_drivers(fs: Fsdb, npi: NpiClient, mapping: Mapping, target_fsdb: str,
                   t: int, clock: Optional[str] = None, edge: str = "posedge") -> Dict[str, Any]:
    """某一拍哪条驱动在起作用：按驱动值与目标值的一致性分类。"""
    vals = _values_at(fs, [target_fsdb], t)
    raw = vals.get(target_fsdb)
    if raw is None:
        return {"status": "error", "error_type": "signal_not_found",
                "error": "目标信号不在波形里: %s" % target_fsdb}
    npi_path = mapping.npi(target_fsdb)
    try:
        hits = npi.trace(npi_path, direction="driver", limit=100)
    except NpiError as exc:
        return {"status": "error", "error_type": "npi_error", "error": str(exc)}
    obj_kind = _kind_of(npi, npi_path)
    procedural = obj_kind in ("npiReg", "npiRegBit", "npiBitVar", "npiLogicVar", "npiIntVar", "npiVar")
    t_eff = t
    capture_note = None
    if clock and procedural:
        te = _clock_edge_before(fs, clock, t, edge)
        if te is None:
            capture_note = "窗口内没有 %s 的 %s 沿（<= %d）；按 t 原值评估" % (clock, edge, t)
        else:
            # 采集沿上的驱动值取 **te-1（沿前一时刻）**：FSDB 里组合更新与寄存器
            # NBA 采集常落在同一时间戳，value_at(te) 会取到沿后的新值（实测
            # y_c 在 365000 同时记录"沿前 254→沿后 0"），沿前一时刻才是
            # 被采集进寄存器的值。
            t_eff = te - 1 if te > 0 else te
            capture_note = ("过程驱动按 %s %s 沿（t=%d）的**沿前一时刻**（%d）取驱动值："
                            "寄存器在沿上采集，且同一时间戳上组合更新与 NBA 采集并存，"
                            "取 te-1 才是被采集进寄存器的值"
                            % (clock, edge, te, t_eff))
    elif procedural and not clock:
        capture_note = ("目标是过程驱动的寄存器且未给 --clock：按 t 时刻原值评估，"
                        "建议给 --clock <时钟> 取采样沿时刻的驱动值更准")
    drivers: List[Dict[str, Any]] = []
    summary = {"match": 0, "differ": 0, "undecidable": 0, "constant": 0, "missing": 0}
    sig_paths: List[str] = []
    for hit in hits:
        dtype, full = hit.type, hit.full
        if dtype == "npiConstant" or full.startswith("[unnamed:"):
            drivers.append({"kind": "constant", "type": dtype, "path": full,
                            "classification": "constant"})
            summary["constant"] += 1
            continue
        sig_paths.append(full)
    value_map = _values_at(fs, [mapping.fsdb(p) for p in sig_paths], t_eff)
    for full, dfull in zip(sig_paths, [mapping.fsdb(p) for p in sig_paths]):
        dval = value_map.get(dfull)
        if dval is None:
            cls = "missing"
        elif has_xz_raw(dval) or has_xz_raw(raw):
            cls = "undecidable"
        else:
            cls = "match" if _same_value(dval, raw) else "differ"
        summary[cls] += 1
        drivers.append({"kind": "signal", "type": "", "path": dfull,
                        "npi_path": full, "value": dval, "value_time": t_eff,
                        "classification": cls})
    return {
        "status": "ok",
        "target": {"path": target_fsdb, "time": t, "value": raw, "npi_kind": obj_kind},
        "mapping": mapping.to_dict(),
        "drivers": drivers,
        "summary": summary,
        "capture_note": capture_note,
        "value_time": t_eff,
        "note": ("match=与目标值一致（该拍的活跃驱动候选）；differ=不一致（非活跃）；"
                 "undecidable=x/z；constant=常量驱动；missing=波形里查不到"),
    }


# ------------------------------------------------------------------ 状态转移

def state_transitions(fs: Fsdb, npi: NpiClient, mapping: Mapping, target_fsdb: str,
                      clock: Optional[str] = None, edge: str = "posedge",
                      start: int = 0, end: Optional[int] = None,
                      limit: int = 200) -> Dict[str, Any]:
    """状态寄存器的实际转移表：发生过的 (from→to)、次数、首现时刻。

    **这不是覆盖率**：没有分母（设计"应该有"的状态与转移），没出现的
    状态可能不可达、可能激励没打到，一次波形区分不了——只报事实。
    给 ``clock`` 时附每个转移首现**采集沿**上的驱动值（诊断"谁把它推进
    这个状态"的第一手数据）。
    """
    res = fs.wave([target_fsdb], clock="none", t0=start, t1=end, max_changes=0)
    ws = res.signals[0] if res.signals else None
    if ws is None or not ws.found:
        return {"status": "error", "error_type": "signal_not_found",
                "error": "目标信号不在波形里: %s" % target_fsdb}
    seq = list(ws.changes)
    if not seq:
        return {"status": "ok", "transitions": [], "count": 0,
                "note": "窗口内该信号没有任何值变"}
    transitions: Dict[Tuple[str, str], Dict[str, Any]] = {}
    x_entries = 0
    for i in range(1, len(seq)):
        prev_t, prev_v = seq[i - 1]
        cur_t, cur_v = seq[i]
        key = (str(prev_v), str(cur_v))
        rec = transitions.setdefault(key, {"from": prev_v, "to": cur_v,
                                           "count": 0, "first_time": cur_t,
                                           "capture_edges": []})
        rec["count"] += 1
        if len(rec["capture_edges"]) < 3:
            rec["capture_edges"].append(cur_t)
        if has_xz_raw(cur_v):
            x_entries += 1
    rows = sorted(transitions.values(), key=lambda r: r["first_time"])
    truncated = len(rows) > int(limit)
    rows = rows[: int(limit)]
    # 采集沿上的驱动值（每个转移类型取首现沿）
    driver_paths: List[str] = []
    npi_path = mapping.npi(target_fsdb)
    try:
        hits = npi.trace(npi_path, direction="driver", limit=100)
    except NpiError as exc:
        hits = []
        driver_err = str(exc)
    else:
        driver_err = None
    for hit in hits:
        if hit.type != "npiConstant" and not hit.full.startswith("[unnamed:"):
            driver_paths.append(mapping.fsdb(hit.full))
    if clock and driver_paths:
        for rec in rows:
            te = _clock_edge_before(fs, clock, rec["first_time"], edge)
            if te is None:
                rec["drivers_at_capture"] = None
                continue
            # 采集沿的驱动值取 te-1（沿前一时刻）：同一时间戳上组合更新与
            # NBA 采集并存，value_at(te) 会取到沿后的新值（口径同 active）。
            t_before = te - 1 if te > 0 else te
            vals = _values_at(fs, driver_paths, t_before)
            rec["capture_edge"] = te
            rec["drivers_at_capture"] = [
                {"path": p, "value": vals.get(p), "value_time": t_before}
                for p in driver_paths
            ]
    return {
        "status": "ok",
        "target": {"path": target_fsdb, "npi_kind": _kind_of(npi, npi_path)},
        "window": {"start": start, "end": end},
        "clock": clock,
        "edge": edge,
        "changes": len(seq),
        "count": len(transitions),
        "x_entries": x_entries,
        "transitions": rows,
        "truncated": truncated,
        "driver_error": driver_err,
        "note": ("这是本波形的实际转移事实，不是覆盖率：没有『应该有』的分母，"
                 "没出现的状态可能是不可达，也可能是激励缺口，区分不了"),
    }
