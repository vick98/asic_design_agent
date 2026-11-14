# 作者：vick 邮箱：ykun@yk9811.com

import unittest

from framework.gates.docs import check_bloat
from framework.gates.numeric import scan_text
from framework.gates.rtl import check_instance, compare_ports
from framework.tests.util import RepoTest
from framework.toolbox.fx import cmul, finish, fmt_s, sat_bounds, shift
from framework.toolbox.fx import line as fx_line


class GateTests(RepoTest):
    def test_d8_narrow_and_ok(self):
        self.assertTrue(scan_text("o_obs_node 8 bit", "d8"))
        self.assertFalse(scan_text("o_obs_node 16 bit", "d8ok"))

    def test_bare_format(self):
        self.assertTrue(scan_text("节点 <8,2,t>", "bare"))

    def test_latency_section_requires_cycles(self):
        self.assertTrue(scan_text("## 8. 模块逻辑块描述\n\n没有周期\n", "lat"))

    def test_formula_stamp(self):
        stamped = fx_line("mul", "<8,2,t> * <8,2,t>", (15, 4, "t"))
        bad = scan_text("<8,2,t> * <8,2,t> → <16,4,t>\nstamp: %s" % stamped["stamp"], "bad")
        plain = scan_text("<8,2,t> * <8,2,t> → <15,4,t>", "plain")
        good = scan_text(
            "<8,2,t> * <8,2,t> → <15,4,t>\nstamp: %s" % stamped["stamp"], "good")
        self.assertTrue(bad)
        self.assertTrue(plain)
        self.assertFalse(good)

    def test_bloat_table(self):
        text = "# 标题\n\n| x |\n\n## 2. 正文\n\n内容\n"
        self.assertTrue(check_bloat(text, "t"))

    def test_rtl_port_width(self):
        spec = (
            "## 3. 端口表\n\n| 名字 | 方向 | 位宽 |\n|---|---|---|\n"
            "| i_a | input | 8 |\n| o_b | output | 8 |\n"
        )
        rtl_ok = "module alu (input [7:0] i_a, output [7:0] o_b);\nendmodule\n"
        rtl_bad = "module alu (input [3:0] i_a, output [7:0] o_b);\nendmodule\n"
        self.assertFalse(compare_ports(spec, rtl_ok, "alu"))
        self.assertTrue(compare_ports(spec, rtl_bad, "alu"))

    def test_missing_instance_port(self):
        mod = "module foo #(parameter W = 8) (input clk, output [7:0] o_q);\nendmodule\n"
        top_bad = "module top; foo u0 (.clk(clk)); endmodule\n"
        self.assertTrue(check_instance(mod, top_bad, "foo", "u0"))

    def test_port_cell_and_stamp_on_next_line(self):
        port = scan_text("| i_a | input | 8（<8,2,t>） | clk | 说明 | 依据 |", "port")
        self.assertFalse(any(item["rule"] == "fx-bare" for item in port))
        stamped = fx_line("mul", "<8,2,t> * <8,2,t>", (15, 4, "t"))
        text = "<8,2,t> * <8,2,t> → <15,4,t>\nstamp: %s\n" % stamped["stamp"]
        self.assertFalse(scan_text(text, "next"))

    def test_stamp_belongs_to_its_own_expression(self):
        # 一行里写两条表达式时，每条只取自己结束之后的第一枚戳记。
        src = (24, 3, "t")
        other = (12, 1, "t")
        mul_expr = "%s ** %s" % (fmt_s(src), fmt_s(other))
        mul_stamp = fx_line("cmul", mul_expr, cmul(src, other))["stamp"]
        fin = finish(src, other, 10)
        fin_expr = "finish %s >> 10 half-up + sat -> %s" % (fmt_s(src), fmt_s(other))
        fin_stamp = fx_line("finish", fin_expr, None,
                            {"shift": fin["shift"], "sat": fin["sat"]})["stamp"]
        line = "%s → %s  stamp: %s；%s  stamp: %s" % (
            mul_expr, fmt_s(cmul(src, other)), mul_stamp, fin_expr, fin_stamp)
        self.assertEqual([f for f in scan_text(line, "f01") if f["rule"].startswith("fx")], [])
        # 拿别人的戳记顶替，仍然报 fx-stamp
        swapped = line.replace(mul_stamp, fin_stamp, 1)
        stamps = [f for f in scan_text(swapped, "f01swap") if f["rule"] == "fx-stamp"]
        self.assertEqual(len(stamps), 1)
        self.assertIn(mul_expr, stamps[0]["detail"])

    def test_stamp_belongs_to_its_own_expression_shift_sat(self):
        shr = shift((16, 4, "t"), 2, shrink=True)
        shr_expr = "%s >> 2 shrink" % fmt_s((16, 4, "t"))
        shr_stamp = fx_line("shift", shr_expr, shr)["stamp"]
        bounds = sat_bounds((12, 1, "t"), symmetric=True)
        sat_expr = "sat %s %s" % (fmt_s((12, 1, "t")), bounds["mode"])
        sat_stamp = fx_line("sat", sat_expr, None, bounds)["stamp"]
        text = "%s → %s  stamp: %s；%s  stamp: %s" % (
            shr_expr, fmt_s(shr), shr_stamp, sat_expr, sat_stamp)
        self.assertEqual([f for f in scan_text(text, "f01b") if f["rule"].startswith("fx")], [])
        swapped = text.replace(shr_stamp, sat_stamp, 1)
        self.assertTrue(any(f["rule"] == "fx-stamp"
                            for f in scan_text(swapped, "f01bswap")))

    def test_connection_table_width_matches_port_table(self):
        # 位宽列 `12（<12,1,t>）` 与端口表同一套取宽，不再整行跳过。
        from framework.gates.specconn import scan_spec_conn
        spec = (
            "# demo\n\n## 3. 模块接口\n\n"
            "| 名字 | 方向 | 位宽 | 时钟域 | 说明 | 位宽依据 |\n|---|---|---|---|---|---|\n"
            "| i_x | input | 12（<12,1,t>） | clk_core | 输入 | 行 2 |\n"
            "| o_y | output | 12（<12,1,t>） | clk_core | 输出 | 行 2 |\n\n"
            "## 6. 模块连接关系\n\n"
            "| 源 | 目标 | 位宽 | 时钟域 | 说明 |\n|---|---|---|---|---|\n"
            "| i_x | u_sub | 12（<12,1,t>） | clk_core | 入 |\n"
            "| u_sub | o_y | 12（<12,1,t>） | clk_core | 出 |\n"
        )
        self.assertFalse([f for f in scan_spec_conn(spec, "spec") if f["rule"] == "C3"])
        bad = spec.replace("| i_x | u_sub | 12（<12,1,t>） |",
                           "| i_x | u_sub | 13（<13,1,t>） |")
        hits = [f for f in scan_spec_conn(bad, "spec") if f["rule"] == "C3"]
        self.assertTrue(hits)
        self.assertIn("i_x", hits[0]["detail"])
        plain = spec.replace("12（<12,1,t>）", "12")
        self.assertFalse([f for f in scan_spec_conn(plain, "spec") if f["rule"] == "C3"])

    def test_bad_shift_and_illegal_format(self):
        bad = scan_text("<16,4,t> >> 2 shrink → <14,3,t>\n", "shr")
        self.assertTrue(any(item["rule"] == "fx" for item in bad))
        illegal = scan_text("看到 <8,8,t> 就停。\n", "badfmt")
        self.assertTrue(any(item["rule"] == "D6b" for item in illegal))

    def test_chain_factor_and_param(self):
        from framework.gates.numeric import scan_params
        chain = "\n".join([
            "| x | a | b | <8,2,t> |",
            "| y | a | b | <8,2,t> |",
            "| z | a | b | <16,4,t> |",
            "x * y -> z",
        ])
        self.assertTrue(any(item["rule"] == "D1b" for item in scan_text(chain, "flow")))
        good_z = chain.replace("<16,4,t>", "<15,4,t>")
        self.assertFalse(any(item["rule"] == "D1b" for item in scan_text(good_z, "flow")))
        factor = "| SEG_A | 存储 | 2×3 = 7 | 16 |"
        self.assertTrue(any(item["rule"] == "D6a" for item in scan_text("区段\n" + factor, "seg")))
        ok = scan_text("区段\n| SEG_A | 存储 | 2×3 = 6 | 16 |", "seg")
        self.assertFalse(any(item["rule"] == "D6a" for item in ok))
        docs = {
            "a.md": "位宽参数 WIDTH = 8\n",
            "b.md": "位宽参数 WIDTH = 9\n",
        }
        self.assertTrue(any(item["rule"] == "D7" for item in scan_params(docs)))
        self.assertFalse(scan_params({"a.md": "位宽参数 WIDTH = 8\n", "b.md": "位宽 WIDTH = 8\n"}))


if __name__ == "__main__":
    unittest.main()
