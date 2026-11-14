# 作者：vick 邮箱：ykun@yk9811.com

"""第三轮 T1、T3：覆盖率记录绑定仿真；sys 场景的用例数只算清单引用的平台。"""

import os
import unittest

from framework.engine import record_run
from framework.gates.run import run_gates
from framework.profile_run import _regression_expectation
from framework.state import init_sys, load_state, sys_dir
from framework.tests.util import RepoTest

SIM = {"capability": "sim", "status": "pass", "summary": "RESULT : PASS", "profile_id": "p"}
COV = {"capability": "coverage", "status": "pass", "summary": "coverage pass", "profile_id": "p"}
COV_CHECKS = {"line": 100.0, "cond": 100.0, "fsm": 100.0, "tgl": 100.0}


def _sim(root, name, coverage=True, full=True, scenario="sys", module=""):
    return record_run(root, name, dict(SIM, scope={
        "scenario": scenario, "module": module, "tc": "", "seeds": [""], "coverage": coverage,
    }, checks={"result_pass": 1, "result_fail": 0, "full_regression": 1 if full else 0,
               "expected_results": 1, "tc_all_cases": 1, "seeds": 1, "observed_cases": 1,
               "cases_source": "cases"}))


def _coverage(root, name, scenario="sys", module=""):
    return record_run(root, name, dict(COV, checks=dict(COV_CHECKS), scope={
        "scenario": scenario, "module": module,
    }))


def _cov_findings(root, name):
    return [item for item in run_gates(root, name, 10, load_state(root, name))
            if item["where"] == "coverage"]


class CoverageBindingTests(RepoTest):
    """覆盖率记录必须引用最近一次全量回归仿真，且该仿真仍新鲜。"""

    def test_coverage_binds_to_the_sim_it_was_run_after(self):
        name = "t1bind"
        init_sys(self.root, name)
        rid = _sim(self.root, name)
        cid = _coverage(self.root, name)
        run = [item for item in load_state(self.root, name)["runs"] if item["id"] == cid][0]
        self.assertEqual((run.get("scope") or {}).get("based_on_sim"), rid)
        self.assertEqual(_cov_findings(self.root, name), [])

    def test_rtl_change_then_coverage_only_is_rejected(self):
        name = "t1rtl"
        init_sys(self.root, name)
        _sim(self.root, name)
        _coverage(self.root, name)
        with open(os.path.join(sys_dir(self.root, name), "rtl", "alu.sv"), "w",
                  encoding="utf-8") as fh:
            fh.write("module alu; endmodule\n")
        details = [item["detail"] for item in _cov_findings(self.root, name)]
        self.assertTrue(details, "改 RTL 只重跑覆盖率未被拒")
        self.assertTrue(any("输入已变更" in item for item in details), details)

    def test_new_full_regression_after_coverage_needs_new_coverage(self):
        name = "t1again"
        init_sys(self.root, name)
        old = _sim(self.root, name)
        _coverage(self.root, name)
        new = _sim(self.root, name)
        self.assertNotEqual(old, new)
        details = [item["detail"] for item in _cov_findings(self.root, name)]
        self.assertTrue(details, "重跑全量仿真后未重跑覆盖率，行 10 未被拒")
        self.assertTrue(any(new in item for item in details), details)

    def test_coverage_without_any_sim_is_rejected(self):
        name = "t1none"
        init_sys(self.root, name)
        _coverage(self.root, name)
        details = [item["detail"] for item in _cov_findings(self.root, name)]
        self.assertTrue(details, "没有仿真记录时覆盖率不该算通过")

    def test_binding_prefers_the_coverage_sim(self):
        """同场景同模块的仿真里，绑定带 --coverage 的那次，而不是最后一次。"""
        name = "t1pref"
        init_sys(self.root, name)
        with_cov = _sim(self.root, name, coverage=True)
        without = _sim(self.root, name, coverage=False)
        cid = _coverage(self.root, name)
        run = [item for item in load_state(self.root, name)["runs"] if item["id"] == cid][0]
        self.assertEqual((run.get("scope") or {}).get("based_on_sim"), with_cov)
        details = [item["detail"] for item in _cov_findings(self.root, name)]
        self.assertTrue(any(without in item for item in details), details)

    def test_pubip_binding_uses_the_matching_module(self):
        name = "t1pub"
        init_sys(self.root, name)
        _sim(self.root, name, scenario="pubip", module="pubip_demo")
        cid = _coverage(self.root, name, scenario="pubip", module="pubip_demo")
        run = [item for item in load_state(self.root, name)["runs"] if item["id"] == cid][0]
        self.assertTrue((run.get("scope") or {}).get("based_on_sim"))


class SysCaseCountTests(RepoTest):
    """T3：sys 场景只数 testbench/<sys>_tb.f 实际引用的那个平台的用例。"""

    def _write(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def _platform(self, sys, dut, cases):
        body = ["class %s_tc_all;" % dut, "  task body();"]
        for case in cases:
            body.append('    %s_tc_%s %s = new("tc_%s");' % (dut, case, case, case))
            body.append("    %s.body();" % case)
        body += ["  endtask", "endclass", ""]
        self._write("%s/testbench/%s/tc/%s_tc_all.sv" % (sys, dut, dut), "\n".join(body))

    def _sys(self, name):
        init_sys(self.root, name)
        self._platform(name, "alu", ["basic", "extra"])
        self._platform(name, name + "_top", ["basic", "busy", "idle"])
        return name

    def test_without_filelist_all_platforms_counted(self):
        name = self._sys("t3all")
        out = _regression_expectation(name, "", {"scenario": "sys", "seeds": [""]},
                                      {"cases_run": 5, "result_pass": 5})
        self.assertEqual(out["tc_all_cases"], 5)
        self.assertEqual(out["full_regression"], 1)

    def test_sys_filelist_limits_the_count(self):
        name = self._sys("t3list")
        self._write("%s/testbench/%s_tb.f" % (name, name),
                    "../testbench/%s_top/%s_top_sim_top.sv\n" % (name, name))
        out = _regression_expectation(name, "", {"scenario": "sys", "seeds": [""]},
                                      {"cases_run": 5, "result_pass": 5})
        self.assertEqual(out["tc_all_cases"], 3, out)
        self.assertEqual(out["full_regression"], 0, "把没引用的模块级平台也算进去了")
        ok = _regression_expectation(name, "", {"scenario": "sys", "seeds": [""]},
                                     {"cases_run": 3, "result_pass": 3})
        self.assertEqual(ok["full_regression"], 1)

    def test_module_scenario_still_uses_its_own_dut(self):
        name = self._sys("t3mod")
        out = _regression_expectation(name, "alu", {"scenario": "module", "seeds": [""]},
                                      {"cases_run": 2, "result_pass": 2})
        self.assertEqual(out["tc_all_cases"], 2)
        self.assertEqual(out["full_regression"], 1)


if __name__ == "__main__":
    unittest.main()
