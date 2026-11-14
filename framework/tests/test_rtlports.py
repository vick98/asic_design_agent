# 作者：vick 邮箱：ykun@yk9811.com

"""tb-gen 端口真值校验（rtlports）与 lec 等价性检查能力。

- rtlports.parse_ports：pyslang 可选（装了走 AST 求值，没装回退正则），
  断言与解析器无关；
- tbgen.port_check：IR 端口 vs RTL 实际端口，拦截不一致的骨架生成；
- lec：judge 判定、run_other 前置检查、行 10 的 hint 提示、driver 解析。
"""

import os
import unittest

from framework.profile_run import judge, run_other
from framework.gates.run import _lec_hint_findings
from framework.rtlports import diff_ports, parse_ports
from framework.state import init_sys, load_state, sys_dir
from framework.tests.util import RepoTest, plant_sample
from framework.tbgen import generate, port_check


def _write_rtl(base, modname, text):
    os.makedirs(os.path.join(base, "rtl"), exist_ok=True)
    with open(os.path.join(base, "rtl", modname + ".sv"), "w", encoding="utf-8") as fh:
        fh.write(text)


class ParsePortsTests(RepoTest):
    def test_parse_simple_module(self):
        name = "pdemo"
        init_sys(self.root, name)
        base = sys_dir(self.root, name)
        _write_rtl(base, "adder",
                   "module adder (\n"
                   "    input  [7:0] a,\n"
                   "    input  [7:0] b,\n"
                   "    output [8:0] sum\n"
                   ");\nendmodule\n")
        ports, parser, errors = parse_ports(base, "adder")
        self.assertEqual(errors, [])
        self.assertIn(parser, ("pyslang", "regex"))
        got = {p["name"]: p for p in ports}
        self.assertEqual(set(got), {"a", "b", "sum"})
        self.assertEqual(got["a"]["direction"], "input")
        self.assertEqual(got["sum"]["direction"], "output")
        if got["sum"].get("width") is not None:
            self.assertEqual(got["sum"]["width"], 9)

    def test_missing_file(self):
        name = "pdemo"
        init_sys(self.root, name)
        ports, parser, errors = parse_ports(sys_dir(self.root, name), "ghost")
        self.assertEqual(ports, [])
        self.assertEqual(parser, "")
        self.assertTrue(errors)


class DiffPortsTests(unittest.TestCase):
    def test_identical(self):
        ports = [{"name": "a", "direction": "input", "width": 8}]
        self.assertEqual(
            __import__("framework.rtlports", fromlist=["diff_ports"]).diff_ports(ports, ports),
            [])

    def test_diffs(self):
        ir = [{"name": "a", "direction": "input", "width": 8},
              {"name": "gone", "direction": "input", "width": 4}]
        rtl = [{"name": "a", "direction": "output", "width": 4},
               {"name": "new", "direction": "input", "width": 1}]
        diffs = diff_ports(ir, rtl)
        self.assertEqual(len(diffs), 4, diffs)
        self.assertTrue(any("gone" in d for d in diffs))
        self.assertTrue(any("new" in d for d in diffs))
        self.assertTrue(any("a 方向" in d for d in diffs))
        self.assertTrue(any("a 位宽" in d for d in diffs))


class PortCheckTests(RepoTest):
    def test_sample_ports_match_mini_rtl(self):
        name = "chkdemo"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        diffs, parser, errors = port_check(sys_dir(self.root, name), name, "alu")
        self.assertEqual(errors, [], errors)
        self.assertEqual(diffs, [], diffs)

    def test_port_drift_blocks_generation(self):
        name = "chkdemo"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        base = sys_dir(self.root, name)
        _write_rtl(base, "alu",
                   "module alu (\n"
                   "    input  [7:0] i_a,\n"
                   "    output [7:0] o_y\n"
                   ");\nendmodule\n")  # 偷偷删了 i_b
        diffs, parser, errors = port_check(base, name, "alu")
        self.assertTrue(any("i_b" in d for d in diffs), diffs)


class LecTests(unittest.TestCase):
    def test_judge_lec(self):
        self.assertEqual(judge("lec", {"equiv": 1}), "pass")
        self.assertEqual(judge("lec", {"equiv": 0, "diff": 1}), "fail")
        self.assertEqual(judge("lec", {"tool_error": 1}), "error")
        self.assertEqual(judge("lec", {"no_report": 1}), "error")
        self.assertEqual(judge("lec", {}), "error")

    def test_driver_parse_and_script(self):
        # 用当前激活剖面的 driver 验证：脚本含关键标记，parse 三态齐全。
        from framework.profile_run import _driver, load_profile
        profile = load_profile()
        drv = _driver(profile, "eda.py")
        script = drv.lec_script(profile, "demo", "alu", "mirror/pub_code/ref/alu_ref.sv")
        self.assertIn("miter -equiv", script)
        self.assertIn("CEC RESULT", script)
        self.assertEqual(drv.parse("lec", "CEC RESULT: EQUIV")["equiv"], 1)
        self.assertEqual(drv.parse("lec", "CEC RESULT: DIFF")["diff"], 1)
        self.assertEqual(drv.parse("lec", "CEC RESULT: NOTOOL")["tool_error"], 1)
        self.assertEqual(drv.parse("lec", "nothing")["no_report"], 1)


class LecRunOtherTests(RepoTest):
    def test_unavailable_when_profile_lacks_lec(self):
        # 当前剖面 lec available:false：run lec 判 unavailable（退出码 3 的语义），
        # 模块/黄金参数的前置检查只在剖面开启 lec 能力后才可达。
        name = "lecdemo"
        init_sys(self.root, name)
        result = run_other("lec", {"sys": name, "module": "alu", "gold": "x.sv"})
        self.assertEqual(result["status"], "unavailable")
        self.assertIn("lec", result["summary"])


class LecHintTests(RepoTest):
    def test_hint_without_lec_pass(self):
        name = "hdemo"
        init_sys(self.root, name)
        # 未登记 golden：无提示
        self.assertEqual(_lec_hint_findings(load_state(self.root, name)), [])
        state = load_state(self.root, name)
        state["golden"].append({"data": "testbench/x/data/g.txt", "gen": "gen.py",
                                "inputs": [], "digest": "", "time": "2026-01-01 00:00:00"})
        findings = _lec_hint_findings(state)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["level"], "hint")
        self.assertEqual(findings[0]["rule"], "lec")
        # 有 lec 通过记录后提示消失
        state["runs"].append({"id": "R001", "capability": "lec", "status": "pass"})
        self.assertEqual(_lec_hint_findings(state), [])


if __name__ == "__main__":
    unittest.main()
