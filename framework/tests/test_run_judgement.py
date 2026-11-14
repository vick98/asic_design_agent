# 作者：vick 邮箱：ykun@yk9811.com

"""第二轮 WP11：运行判定与中端脚本的复现测试。"""

import importlib.util
import os
import unittest

from framework.engine import (
    add_waiver, inputs_digest, record_run,
)
from framework.gates.run import run_gates
from framework.profile_run import judge, load_profile, run_other
from framework.state import init_sys, load_state, sys_dir
from framework.tests.util import RepoTest, checkout_root, decide

MIRROR = "/home/your_account/proj/asic_design_agent"


def _driver(root, filename):
    path = os.path.join(root, "toolchain", "profiles", "example", "drivers", filename)
    spec = importlib.util.spec_from_file_location("r2_" + filename[:-3], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _data(root, *parts):
    return os.path.join(root, "framework", "tests", "data", *parts)


class CoverageTests(RepoTest):
    def test_f06_worst_module_represents_the_dut(self):
        profile = load_profile()
        drv = _driver(self.root, "eda.py")
        sample = "\n".join([
            "SCORE  LINE   COND   TOGGLE FSM    NAME",
            "100.00 100.00 100.00 100.00 --     mod_a",
            " 40.00  40.00  40.00  40.00 --     mod_b",
        ])
        checks = drv.parse("coverage", sample, "")
        self.assertEqual(checks["line"], 40.0)
        self.assertEqual(judge("coverage", checks, profile), "fail")

    def test_r2_dut_row_wins_when_marked(self):
        profile = load_profile()
        drv = _driver(self.root, "eda.py")
        sample = "\n".join([
            "COV_DUT: mod_a",
            "SCORE  LINE   COND   TOGGLE FSM    NAME",
            "100.00 100.00 100.00 100.00 --     mod_a",
            " 40.00  40.00  40.00  40.00 --     mod_b",
        ])
        checks = drv.parse("coverage", sample, "")
        self.assertEqual(checks["line"], 100.0)
        self.assertEqual(judge("coverage", checks, profile), "pass")

    def test_r2_dash_metric_is_na_not_100(self):
        drv = _driver(self.root, "eda.py")
        sample = "\n".join([
            "COV_DUT: mod_a",
            "SCORE  LINE   COND   TOGGLE FSM    NAME",
            " 90.00  90.00  90.00 --     mod_a",
        ])
        checks = drv.parse("coverage", sample, "")
        self.assertEqual(checks["fsm"], "na")

    def test_r2_hierarchy_instance_row_is_the_dut(self):
        """取层次报告里 DUT 实例那一行；实例名不一定等于模块名。

        真实 URG 层次报告：TB 顶层在缩进 1，DUT 与接口实例在缩进 2。
        modlist 给的是模块定义行（模块聚合），不能拿来当 DUT 行。
        """
        drv = _driver(self.root, "eda.py")
        profile = load_profile()
        text = "\n".join([
            "COV_DUT: two_mod_top",
            "--- URG_REPORT:hierarchy ---",
            "SCORE  LINE   COND   TOGGLE FSM",
            " 59.61  85.71 --      59.79  33.33 two_mod_sim_top",
            "  ----------------",
            "  SCORE  LINE   COND   TOGGLE FSM",
            "   54.75  73.68 --      57.25  33.33 u_dut",
            "    ----------------",
            "    SCORE  LINE   COND   TOGGLE FSM",
            "     86.84 100.00 --      73.68 --     u_a",
            "     42.23  61.54 --      31.82  33.33 u_b",
            "--- URG_REPORT:modlist ---",
            "SCORE  LINE   COND   TOGGLE FSM    NAME",
            " 42.23  61.54 --      31.82  33.33 mod_b",
            " 66.07 --     --      66.07 --     two_mod_top",
        ])
        checks = drv.parse("coverage", text, "")
        self.assertEqual(checks["line"], 73.68, "应取 DUT 实例行，而不是 modlist 的模块聚合行")
        self.assertEqual(checks["tgl"], 57.25)
        self.assertEqual(checks["fsm"], 33.33)
        self.assertEqual(judge("coverage", checks, profile), "fail")

    def test_r2_hierarchy_with_interface_instances_passes(self):
        """接口实例与 DUT 实例同层；逐项取数字，`--` 不参与。"""
        drv = _driver(self.root, "eda.py")
        profile = load_profile()
        text = "\n".join([
            "COV_DUT: pubip_counter",
            "--- URG_REPORT:hierarchy ---",
            "SCORE  LINE   COND   TOGGLE FSM",
            " 92.98  78.95 100.00 100.00 --     pubip_counter_sim_top",
            "  ----------------",
            "  SCORE  LINE   COND   TOGGLE FSM",
            "  100.00 --     --     100.00 --     mo_pubip_counter_if",
            "  100.00 100.00 --     100.00 --     mo_rst_if",
            "  100.00 100.00 100.00 100.00 --     pubip_counter_inst",
        ])
        checks = drv.parse("coverage", text, "")
        self.assertEqual(checks["line"], 100.0)
        self.assertEqual(checks["cond"], 100.0)
        self.assertEqual(checks["tgl"], 100.0)
        self.assertEqual(judge("coverage", checks, profile), "pass")

    def test_f10_lowered_gate_needs_waiver(self):
        name = "covdemo"
        init_sys(self.root, name)
        profile = load_profile()
        sys_root = sys_dir(self.root, name)
        _write(os.path.join(sys_root, "testbench", "cov_gate.txt"), "line=0\n")
        clean = {"line": 100.0, "cond": 100.0, "fsm": 100.0, "tgl": 100.0}
        state = load_state(self.root, name)
        self.assertEqual(judge("coverage", dict(clean), profile,
                               sys_root=sys_root, state=state), "fail")
        # COV 下调豁免引用的裁决必须是方向/数值类：开发者点选入库，不要任何令牌。
        did = decide(self.root, name, "接受覆盖率下调", "方向", 1,
                     options="接受覆盖率下调|不接受", pick="接受覆盖率下调")
        add_waiver(self.root, name, "COV", "line", did)
        state = load_state(self.root, name)
        lowered = {"line": 0.0, "cond": 100.0, "fsm": 100.0, "tgl": 100.0}
        self.assertEqual(judge("coverage", dict(lowered), profile,
                               sys_root=sys_root, state=state), "pass")

    def test_f10_raising_the_gate_needs_no_waiver(self):
        name = "covraise"
        init_sys(self.root, name)
        profile = load_profile()
        sys_root = sys_dir(self.root, name)
        _write(os.path.join(sys_root, "testbench", "cov_gate.txt"), "line=95\n")
        from framework.coverage import limits
        self.assertEqual(limits(profile, sys_root)["line"], 95.0)
        state = load_state(self.root, name)
        self.assertEqual(judge("coverage", {"line": 95.0, "cond": 100.0, "fsm": 100.0, "tgl": 100.0},
                               profile, sys_root=sys_root, state=state), "pass")
        self.assertEqual(judge("coverage", {"line": 94.0, "cond": 100.0, "fsm": 100.0, "tgl": 100.0},
                               profile, sys_root=sys_root, state=state), "fail")


class StaSynthTests(RepoTest):
    def test_f07_unconstrained_is_error(self):
        profile = load_profile()
        drv = _driver(self.root, "eda.py")
        checks = drv.parse("sta", "", _data(self.root, "sta"))
        self.assertEqual(judge("sta", checks, profile), "error")

    def test_f07_clean_passes_with_distinct_slacks(self):
        profile = load_profile()
        drv = _driver(self.root, "eda.py")
        checks = drv.parse("sta", "", _data(self.root, "sta_clean"))
        corner = checks["corners"][0]
        self.assertNotEqual(corner["setup_wns"], corner["hold_wns"])
        self.assertEqual(corner["setup_violations"], 0)
        self.assertEqual(corner["hold_violations"], 0)
        self.assertEqual(judge("sta", checks, profile), "pass")

    def test_f07_hold_violation_fails(self):
        profile = load_profile()
        drv = _driver(self.root, "eda.py")
        checks = drv.parse("sta", "", _data(self.root, "sta_hold"))
        corner = checks["corners"][0]
        self.assertEqual(corner["setup_violations"], 0)
        self.assertEqual(corner["hold_violations"], 1)
        self.assertLess(corner["hold_wns"], 0)
        self.assertGreater(corner["setup_wns"], 0)
        self.assertEqual(judge("sta", checks, profile), "fail")

    def test_f07_qor_path_group_is_primary_source(self):
        """PT 的 qor 按路径组给最差 slack 与违例条数，是真实且最稳的来源。"""
        drv = _driver(self.root, "eda.py")
        profile = load_profile()
        qor = ("\n  Timing Path Group 'clk' (max_delay/setup)\n"
               "  Critical Path Length:                    0.41\n"
               "  Critical Path Slack:                    -0.33\n"
               "  No. of Violating Paths:                     4\n"
               "  Timing Path Group 'clk' (min_delay/hold)\n"
               "  Critical Path Length:                    0.29\n"
               "  Critical Path Slack:                     0.34\n"
               "  No. of Violating Paths:                     0\n")
        checks = drv.parse("sta", qor, "")
        corner = checks["corners"][0]
        self.assertEqual(corner["setup_wns"], -0.33)
        self.assertEqual(corner["setup_violations"], 4)
        self.assertEqual(corner["hold_wns"], 0.34)
        self.assertEqual(corner["hold_violations"], 0)
        self.assertEqual(judge("sta", checks, profile), "fail")

    def test_f07_no_violating_paths_counts_as_constrained(self):
        """「没有 slack 小于 X 的路径」是有约束、零违例，不能当成无约束判 error。"""
        drv = _driver(self.root, "eda.py")
        profile = load_profile()
        text = ("--- PT_REPORT:setup ---\nslack (MET)  0.10\n"
                "--- PT_REPORT:hold ---\nNo paths with slack less than 0.00.\n")
        checks = drv.parse("sta", text, "")
        corner = checks["corners"][0]
        self.assertEqual(corner["hold_violations"], 0)
        self.assertEqual(corner.get("wns_is_bound"), 1)
        self.assertNotIn("unconstrained", checks)
        self.assertEqual(judge("sta", checks, profile), "pass")

    def test_f07_markers_take_precedence(self):
        drv = _driver(self.root, "eda.py")
        marked = "\n".join([
            "--- PT_REPORT:setup ---",
            "slack (MET)    0.4000",
            "--- PT_REPORT:hold ---",
            "slack (MET)    0.0100",
        ])
        checks = drv.parse("sta", marked, "")
        self.assertEqual(checks["corners"][0]["setup_wns"], 0.4)
        self.assertEqual(checks["corners"][0]["hold_wns"], 0.01)

    def test_f08_latch_not_found_is_error(self):
        profile = load_profile()
        drv = _driver(self.root, "eda.py")
        head = ("Design Area: 10.0\n"
                "Design  WNS: 0.00  TNS: 0.00  Number of Violating Paths: 0\n")
        checks = drv.parse("synth", head, "")
        self.assertNotIn("latches", checks)
        self.assertEqual(judge("synth", checks, profile), "error")
        self.assertEqual(judge("synth", drv.parse("synth", head + "Latch Count: 0\n", ""), profile), "pass")
        self.assertEqual(judge("synth", drv.parse("synth", head + "Latch Count: 3\n", ""), profile), "fail")

    def test_f26_synth_reads_only_instantiated_pub_code(self):
        """只读子系统 RTL 例化的 pub_code 模块；与子系统同名的文件必须跳过。

        全量读 pub_code 会把别的 IP 一起 elaboration 进来（实测把计数器综合成 17 万门）。
        """
        name = "instdemo"
        init_sys(self.root, name)
        rtl = os.path.join(sys_dir(self.root, name), "rtl")
        _write(os.path.join(rtl, "%s_top.sv" % name),
               "module %s_top;\n  counter u_c (.clk(clk));\n  mem u_m (.clk(clk));\n"
               "endmodule\n" % name)
        # 注释里的例化示例不算数
        _write(os.path.join(rtl, "%s_note.sv" % name),
               "/* unused u_x (.clk(clk)); */\nmodule %s_note; endmodule\n" % name)
        pub = os.path.join(self.root, "pub_code")
        _write(os.path.join(pub, "counter.v"), "module counter(input clk); endmodule\n")
        _write(os.path.join(pub, "mem.sv"), "module mem(input clk); endmodule\n")
        _write(os.path.join(pub, "unused.v"), "module unused(input clk); endmodule\n")
        _write(os.path.join(pub, "%s_note.sv" % name), "module %s_note; endmodule\n" % name)
        _write(os.path.join(sys_dir(self.root, name), "dc", "timed.sdc"),
               "create_clock -period 0.2 [get_ports clk]\n")
        result = run_other("synth", {
            "sys": name, "dry_run": True, "rtl_dir": os.path.join(sys_dir(self.root, name), "rtl"),
            "sdc": os.path.join(sys_dir(self.root, name), "dc", "timed.sdc"), "top": "%s_top" % name,
        })
        self.assertEqual(result["status"], "dry_run", result)
        summary = result["summary"]
        self.assertIn("pub_code/counter.v", summary)
        self.assertIn("pub_code/mem.sv", summary)
        self.assertNotIn("pub_code/unused.v", summary)
        self.assertNotIn("pub_code/%s_note.sv" % name, summary)

    def test_r5_clock_check_is_not_fooled_by_echoed_command(self):
        """综合工具会回显每条命令；标记写成 puts 的字面量时会把命令当成结果（假 no_clock）。"""
        drv = _driver(self.root, "eda.py")
        profile = load_profile()
        name = "clockdemo"
        init_sys(self.root, name)
        _write(os.path.join(sys_dir(self.root, name), "rtl", "%s_top.sv" % name),
               "module %s_top; endmodule\n" % name)
        _write(os.path.join(sys_dir(self.root, name), "dc", "timed.sdc"),
               "create_clock -period 0.2 [get_ports clk]\n")
        script = drv.synth_script(profile, name, "default", "%s_top" % name,
                                 os.path.join(sys_dir(self.root, name), "rtl"),
                                 "timed.sdc")
        echoed = drv.parse("synth", script, "")
        self.assertNotIn("no_clock", echoed, "把回显的命令当成了结果")
        self.assertIn("Clock Count:", script)
        with_clock = "Design Area: 1.0\nDesign  WNS: 0.00  TNS: 0.00 Number of Violating Paths: 0\n" \
                     "Clock Count: 1\nLatch Count: 0\n"
        self.assertNotIn("no_clock", drv.parse("synth", with_clock, ""))
        no_clock = with_clock.replace("Clock Count: 1", "Clock Count: 0")
        self.assertEqual(drv.parse("synth", no_clock, "").get("no_clock"), 1)

    def test_f08_latch_query_uses_existing_option(self):
        """这个 DC 版本没有 all_registers -latches，要用 -level_sensitive 并 catch。"""
        drv = _driver(self.root, "eda.py")
        profile = load_profile()
        name = "latchdemo"
        init_sys(self.root, name)
        _write(os.path.join(sys_dir(self.root, name), "rtl", "%s_top.sv" % name),
               "module %s_top; endmodule\n" % name)
        script = drv.synth_script(profile, name, "default", "%s_top" % name,
                                  os.path.join(sys_dir(self.root, name), "rtl"), "timed.sdc")
        self.assertIn("all_registers -level_sensitive", script)
        self.assertIn("catch", script)
        self.assertNotIn("-latches", script)
        head = "Design Area: 1.0\nDesign  WNS: 0.00  TNS: 0.00 Number of Violating Paths: 0\n"
        self.assertEqual(judge("synth", drv.parse("synth", head + "Latch Count: UNKNOWN\n", ""),
                               profile), "error")
        self.assertEqual(judge("synth", drv.parse("synth", head + "Latch Count: 2\n", ""),
                               profile), "fail")

    def test_r5_synth_requires_clock_in_sdc(self):
        name = "clkdemo"
        init_sys(self.root, name)
        sys_root = sys_dir(self.root, name)
        _write(os.path.join(sys_root, "dc", "loose.sdc"), "set_load 0.1 [all_outputs]\n")
        result = run_other("synth", {"sys": name, "dry_run": True,
                                     "sdc": os.path.join(sys_root, "dc", "loose.sdc")})
        self.assertEqual(result["status"], "error")
        self.assertIn("create_clock", result["summary"])
        _write(os.path.join(sys_root, "dc", "timed.sdc"),
               "create_clock -period 0.2 [get_ports clk_in]\n")
        ok = run_other("synth", {"sys": name, "dry_run": True,
                                 "sdc": os.path.join(sys_root, "dc", "timed.sdc")})
        self.assertEqual(ok["status"], "dry_run")

    def test_f26_synth_reads_rtl_dir_and_pub_code(self):
        name = "synthdemo"
        init_sys(self.root, name)
        rtl = os.path.join(sys_dir(self.root, name), "rtl")
        _write(os.path.join(rtl, "alu.sv"),
               "module alu(input clk);\n  counter u_c (.clk(clk));\nendmodule\n")
        _write(os.path.join(sys_dir(self.root, name), "dc", "timed.sdc"),
               "create_clock -period 0.2 [get_ports clk_in]\n")
        _write(os.path.join(self.root, "pub_code", "counter.v"),
               "module counter(input clk); endmodule\n")
        _write(os.path.join(self.root, "pub_code", "notused.v"),
               "module notused(input clk); endmodule\n")
        result = run_other("synth", {
            "sys": name, "dry_run": True, "sdc": os.path.join(sys_dir(self.root, name), "dc", "timed.sdc"),
            "rtl_dir": os.path.join(sys_dir(self.root, name), "rtl"),
        })
        self.assertEqual(result["status"], "dry_run")
        self.assertIn("%s/%s/rtl/alu.sv" % (MIRROR, name), result["summary"])
        self.assertIn("%s/pub_code/counter.v" % MIRROR, result["summary"])
        self.assertNotIn("pub_code/notused.v", result["summary"])


class RunRecordTests(RepoTest):
    def test_f11_row7_lint_is_per_module(self):
        name = "lintdemo"
        init_sys(self.root, name)
        rtl = os.path.join(sys_dir(self.root, name), "rtl")
        _write(os.path.join(rtl, "alu.sv"), "module alu; endmodule\n")
        _write(os.path.join(rtl, "glue.sv"), "module glue; endmodule\n")
        # 行 7 的模块清单由 rtl/*.sv 推导，不再 set_module 登记。
        record_run(self.root, name, {
            "capability": "lint", "status": "pass", "summary": "lint pass", "profile_id": "p",
            "scope": {"modules": ["alu"]}, "checks": {"errors": 0},
        })
        findings = run_gates(self.root, name, 7, load_state(self.root, name))
        self.assertTrue(any("缺 lint 记录" in item["detail"] and "glue" in item["detail"]
                            for item in findings), findings)
        record_run(self.root, name, {
            "capability": "lint", "status": "pass", "summary": "lint pass", "profile_id": "p",
            "scope": {"modules": ["alu", "glue"]}, "checks": {"errors": 0},
        })
        findings = run_gates(self.root, name, 7, load_state(self.root, name))
        self.assertFalse(any("缺 lint 记录" in item["detail"] for item in findings), findings)

    def test_f11_lint_scope_lists_linted_files(self):
        name = "lintsrc"
        init_sys(self.root, name)
        rtl = os.path.join(sys_dir(self.root, name), "rtl")
        _write(os.path.join(rtl, "alu.sv"), "module alu; endmodule\n")
        _write(os.path.join(rtl, "glue.sv"), "module glue; endmodule\n")
        result = run_other("lint", {"sys": name, "dry_run": True, "no_sync": True})
        self.assertEqual(result["status"], "dry_run")

    def test_r4_pubip_tb_root_counts_cases(self):
        """pubip 场景的 TB 在 pub_code/testbench/<module>，行 10 的用例数要从那里取。"""
        from framework.profile_run import _tc_all_cases
        name = "pubipdemo"
        init_sys(self.root, name)
        tb = os.path.join(self.root, "pub_code", "testbench", "alu")
        _write(os.path.join(tb, "tc", "alu_tc_basic.sv"),
               "class alu_tc_basic;\n  task body();\n  endtask\nendclass\n")
        _write(os.path.join(tb, "tc", "alu_tc_extra.sv"),
               "class alu_tc_extra;\n  task body();\n  endtask\nendclass\n")
        _write(os.path.join(tb, "tc", "alu_tc_factory.svh"),
               '"tc_basic": begin end\n"tc_extra": begin end\n')
        _write(os.path.join(tb, "tc", "alu_tc_all.sv"),
               "class alu_tc_all;\n  task body();\n"
               "    alu_tc_basic a = new(\"tc_basic\");\n    a.body();\n"
               "    alu_tc_extra b = new(\"tc_extra\");\n    b.body();\n"
               "  endtask\nendclass\n")
        self.assertEqual(_tc_all_cases(name, "alu"), 2)

    def test_delegate_is_removed(self):
        # 代判删除（delegate 子命令一并删）：status 不再显示"代判"行；engine 不再有
        # set_delegate/delegate_active；`delegate` 不在子命令表里——argparse 以
        # invalid choice 报错并按退出码 2 结束（旧的"打印提示后返回非 0"兼容壳已删）。
        name = "nodeleg"
        init_sys(self.root, name)
        from framework.engine import status_report
        text = status_report(self.root, name)
        self.assertNotIn("代判", text)
        self.assertFalse(hasattr(__import__("framework.engine", fromlist=["x"]),
                                 "set_delegate"))
        self.assertFalse(hasattr(__import__("framework.engine", fromlist=["x"]),
                                 "delegate_active"))
        spec = importlib.util.spec_from_file_location(
            "cli_delegate", os.path.join(checkout_root(), "script", "framework.py"))
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        import contextlib
        import io
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as ctx:
                cli.main(["delegate", name, "set", "--scope", "阶段 3",
                          "--until", "2000-01-01"])
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("invalid choice", err.getvalue())
        self.assertIn("delegate", err.getvalue())
        # --help 的候选子命令里也不再有 delegate。
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            with self.assertRaises(SystemExit) as ctx:
                cli.main(["--help"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertNotIn("delegate", out.getvalue())

    def test_run_without_sys_warns_about_missing_record(self):
        """缺 --sys 时不能静默丢弃运行记录：要出提示，且确实没记。"""
        import contextlib
        import io
        name = "norecdemo"
        init_sys(self.root, name)
        spec = importlib.util.spec_from_file_location(
            "cli_for_test", os.path.join(checkout_root(), "script", "framework.py"))
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)

        def fake_other(capability, req):
            return {"capability": capability, "status": "pass", "summary": "stub pass",
                    "checks": {}, "artifacts": [], "scope": {}, "sdc_paths": [],
                    "profile_id": "p"}

        real = cli.run_other
        cli.run_other = fake_other
        try:
            err = io.StringIO()
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                code = cli.main(["run", "lint"])
            self.assertEqual(code, 0)
            self.assertIn("未记入运行记录", err.getvalue())
            self.assertEqual(load_state(self.root, name)["runs"], [])
            with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                code = cli.main(["run", "lint", "--sys", name])
            self.assertEqual(code, 0)
            self.assertEqual(len(load_state(self.root, name)["runs"]), 1)
        finally:
            cli.run_other = real

    def test_run_other_full_path_with_stub_transport(self):
        """非 dry-run 的 run_other 要把 parse → judge → scope → collect → artifacts 走完。

        之前这条路径没有任何覆盖，`_collect(..., scope)` 用在 scope 赋值之前就一直没被发现。
        这里把 ssh/rsync 换成假 transport，其余全是真代码。
        """
        import subprocess
        name = "fulldemo"
        init_sys(self.root, name)
        sdc = os.path.join(sys_dir(self.root, name), "dc", "timed.sdc")
        _write(sdc, "create_clock -period 0.2 [get_ports clk_in]\n")
        _write(os.path.join(sys_dir(self.root, name), "rtl", "alu.sv"), "module alu; endmodule\n")
        calls = []

        class FakeProc:
            def __init__(self, stdout="", returncode=0):
                self.stdout = stdout
                self.stderr = ""
                self.returncode = returncode

        class LogProc(FakeProc):
            def __init__(self):
                FakeProc.__init__(self, "NLINT " + "RESULT: PASS\n")

        def fake_run(argv, **kwargs):
            calls.append(argv[0] if isinstance(argv, list) else argv)
            if isinstance(argv, list) and argv[0] == "ssh":
                return LogProc()
            return FakeProc()

        real = subprocess.run
        subprocess.run = fake_run
        try:
            lint = run_other("lint", {"sys": name})
        finally:
            subprocess.run = real
        self.assertEqual(lint["status"], "pass", lint)
        self.assertEqual(lint["checks"].get("errors"), 0)
        self.assertTrue(lint["artifacts"], lint["artifacts"])
        self.assertIn("ssh", calls)
        self.assertEqual(lint["scope"]["modules"], ["alu"])

        def fake_synth(argv, **kwargs):
            if isinstance(argv, list) and argv[0] == "ssh":
                return FakeProc("Design Area: 12.5\nDesign  WNS: 0.10  TNS: 0.00 "
                                "Number of Violating Paths: 0\nLatch Count: 0\n")
            return FakeProc()

        _write(os.path.join(sys_dir(self.root, name), "dc", "stub_top_syn.v"), "// netlist\n")
        _write(os.path.join(sys_dir(self.root, name), "dc", "stub_top_syn.sdc"),
               "create_clock -period 0.2 [get_ports clk_in]\n")
        subprocess.run = fake_synth
        try:
            synth = run_other("synth", {"sys": name, "sdc": sdc, "top": "stub_top"})
        finally:
            subprocess.run = real
        self.assertEqual(synth["status"], "pass", synth)
        self.assertEqual(synth["scope"]["top"], "stub_top")
        self.assertIn(sdc, synth["sdc_paths"])
        self.assertTrue(any(str(item).endswith("_syn.v") for item in synth["artifacts"]),
                        synth["artifacts"])

    def test_sim_rewrites_baked_f_paths(self):
        """数据根换成副本后，.f 里烘死的旧绝对根路径也要改写成镜像根。"""
        name = "fdemo"
        init_sys(self.root, name)
        tb = os.path.join(self.root, "pub_code", "testbench", name)
        _write(os.path.join(tb, "%s_tb.f" % name),
               "+incdir+/somewhere/else/asic_design_agent/tb_common\n"
               "/somewhere/else/asic_design_agent/pub_code/testbench/%s/%s_tb_pkg.sv\n" % (name, name))
        drv = _driver(self.root, "sim.py")
        profile = load_profile()
        roots = drv.baked_roots(profile, name, name)
        self.assertIn("/somewhere/else/asic_design_agent", roots)
        self.assertIn(os.path.join(self.root), roots)
        line = drv.rewrite_line(profile, name, name)
        self.assertIn("s|/somewhere/else/asic_design_agent|%s|g" % MIRROR, line)
        self.assertIn("-name '*.f'", line)

    def test_f09_seed_crash_is_error(self):
        profile = load_profile()
        drv = _driver(self.root, "sim.py")
        crashed = drv.parse("sim", "SEED_CRASH seed=2 rc=139\n", "")
        self.assertEqual(judge("sim", crashed, profile), "error")

    def test_f09_case_end_evidence_counts_cases(self):
        """本平台 TB 每个 seed 只汇总一行 RESULT，全量回归要按跑过的用例数核对。"""
        from framework.profile_run import _regression_expectation
        name = "caseevidence"
        init_sys(self.root, name)
        tb = os.path.join(self.root, "pub_code", "testbench", "alu")
        for case in ("basic", "extra"):
            _write(os.path.join(tb, "tc", "alu_tc_%s.sv" % case),
                   "class alu_tc_%s;\n  task body();\n  endtask\nendclass\n" % case)
        _write(os.path.join(tb, "tc", "alu_tc_all.sv"),
               "class alu_tc_all;\n  task body();\n"
               "    alu_tc_basic a = new(\"tc_basic\");\n    a.body();\n"
               "    alu_tc_extra b = new(\"tc_extra\");\n    b.body();\n"
               "  endtask\nendclass\n")
        covered = _regression_expectation(name, "alu", {"seeds": [""]},
                                         {"result_pass": 1, "result_fail": 0, "cases_run": 2})
        self.assertEqual(covered["tc_all_cases"], 2)
        self.assertEqual(covered["full_regression"], 1, covered)
        self.assertEqual(covered["cases_source"], "cases")
        partial = _regression_expectation(name, "alu", {"seeds": [""]},
                                         {"result_pass": 1, "result_fail": 0, "cases_run": 1})
        self.assertEqual(partial["full_regression"], 0)
        # driver 报不出用例数时退回按 RESULT 行数核对
        by_result = _regression_expectation(name, "alu", {"seeds": [""]},
                                           {"result_pass": 2, "result_fail": 0})
        self.assertEqual(by_result["full_regression"], 1, by_result)
        self.assertEqual(by_result["cases_source"], "results")

    def test_f09_row10_needs_full_regression(self):
        name = "simdemo"
        init_sys(self.root, name)
        base = {"capability": "sim", "status": "pass", "summary": "RESULT : PASS", "profile_id": "p"}
        record_run(self.root, name, dict(base, scope={"scenario": "sys", "tc": "tc_basic"},
                                        checks={"result_pass": 1, "full_regression": 0}))
        findings = run_gates(self.root, name, 10, load_state(self.root, name))
        self.assertTrue(any("全量回归" in item["detail"] for item in findings), findings)
        record_run(self.root, name, dict(base, scope={"scenario": "module", "tc": ""},
                                        checks={"result_pass": 1, "full_regression": 1}))
        findings = run_gates(self.root, name, 10, load_state(self.root, name))
        self.assertTrue(any("全量回归" in item["detail"] for item in findings), findings)
        record_run(self.root, name, dict(base, scope={"scenario": "sys", "tc": ""},
                                        checks={"result_pass": 8, "full_regression": 0}))
        findings = run_gates(self.root, name, 10, load_state(self.root, name))
        self.assertTrue(any("用例数" in item["detail"] for item in findings), findings)
        record_run(self.root, name, dict(base, scope={"scenario": "sys", "tc": ""},
                                        checks={"result_pass": 8, "observed_cases": 3,
                                                "cases_source": "results", "full_regression": 0}))
        findings = run_gates(self.root, name, 10, load_state(self.root, name))
        self.assertTrue(any("RESULT 条数=3" in item["detail"] for item in findings), findings)
        record_run(self.root, name, dict(base, scope={"scenario": "sys", "tc": ""},
                                        checks={"result_pass": 8, "full_regression": 1}))
        findings = run_gates(self.root, name, 10, load_state(self.root, name))
        self.assertFalse(any(item["where"] == "sim" for item in findings), findings)

    def test_coverage_record_does_not_carry_sdc(self):
        """coverage/lint 的运行记录不能挂 SDC：否则改 SDC 会把它们误判成输入已变更。"""
        import subprocess
        name = "covsdc"
        init_sys(self.root, name)
        _write(os.path.join(sys_dir(self.root, name), "rtl", "alu.sv"), "module alu; endmodule\n")
        record_run(self.root, name, {
            "capability": "synth", "status": "pass", "summary": "synth pass", "profile_id": "p",
            "checks": {"errors": 0, "latches": 0, "setup_wns": 0.1, "setup_violations": 0, "area": 1.0},
            "artifacts": ["%s/dc/top_syn.v" % name, "%s/dc/top_syn.sdc" % name],
        })
        sdc = os.path.join(sys_dir(self.root, name), "dc", "top_syn.sdc")
        _write(sdc, "create_clock -period 1.0 [get_ports clk]\n")

        class FakeProc:
            def __init__(self, stdout=""):
                self.stdout = stdout
                self.stderr = ""
                self.returncode = 0

        real = subprocess.run
        subprocess.run = lambda argv, **kwargs: FakeProc("MODULE  LINE  COND  TOGGLE  FSM\n"
                                                        "100.00 100.00 100.00 100.00 100.00\n")
        try:
            coverage = run_other("coverage", {"sys": name})
        finally:
            subprocess.run = real
        self.assertEqual(coverage["status"], "pass", coverage)
        self.assertEqual(coverage["sdc_paths"], [])
        record_run(self.root, name, coverage)
        _write(sdc, "create_clock -period 2.0 [get_ports clk]\n")
        findings = run_gates(self.root, name, 10, load_state(self.root, name))
        self.assertFalse(any(item["where"] == "coverage" and "输入已变更" in item["detail"]
                             for item in findings), findings)

    def test_f30_sta_defaults_to_last_synth_netlist(self):
        name = "stademo"
        init_sys(self.root, name)
        record_run(self.root, name, {
            "capability": "synth", "status": "pass", "summary": "synth pass", "profile_id": "p",
            "checks": {"errors": 0, "latches": 0, "setup_wns": 0.1, "setup_violations": 0, "area": 1.0},
            "artifacts": ["%s/dc/%s_top_syn.v" % (name, name), "%s/dc/%s_top_syn.sdc" % (name, name)],
        })
        result = run_other("sta", {"sys": name, "dry_run": True})
        self.assertEqual(result["status"], "dry_run", result["summary"])
        self.assertIn("%s_top_syn.v" % name, result["summary"])
        self.assertIn("%s_top_syn.sdc" % name, result["summary"])

    def test_f30_sta_without_netlist_is_error(self):
        name = "stonedemo"
        init_sys(self.root, name)
        result = run_other("sta", {"sys": name, "dry_run": True})
        self.assertEqual(result["status"], "error")
        self.assertIn("网表", result["summary"])

    def test_f30_pull_line_targets_local_report_dir(self):
        profile = load_profile()
        drv = _driver(self.root, "eda.py")
        line = drv.pull_line(profile, "demo", "synth", {})
        self.assertIn("%s/demo/dc/" % MIRROR, line)
        self.assertIn("demo/dc/", line)

    def test_f30_sdc_enters_inputs_digest(self):
        name = "sdcdemo"
        init_sys(self.root, name)
        sdc = os.path.join(sys_dir(self.root, name), "dc", "timed.sdc")
        _write(sdc, "create_clock -period 0.2 [get_ports clk_in]\n")
        before = inputs_digest(self.root, name)
        record_run(self.root, name, {
            "capability": "synth", "status": "pass", "summary": "synth pass", "profile_id": "p",
            "sdc_paths": [sdc],
            "checks": {"errors": 0, "latches": 0, "setup_wns": 0.1, "setup_violations": 0, "area": 1.0},
        })
        self.assertNotEqual(before, inputs_digest(self.root, name, [sdc]))
        findings = run_gates(self.root, name, 11, load_state(self.root, name))
        self.assertFalse(any(item["where"] == "synth" and "输入已变更" in item["detail"]
                             for item in findings), findings)
        _write(sdc, "create_clock -period 0.5 [get_ports clk_in]\n")
        findings = run_gates(self.root, name, 11, load_state(self.root, name))
        self.assertTrue(any(item["where"] == "synth" and "输入已变更" in item["detail"]
                            for item in findings), findings)


if __name__ == "__main__":
    unittest.main()
