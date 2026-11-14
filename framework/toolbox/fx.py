# 作者：vick 邮箱：ykun@yk9811.com

"""定点与相关整数计算。模型提交操作数，结果只从这里出。

宽度公式经定点推导核对脚本（derivation_check.mul_expected）验证一致。
加减的符号：两端都是 u 时结果为 u；否则为 t。旧检查器把加减一律写成 t，这里按无符号对齐规则改回 u。
"""

from __future__ import annotations

import hashlib
import json
import re

FMT_RE = re.compile(r"<?\s*(\d+)\s*,\s*(\d+)\s*,\s*([tu])\s*>?")


class FxError(ValueError):
    pass


def parse_fmt(text):
    m = FMT_RE.fullmatch(text.strip())
    if not m:
        raise FxError("定点格式须为 <W,I,t|u>，收到：%s" % text)
    w, i, t = int(m.group(1)), int(m.group(2)), m.group(3)
    if i < 0 or w < 1:
        raise FxError("不合法的格式 <%d,%d,%s>：须 I>=0 且 W>=1" % (w, i, t))
    need = i + 1 if t == "t" else i
    if w < need:
        why = "有符号须预留符号位，W >= I+1" if t == "t" else "无符号须 W >= I"
        raise FxError("不合法的格式 <%d,%d,%s>：%s" % (w, i, t, why))
    return (w, i, t)


def fmt_s(f):
    return "<%d,%d,%s>" % f


def lift(f):
    w, i, t = f
    if t == "t":
        return f
    return (w + 1, i, "t")


def mul(f1, f2):
    if f1[2] == "u" or f2[2] == "u":
        if not (f1[2] == "u" and f2[2] == "u"):
            f1, f2 = lift(f1), lift(f2)
    a, b, t1 = f1
    c, d, t2 = f2
    if t1 == "t" and t2 == "t":
        return (a + c - 1, b + d, "t")
    return (a + c, b + d, "u")


def cmul(f1, f2):
    if f1[2] != "t" or f2[2] != "t":
        raise FxError("复数乘的两端都须为 t，先用 lift 把无符号抬成有符号")
    return (f1[0] + f2[0], f1[1] + f2[1] + 1, "t")


def _grow(f1, f2, sign):
    frac = max(f1[0] - f1[1], f2[0] - f2[1])
    integer = max(f1[1], f2[1]) + 1
    return (integer + frac, integer, sign)


def add(f1, f2):
    if f1[2] == "u" and f2[2] == "u":
        return _grow(f1, f2, "u")
    if f1[2] != f2[2]:
        f1, f2 = lift(f1), lift(f2)
    return _grow(f1, f2, "t")


def sub(f1, f2):
    if f1[2] == "u" and f2[2] == "u":
        max_i = max(f1[1], f2[1])
        max_f = max(f1[0] - f1[1], f2[0] - f2[1])
        return (1 + max_i + max_f, max_i, "t")
    if f1[2] != f2[2]:
        f1, f2 = lift(f1), lift(f2)
    return _grow(f1, f2, "t")


def shift(f, n, shrink=False):
    if n < 0:
        raise FxError("右移位数须 >= 0")
    w, i, t = f
    if not shrink:
        return f
    if i < n or w < n:
        raise FxError("缩短容器需要 I>=%d 且 W>=%d" % (n, n))
    return (w - n, i - n, t)


def sat_bounds(f, symmetric=False):
    w, _i, t = f
    if t == "u":
        return {"min": 0, "max": (1 << w) - 1, "mode": "unsigned"}
    pos = (1 << (w - 1)) - 1
    neg = -(1 << (w - 1))
    if symmetric:
        neg = 1 - (1 << (w - 1))
    return {"min": neg, "max": pos, "mode": "symmetric" if symmetric else "asymmetric"}


def obs16(f):
    w, i, t = f
    if w <= 16:
        return {"format": (16, i, t), "shift": 0, "pad_low": 16 - w, "align": "left"}
    n = w - 16
    if i < n:
        raise FxError("观测右移 %d 位后整数位为负，格式 %s 无法对齐到 16 bit" % (n, fmt_s(f)))
    return {"format": (16, i - n, t), "shift": n, "pad_low": 0, "align": "arith_shr"}


def pack(widths):
    if not widths or any(w < 0 for w in widths):
        raise FxError("位宽列表须为非负整数")
    return {"widths": list(widths), "total": sum(widths)}


def logical_shr(f, n, shrink=False):
    if f[2] != "u":
        raise FxError("逻辑右移只用于无符号数")
    return shift(f, n, shrink)


def addr_capacity(depths, addr_bits, word_bits=None):
    if addr_bits < 1:
        raise FxError("地址位宽须 >= 1")
    total = sum(depths)
    cap = 1 << addr_bits
    out = {
        "depths": list(depths),
        "total_words": total,
        "addr_bits": addr_bits,
        "capacity": cap,
        "fits": total <= cap,
        "spare_bits": addr_bits - (total - 1).bit_length() if total else addr_bits,
        "percent_of_2_20": (total / float(1 << 20)) * 100.0,
        "mbit": (total * word_bits / 1000000.0) if word_bits else None,
    }
    return out


