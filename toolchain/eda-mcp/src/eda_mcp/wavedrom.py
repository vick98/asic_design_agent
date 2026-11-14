"""WaveDrom 时序图生成 —— 原 `aic_tool_trace` 的服务器侧等价实现。

逻辑为 ``~/Desktop/aicer/aic_tool/src/{clock_detector,wave_generator,vcd_parser}.cpp``
的 1:1 移植，取数改为 FFR（:mod:`eda_mcp.fsdb`），**输出 JSON 与原工具逐字节一致**。

设计要点（与原工具对齐的语义细节，改动前务必核对）：

* 值变取数用「``<= t`` 的最近值」，取自 **窗口前也保留种子值**；
* 采样点 = 上升沿与其**下一个下降沿**的中点，下降沿表取自**全时间段**；
* 多 bit 数据标签 32 bit 以内转 16 进制、超过则取低 32 bit 写 ``..xxxxxxxx``；
* ``x``/``z`` 参与位运算时按 0 处理（与 C++ ``bin_to_hex`` 一致）。
"""

from __future__ import annotations

import json
import re
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from .fsdb import Signal

__all__ = [
    "SignalTable",
    "parse_time_with_timescale",
    "unit_to_fs",
    "bin_to_hex",
    "format_data_label",
    "single_bit_wave_char",
    "multi_bit_wave_char",
    "align_time_window",
    "cycle_rising_times",
    "compute_sample_times",
    "WaveDrom",
    "list_signals_text",
    "query_signal_text",
]

_TIME_RE = re.compile(r"^([\d.]+)\s*(s|ms|us|ns|ps|fs)?$")
_TS_RE = re.compile(r"^(\d+)\s*(s|ms|us|ns|ps|fs)$")
_INT_RE = re.compile(r"^\d+$")

_UNIT_FS = {"s": 1e15, "ms": 1e12, "us": 1e9, "ns": 1e6, "ps": 1e3, "fs": 1.0}


def unit_to_fs(unit: str) -> float:
    return _UNIT_FS.get(unit, 1e6)


def parse_time_with_timescale(time_str: str, timescale: str) -> int:
    """``"500ns"`` + ``"1ps"`` -> 500000（单位：FSDB timescale）。"""
    ts = str(time_str).strip().lower()
    if _INT_RE.match(ts):
        return int(ts)
    m = _TIME_RE.match(ts)
    if not m:
        raise ValueError("无效的时间格式: %s" % time_str)
    value = float(m.group(1))
    unit = m.group(2) or ""
    if not unit:
        return int(value)
    tm = _TS_RE.match(str(timescale).strip().lower())
    if not tm:
        raise ValueError("无效的 timescale: %s" % timescale)
    vcd_unit_fs = int(tm.group(1)) * unit_to_fs(tm.group(2))
    return int(value * unit_to_fs(unit) / vcd_unit_fs)


# ------------------------------------------------------------------ 值 -> 波形字符


def bin_to_hex(bin_str: str) -> str:
    b = bin_str
    if b and b[0] in "bB":
        b = b[1:]
    pad = (4 - len(b) % 4) % 4
    b = "0" * pad + b
    out = []
    for i in range(0, len(b), 4):
        val = 0
        for j in range(4):
            val = (val << 1) | (1 if b[i + j].lower() == "1" else 0)
        out.append("0123456789abcdef"[val])
    s = "".join(out).lstrip("0")
    return s or "0"


def single_bit_wave_char(val: str) -> str:
    v = str(val).lower()
    if v in ("0", "1", "x", "z", "u", "d"):
        return v
    return "x"


def multi_bit_wave_char(val: str) -> str:
    v = str(val).lower()
    if v == "x":
        return "x"
    if v == "z":
        return "z"
    if v.startswith("b"):
        bits = v[1:]
        if bits and all(c == "x" for c in bits):
            return "x"
        if bits and all(c == "z" for c in bits):
            return "z"
    return "="


def format_data_label(val: str) -> str:
    v = str(val).lower()
    if v.startswith("b"):
        bits = v[1:]
        if len(bits) > 32:
            low32 = 0
            for c in bits[-32:]:
                low32 = ((low32 << 1) | (1 if c == "1" else 0)) & 0xFFFFFFFF
            return "..%08x" % low32
        return bin_to_hex(v)
    if v.startswith("r"):
        return v[1:]
    return val


# ------------------------------------------------------------------ 时间窗


