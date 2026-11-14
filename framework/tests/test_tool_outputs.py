# 作者：vick 邮箱：ykun@yk9811.com

"""真机确认与现场确认查出的缺陷的复现用例。"""

import os
import subprocess
import unittest

from framework.engine import DONE, RUNNING, advance, tick_report
from framework.profile_run import judge, load_profile, run_other, run_sim
from framework.state import init_sys, load_state, stop_row, sys_dir
from framework.tests.util import RepoTest, checkout_root, plant_sample

QUOTE = "通过"


class FakeProc:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _fake_subprocess(ssh_out, ssh_rc=0):
    def run(argv, **kwargs):
        if isinstance(argv, list) and argv[:1] == ["ssh"]:
            return FakeProc(ssh_out, "", ssh_rc)
        return FakeProc("", "", 0)
    return run


class CompileOnlyTests(RepoTest):
    """只编译的仿真没有 RESULT 行，判据是编译过没过，不该判 error。"""

    def test_judge_reads_the_compile_result(self):
        profile = load_profile()
        ok = {"result_pass": 0, "result_fail": 0, "compile_error": 0, "compile_only": 1}
        self.assertEqual(judge("sim", dict(ok), profile), "pass")
        self.assertEqual(judge("sim", dict(ok, compile_error=1), profile), "error")
        self.assertEqual(judge("sim", dict(ok, wall_timeout=1), profile), "error")

    def _run(self, ssh_out, ssh_rc=0):
        name = "v1compile"
        init_sys(self.root, name)
        real = subprocess.run
        subprocess.run = _fake_subprocess(ssh_out, ssh_rc)
        try:
            return run_sim({"scenario": "module", "sys": name, "module": "alu",
                            "compile_only": True})
        finally:
            subprocess.run = real

    def test_compile_only_success_is_a_pass(self):
        result = self._run("compiling ...\ncompile ok\n")
        self.assertEqual(result["status"], "pass", result)
        self.assertEqual(result["checks"].get("compile_only"), 1)
        self.assertNotIn("full_regression", result["checks"])

    def test_compile_only_failure_is_an_error(self):
        marker = "COMPILE_" + "FAIL"
        result = self._run("Error-[SE] Syntax error\n%s\n" % marker, ssh_rc=2)
        self.assertEqual(result["status"], "error", result)

    def test_full_run_still_needs_results(self):
        name = "v1full"
        init_sys(self.root, name)
        real = subprocess.run
        subprocess.run = _fake_subprocess("SEED_RESULT seed=0 pass=0 fail=0\n")
        try:
            result = run_sim({"scenario": "module", "sys": name, "module": "alu"})
        finally:
            subprocess.run = real
        self.assertEqual(result["status"], "error", result)
        self.assertNotIn("compile_only", result["checks"])


class ToolOutputDecodingTests(RepoTest):
    """时序工具的失败输出里有非 UTF-8 字节，解码不能抛异常。"""

    def test_every_capture_asks_for_replacement(self):
        import re
        path = os.path.join(checkout_root(), "framework", "profile_run.py")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        calls = re.findall(r"capture_output=True, text=True[^)]*", text)
        self.assertTrue(calls)
        for call in calls:
            self.assertIn('errors="replace"', call, call)

    def test_sta_failure_is_recorded_not_crashed(self):
        """工具输出里有非 UTF-8 字节时也要落成 error 记录，不能抛异常溜出去。"""
        name = "v4sta"
        init_sys(self.root, name)
        real = subprocess.run

        def fake(argv, **kwargs):
            if isinstance(argv, list) and argv[:1] == ["ssh"]:
                kwargs.pop("input", None)
                # 用同一个 kwargs 跑一条真的会吐出非法 UTF-8 的命令。
                return real(["printf", "Err" + "or: bad \\377\\376\\n"], **kwargs)
            return FakeProc("", "", 0)

        subprocess.run = fake
        try:
            result = run_other("sta", {"sys": name, "netlist": "%s/rtl/missing.v" % name,
                                       "sdc": "%s/t.sdc" % name})
        finally:
            subprocess.run = real
        self.assertEqual(result["status"], "error", result)


class RetreatClearsConfirmationTests(RepoTest):
    """现场发现：退回进行中后，上一次"完成"的痕迹不该留在行上。

    `status`/`*_status.md` 会照抄 `done_at`，`state.json` 会留着确认痕迹，
    看着像"这一版已经被确认过"。改写后：完成由 tick 自动写入（不写确认原话），
    退回清理断言为 done_at/confirmed_at/fingerprint（confirm_quote 保持空）。
    """

    def _plant(self, name):
        init_sys(self.root, name)
        plant_sample(self.root, name)

    def _finish(self, name, sid):
        """补独立审查记录后 tick：自动启动 + 自动完成（四相位）。"""
        from framework.tests.util import review
        review(self.root, name, sid)
        tick_report(self.root, name)

    def test_retreat_clears_done_at_and_quote(self):
        name = "v7retreat"
        self._plant(name)
        self._finish(name, 1)
        row = stop_row(load_state(self.root, name), 1)
        self.assertEqual(row["state"], DONE)
        self.assertEqual(row["confirm_quote"], "")
        self.assertTrue(row["done_at"])
        self.assertTrue(row["fingerprint"])
        advance(self.root, name, 1, RUNNING)
        row = stop_row(load_state(self.root, name), 1)
        self.assertEqual(row["state"], RUNNING)
        for key in ("done_at", "confirmed_at", "confirm_quote", "fingerprint"):
            self.assertEqual(row.get(key), "", "%s 没清掉" % key)
        # 重推：审查记录仍对得上当前产物，tick 自动完成，确认语句仍为空。
        tick_report(self.root, name)
        row = stop_row(load_state(self.root, name), 1)
        self.assertEqual(row["state"], DONE)
        self.assertEqual(row["confirm_quote"], "")

    def test_cascade_clears_downstream_done_marks(self):
        name = "v7cascade"
        self._plant(name)
        self._finish(name, 1)
        for sid in (2, 3):
            self._finish(name, sid)
        for sid in (1, 2, 3):
            row = stop_row(load_state(self.root, name), sid)
            self.assertEqual(row["state"], DONE)
            self.assertTrue(row["done_at"])
        advance(self.root, name, 1, RUNNING)
        state = load_state(self.root, name)
        self.assertEqual(stop_row(state, 1)["confirm_quote"], "")
        for sid in (2, 3):
            row = stop_row(state, sid)
            self.assertEqual(row["state"], RUNNING, "行 %d 没被级联退回" % sid)
            self.assertEqual(row.get("done_at"), "", "行 %d 的完成时间没跟着级联清掉" % sid)
            self.assertEqual(row["confirm_quote"], "", "行 %d 的确认痕迹没跟着级联清掉" % sid)

    def test_status_doc_does_not_show_a_done_time_for_a_retreated_row(self):
        name = "v7status"
        self._plant(name)
        self._finish(name, 1)
        advance(self.root, name, 1, RUNNING)
        with open(os.path.join(sys_dir(self.root, name), "%s_status.md" % name),
                  encoding="utf-8") as fh:
            text = fh.read()
        row = [line for line in text.splitlines() if line.startswith("| 1 |")]
        self.assertTrue(row, text)
        self.assertNotIn("2026", row[0], row[0])


if __name__ == "__main__":
    unittest.main()
