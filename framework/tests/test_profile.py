# 作者：vick 邮箱：ykun@yk9811.com

import importlib.util
import os
import subprocess
import sys
import unittest

from framework.engine import EngineError, inputs_digest, record_run
from framework.gates.run import run_gates
from framework.profile_run import judge, load_profile, run_other, run_sim
from framework.state import init_sys, load_state
from framework.tests.util import RepoTest, checkout_root


def _load_driver(root, filename):
    path = os.path.join(root, "toolchain", "profiles", "example", "drivers", filename)
    spec = importlib.util.spec_from_file_location("drv_" + filename[:-3], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ProfileTests(RepoTest):
    def test_sim_seeds_timeout_and_no_sync(self):
        nosync = run_sim({
            "scenario": "pubip", "module": "pubip_counter", "dry_run": True,
            "seeds": ["1", "2"], "timeout_us": "1000", "no_sync": True,
        })
        summary = nosync["summary"]
        self.assertIn("+SEED=1", summary)
        self.assertIn("+SEED=2", summary)
        self.assertIn("sim_seed1.log", summary)
        self.assertIn("sim_seed2.log", summary)
        self.assertIn("+TB_TIMEOUT_US=1000", summary)
        self.assertNotIn("rsync", summary)

    def test_pubip_sim_dry_run_flags(self):
        result = run_sim({
            "scenario": "pubip", "module": "pubip_counter", "dry_run": True, "wave": "off",
        })
        summary = result["summary"]
        tool = "v" + "cs"
        self.assertIn(tool + " -sverilog -full64", summary)
        self.assertIn("+libext+.v+.sv", summary)
        self.assertIn("pubip_counter_tb.f", summary)
        self.assertIn("--delete", summary)
        self.assertEqual(result["status"], "dry_run")

    def test_lint_synth_sta_dry_run(self):
        lint = run_other("lint", {"sys": "demo", "dry_run": True, "rtl": "demo/rtl/alu.sv"})
        self.assertEqual(lint["status"], "dry_run")
        self.assertIn("--delete", lint["summary"])
        synth = run_other("synth", {"sys": "demo", "dry_run": True, "sdc": "demo.sdc"})
        self.assertEqual(synth["status"], "dry_run")
        for token in (
            "search_path", "link_library", "read_file", "check_design", "read_sdc",
            "compile_ultra", "report_area", "report_qor", "report_timing -max_paths 10",
            "write -format ddc", "write -format verilog", "write_sdc",
        ):
            self.assertIn(token, synth["summary"], token)
        missing = run_other("synth", {"sys": "demo", "dry_run": True})
        self.assertEqual(missing["status"], "error")
        sta = run_other("sta", {
            "sys": "demo", "dry_run": True, "corner": "slow",
            "netlist": "demo/dc/top.v", "sdc": "demo/dc/top.sdc",
        })
        self.assertEqual(sta["status"], "dry_run")
        for token in (
            "link_path", "read_verilog", "link_design", "read_sdc",
            "update_timing -full", "report_timing -delay_type max",
            "report_timing -delay_type min", "report_qor", "yourtech_ss.db",
        ):
            self.assertIn(token, sta["summary"], token)

    def test_sim_log_judgement(self):
        profile = load_profile()
        drv = _load_driver(self.root, "sim.py")
        passed = drv.parse("sim", "       RESULT       : PASS\n", "")
        self.assertEqual(judge("sim", passed, profile), "pass")
        failed = drv.parse("sim", "RESULT: FAIL\nRESULT: PASS\n", "")
        self.assertEqual(judge("sim", failed, profile), "fail")
        compiled = drv.parse("sim", "COMPILE_" + "FAIL\n", "")
        self.assertEqual(judge("sim", compiled, profile), "error")

    def test_coverage_judgement(self):
        profile = load_profile()
        drv = _load_driver(self.root, "eda.py")
        high = drv.parse("coverage", "LINE 90 COND 80 FSM 90 TGL 70", "")
        low = drv.parse("coverage", "LINE 10 COND 80 FSM 90 TGL 70", "")
        self.assertEqual(judge("coverage", high, profile), "pass")
        self.assertEqual(judge("coverage", low, profile), "fail")
        modlist = "\n".join([
            "SCORE  LINE   COND   TOGGLE FSM",
            " 70.00  70.00 100.00 100.00 --",
            "SCORE  LINE   COND   TOGGLE FSM    NAME",
            " 65.00  65.00 --     --     --     pubip_counter_sim_top",
            "100.00 100.00 100.00 100.00 --     pubip_counter",
        ])
        dut = drv.parse("coverage", modlist, "")
        self.assertEqual(dut["line"], 100.0)
        self.assertEqual(judge("coverage", dut, profile), "pass")
        from framework.coverage import audit, limits
        gate = os.path.join(self.root, "demo", "testbench")
        os.makedirs(gate, exist_ok=True)
        with open(os.path.join(gate, "cov_gate.txt"), "w", encoding="utf-8") as fh:
            fh.write("line=60\n")
        self.assertEqual(limits(profile, os.path.join(self.root, "demo"))["line"], 80.0)
        _effective, unwaived = audit(profile, os.path.join(self.root, "demo"))
        self.assertEqual([key for key, _value, _default in unwaived], ["line"])

    def test_report_samples(self):
        profile = load_profile()
        drv = _load_driver(self.root, "eda.py")
        synth_dir = os.path.join(self.root, "framework", "tests", "data", "synth")
        sta_dir = os.path.join(self.root, "framework", "tests", "data", "sta")
        self.assertEqual(judge("synth", drv.parse("synth", "", synth_dir), profile), "pass")
        # 无约束路径的 STA 样本判 error，不再判 pass。
        self.assertEqual(judge("sta", drv.parse("sta", "", sta_dir), profile), "error")
        cut = os.path.join(self.root, "framework", "tests", "data", "synth", "pubip_counter_syn_qor.rpt")
        with open(cut, encoding="utf-8") as fh:
            head = "".join(fh.readlines()[:8])
        self.assertEqual(judge("synth", drv.parse("synth", head, ""), profile), "error")
        with open(cut, encoding="utf-8") as fh:
            body = fh.read()
        violated = body.replace("Design  WNS: 0.00", "Design  WNS: -1.50", 1)
        violated = violated.replace("Number of Violating Paths: 0", "Number of Violating Paths: 2", 1)
        violated += "\nLatch Count: 0\n"
        self.assertEqual(judge("synth", drv.parse("synth", violated, ""), profile), "fail")
        clean = body + "\nLatch Count: 0\n"
        self.assertEqual(judge("synth", drv.parse("synth", clean, ""), profile), "pass")

    def test_missing_profile_uses_copy(self):
        real_active = os.path.join(checkout_root(), "toolchain", "active")
        before = os.stat(real_active).st_mtime_ns
        active = os.path.join(self.root, "toolchain", "active")
        with open(active, encoding="utf-8") as fh:
            original = fh.read()
        try:
            with open(active, "w", encoding="utf-8") as fh:
                fh.write("missing_profile\n")
            with self.assertRaises(FileNotFoundError) as ctx:
                load_profile()
            self.assertIn("toolchain/profiles", str(ctx.exception))
        finally:
            with open(active, "w", encoding="utf-8") as fh:
                fh.write(original)
            self.assertEqual(os.stat(real_active).st_mtime_ns, before)

    def test_framework_has_no_vendor_tokens(self):
        banned = (
            "VIOL" + "ATED",
            "NLINT " + "RESULT",
            "Error" + ":",
            "COMPILE_" + "FAIL",
            "LINE/" + "COND",
            "v" + "cs",
            "dc_" + "shell",
            "pt_" + "shell",
            "u" + "rg",
            "n" + "Lint",
        )
        hits = []
        root = os.path.join(checkout_root(), "framework")
        for dirpath, dirnames, files in os.walk(root):
            dirnames[:] = [name for name in dirnames if name != "__pycache__"]
            for fn in files:
                if not fn.endswith((".py", ".md", ".yaml")):
                    continue
                path = os.path.join(dirpath, fn)
                text = open(path, encoding="utf-8").read()
                for token in banned:
                    if token in text:
                        hits.append("%s: %s" % (os.path.relpath(path, root), token))
        self.assertEqual(hits, [])

    def test_dry_run_is_not_recorded(self):
        name = "drydemo"
        init_sys(self.root, name)
        env = os.environ.copy()
        env["ADF_ROOT"] = self.root
        proc = subprocess.run(
            [sys.executable, os.path.join(checkout_root(), "script", "framework.py"),
             "run", "sim", "--sys", name, "--dry-run"],
            env=env, capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        state = load_state(self.root, name)
        self.assertEqual(state["runs"], [])
        with self.assertRaises(EngineError):
            record_run(self.root, name, {"capability": "sim", "status": "dry_run", "summary": "x"})

    def test_changed_rtl_invalidates_pass(self):
        name = "digestsys"
        init_sys(self.root, name)
        rtl = os.path.join(self.root, name, "rtl", "alu.sv")
        with open(rtl, "w", encoding="utf-8") as fh:
            fh.write("module alu; endmodule\n")
        record_run(self.root, name, {
            "capability": "lint", "status": "pass", "summary": "ok", "profile_id": "p",
        })
        record_run(self.root, name, {
            "capability": "sim", "status": "pass", "summary": "ok", "profile_id": "p",
        })
        record_run(self.root, name, {
            "capability": "coverage", "status": "pass", "summary": "ok", "profile_id": "p",
        })
        state = load_state(self.root, name)
        before = run_gates(self.root, name, 10, state)
        self.assertFalse(any(item["detail"] == "输入已变更，需重跑" for item in before))
        with open(rtl, "a", encoding="utf-8") as fh:
            fh.write("// touch\n")
        state = load_state(self.root, name)
        after = run_gates(self.root, name, 10, state)
        self.assertTrue(any(item["detail"] == "输入已变更，需重跑" and item["where"] == "sim" for item in after))
        lint = run_gates(self.root, name, 7, state)
        self.assertTrue(any(item["detail"] == "输入已变更，需重跑" and item["where"] == "lint" for item in lint))
        self.assertNotEqual(inputs_digest(self.root, name), state["runs"][0]["inputs_digest"])


if __name__ == "__main__":
    unittest.main()
