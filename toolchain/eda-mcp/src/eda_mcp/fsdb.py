"""FFR（FSDB File Reader）波形读取层。

通过 `native/fsdbq` 子进程访问 FSDB —— **不需要 Verdi、不需要 License、不需要 X**。
本模块只负责「取数」，所有时序语义在 :mod:`eda_mcp.wavedrom` 里。

fsdbq 的行协议（stdout，tab 分隔）::

    I  key value                              文件元信息
    V  hier idcode l r vtype dir              变量
    S  hier depth                             层次
    C  hier period cv nedges nrising          选定时钟
    R  time / F time                          时钟上升/下降沿
    B  idx requested resolved idcode l r      信号解析结果
    N  idx requested                          信号未找到
    P  idx time value                         窗口起点前的种子值
    W  idx time value                         值变
    E  idx count truncated                    值变统计
    Z  key value                              汇总

FFR 自身会往 stdout 打杂项行（如 ``logDir = /tmp/``），故只认上表首字符 + TAB。
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

__all__ = [
    "FsdbError",
    "Signal",
    "WaveSignal",
    "WaveResult",
    "Fsdb",
    "value_at",
]

_RECOGNIZED = frozenset("IVSCRFBPWENZ")


class FsdbError(RuntimeError):
    """fsdbq 调用失败或波形不合法。"""


# --------------------------------------------------------------------- 数据模型


@dataclass
class Signal:
    hier: str
    idcode: int
    l: int
    r: int
    vtype: str = "wire"
    direction: int = 0

    @property
    def name(self) -> str:
        return self.hier.rsplit(".", 1)[-1]

    @property
    def width(self) -> int:
        return abs(self.l - self.r) + 1

    @property
    def is_single_bit(self) -> bool:
        return self.width == 1

    @property
    def scope(self) -> str:
        return self.hier.rsplit(".", 1)[0] if "." in self.hier else ""

    @property
    def depth(self) -> int:
        return self.hier.count(".")

    def to_dict(self) -> Dict[str, object]:
        return {
            "hier": self.hier,
            "name": self.name,
            "scope": self.scope,
            "l": self.l,
            "r": self.r,
            "width": self.width,
            "type": self.vtype,
        }


@dataclass
class WaveSignal:
    """一个信号的值变序列。``changes`` 已含窗口前的种子值（若取到）。"""

    requested: str
    resolved: Optional[str] = None
    idcode: Optional[int] = None
    l: int = 0
    r: int = 0
    changes: List[Tuple[int, str]] = field(default_factory=list)
    total: int = 0
    truncated: bool = False

    @property
    def found(self) -> bool:
        return self.resolved is not None

    @property
    def width(self) -> int:
        return abs(self.l - self.r) + 1

    @property
    def is_single_bit(self) -> bool:
        return self.width == 1

    def value_at(self, t: int) -> str:
        """取 ``<= t`` 的最近值；无则 ``"x"``（与旧工具 VCDParser 语义一致）。"""
        return value_at(self.changes, t)


@dataclass
class WaveResult:
    clock: Optional[str] = None
    period: float = 0.0
    cv: float = 0.0
    nedges: int = 0
    rising: List[int] = field(default_factory=list)
    falling: List[int] = field(default_factory=list)
    signals: List[WaveSignal] = field(default_factory=list)

    def by_index(self, idx: int) -> Optional[WaveSignal]:
        if 0 <= idx < len(self.signals):
            return self.signals[idx]
        return None


def value_at(changes: Sequence[Tuple[int, str]], t: int) -> str:
    """二分取 ``<= t`` 的最近值（与 VCDParser::get_value_at_time 等价）。"""
    lo, hi, best = 0, len(changes) - 1, None
    while lo <= hi:
        mid = (lo + hi) // 2
        if changes[mid][0] <= t:
            best = changes[mid]
            lo = mid + 1
        else:
            hi = mid - 1
    return best[1] if best is not None else ""


# --------------------------------------------------------------------- FFR 封装


def _iter_records(text: str):
    for line in text.splitlines():
        if len(line) < 2 or line[0] not in _RECOGNIZED or line[1] != "\t":
            continue
        yield line.split("\t")


def missing_path_message(kind: str, given: str) -> str:
    """路径不存在时的统一报错：解析后的绝对路径 + 入参原样 + 当前 CWD + 远端提示。

    实测踩过：拿本机的绝对路径在远端 EDA 主机上必然不存在，而只回显拼接后的
    绝对路径看不出"是按什么拼的、在哪台机器上拼的"。
    """
    resolved = os.path.abspath(os.path.expanduser(given))
    return ("%s: %s（入参原样: %s；当前 CWD: %s；"
            "注意：本工具在远端主机上解析路径，本机绝对路径在这里通常不存在）"
            % (kind, resolved, given, os.getcwd()))


class Fsdb:
    """一个 FSDB 文件的只读句柄（无状态：每次调用都是一次 fsdbq 进程）。"""

    def __init__(self, path: str, fsdbq: Optional[str] = None, timeout: int = 300):
        self.given = str(path)
        self.path = os.path.abspath(os.path.expanduser(path))
        self.fsdbq = fsdbq
        self.timeout = timeout
        if not self.fsdbq:
            raise FsdbError("未找到 fsdbq 可执行文件，请运行 eda-mcp doctor 或设置 fsdb.fsdbq_bin")
        if not os.path.isfile(self.path):
            raise FsdbError(missing_path_message("FSDB 文件不存在", path))

    # ---- 底层调用 ----
    def _run(self, mode: str, *args: str) -> List[List[str]]:
        cmd = [self.fsdbq, mode, self.path] + [str(a) for a in args]
        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                timeout=self.timeout,
            )
        except OSError as exc:
            raise FsdbError("无法执行 fsdbq: %s" % exc)
        except subprocess.TimeoutExpired:
            raise FsdbError("fsdbq 超时（%ss）: %s" % (self.timeout, " ".join(cmd)))
        records = list(_iter_records(proc.stdout))
        if not records:
            err = (proc.stderr or "").strip().splitlines()
            raise FsdbError(
                "fsdbq 无输出 (rc=%d): %s" % (proc.returncode, err[-1] if err else "未知错误")
            )
        return records

    # ---- info ----
    def info(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for rec in self._run("info"):
            if rec[0] == "I" and len(rec) >= 3:
                out[rec[1]] = rec[2]
        for key in ("min_time", "max_time"):
            if key in out:
                try:
                    out[key + "_int"] = int(out[key])
                except ValueError:
                    pass
        return out

    def scale_unit(self) -> str:
        return self.info().get("scale_unit", "")

    def time_range(self) -> Tuple[int, int]:
        info = self.info()
        return info.get("min_time_int", 0), info.get("max_time_int", 0)

    # ---- 信号 / 层次 ----
    def signals(
        self,
        pattern: Optional[str] = None,
        scope: Optional[str] = None,
        max_depth: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[Signal]:
        args: List[str] = []
        if pattern:
            args += ["--pattern", pattern]
        if scope:
            args += ["--scope", scope]
        if max_depth is not None:
            args += ["--max-depth", str(max_depth)]
        if limit is not None:
            args += ["--limit", str(limit)]
        out: List[Signal] = []
        for rec in self._run("vars", *args):
            if rec[0] != "V" or len(rec) < 7:
                continue
            out.append(
                Signal(
                    hier=rec[1],
                    idcode=int(rec[2]),
                    l=int(rec[3]),
                    r=int(rec[4]),
                    vtype=rec[5],
                    direction=int(rec[6]),
                )
            )
        out.sort(key=lambda s: s.hier)
        return out

    def scopes(
        self,
        scope: Optional[str] = None,
        max_depth: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[Tuple[str, int]]:
        args: List[str] = []
        if scope:
            args += ["--scope", scope]
        if max_depth is not None:
            args += ["--max-depth", str(max_depth)]
        if limit is not None:
            args += ["--limit", str(limit)]
        out: List[Tuple[str, int]] = []
        for rec in self._run("scopes", *args):
            if rec[0] == "S" and len(rec) >= 3:
                out.append((rec[1], int(rec[2])))
        return out

    # ---- 波形 ----
    def wave(
        self,
        signals: Sequence[str],
        clock: str = "auto",
        clock_pattern: str = "clk",
        t0: Optional[int] = None,
        t1: Optional[int] = None,
        max_changes: Optional[int] = None,
    ) -> WaveResult:
        args: List[str] = ["--clock", clock, "--pattern", clock_pattern]
        if t0 is not None:
            args += ["--from", str(int(t0))]
        if t1 is not None:
            args += ["--to", str(int(t1))]
        if max_changes is not None:
            args += ["--max-changes", str(int(max_changes))]
        args += list(signals)

        res = WaveResult()
        slots: Dict[int, WaveSignal] = {}
        for rec in self._run("wave", *args):
            tag = rec[0]
            if tag == "C" and len(rec) >= 6:
                res.clock = rec[1]
                res.period = float(rec[2])
                res.cv = float(rec[3])
                res.nedges = int(rec[4])
            elif tag == "R" and len(rec) >= 2:
                res.rising.append(int(rec[1]))
            elif tag == "F" and len(rec) >= 2:
                res.falling.append(int(rec[1]))
            elif tag == "B" and len(rec) >= 7:
                idx = int(rec[1])
                ws = slots.get(idx) or WaveSignal(requested=rec[2])
                ws.requested = rec[2]
                ws.resolved = rec[3]
                ws.idcode = int(rec[4])
                ws.l = int(rec[5])
                ws.r = int(rec[6])
                slots[idx] = ws
            elif tag == "N" and len(rec) >= 3:
                idx = int(rec[1])
                slots[idx] = WaveSignal(requested=rec[2])
            elif tag == "P" and len(rec) >= 4:
                ws = slots.setdefault(int(rec[1]), WaveSignal(requested=""))
                ws.changes.append((int(rec[2]), rec[3]))
            elif tag == "W" and len(rec) >= 4:
                ws = slots.setdefault(int(rec[1]), WaveSignal(requested=""))
                ws.changes.append((int(rec[2]), rec[3]))
            elif tag == "E" and len(rec) >= 4:
                ws = slots.setdefault(int(rec[1]), WaveSignal(requested=""))
                ws.total = int(rec[2])
                ws.truncated = rec[3] not in ("0", "")
            elif tag == "Z" and len(rec) >= 3 and rec[1] == "clock":
                res.clock = res.clock or rec[2]

        res.signals = [slots[i] for i in sorted(slots)]
        for ws in res.signals:
            ws.changes.sort(key=lambda kv: kv[0])
        return res


def open_fsdb(path: str, cfg=None) -> Fsdb:
    """按配置打开一个 FSDB。"""
    fsdbq = cfg.fsdbq() if cfg is not None else None
    timeout = int(cfg.get("verdi.import_timeout_s", 300)) if cfg is not None else 300
    return Fsdb(path, fsdbq=fsdbq, timeout=timeout)
