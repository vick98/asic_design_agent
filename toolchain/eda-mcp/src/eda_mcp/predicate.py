"""信号表达式 DSL 与 4 值求值。

供 `windows`（时间窗搜索）与调试查询使用：把一句布尔/算术表达式按 fsdbq 的
4 值位串口径求值。设计口径：

* **值统一表示**：位向量（0/1/x/z 的位串，带位宽）或实数。fsdbq 原始值
  （``b0101``/``b1``/``bx``/``r3.14``）与本模块的 :class:`V` 互转。
* **不可决不冒充可决**：任何含 x/z 的比较、算术、移位结果为 x（undecidable）；
  ``===``/``!==`` 按字面（x 匹配 x）恒可决；逻辑运算用三值 Kleene 语义
  （``x&&0=0``、``x||1=1``）。
* **无符号口径**：fsdbq 值不带符号信息，比较与算术一律按无符号处理；
  有符号数的判读建议直接给原值（bin/hex）由人判读，或在表达式里写
  显式补码换算。这是已知边界，不是缺陷。

语法（先双字符后单字符匹配，支持括号嵌套）::

    ternary  := or [ '?' ternary ':' ternary ]
    or       := and ( '||' and )*
    and      := bitor ( '&&' bitor )*
    bitor    := bitxor ( '|' bitxor )*
    bitxor   := bitand ( '^' bitand )*
    bitand   := eq ( '&' eq )*
    eq       := rel ( ('==='|'!=='|'=='|'!=') rel )*
    rel      := shift ( ('<='|'>='|'<'|'>') shift )*
    shift    := add ( ('<<'|'>>>'|'>>') add )*
    add      := mul ( ('+'|'-') mul )*
    mul      := unary ( ('*'|'/'|'%') unary )*
    unary    := ( '!' | '~' | '-' | '&' | '|' | '^' )* postfix
                （前缀 ``&``/``|``/``^`` 是归约：&a、|a、^a）
    postfix  := primary ( '[' num ( ':' num )? ']' )*
    primary  := '(' ternary ')' | 字面量 | 信号路径

字面量：``12``、``4.5``（实数）、``8'hAF``、``4'b10x1``、``3``（十进制）、
``'b1``、``x``、``z``；下划线分隔符剔除。信号路径：点分层次名
（段名 ``[A-Za-z_][\\w$]*``，可含位选后缀）。
"""

from __future__ import annotations

import re
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Union

__all__ = [
    "ExprError",
    "V",
    "value_from_fsdb",
    "parse_expr",
    "collect_signals",
    "evaluate",
    "truth_of",
]

_XZ = frozenset("xzXZ")


class ExprError(ValueError):
    """表达式语法或求值口径错误（带位置）。"""


# ------------------------------------------------------------------ 值

UNKNOWN = "x"


class V:
    """一个 4 值（或实数）值。``bits`` 为 None 时是实数（``real``）。

    bits 是 ``'0'/'1'/'x'/'z'`` 的列表，LSB 在后（与书写顺序一致）。
    """

    __slots__ = ("bits", "real")

    def __init__(self, bits: Optional[List[str]] = None, real: Optional[float] = None):
        self.bits = bits
        self.real = real

    # ---- 判别 ----
    @property
    def is_real(self) -> bool:
        return self.bits is None

    @property
    def width(self) -> int:
        return 0 if self.bits is None else len(self.bits)

    def has_xz(self) -> bool:
        if self.bits is None:
            return False
        return any(b in _XZ for b in self.bits)

    def int_or_none(self) -> Optional[int]:
        if self.bits is None:
            return self.real
        if self.has_xz():
            return None
        n = 0
        for b in self.bits:
            n = (n << 1) | (1 if b == "1" else 0)
        return n

    def to_bool(self) -> Optional[bool]:
        """归约成 0/1（非零为真）；不可决返回 None。"""
        if self.is_real:
            return bool(self.real)
        if self.has_xz():
            return None
        return any(b == "1" for b in self.bits)

    # ---- 表示 ----
    def raw(self) -> str:
        """转回 fsdbq 口径字符串（``b0101``/``bx``/``r3.14``）。"""
        if self.bits is None:
            return "r%r" % (self.real,)
        if not self.bits:
            return "bx"
        return "b" + "".join(self.bits)

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return "V(%s)" % (self.raw(),)

    def __eq__(self, other) -> bool:  # pragma: no cover - 测试便利
        return isinstance(other, V) and self.bits == other.bits and self.real == other.real

    # ---- 构造 ----
    @staticmethod
    def from_int(n: int, width: Optional[int] = None) -> "V":
        if width is None:
            width = max(1, n.bit_length())
        return V([("1" if (n >> (width - 1 - i)) & 1 else "0") for i in range(width)])

    @staticmethod
    def x(width: int = 1) -> "V":
        return V([UNKNOWN] * max(1, width))

    @staticmethod
    def one() -> "V":
        return V(["1"])

    @staticmethod
    def zero() -> "V":
        return V(["0"])


