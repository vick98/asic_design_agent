"""predicate 测试：表达式 DSL 解析与 4 值求值口径。

重点守住三条口径：
* 含 x/z 的比较/算术/移位一律不可决（x），``===``/``!==`` 恒可决；
* 逻辑运算三值 Kleene（``x&&0=0``、``x||1=1``）；
* 查不到的信号值（None）按 x 处理，不冒充 0。
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from eda_mcp.predicate import (  # noqa: E402
    ExprError,
    V,
    collect_signals,
    evaluate,
    parse_expr,
    truth_of,
    value_from_fsdb,
)


def ev(expr: str, values: dict):
    return evaluate(parse_expr(expr), lambda name: values.get(name))


def b(bits: str) -> V:
    return V(list(bits))


class ParseTests(unittest.TestCase):
    def test_precedence_and_parens(self):
        # && 高于 ||；+ 高于 >
        self.assertEqual(collect_signals(parse_expr("a || b && c")), ["a", "b", "c"])
        self.assertEqual(collect_signals(parse_expr("(a || b) && c")), ["a", "b", "c"])
        self.assertEqual(collect_signals(parse_expr("a + b > 3")), ["a", "b"])
        self.assertEqual(collect_signals(parse_expr("a > 3 && b != 4 || c")), ["a", "b", "c"])

    def test_literals(self):
        self.assertEqual(ev("8'hFF", {}) .raw(), "b11111111")
        self.assertEqual(ev("4'b10x1", {}).raw(), "b10x1")
        self.assertEqual(ev("12", {}).raw(), "b1100")
        self.assertEqual(ev("'b1", {}).raw(), "b1")
        self.assertEqual(ev("4.5", {}).raw(), "r4.5")
        self.assertEqual(ev("8'd10", {}).raw(), "b00001010")
        self.assertEqual(ev("8'b1_010", {}).raw(), "b00001010")

    def test_errors(self):
        with self.assertRaises(ExprError):
            parse_expr("a &&")
        with self.assertRaises(ExprError):
            parse_expr("(a && b")
        with self.assertRaises(ExprError):
            parse_expr("a ? b")
        with self.assertRaises(ExprError):
            parse_expr("")

    def test_signals_dedup_order(self):
        self.assertEqual(collect_signals(parse_expr("b.a == 1 && b.a > 0 && a.c")), ["b.a", "a.c"])
        self.assertEqual(collect_signals(parse_expr("u.x[3] == u.y[7:4]")), ["u.x", "u.y"])


class EvalTests(unittest.TestCase):
    def test_missing_value_is_x(self):
        # 波形里查不到的信号按 x，不冒充 0
        self.assertEqual(ev("u.req == 1", {}).raw(), "bx")
        self.assertEqual(truth_of(ev("u.req == 1", {})), "undecidable")

    def test_equality_with_x_undecidable(self):
        self.assertEqual(ev("a == 1", {"a": "bx"}).raw(), "bx")
        self.assertEqual(ev("a == 1", {"a": "b1"}).raw(), "b1")
        self.assertEqual(ev("a != 1", {"a": "bx"}).raw(), "bx")

    def test_case_equality_always_decidable(self):
        self.assertEqual(ev("a === 4'bx1x0", {"a": "bx1x0"}).raw(), "b1")
        self.assertEqual(ev("a !== 4'bx1x0", {"a": "bx1x0"}).raw(), "b0")
        self.assertEqual(ev("a === 4'b0000", {"a": "bx1x0"}).raw(), "b0")

    def test_kleene_logic(self):
        self.assertEqual(ev("a && b", {"a": "bx", "b": "b0"}).raw(), "b0")
        self.assertEqual(ev("a && b", {"a": "bx", "b": "b1"}).raw(), "bx")
        self.assertEqual(ev("a || b", {"a": "bx", "b": "b1"}).raw(), "b1")
        self.assertEqual(ev("a || b", {"a": "bx", "b": "b0"}).raw(), "bx")
        self.assertEqual(ev("!a", {"a": "bx"}).raw(), "bx")
        self.assertEqual(ev("!a", {"a": "b0"}).raw(), "b1")

    def test_compare_and_arith(self):
        self.assertEqual(ev("a > b", {"a": "b0100", "b": "b0011"}).raw(), "b1")
        self.assertEqual(ev("a + b", {"a": "b0011", "b": "b0001"}).raw(), "b00100")
        self.assertEqual(ev("a - b", {"a": "b0001", "b": "b0011"}).raw(), "b11110")
        self.assertEqual(ev("a * b", {"a": "b010", "b": "b011"}).raw(), "b000110")
        self.assertEqual(ev("a > b", {"a": "b0x00", "b": "b0011"}).raw(), "bx")

    def test_unsigned_semantics(self):
        # 已知口径：无符号。1111(15) > 0001(1)，而不是 -1 < 1
        self.assertEqual(ev("a > b", {"a": "b1111", "b": "b0001"}).raw(), "b1")

    def test_bitwise_and_reduction(self):
        # 1x0 与 0100：bit1 处 x&0=0 可决，bit2 处 1&1=1
        self.assertEqual(ev("a & b", {"a": "b1x0", "b": "b0100"}).raw(), "b0100")
        self.assertEqual(ev("a | b", {"a": "b1x0", "b": "b0100"}).raw(), "b01x0")
        self.assertEqual(ev("a & b", {"a": "b1x1", "b": "b0101"}).raw(), "b0101")
        self.assertEqual(ev("&a", {"a": "b1111"}).raw(), "b1")
        self.assertEqual(ev("&a", {"a": "b1110"}).raw(), "b0")
        self.assertEqual(ev("&a", {"a": "b1x0"}).raw(), "b0")   # 有 0 可决
        self.assertEqual(ev("&a", {"a": "b11x1"}).raw(), "bx")  # 无 0 不可决
        self.assertEqual(ev("|a", {"a": "b000x"}).raw(), "bx")
        self.assertEqual(ev("^a", {"a": "b110"}).raw(), "b0")
        self.assertEqual(ev("^a", {"a": "b1x0"}).raw(), "bx")

    def test_shift(self):
        self.assertEqual(ev("a << 2", {"a": "b0001"}).raw(), "b0100")
        self.assertEqual(ev("a >> 2", {"a": "b1000"}).raw(), "b0010")
        self.assertEqual(ev("a << b", {"a": "b0001", "b": "bx"}).raw(), "bx")  # 移位量不可决 → x

    def test_select_and_part(self):
        vals = {"u.v": "b1101"}
        self.assertEqual(ev("u.v[3]", vals).raw(), "b1")
        self.assertEqual(ev("u.v[0]", vals).raw(), "b1")
        self.assertEqual(ev("u.v[1]", vals).raw(), "b0")
        self.assertEqual(ev("u.v[9]", vals).raw(), "bx")
        self.assertEqual(ev("u.v[3:1]", vals).raw(), "b110")
        self.assertEqual(ev("u.v[1] & u.v[2]", vals).raw(), "b0")

    def test_ternary(self):
        vals = {"c": "b1", "a": "b0010", "b": "b1111"}
        self.assertEqual(ev("c ? a : b", vals).raw(), "b0010")
        self.assertEqual(ev("!c ? a : b", vals).raw(), "b1111")
        self.assertEqual(ev("c ? a : b", {"c": "bx", "a": "b1", "b": "b0"}).raw(), "bx")

    def test_real_values(self):
        vals = {"u.real": "r3.5"}
        self.assertEqual(ev("u.real > 3.0", vals).raw(), "b1")
        self.assertEqual(ev("u.real < 3.0", vals).raw(), "b0")
        self.assertEqual(ev("u.real == bx", vals).raw(), "bx")  # 对 x 比较不可决

    def test_truth_of(self):
        self.assertEqual(truth_of(value_from_fsdb("b1")), "true")
        self.assertEqual(truth_of(value_from_fsdb("b0")), "false")
        self.assertEqual(truth_of(value_from_fsdb("bx")), "undecidable")
        self.assertEqual(truth_of(value_from_fsdb(None)), "undecidable")
        self.assertEqual(truth_of(value_from_fsdb("b1110")), "true")
        self.assertEqual(truth_of(value_from_fsdb("b0000")), "false")

    def test_value_from_fsdb(self):
        self.assertEqual(value_from_fsdb("b0101").raw(), "b0101")
        self.assertEqual(value_from_fsdb("b1").raw(), "b1")
        self.assertEqual(value_from_fsdb("bx").raw(), "bx")
        self.assertEqual(value_from_fsdb("r2.5").raw(), "r2.5")
        self.assertEqual(value_from_fsdb(None).raw(), "bx")
        self.assertEqual(value_from_fsdb("").raw(), "bx")
        self.assertEqual(value_from_fsdb("0101").raw(), "b0101")


class WindowSemanticsTests(unittest.TestCase):
    """给 timequery 用的复合口径：条件只有"确真"才成窗。"""

    def test_compound_condition(self):
        expr = "u.req == 1 && u.cnt > 8'd1"
        self.assertEqual(truth_of(ev(expr, {"u.req": "b1", "u.cnt": "b0010"})), "true")
        self.assertEqual(truth_of(ev(expr, {"u.req": "b1", "u.cnt": "b0001"})), "false")
        self.assertEqual(truth_of(ev(expr, {"u.req": "bx", "u.cnt": "b0010"})), "undecidable")

    def test_handshake_condition(self):
        expr = "u.valid == 1 && u.ready == 1"
        self.assertEqual(truth_of(ev(expr, {"u.valid": "b1", "u.ready": "b1"})), "true")
        self.assertEqual(truth_of(ev(expr, {"u.valid": "b1", "u.ready": "b0"})), "false")


if __name__ == "__main__":
    unittest.main()
