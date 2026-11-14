# 作者：vick 邮箱：ykun@yk9811.com

import unittest

from framework.tests.util import RepoTest
from framework.toolbox.fx import (
    FxError, add, addr_capacity, cmul, finish, golden_tol, latency, lift, logical_shr, mul, obs16,
    parse_fmt, round_shr, run_chain, sat_bounds, shift, sub,
)


class FxTests(RepoTest):
    def test_signed_mul(self):
        self.assertEqual(mul((8, 2, "t"), (8, 2, "t")), (15, 4, "t"))

    def test_unsigned_mul(self):
        self.assertEqual(mul((8, 2, "u"), (8, 2, "u")), (16, 4, "u"))

    def test_cmul(self):
        self.assertEqual(cmul((8, 2, "t"), (8, 2, "t")), (16, 5, "t"))

    def test_unsigned_add(self):
        self.assertEqual(add((8, 2, "u"), (8, 2, "u")), (9, 3, "u"))

    def test_signed_add_stays_signed(self):
        self.assertEqual(add((8, 2, "t"), (8, 3, "t"))[2], "t")

    def test_shrink_shift(self):
        self.assertEqual(shift((16, 4, "t"), 2, shrink=True), (14, 2, "t"))

    def test_obs16(self):
        self.assertEqual(obs16((20, 8, "t"))["format"], (16, 4, "t"))

    def test_sat_negative(self):
        self.assertEqual(sat_bounds((8, 1, "t"), False)["min"], -128)

    def test_round_half_up(self):
        self.assertEqual(round_shr(5, 1, "half_up"), 3)

    def test_round_even(self):
        self.assertEqual(round_shr(5, 1, "even"), 2)

    def test_latency(self):
        self.assertEqual(latency([1, 2]), 3)

    def test_finish_closes_and_bounds(self):
        got = finish((23, 1, "t"), (12, 1, "t"), 11)
        self.assertEqual(got["shift"], 11)
        self.assertEqual(got["f_src"], 21)
        self.assertEqual(got["f_dst"], 10)
        self.assertEqual(got["sat"]["min"], -2047)
        self.assertEqual(got["sat"]["max"], 2047)

    def test_finish_rejects_fraction_mismatch(self):
        with self.assertRaises(FxError):
            finish((24, 3, "t"), (12, 1, "t"), 11)

    def test_finish_rejects_sign_change(self):
        with self.assertRaises(FxError):
            finish((12, 1, "t"), (12, 1, "u"), 0)

    def test_golden_tol_lsb(self):
        # 新口径（I 不含符号位）：f = W−I−1 = 8−2−1 = 5
        self.assertEqual(golden_tol((8, 2, "t"), 1)["lsb_exp"], -5)

    def test_logical_shr(self):
        self.assertEqual(logical_shr((8, 2, "u"), 1, True), (7, 1, "u"))

    def test_addr_percent(self):
        got = addr_capacity([1024], 10)["percent_of_2_20"]
        self.assertLess(abs(got - 0.09765625), 1e-6)

    def test_addr_mbit(self):
        got = addr_capacity([1024], 10, word_bits=16)["mbit"]
        self.assertLess(abs(got - 0.016384), 1e-9)

    def test_golden_legality_and_lift(self):
        with self.assertRaises(FxError):
            parse_fmt("<8,8,t>")
        self.assertEqual(parse_fmt("<8,7,t>"), (8, 7, "t"))
        self.assertEqual(parse_fmt("<8,8,u>"), (8, 8, "u"))
        self.assertEqual(lift(parse_fmt("<8,8,u>")), (9, 8, "t"))
        self.assertEqual(lift(parse_fmt("<8,4,u>")), (9, 4, "t"))
        self.assertEqual(lift(parse_fmt("<8,2,t>")), (8, 2, "t"))

    def test_golden_mul_and_cmul(self):
        self.assertEqual(mul((14, 4, "t"), (12, 3, "t")), (25, 7, "t"))
        self.assertEqual(mul((8, 8, "u"), (8, 7, "t")), (16, 15, "t"))
        self.assertEqual(mul((8, 4, "u"), (8, 4, "t")), (16, 8, "t"))
        self.assertEqual(cmul((14, 4, "t"), (12, 2, "t")), (26, 7, "t"))
        with self.assertRaises(FxError):
            cmul((8, 2, "u"), (8, 2, "t"))

    def test_golden_add_and_sub(self):
        self.assertEqual(add((8, 2, "t"), (8, 3, "t")), (10, 4, "t"))
        self.assertEqual(add((14, 4, "t"), (12, 3, "t")), (15, 5, "t"))
        self.assertEqual(add((8, 4, "u"), (8, 4, "t")), (10, 5, "t"))
        self.assertEqual(add((8, 8, "u"), (8, 7, "t")), (10, 9, "t"))
        self.assertEqual(sub((8, 8, "u"), (8, 8, "u")), (9, 8, "t"))
        self.assertEqual(sub((8, 4, "u"), (8, 2, "u")), (11, 4, "t"))
        self.assertEqual(sub((8, 2, "t"), (8, 2, "t")), (9, 3, "t"))
        self.assertEqual(sub((8, 4, "u"), (8, 4, "t")), (10, 5, "t"))

    def test_golden_shift_obs_sat_round(self):
        self.assertEqual(shift((16, 4, "t"), 2, shrink=False), (16, 4, "t"))
        with self.assertRaises(FxError):
            shift((16, 1, "t"), 2, shrink=True)
        got = obs16((12, 3, "t"))
        self.assertEqual(got["format"], (16, 3, "t"))
        self.assertEqual(got["pad_low"], 4)
        self.assertEqual(sat_bounds((8, 1, "t"), False)["max"], 127)
        self.assertEqual(sat_bounds((8, 1, "t"), True)["min"], -127)
        self.assertEqual(sat_bounds((8, 1, "u"), False)["min"], 0)
        self.assertEqual(sat_bounds((8, 1, "u"), False)["max"], 255)
        self.assertEqual(round_shr(5, 1, "trunc"), 2)
        self.assertEqual(round_shr(-5, 1, "trunc"), -3)
        self.assertEqual(round_shr(-5, 1, "half_up"), -2)
        self.assertEqual(round_shr(-3, 1, "half_up"), -1)
        self.assertEqual(round_shr(7, 1, "even"), 4)
        self.assertEqual(round_shr(-5, 1, "even"), -2)
        self.assertEqual(round_shr(-3, 1, "even"), -2)

    def test_golden_tol_ref(self):
        plain = golden_tol((8, 2, "t"), 1)
        self.assertEqual(plain["GOLDEN_TOL"], 1)
        scaled = golden_tol((8, 2, "t"), 1, parse_fmt("<10,2,t>"))
        self.assertEqual(scaled["GOLDEN_TOL"], 4)
        finer = golden_tol((8, 2, "t"), 1, parse_fmt("<8,4,t>"))
        self.assertEqual(finer["GOLDEN_TOL"], 0)

    def test_chain(self):
        env, rows = run_chain(
            {"a": "<8,2,t>", "b": "<8,2,t>"},
            [{"op": "mul", "a": "a", "b": "b", "dst": "c"}],
        )
        self.assertEqual(env["c"], (15, 4, "t"))
        self.assertTrue(rows)


if __name__ == "__main__":
    unittest.main()