def value_from_fsdb(raw: Optional[str]) -> V:
    """fsdbq 原始值（``b0101``/``b1``/``bx``/``r3.14``）→ :class:`V`。

    None / 空串 / 未在波形里出现过一律按 x（不可决）处理——查不到值
    不能冒充 0。
    """
    if raw is None:
        return V.x()
    s = str(raw).strip()
    if not s:
        return V.x()
    if s[0] in "rR":
        try:
            return V(real=float(s[1:]))
        except ValueError:
            return V.x()
    if s[0] in "bB":
        bits = s[1:].lower().replace("_", "")
        if not bits:
            return V.x()
        return V([c if c in "01xz" else "x" for c in bits])
    # 无前缀：按裸位串/数字兜底
    s = s.lower()
    if set(s) <= set("01xz"):
        return V(list(s) or ["x"])
    try:
        return V(real=float(s))
    except ValueError:
        return V([c if c in "01xz" else "x" for c in s])


def _pad(a: V, b: V) -> Tuple[List[str], List[str]]:
    w = max(a.width, b.width)
    return _ext_bits(a, w), _ext_bits(b, w)


def _ext_bits(v: V, width: int) -> List[str]:
    if v.is_real:
        n = int(v.real)
        return [("1" if (n >> (width - 1 - i)) & 1 else "0") for i in range(width)]
    bits = list(v.bits) if v.bits else ["x"]
    if len(bits) < width:
        bits = ["0"] * (width - len(bits)) + bits
    return bits[:width] if len(bits) > width else bits


# ------------------------------------------------------------------ 词法

_TOKEN_RE = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<lit>(?:\d+[sS]?)?'[sS]?[bBoOdDhH][0-9a-fA-FxzXZ_]+)
  | (?P<num>\d+\.\d+|\d+)
  | (?P<name>[A-Za-z_\\][\w$]*(?:\.[A-Za-z_\\$][\w$]*)*)
  | (?P<op>===|!==|<<|>>>|>>|<=|>=|&&|\|\||==|!=|[-+*/%<>!~&|^()\[\]:?.])
    """,
    re.VERBOSE,
)

_NAME_RE = re.compile(r"[A-Za-z_\\][\w$]*")


def _lex(text: str) -> List[Tuple[str, str, int]]:
    out: List[Tuple[str, str, int]] = []
    pos = 0
    while pos < len(text):
        m = _TOKEN_RE.match(text, pos)
        if not m:
            raise ExprError("无法识别的字符 %r（位置 %d）" % (text[pos], pos))
        pos = m.end()
        if m.lastgroup == "ws":
            continue
        kind = {"lit": "lit", "num": "num", "name": "name", "op": "op"}[m.lastgroup]
        out.append((kind, m.group().strip(), m.start()))
    out.append(("eof", "", len(text)))
    return out


def _lit_to_value(text: str) -> V:
    """``8'hAF`` / ``4'b10x1`` / ``'b1`` / ``3`` / ``4.5`` → V。"""
    t = text.replace("_", "").strip()
    m = re.match(r"^(\d*)[sS]?'[sS]?([bBoOdDhH])([0-9a-fA-FxzXZ]+)$", t)
    if m:
        width = int(m.group(1)) if m.group(1) else 0
        base = m.group(2).lower()
        digits = m.group(3).lower()
        per = {"b": 1, "o": 3, "d": 0, "h": 4}[base]
        bits: List[str] = []
        if base == "d":
            if set(digits) <= set("0123456789"):
                bits = list(bin(int(digits))[2:])
            else:
                raise ExprError("十进制字面量含 x/z: %s" % text)
        else:
            for ch in digits:
                if ch in "xz":
                    bits.extend([ch] * (per or 1))
                else:
                    v = int(ch, 16)
                    for i in range((per or 1) - 1, -1, -1):
                        bits.append("1" if (v >> i) & 1 else "0")
        if width and len(bits) < width:
            bits = ["0"] * (width - len(bits)) + bits
        elif width and len(bits) > width:
            bits = bits[len(bits) - width:]
        return V(bits or ["x"])
    if re.match(r"^\d+\.\d+$", t):
        return V(real=float(t))
    if re.match(r"^\d+$", t):
        return V.from_int(int(t))
    if t.lower() == "x":
        return V(["x"])
    if t.lower() == "z":
        return V(["z"])
    raise ExprError("无法解析的字面量: %s" % text)


