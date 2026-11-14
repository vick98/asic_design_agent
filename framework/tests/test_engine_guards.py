# 作者：vick 邮箱：ykun@yk9811.com

"""第二轮走查后的补漏：豁免、行 7 摘要、骨架默认失败、旧报告、STA 汇总、引擎家目录。"""

import importlib.util
import os
import pwd
import subprocess
import sys

from framework import engine
from framework.engine import (
    EngineError, add_waiver, record_run, withdraw_decision,
)
from framework.gates.run import run_gates
from framework.profile_run import judge, load_profile
from framework.state import init_sys, load_state, sys_dir
from framework.tbgen import generate
from framework.tests.util import RepoTest, checkout_root, decide, review

QUOTE = "同意"


def _driver(root, filename):
    path = os.path.join(root, "toolchain", "profiles", "example", "drivers", filename)
    spec = importlib.util.spec_from_file_location("r3_" + filename[:-3], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _lint(root, name, modules):
    return record_run(root, name, {
        "capability": "lint", "status": "pass", "summary": "lint pass", "profile_id": "p",
        "scope": {"modules": list(modules)}, "checks": {"errors": 0},
    })


def _record_decision(root, name, content):
    """记录类裁决直接入库（两步链路），停点 1 → 行 1。"""
    return decide(root, name, content, "记录", 1)


def _dir_decision(root, name, content):
    """方向类裁决：开发者点选入库（红线动作），不需要任何令牌或终端。"""
    return decide(root, name, content, "方向", 1,
                  options="%s|其他" % content, pick=content)


def _row7_mod_findings(root, name):
    return [item for item in run_gates(root, name, 7, load_state(root, name))
            if item.get("rule") in ("mod", "run")]


class WaiverTests(RepoTest):
    def test_waive_needs_directional_decision(self):
        # 旧断言：豁免要令牌与终端照抄 → 新断言：豁免自动，只校验引用的裁决存在且
        # 是方向/数值类（点选入库）；记录类裁决不可豁免 → 依据豁免口径与红线第 2 条。
        name = "waivehuman"
        init_sys(self.root, name)
        did = _record_decision(self.root, name, "接受缺章节")
        with self.assertRaises(EngineError) as ctx:
            add_waiver(self.root, name, "S1", "info_input/x.md", did)
        self.assertIn("方向/数值", str(ctx.exception))
        with self.assertRaises(EngineError) as ctx:
            add_waiver(self.root, name, "S1", "info_input/x.md", "D0-999")
        self.assertIn("已入库裁决", str(ctx.exception))
        self.assertEqual(load_state(self.root, name)["waivers"], [])
        did2 = _dir_decision(self.root, name, "缺章节可以接受")
        add_waiver(self.root, name, "S1", "info_input/x.md", did2)
        waiver = load_state(self.root, name)["waivers"][0]
        self.assertEqual(waiver["decision"], did2)

    def test_waive_fingerprint_rule_rejected(self):
        name = "waivefp"
        init_sys(self.root, name)
        did = _dir_decision(self.root, name, "接受产物改动")
        with self.assertRaises(EngineError) as ctx:
            add_waiver(self.root, name, "fingerprint", "info_input/x.md", did)
        self.assertIn("fingerprint", str(ctx.exception))

    def test_waive_cli_without_terminal_now_passes(self):
        # 旧断言：CLI 豁免没有终端要拒 → 新断言：CLI 豁免自动，不要终端；
        # 忽略型 --confirm 已删，传它必须 argparse 报错（同一用例双向验证）。
        name = "waivecli"
        init_sys(self.root, name)
        did = _dir_decision(self.root, name, "接受缺章节")
        script = os.path.join(checkout_root(), "script", "framework.py")
        env = os.environ.copy()
        env["ADF_ROOT"] = self.root
        proc = subprocess.run(
            [sys.executable, script,
             "waive", name, "add", "--rule", "S1", "--where", "x", "--decision", did],
            env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(load_state(self.root, name)["waivers"][0]["decision"], did)
        proc = subprocess.run(
            [sys.executable, script,
             "waive", name, "add", "--rule", "S1", "--where", "x", "--decision", did,
             "--confirm", QUOTE],
            env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("unrecognized", proc.stderr)
        self.assertEqual(len(load_state(self.root, name)["waivers"]), 1, "被拒的调用不得再记一条")

    def test_cov_waiver_needs_a_live_directional_decision(self):
        name = "covlive"
        init_sys(self.root, name)
        sys_root = sys_dir(self.root, name)
        _write(os.path.join(sys_root, "testbench", "cov_gate.txt"), "line = 50\n")
        did = _dir_decision(self.root, name, "line 下调到 50")
        add_waiver(self.root, name, "COV", "line", did)
        profile = load_profile()
        checks = {"line": 60.0, "cond": 100.0, "fsm": 100.0, "tgl": 100.0}
        self.assertEqual(judge("coverage", dict(checks), profile, sys_root=sys_root,
                               state=load_state(self.root, name)), "pass")
        withdraw_decision(self.root, name, did)
        # 撤回的裁决不再是有效证据（口径见 engine._decision_exists）：引用的裁决撤回后，
        # 豁免必须失效、覆盖率判据回到 fail。这要求豁免过滤（profile_run.judge 的 live、
        # gates.run._without_waivers 的 known）按 withdrawn 排除——此前 withdraw 是"删行"，
        # 那两处"id 存在即可"才等价于"有效"。
        self.assertEqual(judge("coverage", dict(checks), profile, sys_root=sys_root,
                               state=load_state(self.root, name)), "fail")


class Row7DigestTests(RepoTest):
    def _setup(self, name):
        init_sys(self.root, name)
        rtl = os.path.join(sys_dir(self.root, name), "rtl")
        _write(os.path.join(rtl, "alu.sv"), "module alu(input logic a, output logic y); assign y = a; endmodule\n")
        _write(os.path.join(rtl, "glue.sv"), "module glue(input logic a, output logic y); assign y = a; endmodule\n")
        # 行 7 的模块清单由 rtl/*.sv 推导，不再 set_module 登记；
        # 通过态由 lint/审查证据推导。两个模块文件就位即构成清单。
        return rtl

    def test_reviewed_module_edited_needs_new_lint_and_review(self):
        name = "row7review"
        rtl = self._setup(name)
        _lint(self.root, name, ["alu"])
        # 审查记录要带 report/<文件>.md，review() 写好报告再登记。
        review(self.root, name, 7, module="alu")
        _write(os.path.join(rtl, "alu.sv"), "module alu(input logic a, output logic y); always_comb y = y; endmodule\n")
        _lint(self.root, name, ["glue"])
        findings = _row7_mod_findings(self.root, name)
        self.assertTrue(any("alu" in item["detail"] for item in findings), findings)

    def test_module_lint_goes_stale_after_edit(self):
        name = "row7stale"
        rtl = self._setup(name)
        _lint(self.root, name, ["alu"])
        _write(os.path.join(rtl, "alu.sv"), "module alu(input logic a, output logic y); always_comb y = y; endmodule\n")
        _lint(self.root, name, ["glue"])
        findings = _row7_mod_findings(self.root, name)
        self.assertTrue(any("alu" in item["detail"] for item in findings), findings)
        _lint(self.root, name, ["alu"])
        self.assertEqual(_row7_mod_findings(self.root, name), [])

    def test_review_record_refuses_stale_lint(self):
        name = "row7revstale"
        rtl = self._setup(name)
        _lint(self.root, name, ["alu"])
        _write(os.path.join(rtl, "alu.sv"), "module alu(input logic a, output logic y); assign y = ~a; endmodule\n")
        # 报告先备好（review() 会写），这样才能确认拒绝的原因是 lint 陈旧，
        # 而不是"缺报告"这类前置错误。
        with self.assertRaises(EngineError) as ctx:
            review(self.root, name, 7, module="alu")
        self.assertIn("lint", str(ctx.exception))


class TbSkeletonTests(RepoTest):
    def test_skeleton_fails_until_filled(self):
        name = "skel"
        init_sys(self.root, name)
        generate(sys_dir(self.root, name), name, "alu")
        tb = os.path.join(sys_dir(self.root, name), "testbench", "alu")
        case = open(os.path.join(tb, "tc", "alu_tc_basic.sv"), encoding="utf-8").read()
        self.assertIn("m_fail_cnt", case)
        self.assertIn("骨架未填写", case)
        self.assertNotIn("RESULT: PASS", case)

    def test_zero_checks_is_not_a_pass(self):
        pkg = open(os.path.join(checkout_root(), "tb_common", "tb_pkg.sv"), encoding="utf-8").read()
        summary = pkg[pkg.index("function void report_summary"):]
        summary = summary[:summary.index("endfunction")]
        self.assertIn("m_pass_cnt + m_fail_cnt == 0", summary)
        self.assertLess(summary.index("m_pass_cnt + m_fail_cnt == 0"), summary.index("RESULT"))


class StaleReportTests(RepoTest):
    def _profile(self):
        return load_profile()

    def test_scripts_remove_old_reports_before_the_tool_runs(self):
        drv = _driver(self.root, "eda.py")
        profile = self._profile()
        # 版本探针行在脚本开头（`<工具> -version`），裸工具名会命中它而不是
        # 真正的调用行；这里一律用调用形态定位"真跑"，顺带钉住探针在真跑之前。
        lint = drv.lint_script(profile, "demo", "demo/rtl")
        lint_run = lint.index("n" + "Lint -nologo")
        self.assertIn("TOOL_VERSION lint", lint[:lint_run])
        self.assertLess(lint.index("rm -f"), lint_run)
        self.assertIn("nlint_report.txt", lint[lint.index("rm -f"):lint_run])
        synth = drv.synth_script(profile, "demo", sdc="x.sdc")
        synth_run = synth.index("dc_" + "shell -f ")
        self.assertIn("TOOL_VERSION synth", synth[:synth_run])
        self.assertLess(synth.index("rm -f"), synth_run)
        head = synth[:synth_run]
        for name in ("adf_checks.rpt", "demo_top_syn_qor.rpt", "demo_top_syn.v", "dc.log"):
            self.assertIn(name, head[head.index("rm -f"):])
        sta = drv.sta_script(profile, "demo", netlist="/m/demo/dc/demo_top_syn.v", sdc="/m/x.sdc")
        sta_run = sta.index("pt_" + "shell -f ")
        self.assertIn("TOOL_VERSION sta", sta[:sta_run])
        self.assertLess(sta.index("rm -f"), sta_run)
        head = sta[:sta_run]
        for name in ("demo_top_sta_setup.rpt", "demo_top_sta_hold.rpt", "demo_top_sta_qor.rpt", "pt.log"):
            self.assertIn(name, head[head.index("rm -f"):])

    def test_lint_without_report_is_error(self):
        drv = _driver(self.root, "eda.py")
        checks = drv.parse("lint", "NLINT " + "RESULT: NOREPORT\n", "")
        self.assertEqual(judge("lint", checks, self._profile()), "error")

    def test_sta_tool_error_is_error(self):
        drv = _driver(self.root, "eda.py")
        text = ("--- PT_REPORT:qor ---\n"
                "  Timing Path Group 'clk' (max_delay/setup)\n"
                "  Critical Path Slack:                     0.30\n"
                "  No. of Violating Paths:                     0\n"
                "  Timing Path Group 'clk' (min_delay/hold)\n"
                "  Critical Path Slack:                     0.10\n"
                "  No. of Violating Paths:                     0\n"
                "Error" + ": Unable to link design 'demo_top'. (LNK-005)\n")
        checks = drv.parse("sta", text, "")
        self.assertEqual(judge("sta", checks, self._profile()), "error")


class StaSummaryTests(RepoTest):
    def test_worst_path_group_wins(self):
        drv = _driver(self.root, "eda.py")
        text = ("--- PT_REPORT:qor ---\n"
                "  Timing Path Group 'clk_a' (max_delay/setup)\n"
                "  Critical Path Slack:                    -0.33\n"
                "  No. of Violating Paths:                     4\n"
                "  Timing Path Group 'clk_b' (max_delay/setup)\n"
                "  Critical Path Slack:                     0.50\n"
                "  No. of Violating Paths:                     0\n"
                "  Timing Path Group 'clk_a' (min_delay/hold)\n"
                "  Critical Path Slack:                    -0.02\n"
                "  No. of Violating Paths:                     1\n"
                "  Timing Path Group 'clk_b' (min_delay/hold)\n"
                "  Critical Path Slack:                     0.10\n"
                "  No. of Violating Paths:                     2\n")
        corner = drv.parse("sta", text, "")["corners"][0]
        self.assertEqual(corner["setup_wns"], -0.33)
        self.assertEqual(corner["setup_violations"], 4)
        self.assertEqual(corner["hold_wns"], -0.02)
        self.assertEqual(corner["hold_violations"], 3)
        self.assertEqual(judge("sta", drv.parse("sta", text, ""), load_profile()), "fail")

    def test_no_constrained_paths_still_seen_with_qor(self):
        drv = _driver(self.root, "eda.py")
        text = ("--- PT_REPORT:setup ---\nNo constrained paths.\n"
                "--- PT_REPORT:hold ---\nNo constrained paths.\n"
                "--- PT_REPORT:qor ---\n"
                "  Timing Path Group 'clk' (max_delay/setup)\n"
                "  Critical Path Slack:                     0.30\n"
                "  No. of Violating Paths:                     0\n"
                "  Timing Path Group 'clk' (min_delay/hold)\n"
                "  Critical Path Slack:                     0.10\n"
                "  No. of Violating Paths:                     0\n")
        self.assertEqual(judge("sta", drv.parse("sta", text, ""), load_profile()), "error")

    def test_sta_script_checks_timing_coverage(self):
        drv = _driver(self.root, "eda.py")
        sta = drv.sta_script(load_profile(), "demo", netlist="/m/demo/dc/demo_top_syn.v", sdc="/m/x.sdc")
        self.assertIn("check_timing", sta)
        self.assertIn("--- PT_REPORT:check ---", sta)

    def test_unconstrained_endpoints_block_row11_until_waived(self):
        drv = _driver(self.root, "eda.py")
        text = ("--- PT_REPORT:qor ---\n"
                "  Timing Path Group 'clk' (max_delay/setup)\n"
                "  Critical Path Slack:                     0.30\n"
                "  No. of Violating Paths:                     0\n"
                "  Timing Path Group 'clk' (min_delay/hold)\n"
                "  Critical Path Slack:                     0.10\n"
                "  No. of Violating Paths:                     0\n"
                "--- PT_REPORT:check ---\n"
                "Warning: There are 3 endpoints which are not constrained for maximum delay.\n")
        checks = drv.parse("sta", text, "")
        self.assertEqual(checks.get("unconstrained_endpoints"), 3)
        self.assertEqual(judge("sta", checks, load_profile()), "pass")
        name = "staunc"
        init_sys(self.root, name)
        record_run(self.root, name, {
            "capability": "synth", "status": "pass", "summary": "", "profile_id": "p",
            "checks": {"errors": 0, "latches": 0, "setup_wns": 0.1, "setup_violations": 0, "area": 1.0},
        })
        record_run(self.root, name, {
            "capability": "sta", "status": "pass", "summary": "", "profile_id": "p", "checks": checks,
        })
        findings = run_gates(self.root, name, 11, load_state(self.root, name))
        self.assertTrue(any(item["rule"] == "sta-unconstrained" for item in findings), findings)
        did = _dir_decision(self.root, name, "输出端口不约束")
        add_waiver(self.root, name, "sta-unconstrained", "sta", did)
        findings = run_gates(self.root, name, 11, load_state(self.root, name))
        self.assertFalse(any(item["rule"] == "sta-unconstrained" for item in findings), findings)


class ProblemCloseTests(RepoTest):
    def test_closing_a_blocking_problem_needs_fresh_evidence(self):
        # 旧断言：关闭阻断要令牌与终端照抄 → 新断言：自动，但要证据存在且不早于
        # 问题登记时间 → 依据证据晚于问题登记的登记序号。
        name = "probclose"
        init_sys(self.root, name)
        from framework.engine import add_problem, close_problem, record_run
        blocking = add_problem(self.root, name, "阻断", 3, "缺时钟", "spec_review")
        hint = add_problem(self.root, name, "阻断", 3, "措辞", "spec_review")
        # 问题类型只剩阻断/待裁决：第二条也按阻断登记，走同一套证据时效判据。
        # 证据缺失直接拒。
        with self.assertRaises(EngineError):
            close_problem(self.root, name, hint)
        # 证据过旧：把问题登记时间改到未来，再拿现在的运行记录当证据。
        rid = record_run(self.root, name, {
            "capability": "sim", "status": "pass", "summary": "RESULT : PASS",
            "profile_id": "p",
            "scope": {"scenario": "sys", "module": "", "tc": "", "seeds": ["1"]},
            "checks": {"result_pass": 1, "result_fail": 0, "full_regression": 1},
        })
        from framework.state import load_state, save
        state = load_state(self.root, name)
        for item in state["problems"]:
            if item["id"] == blocking:
                item["time"] = "2999-01-01 00:00"
        save(self.root, name, state)
        with self.assertRaises(EngineError) as ctx:
            close_problem(self.root, name, blocking, evidence=rid)
        self.assertIn("早于问题登记", str(ctx.exception))
        # 证据齐备即闭合，不要终端。
        state = load_state(self.root, name)
        for item in state["problems"]:
            if item["id"] == blocking:
                item["time"] = "2000-01-01 00:00"
        save(self.root, name, state)
        close_problem(self.root, name, blocking, evidence=rid)
        close_problem(self.root, name, hint, evidence=rid)
        items = [p for p in load_state(self.root, name)["problems"]]
        closed = {p["id"]: p for p in items}
        self.assertFalse(closed[blocking]["open"])
        self.assertEqual(closed[blocking]["evidence"], rid)

    def test_tradeoff_problem_needs_a_directional_decision(self):
        # 红线第 4 条：需要取舍的阻断问题先转为决策再关闭；kind=待裁决 或
        # 带 options/blocks 都算需要取舍。
        name = "probtrade"
        init_sys(self.root, name)
        from framework.engine import add_problem, close_problem, record_run
        rid = record_run(self.root, name, {
            "capability": "sim", "status": "pass", "summary": "RESULT : PASS",
            "profile_id": "p",
            "scope": {"scenario": "sys", "module": "", "tc": "", "seeds": ["1"]},
            "checks": {"result_pass": 1, "result_fail": 0, "full_regression": 1},
        })
        trade = add_problem(self.root, name, "待裁决", 3, "缓存取多大", "spec_review",
                            options="8|16|32")
        with self.assertRaises(EngineError) as ctx:
            close_problem(self.root, name, trade, evidence=rid)
        self.assertIn("先转为决策", str(ctx.exception))
        with self.assertRaises(EngineError) as ctx:
            close_problem(self.root, name, trade, evidence="D0-999")
        self.assertIn("不存在", str(ctx.exception))
        # 记录类裁决也不行：必须方向/数值类（点选入库的取舍）。
        rec_did = _record_decision(self.root, name, "缓存取 8 的备案")
        with self.assertRaises(EngineError) as ctx:
            close_problem(self.root, name, trade, evidence=rec_did)
        self.assertIn("先转为决策", str(ctx.exception))
        did = _dir_decision(self.root, name, "缓存取 16")
        close_problem(self.root, name, trade, evidence=did)
        self.assertFalse(
            [p for p in load_state(self.root, name)["problems"] if p["id"] == trade][0]["open"])


class InputsDigestTests(RepoTest):
    def _sys(self, name):
        init_sys(self.root, name)
        _write(os.path.join(sys_dir(self.root, name), "rtl", "top.sv"),
               "module top(input logic clk_in);\n  pubip_counter #(.MAX_NUM(8)) u_cnt (.clk_in(clk_in));\nendmodule\n")
        return name

    def test_tb_common_change_invalidates_runs(self):
        name = self._sys("digtb")
        before = engine.inputs_digest(self.root, name)
        with open(os.path.join(self.root, "tb_common", "tb_define.svh"), "a", encoding="utf-8") as fh:
            fh.write("\n// changed\n")
        self.assertNotEqual(engine.inputs_digest(self.root, name), before)

    def test_instantiated_pub_code_change_invalidates_runs(self):
        name = self._sys("digpub")
        before = engine.inputs_digest(self.root, name)
        with open(os.path.join(self.root, "pub_code", "pubip_sat.sv"), "a", encoding="utf-8") as fh:
            fh.write("\n// unrelated ip\n")
        self.assertEqual(engine.inputs_digest(self.root, name), before)
        with open(os.path.join(self.root, "pub_code", "pubip_counter.v"), "a", encoding="utf-8") as fh:
            fh.write("\n// used ip\n")
        self.assertNotEqual(engine.inputs_digest(self.root, name), before)


class SynthPubReadsTests(RepoTest):
    def test_nested_pub_code_is_read(self):
        name = "nestpub"
        init_sys(self.root, name)
        rtl = os.path.join(sys_dir(self.root, name), "rtl")
        _write(os.path.join(rtl, "%s_top.sv" % name),
               "module %s_top(input logic clk_in);\n"
               "  pubip_dynamic_mem #(.W(8)) u_mem (.clk_in(clk_in));\nendmodule\n" % name)
        drv = _driver(self.root, "eda.py")
        script = drv.synth_script(load_profile(), name, sdc="x.sdc")
        self.assertIn("pub_code/pubip_dynamic_mem.sv", script)
        self.assertIn("pub_code/sdpram_wrapper.sv", script)
        self.assertNotIn("pub_code/pubip_sat.sv", script)


class EngineHomeTests(RepoTest):
    """放行令牌已删除；引擎家目录仍按真实家目录算，不认 $HOME。"""

    def test_real_home_ignores_home_variable(self):
        saved = os.environ.get("HOME")
        os.environ["HOME"] = os.path.join(self.root, "elsewhere")
        try:
            self.assertEqual(engine.real_home(), pwd.getpwuid(os.geteuid()).pw_dir)
        finally:
            os.environ["HOME"] = saved

    def test_script_folder_has_no_fake_terminal(self):
        folder = os.path.join(checkout_root(), "script")
        for fn in os.listdir(folder):
            if fn.endswith(".py"):
                text = open(os.path.join(folder, fn), encoding="utf-8").read()
                self.assertNotIn("def isatty", text, fn)