def align_time_window(
    rising: Sequence[int],
    start_time: int = -1,
    end_time: int = -1,
    center_time: int = -1,
    num_cycles: int = 20,
) -> Tuple[int, int]:
    """与 ``WaveGenerator::align_time_window`` 等价。"""
    if not rising:
        raise ValueError("未找到时钟上升沿")

    if start_time >= 0 and end_time >= 0:
        aligned_start = start_time
        for rt in reversed(rising):
            if rt <= start_time:
                aligned_start = rt
                break
        aligned_end = end_time
        for rt in rising:
            if rt >= end_time:
                aligned_end = rt
                break
        return aligned_start, aligned_end

    if center_time >= 0:
        aligned_center = center_time
        for rt in reversed(rising):
            if rt <= center_time:
                aligned_center = rt
                break
        half = num_cycles // 2
        aligned_start = aligned_center
        for i, rt in enumerate(rising):
            if rt == aligned_center:
                aligned_start = rising[max(0, i - half)]
                break
        end_idx = -1
        for i, rt in enumerate(rising):
            if rt >= aligned_center:
                end_idx = i
                break
        if end_idx < 0:
            end_idx = len(rising) - 1
        remaining = num_cycles - half - 1
        end_idx = min(end_idx + remaining, len(rising) - 1)
        return aligned_start, rising[end_idx]

    aligned_start = rising[0]
    end_idx = min(num_cycles - 1, len(rising) - 1)
    return aligned_start, rising[end_idx]


def cycle_rising_times(rising: Sequence[int], start_time: int, end_time: int) -> List[int]:
    return [rt for rt in rising if start_time <= rt <= end_time]