def golden_tol(fmt, lsb=1, ref=None):
    if lsb < 0:
        raise FxError("LSB 个数不能为负")
    # 口径与 rules/dsp.md 一致：整数位 I 不含符号位——t 的 f = W−I−1，u 的 f = W−I。
    sign_bits = 1 if fmt[2] == "t" else 0
    frac = fmt[0] - fmt[1] - sign_bits
    tol = lsb
    if ref is not None:
        frac_ref = ref[0] - ref[1] - (1 if ref[2] == "t" else 0)
        exp = frac_ref - frac
        tol = lsb << exp if exp >= 0 else lsb >> (-exp)
    return {"GOLDEN_TOL": tol, "lsb_exp": -frac, "k": lsb}


def round_shr(value, n, mode):
    if n < 0:
        raise FxError("移位数须 >= 0")
    if mode not in ("trunc", "half_up", "even"):
        raise FxError("舍入方式须为 trunc、half_up 或 even")
    if n == 0:
        return value
    base = value >> n
    rem = value & ((1 << n) - 1)
    half = 1 << (n - 1)
    if mode == "trunc" or rem < half:
        return base
    if mode == "half_up" or rem > half:
        return base + 1
    return base + (base & 1)


def latency(cycles):
    if not cycles:
        raise FxError("没有拍数可加")
    if any(c < 0 for c in cycles):
        raise FxError("拍数不能为负")
    return sum(cycles)


def sac_shift(src, dst):
    if src[2] != dst[2]:
        raise FxError("饱和截位不改变符号类型")
    dw, di = src[0] - dst[0], src[1] - dst[1]
    if dw < 0 or dw != di:
        raise FxError("目标格式不是把 W 和 I 同步缩短")
    return dw


def finish(src, dst, n, mode="half_up"):
    """收尾：src 右移 n 位（round-half-up）后经饱和落入 dst 容器。

    闭合条件：符号类型一致，且 f_dst = f_src − n（f 按 I 不含符号位口径）。
    饱和允许 I_dst < I_src：数值峰值靠实测/设计余量装下，截极端值是收尾的
    设计行为；返回目标饱和界供文档引用。
    """
    if n < 0:
        raise FxError("右移位数须 >= 0")
    if src[2] != dst[2]:
        raise FxError("收尾不改变符号类型，先对齐符号")
    f_src = src[0] - src[1] - (1 if src[2] == "t" else 0)
    f_dst = dst[0] - dst[1] - (1 if dst[2] == "t" else 0)
    if f_dst != f_src - n:
        raise FxError(
            "小数位不闭合：源 f=%d，右移 %d 位后 f=%d，目标容器 f=%d"
            % (f_src, n, f_src - n, f_dst))
    return {"shift": n, "mode": mode, "f_src": f_src, "f_dst": f_dst,
            "sat": sat_bounds(dst, symmetric=(dst[2] == "t"))}


def run_chain(nodes, ops):
    env = {name: parse_fmt(fmt) for name, fmt in nodes.items()}
    lines = []
    for op in ops:
        kind = op["op"]
        dst = op["dst"]
        if kind == "lift":
            result = lift(env[op["a"]])
            expr = "lift %s" % fmt_s(env[op["a"]])
        else:
            a, b = env[op["a"]], env[op["b"]]
            if kind == "mul":
                result = mul(a, b)
                expr = "%s * %s" % (fmt_s(a), fmt_s(b))
            elif kind == "cmul":
                result = cmul(a, b)
                expr = "%s ** %s" % (fmt_s(a), fmt_s(b))
            elif kind == "add":
                result = add(a, b)
                expr = "%s + %s" % (fmt_s(a), fmt_s(b))
            elif kind == "sub":
                result = sub(a, b)
                expr = "%s - %s" % (fmt_s(a), fmt_s(b))
            else:
                raise FxError("链上不支持运算 %s" % kind)
        env[dst] = result
        lines.append(line(kind, "%s = %s" % (dst, expr), result))
    return env, lines


def stamp(kind, payload):
    raw = json.dumps({"kind": kind, "payload": payload}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def line(kind, expr, result_fmt=None, extra=None, note=None):
    """note 只进文本行，不进戳记：加了数值显示之后，已有文档的戳记照样有效。"""
    body = {"expr": expr}
    if result_fmt is not None:
        body["format"] = fmt_s(result_fmt)
    if extra:
        body.update(extra)
    sid = stamp(kind, body)
    shown = expr if result_fmt is None else "%s → %s" % (expr, fmt_s(result_fmt))
    if note:
        shown = "%s %s" % (shown, note)
    return {"kind": kind, "text": shown, "stamp": sid, "body": body}


def note_text(kind, result, extra=None):
    """把结果显示成人读的一段字，供文档粘贴。"""
    if kind == "sat":
        return "范围 %d..%d" % (result["min"], result["max"])
    if kind == "pack":
        return "合计位宽 %d" % result["total"]
    if kind == "addr":
        return "总字数 %d 容量 %d %s" % (
            result["total_words"], result["capacity"], "放得下" if result["fits"] else "放不下")
    if kind == "round":
        return "结果 %d" % result
    if kind == "latency":
        return "拍数合计 %d" % result
    if kind == "sac":
        return "移位 %d" % result
    if kind == "finish":
        return "右移 %d 位 %s 后饱和，界 %d..%d" % (
            result["shift"], result["mode"], result["sat"]["min"], result["sat"]["max"])
    if kind == "tol":
        exp = result["lsb_exp"]
        return "k=%d 参考刻度 2^%d=%.6g" % (result["k"], exp, 2.0 ** exp)
    return ""
