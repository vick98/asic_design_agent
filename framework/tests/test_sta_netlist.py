# 作者：vick 邮箱：ykun@yk9811.com

"""第三轮 T2：run sta 不带 --netlist 时，按名字取本次综合写出的网表与 SDC。"""

import importlib.util
import os
import unittest

from framework.engine import record_run
from framework.profile_run import _synth_netlist, _synth_sdc, run_other
from framework.state import init_sys
from framework.tests.util import RepoTest, checkout_root

SYNTH_CHECKS = {"errors": 0, "latches": 0, "setup_wns": 0.1, "setup_violations": 0, "area": 1.0}


def _driver(root, filename):
    path = os.path.join(root, "toolchain", "profiles", "example", "drivers", filename)
    spec = importlib.util.spec_from_file_location("r3sta_" + filename[:-3], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class SynthProductNameTests(RepoTest):
    def _write(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def test_driver_declares_what_it_writes(self):
        drv = _driver(self.root, "eda.py")
        self.assertEqual(drv.synth_products("sample", "")["netlist"], "sample_top_syn.v")
        self.assertEqual(drv.synth_products("sample", "")["sdc"], "sample_top_syn.sdc")
        self.assertEqual(drv.synth_products("sample", "alu")["netlist"], "alu_syn.v")
        # 脚本里写出的文件名与声明必须一致。
        script = drv.synth_script({"mirror_root": "/m", "local_root": "/l", "tool_root": "/t"},
                                  "sample", top="alu")
        self.assertIn("write -format verilog -output alu_syn.v", script)
        self.assertIn("write_sdc alu_syn.sdc", script)

    def _record(self, name, top, artifacts):
        record_run(self.root, name, {
            "capability": "synth", "status": "pass", "summary": "synth pass", "profile_id": "p",
            "checks": dict(SYNTH_CHECKS, netlist="%s_syn.v" % top, sdc="%s_syn.sdc" % top),
            "artifacts": artifacts,
        })

    def test_sta_default_takes_the_run_product_not_the_first_alphabetically(self):
        name = "sample"
        init_sys(self.root, name)
        dc = "%s/dc" % name
        self._write("%s/alu_syn.v" % dc, "// 别的顶层留下的网表\n")
        self._write("%s/alu_syn.sdc" % dc, "create_clock -period 5 [get_ports clk_in]\n")
        self._write("%s/sample_top_syn.v" % dc, "// 本次综合的网表\n")
        self._write("%s/sample_top_syn.sdc" % dc, "create_clock -period 5 [get_ports clk_in]\n")
        self._record(name, "sample_top", [
            "%s/alu_syn.v" % dc, "%s/alu_syn.sdc" % dc,
            "%s/sample_top_syn.v" % dc, "%s/sample_top_syn.sdc" % dc,
        ])
        self.assertEqual(_synth_netlist(name), "%s/sample_top_syn.v" % dc)
        self.assertEqual(_synth_sdc(name), "%s/sample_top_syn.sdc" % dc)
        result = run_other("sta", {"sys": name, "dry_run": True})
        self.assertEqual(result["status"], "dry_run")
        self.assertIn("sample_top_syn.v", result["summary"])
        self.assertIn("sample_top_syn.sdc", result["summary"])
        self.assertNotIn("alu_syn.v", result["summary"])

    def test_old_records_without_names_still_resolve(self):
        name = "sample"
        init_sys(self.root, name)
        record_run(self.root, name, {
            "capability": "synth", "status": "pass", "summary": "synth pass", "profile_id": "p",
            "checks": dict(SYNTH_CHECKS),
            "artifacts": ["%s/dc/sample_top_syn.v" % name, "%s/dc/sample_top_syn.sdc" % name],
        })
        self.assertEqual(_synth_netlist(name), "%s/dc/sample_top_syn.v" % name)
        self.assertEqual(_synth_sdc(name), "%s/dc/sample_top_syn.sdc" % name)

    def test_explicit_netlist_still_wins(self):
        name = "sample"
        init_sys(self.root, name)
        dc = "%s/dc" % name
        self._write("%s/sample_top_syn.sdc" % dc, "create_clock -period 5 [get_ports clk_in]\n")
        self._record(name, "sample_top",
                     ["%s/sample_top_syn.v" % name, "%s/sample_top_syn.sdc" % dc])
        result = run_other("sta", {"sys": name, "dry_run": True,
                                   "netlist": "%s/dc/hand_written.v" % name})
        self.assertIn("hand_written.v", result["summary"])


if __name__ == "__main__":
    unittest.main()
