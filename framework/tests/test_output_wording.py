# 作者：vick 邮箱：ykun@yk9811.com

"""行 10 提示措辞、pubip 场景的输入摘要、tb-gen 的子系统级清单。"""

import os
import unittest

from framework.engine import inputs_digest, record_run
from framework.gates.run import run_gates
from framework.state import init_sys, load_state, sys_dir
from framework.tbgen import generate
from framework.tests.util import RepoTest

BASE = {"capability": "sim", "status": "pass", "summary": "RESULT : PASS", "profile_id": "p"}


class Row10MessageTests(RepoTest):
    def test_missing_case_count_is_explained(self):
        name = "t8msg"
        init_sys(self.root, name)
        record_run(self.root, name, dict(
            BASE, scope={"scenario": "sys", "module": "", "tc": "", "seeds": ["1"]},
            checks={"result_pass": 1, "result_fail": 0, "full_regression": 0,
                    "expected_results": 4, "tc_all_cases": 4, "seeds": 1}))
        findings = run_gates(self.root, name, 10, load_state(self.root, name))
        details = [item["detail"] for item in findings if item["where"] == "sim"]
        self.assertTrue(details, findings)
        self.assertIn("记录里没有用例数", details[0])
        self.assertNotIn("?", details[0])

    def test_present_case_count_still_shown(self):
        name = "t8msg2"
        init_sys(self.root, name)
        record_run(self.root, name, dict(
            BASE, scope={"scenario": "sys", "module": "", "tc": "", "seeds": ["1"]},
            checks={"result_pass": 1, "result_fail": 0, "full_regression": 0,
                    "expected_results": 4, "tc_all_cases": 4, "seeds": 1,
                    "observed_cases": 2, "cases_source": "cases"}))
        findings = run_gates(self.root, name, 10, load_state(self.root, name))
        details = [item["detail"] for item in findings if item["where"] == "sim"]
        self.assertIn("用例数=2", details[0])


class PubipInputsTests(RepoTest):
    """pubip 场景的输入不在子系统目录里，摘要要按场景把公共 IP 与它的 TB 算进去。"""

    def _write(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def _sys(self, name):
        init_sys(self.root, name)
        self._write("%s/rtl/%s.sv" % (name, name), "module top; endmodule\n")
        self._write("pub_code/pubip_demo.v", "module pubip_demo; endmodule\n")
        self._write("pub_code/testbench/pubip_demo/tc/pubip_demo_tc_all.sv",
                    "class pubip_demo_tc_all; endclass\n")
        return name

    def test_pubip_scenario_covers_ip_and_its_tb(self):
        name = self._sys("t8pub")
        before = inputs_digest(self.root, name, scenario="pubip", module="pubip_demo")
        self._write("pub_code/pubip_demo.v", "module pubip_demo; endmodule\n// changed\n")
        after_ip = inputs_digest(self.root, name, scenario="pubip", module="pubip_demo")
        self.assertNotEqual(after_ip, before)
        self._write("pub_code/testbench/pubip_demo/tc/pubip_demo_tc_all.sv",
                    "class pubip_demo_tc_all; endclass\n// changed\n")
        after_tb = inputs_digest(self.root, name, scenario="pubip", module="pubip_demo")
        self.assertNotEqual(after_tb, after_ip)

    def test_other_ip_still_ignored(self):
        name = self._sys("t8other")
        before = inputs_digest(self.root, name, scenario="pubip", module="pubip_demo")
        self._write("pub_code/pubip_other.v", "module pubip_other; endmodule\n")
        self.assertEqual(inputs_digest(self.root, name, scenario="pubip", module="pubip_demo"), before)

    def test_pubip_run_does_not_stand_in_for_latest_sim(self):
        """pubip 变体记录不当"最近一次仿真"——行 10 只认 sys 全量回归，
        不被 pubip 记录顶掉；pubip 记录的时效由它自己的 inputs_digest 留档。"""
        name = self._sys("t8rec")
        rid = record_run(self.root, name, dict(
            {"capability": "sim", "status": "pass", "summary": "RESULT : PASS", "profile_id": "p"},
            scope={"scenario": "pubip", "module": "pubip_demo", "seeds": [""]}))
        self.assertTrue(rid)
        findings = run_gates(self.root, name, 10, load_state(self.root, name))
        self.assertTrue(any(item["detail"] == "行 10 需要最近一次仿真 pass"
                            for item in findings), findings)
        self.assertFalse(any(item["detail"] == "输入已变更，需重跑" and item["where"] == "sim"
                             for item in findings), findings)
        self._write("pub_code/testbench/pubip_demo/tc/pubip_demo_tc_all.sv",
                    "class pubip_demo_tc_all; endclass\n// changed\n")
        findings = run_gates(self.root, name, 10, load_state(self.root, name))
        self.assertTrue(any(item["detail"] == "行 10 需要最近一次仿真 pass"
                            for item in findings), findings)
        # sys 全量回归记在 pubip 记录之后，仍被认作最近一次仿真（不被顶掉）。
        record_run(self.root, name, dict(
            {"capability": "sim", "status": "pass", "summary": "RESULT : PASS", "profile_id": "p",
             "checks": {"full_regression": 1}},
            scope={"scenario": "sys", "seeds": [""]}))
        findings = run_gates(self.root, name, 10, load_state(self.root, name))
        self.assertFalse(any(item["where"] == "sim" and "最近一次仿真" in item["detail"]
                             for item in findings), findings)


class TbGenSysListTests(RepoTest):
    def test_module_dut_does_not_claim_the_sys_filelist(self):
        name = "t8tb"
        init_sys(self.root, name)
        sys_root = sys_dir(self.root, name)
        with open(os.path.join(sys_root, "spec_doc", "%s_spec.md" % name), "w",
                  encoding="utf-8") as fh:
            fh.write("# 顶层\n\n## 3. 接口\n\n| 端口 | 方向 | 位宽 |\n|---|---|---|\n"
                     "| clk_in | input | 1 |\n")
        with open(os.path.join(sys_root, "spec_doc", "alu_spec.md"), "w", encoding="utf-8") as fh:
            fh.write("# alu\n\n## 3. 接口\n\n| 端口 | 方向 | 位宽 |\n|---|---|---|\n"
                     "| clk_in | input | 1 |\n| o_y | output | 8 |\n")
        generate(sys_root, name, "alu")
        self.assertFalse(os.path.isfile(os.path.join(sys_root, "testbench", "%s_tb.f" % name)))
        generate(sys_root, name, name + "_top")
        path = os.path.join(sys_root, "testbench", "%s_tb.f" % name)
        self.assertTrue(os.path.isfile(path))
        with open(path, encoding="utf-8") as fh:
            self.assertIn("testbench/%s_top/" % name, fh.read())


if __name__ == "__main__":
    unittest.main()