# ------------------------------------------------------------------ 语法树
# 节点用 tuple：(kind, ...)
#   ("bin", op, l, r)  ("un", op, x)  ("sel", base, idx)  ("part", base, hi, lo)
#   ("sig", name)      ("lit", V)     ("cond", c, a, b)

_BIN_OPS = frozenset((
    "&&", "||", "==", "!=", "===", "!==", "<", "<=", ">", ">=",
    "+", "-", "*", "/", "%", "&", "|", "^", "<<", ">>", ">>>",
))
_UN_OPS = frozenset(("!", "~", "-", "&", "|", "^"))


class _Parser:
    def __init__(self, text: str):
        self.toks = _lex(text)
        self.i = 0
        self.text = text

    def _peek(self) -> Tuple[str, str, int]:
        return self.toks[self.i]

    def _next(self) -> Tuple[str, str, int]:
        tok = self.toks[self.i]
        self.i += 1
        return tok

    def _accept_op(self, *ops: str) -> Optional[Tuple[str, str, int]]:
        kind, val, pos = self._peek()
        if kind == "op" and val in ops:
            self.i += 1
            return (kind, val, pos)
        return None

    def parse(self):
        node = self._ternary()
        kind, val, pos = self._peek()
        if kind != "eof":
            raise ExprError("位置 %d 有多余内容 %r" % (pos, val or self.text[pos:pos + 8]))
        return node

    def _ternary(self):
        cond = self._or()
        if self._accept_op("?"):
            a = self._ternary()
            if not self._accept_op(":"):
                kind, val, pos = self._peek()
                raise ExprError("位置 %d：三元表达式缺 ':'" % (pos,))
            b = self._ternary()
            return ("cond", cond, a, b)
        return cond

    def _or(self):
        node = self._and()
        while self._accept_op("||"):
            node = ("bin", "||", node, self._and())
        return node

    def _and(self):
        node = self._bitor()
        while self._accept_op("&&"):
            node = ("bin", "&&", node, self._bitor())
        return node

    def _bitor(self):
        node = self._bitxor()
        while self._accept_op("|"):
            node = ("bin", "|", node, self._bitxor())
        return node

    def _bitxor(self):
        node = self._bitand()
        while self._accept_op("^"):
            node = ("bin", "^", node, self._bitand())
        return node

    def _bitand(self):
        node = self._eq()
        while self._accept_op("&"):
            node = ("bin", "&", node, self._eq())
        return node

    def _eq(self):
        node = self._rel()
        while True:
            op = self._accept_op("===", "!==", "==", "!=")
            if not op:
                return node
            node = ("bin", op[1], node, self._rel())

    def _rel(self):
        node = self._shift()
        while True:
            op = self._accept_op("<=", ">=", "<", ">")
            if not op:
                return node
            node = ("bin", op[1], node, self._shift())

    def _shift(self):
        node = self._add()
        while True:
            op = self._accept_op("<<", ">>>", ">>")
            if not op:
                return node
            node = ("bin", op[1], node, self._add())

    def _add(self):
        node = self._mul()
        while True:
            op = self._accept_op("+", "-")
            if not op:
                return node
            node = ("bin", op[1], node, self._mul())

    def _mul(self):
        node = self._unary()
        while True:
            op = self._accept_op("*", "/", "%")
            if not op:
                return node
            node = ("bin", op[1], node, self._unary())

    def _unary(self):
        ops: List[str] = []
        while True:
            op = self._accept_op(*_UN_OPS)
            if not op:
                break
            ops.append(op[1])
        node = self._postfix()
        for op in reversed(ops):
            node = ("un", op, node)
        return node

    def _postfix(self):
        node = self._primary()
        while True:
            if not self._accept_op("["):
                return node
            hi = self._ternary()
            if self._accept_op(":"):
                lo = self._ternary()
                if not self._accept_op("]"):
                    raise ExprError("位选缺 ']'")
                node = ("part", node, hi, lo)
            else:
                if not self._accept_op("]"):
                    raise ExprError("位选缺 ']'")
                node = ("sel", node, hi)
            while self._accept_op("["):
                idx = self._ternary()
                if self._accept_op(":"):
                    lo = self._ternary()
                    if not self._accept_op("]"):
                        raise ExprError("位选缺 ']'")
                    node = ("part", node, idx, lo)
                else:
                    if not self._accept_op("]"):
                        raise ExprError("位选缺 ']'")
                    node = ("sel", node, idx)
            # 连续位选支持：sig[3][0]
    def _primary(self):
        kind, val, pos = self._peek()
        if kind == "op" and val == "(":
            self._next()
            node = self._ternary()
            if not self._accept_op(")"):
                raise ExprError("括号不匹配（位置 %d）" % pos)
            return node
        if kind == "num":
            self._next()
            return ("lit", _lit_to_value(val))
        if kind == "lit":
            self._next()
            return ("lit", _lit_to_value(val))
        if kind == "name":
            self._next()
            if val.lower() in ("x", "z", "bx", "bz"):
                return ("lit", V([val.lower()[-1]]))
            return ("sig", val)
        if kind == "op" and val in ("&", "|", "^"):
            # 前缀归约落在 _unary；这里兜住裸出现
            raise ExprError("位置 %d：孤立的 %r" % (pos, val))
        raise ExprError("位置 %d：期待信号、字面量或 '('，得到 %r" % (pos, val or "结尾"))