def compute_sample_times(rising_window: Sequence[int], falling_all: Sequence[int]) -> List[int]:
    """采样点 = 上升沿与其**下一个下降沿**的中点（下降沿取自全时间段）。"""
    out: List[int] = []
    for rt in rising_window:
        nxt = None
        for ft in falling_all:
            if ft > rt:
                nxt = ft
                break
        out.append((rt + nxt) // 2 if nxt is not None else rt)
    return out


# ------------------------------------------------------------------ 信号表


class SignalTable:
    """等价于 ``VCDParser::hierarchy_index`` / ``name_index`` 的解析规则。"""

    def __init__(self, signals: Iterable[Signal]):
        self.signals: List[Signal] = list(signals)
        self._by_hier: Dict[str, Signal] = {}
        self._by_name: Dict[str, List[Signal]] = {}
        for s in self.signals:
            self._by_hier.setdefault(s.hier, s)
            self._by_name.setdefault(s.name, []).append(s)
        for name, lst in self._by_name.items():
            lst.sort(key=lambda s: s.depth)

    def resolve(self, path: str) -> Tuple[str, Optional[Signal]]:
        """返回 ``("exact"|"fuzzy"|"", Signal|None)``。"""
        hit = self._by_hier.get(path)
        if hit is not None:
            return "exact", hit
        leaf = path.rsplit(".", 1)[-1]
        cands = self._by_name.get(leaf)
        if cands:
            return "fuzzy", cands[0]
        return "", None

    def query(self, path: str) -> List[Signal]:
        """等价于 ``VCDParser::query_signal``：带点只做精确，否则列全部同名。"""
        if "." in path:
            hit = self._by_hier.get(path)
            return [hit] if hit is not None else []
        return list(self._by_name.get(path, []))

    def all_sorted(self) -> List[Signal]:
        return sorted(self.signals, key=lambda s: s.hier)


# ------------------------------------------------------------------ 生成器


class WaveDrom:
    """把「时钟 + 一组信号」渲染成 WaveDrom JSON。

    :param table: 信号表（用于解析请求路径与取位宽）
    :param clock_path: 时钟的**请求路径**（原工具把 ``signal_order[0]`` 设为它）
    :param clock_id: 时钟的 idcode（判 ``is_clock`` 用）
    :param rising: 全时间段上升沿
    :param falling: 全时间段下降沿
    :param changes_of: ``hier -> [(time, value)]``（含窗口前种子值）
    """

    def __init__(
        self,
        table: SignalTable,
        clock_path: str,
        clock_id: Optional[int],
        rising: Sequence[int],
        falling: Sequence[int],
        changes_of: Callable[[str], Sequence[Tuple[int, str]]],
    ):
        self.table = table
        self.clock_path = clock_path
        self.clock_id = clock_id
        self.rising = list(rising)
        self.falling = list(falling)
        self.changes_of = changes_of

    # ---- 单条 ----
    @staticmethod
    def _render(name: str, wave: str, data: Optional[Sequence[str]] = None) -> str:
        entry = '    {\n      "name": %s,\n      "wave": "%s",\n      "period": 2' % (
            json.dumps(name, ensure_ascii=False),
            wave,
        )
        if data:
            entry += ',\n      "data": [\n'
            entry += ",\n".join('        %s' % json.dumps(d, ensure_ascii=False) for d in data)
            entry += "\n      ]"
        return entry + "\n    }"

    @staticmethod
    def _render_notfound(path: str, n: int) -> str:
        return WaveDrom._render(path + "_notfind", "x" + "." * (n - 1))

    def _render_signal(
        self,
        sig: Optional[Signal],
        entry_name: str,
        sample_times: Sequence[int],
        is_clock: bool,
        full_log=None,
    ) -> str:
        n = len(sample_times)
        if is_clock:
            return self._render(entry_name, "p" + "." * (n - 1))

        assert sig is not None
        single = sig.width == 1
        changes = self.changes_of(sig.hier)
        wave = ""
        labels: List[str] = []
        prev_val = None
        for i, st in enumerate(sample_times):
            val = _value_at(changes, st) or "x"
            wc = single_bit_wave_char(val) if single else multi_bit_wave_char(val)
            if i > 0 and val == prev_val:
                wave += "."
            else:
                wave += wc
                if (not single) and wc in ("=", "2", "3", "4", "5"):
                    labels.append(format_data_label(val))
                    if full_log is not None:
                        v = str(val).lower()
                        if v.startswith("b") and len(v) - 1 > 32:
                            full_log.write(
                                "%s  sample=%d  time=%d  width=%d  %s\n"
                                % (sig.hier, i, st, len(v) - 1, bin_to_hex(v[1:]))
                            )
            prev_val = val
        return self._render(entry_name, wave, labels)

    # ---- 整体 ----
    def generate(
        self,
        signal_order: Sequence[str],
        start_time: int,
        end_time: int,
        full_log=None,
    ) -> str:
        rising_window = cycle_rising_times(self.rising, start_time, end_time)
        if not rising_window:
            raise ValueError(
                "时间窗口 [%d, %d] 内未找到时钟上升沿" % (start_time, end_time)
            )
        sample_times = compute_sample_times(rising_window, self.falling)

        entries: List[str] = []
        for path in signal_order:
            match, sig = self.table.resolve(path)
            if not sig:
                entries.append(self._render_notfound(path, len(sample_times)))
                continue
            if match == "fuzzy":
                entry_name = path + "_match"
            elif match == "exact":
                entry_name = sig.hier
            else:
                entry_name = path
            is_clock = self.clock_id is not None and sig.idcode == self.clock_id
            entries.append(
                self._render_signal(sig, entry_name, sample_times, is_clock, full_log)
            )

        return '{\n  "signal": [\n' + ",\n".join(entries) + "\n  ]\n}\n"

    def cycle_count(self, start_time: int, end_time: int) -> int:
        return len(cycle_rising_times(self.rising, start_time, end_time))


def _value_at(changes: Sequence[Tuple[int, str]], t: int) -> str:
    lo, hi, best = 0, len(changes) - 1, None
    while lo <= hi:
        mid = (lo + hi) // 2
        if changes[mid][0] <= t:
            best = changes[mid]
            lo = mid + 1
        else:
            hi = mid - 1
    return best[1] if best is not None else ""


# ------------------------------------------------------------------ 列表 / 查询


def _pad(text: str, width: int) -> str:
    """按 **UTF-8 字节数** 左对齐补空格（C++ std::setw 的口径），保证与原工具文本一致。"""
    n = len(text.encode("utf-8"))
    return text + " " * max(0, width - n)


def signals_as_args(signals: Sequence[Signal]) -> str:
    """把信号列表输出成可直接粘进 ``wave -s`` 的参数串。

    配合 ``signals --pattern`` 用：一次列出匹配、一次粘走，不用手抄全名。
    """
    return " ".join("-s %s" % sig.hier for sig in signals)


def list_signals_text(signals: Sequence[Signal], title: str = "波形中的信号列表") -> str:
    """等价 `aic_tool_trace --list-signals` 的文本输出。"""
    lines = [
        "",
        "%s:" % title,
        "%s%s%s" % (_pad("层次路径", 60), _pad("位宽", 10), "类型"),
        "-" * 80,
    ]
    for sig in signals:
        lines.append("%s [%s] %s" % (_pad(sig.hier, 60), _pad(str(sig.width), 7), sig.vtype))
    return "\n".join(lines) + "\n"


def query_signal_text(results: Sequence[Signal], query_name: str) -> str:
    """等价 `aic_tool_trace --query <name>` 的文本输出。"""
    if not results:
        return "\n未找到匹配信号: '%s'\n" % query_name
    if "." in query_name:
        r = results[0]
        return "\n精确匹配 (1 个):\n  %s [%s] %s\n" % (
            _pad(r.hier, 50),
            _pad(str(r.width), 6),
            r.vtype,
        )
    out = ["\n模糊匹配 '%s' -> %d 个同名信号 (按层次由浅到深):" % (query_name, len(results))]
    for r in results:
        out.append("  %s [%s] %s" % (_pad(r.hier, 50), _pad(str(r.width), 6), r.vtype))
    return "\n".join(out) + "\n"
