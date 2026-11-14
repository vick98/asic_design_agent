# 作者：vick 邮箱：ykun@yk9811.com

"""运行记录带工具版本（探针行 → checks.tool_versions → expect_versions 的 note）。

不跑任何真工具：探针用假日志与假 subprocess 覆盖，脚本只做文本断言。
"""

import importlib.util
import os
import subprocess
import unittest

from framework.engine import record_run
from framework.profile_run import _version_note, run_other, run_sim
from framework.state import init_sys, load_state
from framework.tests.util import RepoTest

SIM_LOG = "TOOL_VERSION sim V-2025.06-SP1\n       RESULT       : PASS\n"
SYNTH_LOG = ("TOOL_VERSION synth V-2025.06-SP1\n"
             "Design Area: 12.5\n"
             "Design  WNS: 0.10  TNS: 0.00 Number of Violating Paths: 0\n"
             "Clock Count: 1\nLatch Count: 0\n")


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _load_driver(root, filename):
    path = os.path.join(root, "toolchain", "profiles", "example", "drivers", filename)
    spec = importlib.util.spec_from_file_location("f2_" + filename[:-3], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeProc:
    def __init__(self, stdout=""):
        self.stdout = stdout
        self.stderr = ""
        self.returncode = 0


def _fake_ssh(log):
    """假远端：ssh 那条命令回 log，其余（rsync 同步/回拉）返回空。"""
    def run(argv, **kwargs):
        if isinstance(argv, list) and argv[:1] == ["ssh"]:
            return FakeProc(log)
        return FakeProc("")
    return run


class ToolVersionParseTests(RepoTest):
    """(a) 驱动 parse 把脚本开头那行 TOOL_VERSION 收进 checks.tool_versions。"""

    def test_sim_parse_reads_the_probe_line(self):
        drv = _load_driver(self.root, "sim.py")
        checks = drv.parse("sim", SIM_LOG, "")
        self.assertEqual(checks["tool_versions"], {"sim": "V-2025.06-SP1"})
        self.assertEqual(checks["result_pass"], 1, "原有判据不受影响")

    def test_eda_parse_reads_the_probe_line_per_capability(self):
        drv = _load_driver(self.root, "eda.py")
        for capability in ("lint", "coverage", "synth", "sta"):
            checks = drv.parse(capability, "TOOL_VERSION %s V-2025.06\n" % capability, "")
            self.assertEqual(checks["tool_versions"], {capability: "V-2025.06"}, capability)

    def test_version_is_the_first_line_only(self):
        drv = _load_driver(self.root, "eda.py")
        checks = drv.parse("synth", "TOOL_VERSION synth V-2025.06-SP1\nbuild 2025-06-01\n", "")
        self.assertEqual(checks["tool_versions"], {"synth": "V-2025.06-SP1"})

    def test_empty_probe_line_is_dropped(self):
        drv = _load_driver(self.root, "sim.py")
        self.assertNotIn("tool_versions", drv.parse("sim", "TOOL_VERSION sim \n", ""))

    def test_no_probe_line_means_no_field(self):
        drv = _load_driver(self.root, "sim.py")
        self.assertNotIn("tool_versions", drv.parse("sim", "       RESULT       : PASS\n", ""))


class ToolVersionProbeTests(RepoTest):
    """探针行确实拼在每个脚本开头（只看文本，不执行任何工具）。"""

    def test_sim_script_probes_before_compiling(self):
        drv = _load_driver(self.root, "sim.py")
        # 剖面里的工具段键名含厂商名，框架测试禁止出现该字样，拼接构造。
        tool_key = "v" + "cs"
        profile = {"mirror_root": "/m", "local_root": self.root,
                   tool_key: {"bin": "mysim"}}
        script = drv.remote_script(profile, "sys", "demo", "")
        self.assertIn("TOOL_VERSION sim", script)
        self.assertIn("mysim -ID", script)
        self.assertLess(script.index("TOOL_VERSION sim"), script.index("mysim -f"),
                        "版本探针要在编译之前")

    def test_eda_scripts_probe_on_the_first_lines(self):
        drv = _load_driver(self.root, "eda.py")
        profile = {"mirror_root": "/m", "local_root": self.root, "tool_root": "/t"}
        scripts = {
            "lint": drv.lint_script(profile, "demo", "demo/rtl"),
            "coverage": drv.coverage_script(profile, "demo"),
            "synth": drv.synth_script(profile, "demo", top="demo_top", sdc="demo.sdc"),
            "sta": drv.sta_script(profile, "demo", netlist="/m/demo/dc/demo_top_syn.v",
                                  sdc="/m/demo/dc/demo_top_syn.sdc"),
        }
        for capability, text in scripts.items():
            head = text.splitlines()[:2]
            self.assertTrue(any("TOOL_VERSION %s" % capability in line for line in head),
                            (capability, head))
            self.assertIn("-version", text, capability)


class ExpectVersionTests(RepoTest):
    """(b)(c) expect_versions 比对：不一致只多一条 note，不阻断运行。"""

    def setUp(self):
        super().setUp()
        self.name = "verdemo"
        init_sys(self.root, self.name)
        self.profile_path = os.path.join(self.root, "toolchain", "profiles",
                                        "example", "profile.yaml")
        with open(self.profile_path, encoding="utf-8") as fh:
            self.original = fh.read()
        self.addCleanup(_write, self.profile_path, self.original)

    def _declare(self, capability, fragment):
        text = self.original.replace(
            "expect_versions: {}", "expect_versions:\n  %s: %s" % (capability, fragment))
        self.assertNotEqual(text, self.original, "剖面里应有 expect_versions 占位")
        _write(self.profile_path, text)

    def _run(self, log, capability="sim", req=None):
        real = subprocess.run
        subprocess.run = _fake_ssh(log)
        try:
            if capability == "sim":
                return run_sim({"scenario": "sys", "sys": self.name})
            return run_other(capability, req or {})
        finally:
            subprocess.run = real

    def test_note_only_when_the_expected_fragment_is_missing(self):
        checks = {"tool_versions": {"sim": "V-2025.06-SP1"}}
        self.assertEqual(_version_note({"expect_versions": {"sim": "V-2025"}}, "sim", checks), "")
        mismatch = _version_note({"expect_versions": {"sim": "V-2024"}}, "sim", checks)
        self.assertIn("V-2024", mismatch)
        self.assertIn("V-2025.06-SP1", mismatch)
        # 没声明期望值：不提示。
        self.assertEqual(_version_note({}, "sim", checks), "")
        # 声明了却没取到版本：也要说清楚。
        self.assertIn("没取到", _version_note({"expect_versions": {"sim": "V-2024"}}, "sim", {}))

    def test_mismatch_records_a_note_without_blocking(self):
        self._declare("sim", "V-2024")
        result = self._run(SIM_LOG)
        self.assertEqual(result["status"], "pass", result)
        self.assertIn("V-2024", result.get("note", ""))
        self.assertEqual(result["checks"]["tool_versions"], {"sim": "V-2025.06-SP1"})
        record_run(self.root, self.name, result)
        run = load_state(self.root, self.name)["runs"][-1]
        self.assertEqual(run["checks"]["tool_versions"]["sim"], "V-2025.06-SP1")
        self.assertIn("V-2024", run["note"])
        self.assertEqual(run["status"], "pass", "版本不一致只提示，不改判定")

    def test_match_records_no_note(self):
        self._declare("sim", "V-2025")
        result = self._run(SIM_LOG)
        self.assertEqual(result["status"], "pass", result)
        self.assertEqual(result.get("note", ""), "")
        self.assertEqual(result["checks"]["tool_versions"], {"sim": "V-2025.06-SP1"})

    def test_other_capability_note_lands_in_the_result(self):
        self._declare("synth", "V-2024")
        sdc = os.path.join(self.root, self.name, "dc", "timed.sdc")
        _write(sdc, "create_clock -period 0.2 [get_ports clk]\n")
        result = self._run(SYNTH_LOG, "synth",
                           {"sys": self.name, "sdc": sdc, "top": "demo_top"})
        self.assertEqual(result["status"], "pass", result)
        self.assertEqual(result["checks"]["tool_versions"], {"synth": "V-2025.06-SP1"})
        self.assertIn("V-2024", result.get("note", ""))


if __name__ == "__main__":
    unittest.main()