def parse_expr(text: str):
    """把表达式字符串解析成语法树；语法错误抛 :class:`ExprError`。"""
    if not text or not str(text).strip():
        raise ExprError("表达式为空")
    return _Parser(str(text)).parse()


def collect_signals(node) -> List[str]:
    """按出现顺序收集表达式里引用的信号名（去重）。"""
    out: List[str] = []
    seen = set()

    def walk(n):
        if not isinstance(n, tuple):
            return
        kind = n[0]
        if kind == "sig":
            if n[1] not in seen:
                seen.add(n[1])
                out.append(n[1])
        elif kind in ("bin",):
            walk(n[2])
            walk(n[3])
        elif kind == "un":
            walk(n[2])
        elif kind in ("sel", "part"):
            walk(n[1])
            for sub in n[2:]:
                walk(sub)
        elif kind == "cond":
            walk(n[1])
            walk(n[2])
            walk(n[3])
        # "lit" 无信号

    walk(node)
    return out


# ------------------------------------------------------------------ 求值

def _b2i(b: str) -> int:
    return 1 if b == "1" else 0


def _bits_of(v: V, width: Optional[int] = None) -> List[str]:
    if width is None:
        return _ext_bits(v, v.width or 1)
    return _ext_bits(v, width)


def _cmp_known(a: V, b: V) -> Optional[int]:
    """两边都可决时返回 -1/0/1，否则 None。实数与位向量混比按数值。"""
    if a.is_real or b.is_real:
        if not a.is_real and a.has_xz():
            return None
        if not b.is_real and b.has_xz():
            return None
        fa = a.real if a.is_real else a.int_or_none()
        fb = b.real if b.is_real else b.int_or_none()
        if fa is None or fb is None:
            return None
        return -1 if fa < fb else (1 if fa > fb else 0)
    ia, ib = a.int_or_none(), b.int_or_none()
    if ia is None or ib is None:
        return None
    return -1 if ia < ib else (1 if ia > ib else 0)


