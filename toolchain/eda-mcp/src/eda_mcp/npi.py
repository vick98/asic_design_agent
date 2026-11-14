"""Verdi NPI 设计模型查询（客户端侧）。

把 :mod:`eda_mcp.daemon` 的 TCL 记录流解析成结构化数据。每条记录的字段以
`prelude.tcl` 的约定为准。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from .config import Config
from .daemon import DesignDaemon, DaemonError, open_design, parse_records

__all__ = [
    "NpiError",
    "HierNode",
    "ObjInfo",
    "TraceHit",
    "NpiClient",
    "connect",
]


class NpiError(RuntimeError):
    pass


@dataclass
class HierNode:
    depth: int
    full: str
    def_name: str = ""
    file: str = ""
    line: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "depth": self.depth,
            "full": self.full,
            "def": self.def_name,
            "file": self.file,
            "line": self.line,
        }


@dataclass
class ObjInfo:
    full: str
    type: str = ""
    name: str = ""
    direction: str = ""
    net_type: str = ""
    left: Optional[int] = None
    right: Optional[int] = None
    width: int = 1
    file: str = ""
    line: int = 0
    source: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "full": self.full,
            "name": self.name,
            "type": self.type,
            "direction": self.direction,
            "net_type": self.net_type,
            "left": self.left,
            "right": self.right,
            "width": self.width,
            "file": self.file,
            "line": self.line,
            "source": self.source.strip(),
        }


@dataclass
class TraceHit:
    direction: str
    type: str
    full: str

    def to_dict(self) -> Dict[str, Any]:
        return {"direction": self.direction, "type": self.type, "full": self.full}


def _int(text: str) -> Optional[int]:
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


class NpiClient:
    """一个设计模型 daemon 的查询客户端。"""

    def __init__(self, daemon: DesignDaemon):
        self.daemon = daemon

    # ---- 底层 ----
    def _query(self, cmd: str, *args: Any, timeout: float = 120.0) -> List[List[str]]:
        text = self.daemon.query(cmd, *args, timeout=timeout)
        rows = parse_records(text)
        errors = [r for r in rows if r and r[0] == "E"]
        if errors:
            key = errors[0][1] if len(errors[0]) > 1 else "error"
            val = errors[0][2] if len(errors[0]) > 2 else ""
            if key == "notfound":
                raise NpiError("对象不存在: %s" % val)
            raise NpiError("NPI 查询失败(%s): %s" % (key, val))
        return rows

    # ---- 查询 ----
    def ping(self) -> bool:
        rows = self._query("ping", timeout=20)
        return any(r[0] == "Z" and len(r) > 1 and r[1] == "pong" for r in rows)

    def hierarchy(
        self,
        root: Optional[str] = None,
        max_depth: Optional[int] = None,
        pattern: Optional[str] = None,
    ) -> List[HierNode]:
        rows = self._query(
            "scopes",
            root or "",
            -1 if max_depth is None else int(max_depth),
            pattern or "",
        )
        out: List[HierNode] = []
        for r in rows:
            if r[0] != "H" or len(r) < 6:
                continue
            out.append(
                HierNode(
                    depth=_int(r[1]) or 0,
                    full=r[2],
                    def_name=r[3],
                    file=r[4],
                    line=_int(r[5]) or 0,
                )
            )
        out.sort(key=lambda n: (n.depth, n.full))
        return out

    @staticmethod
    def _obj_from(r: Sequence[str]) -> ObjInfo:
        return ObjInfo(
            full=r[1],
            type=r[2],
            name=r[3],
            direction=r[4],
            net_type=r[5],
            left=_int(r[6]) if len(r) > 6 else None,
            right=_int(r[7]) if len(r) > 7 else None,
            width=_int(r[8]) if len(r) > 8 and _int(r[8]) else 1,
            file=r[9] if len(r) > 9 else "",
            line=_int(r[10]) if len(r) > 10 and _int(r[10]) else 0,
            source=r[11] if len(r) > 11 else "",
        )

    def object(self, path: str) -> ObjInfo:
        rows = self._query("object", path, timeout=30)
        for r in rows:
            if r[0] == "O":
                return self._obj_from(r)
        raise NpiError("未取到对象属性: %s" % path)

    def module(self, path: str) -> Dict[str, Any]:
        """模块/实例详情：端口、网络、参数、子实例（按类型分组）。"""
        rows = self._query("module", path, timeout=60)
        objs = [self._obj_from(r) for r in rows if r[0] == "O"]
        buckets: Dict[str, List[ObjInfo]] = {
            "ports": [],
            "nets": [],
            "params": [],
            "instances": [],
            "others": [],
        }
        for o in objs:
            t = o.type
            if t in ("npiPort", "npiIODecl"):
                buckets["ports"].append(o)
            elif t in ("npiNet", "npiNetBit", "npiReg", "npiRegBit", "npiBitVar",
                       "npiLogicVar", "npiIntVar", "npiVar"):
                buckets["nets"].append(o)
            elif t in ("npiParameter", "npiLocalParam", "npiParameterBit"):
                buckets["params"].append(o)
            elif t in ("npiInstance", "npiModule"):
                buckets["instances"].append(o)
            else:
                buckets["others"].append(o)
        # 按全名去重（同一个信号可能被多种类型迭代器取到）
        for key, lst in buckets.items():
            seen = set()
            uniq = []
            for o in sorted(lst, key=lambda x: (x.full, x.type)):
                if o.full in seen:
                    continue
                seen.add(o.full)
                uniq.append(o)
            buckets[key] = uniq
        return {
            "path": path,
            "counts": {k: len(v) for k, v in buckets.items()},
            **{k: [o.to_dict() for o in v] for k, v in buckets.items()},
        }

    def find(self, pattern: str, limit: int = 200) -> List[ObjInfo]:
        rows = self._query("find", pattern, int(limit), timeout=180)
        return [self._obj_from(r) for r in rows if r[0] == "O"]

    def trace(self, signal: str, direction: str = "both", limit: int = 200) -> List[TraceHit]:
        dirs = ["driver", "load"] if direction in ("both", "") else [direction]
        hits: List[TraceHit] = []
        seen = set()
        for d in dirs:
            rows = self._query("trace", signal, d, timeout=120)
            for r in rows:
                if r[0] != "T" or len(r) < 4:
                    continue
                key = (r[1], r[3])
                if key in seen:
                    continue
                seen.add(key)
                hits.append(TraceHit(direction=r[1], type=r[2], full=r[3]))
                if len(hits) >= limit:
                    return hits
        return hits

    def equivalent(self, signal: str) -> List[TraceHit]:
        rows = self._query("equiv", signal, timeout=120)
        return [
            TraceHit(direction="equiv", type=r[2], full=r[3])
            for r in rows
            if r[0] == "T" and len(r) >= 4
        ]

    def stmtmap(self, root: str = "", max_depth: int = 8, limit: int = 5000) -> List[Dict[str, Any]]:
        """连续赋值语句图（模块树递归，含 generate 作用域）。

        每条语句：``{lhs, lhs_text, file, line, rhs}``。**口径**：只覆盖
        连续赋值；always/initial 过程赋值语句体在 Verdi NPI 无头模式下
        不可达（V-2023.12 实测），过程驱动的寄存器拿不到语句语境。
        """
        rows = self._query("stmtmap", root, int(max_depth), int(limit), timeout=180)
        out: List[Dict[str, Any]] = []
        for r in rows:
            if r[0] != "S" or len(r) < 6:
                continue
            out.append({
                "lhs": r[1],
                "lhs_text": r[2],
                "file": r[3],
                "line": _int(r[4]) or 0,
                "rhs": r[5],
            })
        return out


def connect(
    design_id: str,
    cfg: Optional[Config] = None,
    files: Optional[Sequence[str]] = None,
    filelist: Optional[str] = None,
    top: Optional[str] = None,
    sv: bool = True,
    wait: bool = True,
    timeout: Optional[float] = None,
) -> NpiClient:
    """建/复用设计 daemon 并返回查询客户端。"""
    d = open_design(design_id, cfg=cfg, files=files, filelist=filelist, top=top, sv=sv)
    if wait and not d.alive():
        d.start(timeout=timeout)
    return NpiClient(d)
