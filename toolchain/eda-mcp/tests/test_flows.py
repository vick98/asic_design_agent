"""作业管理、VCS 命令组装、DC/PT 模板与判定、路径护栏。"""

import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from eda_mcp import syn as synmod  # noqa: E402
from eda_mcp.config import Config, defaults  # noqa: E402
from eda_mcp.jobs import JobManager  # noqa: E402
from eda_mcp.sim import compile_command, run_command  # noqa: E402
from eda_mcp.workspace import (  # noqa: E402
    WorkspaceError,
    fix_filelist_prefixes,
    guard_path,
    resolve_scenario,
)


def make_cfg(root):
    data = defaults()
    data["eda"]["workspace_root"] = root
    data["security"]["allowed_roots"] = [root]
    data["jobs"]["cache_dir"] = os.path.join(root, ".cache")
    return Config(data)


class TestWorkspace(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = make_cfg(self.tmp)

    def test_scenario_mapping_matches_run_sim(self):
        a = resolve_scenario(self.cfg, "A", "mysys")
        self.assertEqual(a.work, os.path.join(self.tmp, "mysys", "work"))
        self.assertEqual(a.filelist, "../testbench/mysys_tb.f")
        self.assertEqual(a.ydirs, ["-y", "../rtl", "-y", "../../pub_code"])

        b = resolve_scenario(self.cfg, "B", "mysys", "mymod")
        self.assertEqual(b.work, os.path.join(self.tmp, "mysys", "work", "mymod"))
        self.assertEqual(b.filelist, "../../testbench/mymod/mymod_tb.f")
        self.assertEqual(b.ydirs, ["-y", "../../rtl", "-y", "../../../pub_code"])

        c = resolve_scenario(self.cfg, "C", module="pubip_counter")
        self.assertEqual(c.work, os.path.join(self.tmp, "pub_code", "work", "pubip_counter"))
        self.assertEqual(c.filelist, "../../testbench/pubip_counter/pubip_counter_tb.f")
        self.assertEqual(c.ydirs, ["-y", "../.."])

    def test_scenario_requires_args(self):
        with self.assertRaises(WorkspaceError):
            resolve_scenario(self.cfg, "B", "only_sys")
        with self.assertRaises(WorkspaceError):
            resolve_scenario(self.cfg, "Z")

    def test_guard_path_rejects_outside(self):
        with self.assertRaises(WorkspaceError):
            guard_path(self.cfg, "/etc/passwd")
        inside = os.path.join(self.tmp, "x")
        self.assertEqual(guard_path(self.cfg, inside), inside)

    def test_fix_filelist_prefixes(self):
        d = os.path.join(self.tmp, "pub_code", "testbench", "m")
        os.makedirs(d)
        f = os.path.join(d, "m_tb.f")
        base = os.path.basename(self.tmp)
        with open(f, "w") as fh:
            fh.write("+incdir+/Users/someone/work/%s/pub_code\n" % base)
            fh.write("/Users/someone/work/%s/tb_common/tb_define.svh\n" % base)
        changed = fix_filelist_prefixes(self.cfg)
        self.assertEqual(changed, [os.path.relpath(f, self.tmp)])
        with open(f) as fh:
            text = fh.read()
        self.assertIn(self.tmp + "/pub_code", text)
        self.assertNotIn("/Users/someone", text)
        # 幂等
        self.assertEqual(fix_filelist_prefixes(self.cfg), [])


class TestSimCommands(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = make_cfg(self.tmp)
        self.sc = resolve_scenario(self.cfg, "C", module="m")

    def test_compile_plain(self):
        cmd = compile_command(self.cfg, self.sc)
        self.assertIn("-f ../../testbench/m/m_tb.f", cmd)
        self.assertIn("+libext+.v+.sv", cmd)
        self.assertIn("-l compile.log", cmd)
        self.assertNotIn("+define+DEBUG_CODE_EN", cmd)
        self.assertNotIn("+nolibcell", cmd)

    def test_compile_wave_vcd(self):
        cmd = compile_command(self.cfg, self.sc, wave=True, wave_vcd=True)
        self.assertIn("+define+DEBUG_CODE_EN", cmd)
        self.assertNotIn("+nolibcell", cmd)
        self.assertNotIn("pli.a", cmd)

    def test_compile_wave_fsdb_requires_pli(self):
        # PLI 不存在时必须直接报错，而不是产出一条编译不了的命令
        # （用临时目录指向一个"存在但没有 PLI"的 VERDI_HOME，避免依赖本机环境）
        vh = os.path.join(self.tmp, "verdi-empty")
        os.makedirs(vh)
        self.cfg._d["verdi"]["verdi_home"] = vh  # noqa: SLF001
        self.cfg._d["fsdb"]["verdi_home"] = vh   # noqa: SLF001
        with self.assertRaises(Exception):
            compile_command(self.cfg, self.sc, wave=True)

    def test_compile_wave_fsdb_flags(self):
        vh = os.path.join(self.tmp, "verdi")
        pli = os.path.join(vh, "share", "PLI", "VCS", "LINUX64")
        os.makedirs(pli)
        open(os.path.join(pli, "pli.a"), "w").close()
        open(os.path.join(pli, "novas.tab"), "w").close()
        self.cfg._d["verdi"]["verdi_home"] = vh  # noqa: SLF001
        self.cfg._d["fsdb"]["verdi_home"] = vh   # noqa: SLF001
        cmd = compile_command(self.cfg, self.sc, wave=True)
        self.assertIn("+nolibcell", cmd)           # 缺了会丢 DUT
        self.assertIn("+define+TB_DUMP_FSDB", cmd)
        self.assertIn("-fno-lto", cmd)
        self.assertIn("novas.tab", cmd)
        self.assertIn("pli.a", cmd)

    def test_run_command(self):
        cmd = run_command(self.cfg, tc="tc_basic", seed=5, timeout_us=1000, wall_timeout_s=60)
        self.assertIn("+TC=tc_basic", cmd)
        self.assertIn("+SEED=5", cmd)
        self.assertIn("+TB_TIMEOUT_US=1000", cmd)
        self.assertTrue(cmd.startswith("timeout 60 ./simv"))


class TestSynTemplates(unittest.TestCase):
    def test_dc_tcl(self):
        tcl = synmod.render_dc_tcl("top", ["/a/x.v", "/a/y.sv"], lib="stdht",
                                   sdc="/a/c.sdc")
        self.assertIn("set target_library yourtechHT_tt.db", tcl)
        self.assertIn("STDHT/Synopsys", tcl)
        self.assertIn("read_file -format sverilog /a/x.v", tcl)
        self.assertIn("current_design top", tcl)
        self.assertIn("read_sdc /a/c.sdc", tcl)
        self.assertIn("compile_ultra", tcl)
        self.assertIn("report_timing -max_paths 10 > top_syn_timing.rpt", tcl)
        self.assertTrue(tcl.rstrip().endswith("exit"))

    def test_dc_tcl_without_sdc(self):
        self.assertIn("# （无 SDC", synmod.render_dc_tcl("top", ["/a/x.v"]))

    def test_pt_tcl(self):
        tcl = synmod.render_pt_tcl("top", "/dc/top_syn.v", "/dc/top_syn.sdc", corner="ss")
        self.assertIn("yourtech_ss.db", tcl)
        self.assertIn("read_verilog /dc/top_syn.v", tcl)
        self.assertIn("link_design top", tcl)
        self.assertIn("update_timing -full", tcl)
        self.assertIn("top_sta_setup.rpt", tcl)
        self.assertIn("top_sta_hold.rpt", tcl)


class TestVerdict(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = make_cfg(self.tmp)
        self.dc = os.path.join(self.tmp, "dc")
        os.makedirs(self.dc)
        self.jm = JobManager(self.cfg)

    def _job(self, extra):
        job = self.jm.submit("x", "true", cwd=self.dc, extra=extra)
        self.jm.wait(job.id, timeout=10)
        return job

    def _write(self, name, text):
        p = os.path.join(self.dc, name)
        with open(p, "w") as fh:
            fh.write(text)
        return p

    def test_pass_with_violation_detected(self):
        self._write("dc.log", "some log\n")
        self._write("top_syn_timing.rpt", "slack (VIOLATED) -0.12\n")
        job = self._job({"step": "syn", "reports": {
            "log": os.path.join(self.dc, "dc.log"),
            "timing": os.path.join(self.dc, "top_syn_timing.rpt")}})
        v = synmod.report_verdict(self.cfg, job.id)
        self.assertEqual(v["verdict"], "FAIL")
        self.assertTrue(v["violations"])

    def test_pass_but_unconstrained_is_flagged(self):
        self._write("pt.log", "ok\n")
        self._write("top_sta_setup.rpt", "No constrained paths.\n")
        self._write("top_sta_hold.rpt", "No constrained paths.\n")
        job = self._job({"step": "sta", "reports": {
            "log": os.path.join(self.dc, "pt.log"),
            "setup": os.path.join(self.dc, "top_sta_setup.rpt"),
            "hold": os.path.join(self.dc, "top_sta_hold.rpt")}})
        v = synmod.report_verdict(self.cfg, job.id)
        self.assertEqual(v["verdict"], "PASS")
        self.assertFalse(v["constrained"])
        self.assertIn("无受约束路径", v["reason"])

    def test_error_line_fails(self):
        self._write("dc.log", "Error: cannot link\n")
        self._write("top_syn_timing.rpt", "slack (MET) 0.0\n")
        job = self._job({"step": "syn", "reports": {
            "log": os.path.join(self.dc, "dc.log"),
            "timing": os.path.join(self.dc, "top_syn_timing.rpt")}})
        v = synmod.report_verdict(self.cfg, job.id)
        self.assertEqual(v["verdict"], "FAIL")
        self.assertEqual(v["reason"], "运行错误（日志有 Error 行）")

    def test_missing_report_fails(self):
        self._write("dc.log", "fine\n")
        job = self._job({"step": "syn", "reports": {
            "log": os.path.join(self.dc, "dc.log"),
            "timing": os.path.join(self.dc, "nope.rpt")}})
        v = synmod.report_verdict(self.cfg, job.id)
        self.assertEqual(v["verdict"], "FAIL")
        self.assertEqual(v["reason"], "报告缺失")


class TestJobs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = make_cfg(self.tmp)
        self.jm = JobManager(self.cfg)

    def test_submit_wait_and_log(self):
        job = self.jm.submit("echo", "echo hello; echo world")
        done = self.jm.wait(job.id, timeout=15)
        self.assertEqual(done.state, "completed")
        self.assertEqual(done.rc, 0)
        text = self.jm.log(job.id, tail_lines=1)
        self.assertEqual(text.strip(), "world")
        self.assertEqual(self.jm.log(job.id, grep="hello").strip(), "hello")

    def test_failure_exit_code(self):
        job = self.jm.submit("false", "exit 3")
        done = self.jm.wait(job.id, timeout=15)
        self.assertEqual(done.state, "failed")
        self.assertEqual(done.rc, 3)

    def test_kill(self):
        job = self.jm.submit("sleep", "sleep 60")
        time.sleep(0.4)
        killed = self.jm.kill(job.id)
        self.assertIn(killed.state, ("killed", "failed"))
        self.assertNotEqual(killed.rc, 0)

    def test_list_and_prune(self):
        ids = [self.jm.submit("t", "true").id for _ in range(3)]
        self.jm.wait(ids[-1], timeout=10)
        got = self.jm.list(limit=10)
        self.assertEqual(len(got), 3)
        self.jm.prune(keep=1)
        self.assertEqual(len(self.jm.list(limit=10)), 1)

    def test_unknown_job(self):
        with self.assertRaises(Exception):
            self.jm.get("no-such-job")


if __name__ == "__main__":
    unittest.main(verbosity=2)