def _eval_bin(op: str, l: V, r: V) -> V:
    # 逻辑（三值 Kleene）
    if op == "&&":
        a, b = l.to_bool(), r.to_bool()
        if a is False or b is False:
            return V.zero()
        if a is None or b is None:
            return V(["x"])
        return V.one() if (a and b) else V.zero()
    if op == "||":
        a, b = l.to_bool(), r.to_bool()
        if a is True or b is True:
            return V.one()
        if a is None or b is None:
            return V(["x"])
        return V.one() if (a or b) else V.zero()
    # 相等
    if op in ("==", "!=", "===", "!=="):
        if op in ("===", "!=="):
            la, lb = _bits_of(l), _bits_of(r)
            same = la == lb
            # 位宽补齐后逐位比（_bits_of 已补到同宽）
            res = V.one() if same else V.zero()
            return res if op == "===" else V.zero() if same else V.one()
        c = _cmp_known(l, r)
        if c is None:
            return V(["x"])
        eq = c == 0
        return V.one() if eq == (op == "==") else V.zero()
    # 按位运算：逐位处理，x&0=0、x|1=1 可决（放在 xz 短路**之前**）
    la, lb = _pad(l, r)
    if op == "&":
        return V([("0" if (x == "0" or y == "0") else
                   ("x" if (x in _XZ or y in _XZ) else "1"))
                  for x, y in zip(la, lb)])
    if op == "|":
        return V([("1" if (x == "1" or y == "1") else
                   ("x" if (x in _XZ or y in _XZ) else "0"))
                  for x, y in zip(la, lb)])
    if op == "^":
        if any(x in _XZ or y in _XZ for x, y in zip(la, lb)):
            return V(["x"] * len(la))
        return V([str(_b2i(x) ^ _b2i(y)) for x, y in zip(la, lb)])
    # 关系/算术/移位：任一边不可决即 x
    if l.has_xz() or r.has_xz():
        return V(["x"])
    if l.is_real or r.is_real:
        fa = l.real if l.is_real else float(l.int_or_none() or 0)
        fb = r.real if r.is_real else float(r.int_or_none() or 0)
        if op == "<":
            return V.one() if fa < fb else V.zero()
        if op == "<=":
            return V.one() if fa <= fb else V.zero()
        if op == ">":
            return V.one() if fa > fb else V.zero()
        if op == ">=":
            return V.one() if fa >= fb else V.zero()
        if op == "+":
            return V(real=fa + fb)
        if op == "-":
            return V(real=fa - fb)
        if op == "*":
            return V(real=fa * fb)
        if op == "/":
            return V(real=fa / fb) if fb else V(["x"])
        return V(["x"])
    if op in ("<", "<=", ">", ">="):
        c = _cmp_known(l, r)
        if c is None:
            return V(["x"])
        res = {"<": c < 0, "<=": c <= 0, ">": c > 0, ">=": c >= 0}[op]
        return V.one() if res else V.zero()
    la, lb = _pad(l, r)
    if op == "+":
        return V.from_int(l.int_or_none() + r.int_or_none(), width=max(len(la), len(lb)) + 1)
    if op == "-":
        return V.from_int(l.int_or_none() - r.int_or_none(), width=max(len(la), len(lb)) + 1)
    if op == "*":
        return V.from_int(l.int_or_none() * r.int_or_none(), width=len(la) + len(lb))
    if op in ("/", "%"):
        ri = r.int_or_none()
        if ri == 0:
            return V.x(max(len(la), len(lb)))
        li = l.int_or_none()
        return V.from_int(li // ri if op == "/" else li % ri, width=max(len(la), len(lb)))
    if op in ("<<", ">>", ">>>"):
        sh = r.int_or_none()
        if sh is None or sh < 0:
            return V.x(len(la))
        bits = la
        if op == "<<":
            bits = bits[sh:] + ["0"] * min(sh, len(la))
        else:
            fill = ["0"]  # 无符号口径 >> 与 >>> 同
            bits = fill * min(sh, len(la)) + bits[:max(0, len(la) - sh)]
        return V(bits)
    raise ExprError("不支持的双目运算: %s" % op)


def _eval_un(op: str, x: V) -> V:
    if op == "!":
        b = x.to_bool()
        if b is None:
            return V(["x"])
        return V.zero() if b else V.one()
    if op == "~":
        if x.is_real:
            return V.from_int(~int(x.real))
        return V([("x" if b in _XZ else ("1" if b == "0" else "0")) for b in _bits_of(x)])
    if op == "-":
        if x.is_real:
            return V(real=-x.real)
        if x.has_xz():
            return V(["x"] * x.width)
        return V.from_int(-x.int_or_none(), width=x.width + 1)
    if op in ("&", "|", "^"):
        bits = _bits_of(x)
        if op == "&":
            if "0" in bits:
                return V.zero()
            if "x" in bits or "z" in bits:
                return V(["x"])
            return V.one()
        if op == "|":
            if "1" in bits:
                return V.one()
            if "x" in bits or "z" in bits:
                return V(["x"])
            return V.zero()
        if any(b in _XZ for b in bits):
            return V(["x"])
        return V.one() if (bits.count("1") % 2) else V.zero()
    raise ExprError("不支持的单目运算: %s" % op)


def _select(bits: List[str], msb_index: int) -> str:
    """按 ``sig[i]`` 语义取位：i 以 **LSB=0** 计（fsdbq 位串 LSB 在末尾）。"""
    if msb_index < 0 or msb_index >= len(bits):
        return "x"
    return bits[len(bits) - 1 - msb_index]


def evaluate(node, get_value: Callable[[str], Optional[str]]) -> V:
    """对语法树求值。``get_value(信号全路径)`` 返回 fsdbq 原始值或 None。

    None（波形里没有该信号/该时刻之前无值）一律按 x 处理。
    """
    kind = node[0]
    if kind == "lit":
        return node[1]
    if kind == "sig":
        return value_from_fsdb(get_value(node[1]))
    if kind == "un":
        return _eval_un(node[1], evaluate(node[2], get_value))
    if kind == "bin":
        return _eval_bin(node[1], evaluate(node[2], get_value), evaluate(node[3], get_value))
    if kind == "cond":
        c = evaluate(node[1], get_value).to_bool()
        if c is None:
            return V(["x"])
        return evaluate(node[2] if c else node[3], get_value)
    if kind == "sel":
        base = evaluate(node[1], get_value)
        idx = evaluate(node[2], get_value).int_or_none()
        if idx is None or base.has_xz():
            return V(["x"])
        return V([_select(_bits_of(base), idx)])
    if kind == "part":
        base = evaluate(node[1], get_value)
        hi = evaluate(node[2], get_value).int_or_none()
        lo = evaluate(node[3], get_value).int_or_none()
        if hi is None or lo is None or base.has_xz():
            return V.x(max(1, abs(hi or 0 - (lo or 0)) + 1))
        if hi < lo:
            hi, lo = lo, hi
        bits = _bits_of(base)
        out = []
        for i in range(hi, lo - 1, -1):  # MSB→LSB，与书写顺序一致
            out.append(_select(bits, i))
        return V(out)
    raise ExprError("未知语法节点: %r" % (kind,))


def truth_of(v: V) -> str:
    """把一个值判成 ``true`` / ``false`` / ``undecidable``（x/z 一律不可决）。"""
    b = v.to_bool()
    if b is None:
        return "undecidable"
    return "true" if b else "false"
