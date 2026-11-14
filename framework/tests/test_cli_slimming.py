# 作者：vick 邮箱：ykun@yk9811.com

"""命令行瘦身的验收：删除的参数/命令不得复活 + status 是只读版 tick。

一、反向守卫（全走真 CLI 进程，argparse 的退出码与 stderr 才是结论）：
  - `advance --confirm` / `--enter-structure` / `--loop-side`：三个参数已删，必须报
    unrecognized；
  - `delegate` 子命令不在 `--help`，调用按 invalid choice 退出码 2 结束；
  - `review <sys> --stop N` 只出审核清单，不带 `--report` 也退出 0；
  - `review record` 缺 `--report` 必须报错；`review --row` 别名已删；
  - `review record` / `waive add` / `problem close` 的忽略型 `--confirm` 必须 unrecognized；
  - `module --state` 只留 `退回`，别的状态一律被 argparse 拒。

二、`status` 只读验收：输出里除"当前位置"外还要有 `可推进的工作：` 与 `需要开发者：`
两张清单（status 是只读版 tick），但**不写事件、不改 state.json**——
前后对比 `events.jsonl` 的字节与 `state.json` 的 mtime/字节完全不变。
"""

import os
import unittest

from framework.state import init_sys, sys_dir
from framework.tests.util import RepoTest, cli, plant_sample, review


class RemovedCliSurfaceTests(RepoTest):
    """删除即删除：没有兼容壳，CLI 见到旧参数/旧命令必须 argparse 报错。"""

    def setUp(self):
        super().setUp()
        self.name = "slim"
        init_sys(self.root, self.name)

    def _rejected(self, *argv):
        proc = cli(self.root, *argv)
        self.assertNotEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("unrecognized", proc.stderr, proc.stderr)
        return proc

    def test_advance_confirm_flag_is_gone(self):
        self._rejected("advance", self.name, "--stop", "1", "--to", "进行中",
                       "--confirm", "x")

    def test_advance_enter_structure_flag_is_gone(self):
        self._rejected("advance", self.name, "--stop", "1", "--to", "进行中",
                       "--enter-structure")

    def test_advance_loop_side_flag_is_gone(self):
        self._rejected("advance", self.name, "--stop", "1", "--to", "进行中",
                       "--loop-side", "tb")
        self.assertEqual(load_items(self.root, self.name), [], "被拒的调用不得开事项")

    def test_delegate_subcommand_is_gone(self):
        proc = cli(self.root, "delegate", self.name, "set", "--scope", "阶段 3")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("invalid choice", proc.stderr)
        help_proc = cli(self.root, "--help")
        self.assertEqual(help_proc.returncode, 0, help_proc.stderr)
        self.assertNotIn("delegate", help_proc.stdout)

    def test_review_stop_without_report_exits_zero(self):
        # 审核清单只是给人看的检查单，不产生审查记录，不该被 --report 挡住。
        proc = cli(self.root, "review", self.name, "--stop", "1")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("停点 1 审核", proc.stdout)

    def test_review_record_requires_report(self):
        proc = cli(self.root, "review", self.name, "record", "--stop", "1",
                   "--author", "a", "--reviewer", "b")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("--report", proc.stderr)

    def test_review_row_alias_is_gone(self):
        self._rejected("review", self.name, "record", "--stop", "1", "--row", "1",
                       "--author", "a", "--reviewer", "b", "--report", "report/x.md")

    def test_review_confirm_flag_is_gone(self):
        self._rejected("review", self.name, "record", "--stop", "1", "--author", "a",
                       "--reviewer", "b", "--report", "report/x.md", "--confirm", "通过")

    def test_waive_confirm_flag_is_gone(self):
        self._rejected("waive", self.name, "add", "--rule", "S1", "--where", "x",
                       "--decision", "D1-001", "--confirm", "x")

    def test_problem_close_confirm_flag_is_gone(self):
        self._rejected("problem", self.name, "close", "--id", "R001",
                       "--evidence", "x", "--confirm", "x")

    def test_module_state_only_accepts_retreat(self):
        ok = cli(self.root, "module", self.name, "--row", "7", "--name", "alu",
                 "--state", "退回")
        self.assertEqual(ok.returncode, 0, ok.stderr)
        for bad in ("已生成", "lint 通过", "审查通过", "连接通过"):
            proc = cli(self.root, "module", self.name, "--row", "7", "--name", "alu",
                       "--state", bad)
            self.assertNotEqual(proc.returncode, 0, bad)
            self.assertIn("invalid choice", proc.stderr, bad)


class StatusIsReadOnlyTickTests(RepoTest):
    """status 是只读版 tick——两张清单要出现，事件与 state.json 一个字节都不许动。"""

    def test_status_lists_two_tick_lists_without_writing(self):
        name = "slimstatus"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        # 造出现实：行 1 的独立审查记录齐备但还没跑 tick（有可推进的工作）。
        review(self.root, name, 1)
        base = sys_dir(self.root, name)
        state_path = os.path.join(base, "state.json")
        events_path = os.path.join(base, "events.jsonl")

        def snapshot():
            stat = os.stat(state_path)
            with open(state_path, "rb") as fh:
                state_bytes = fh.read()
            with open(events_path, "rb") as fh:
                events_bytes = fh.read()
            return (stat.st_mtime_ns, stat.st_size, state_bytes, events_bytes)

        before = snapshot()
        proc = cli(self.root, "status", name)
        after = snapshot()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("可推进的工作：", proc.stdout)
        self.assertIn("需要开发者：", proc.stdout)
        self.assertEqual(before, after,
                         "status 必须纯读取：不写 state.json、不记事件")

    def test_status_does_not_run_the_tick_phases(self):
        # 只读的另一面：停在"进行中"的行 1 不会因为 status 被推进（tick 才会）。
        name = "slimstill"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        review(self.root, name, 1)
        from framework.state import load_state, stop_row
        before = stop_row(load_state(self.root, name), 1)["state"]
        cli(self.root, "status", name)
        self.assertEqual(stop_row(load_state(self.root, name), 1)["state"], before)
        self.assertNotEqual(before, "完成（审核通过）", "夹具前提：status 前这一行还没完成")


def load_items(root, name):
    from framework.state import load_state
    return load_state(root, name)["items"]


if __name__ == "__main__":
    unittest.main()
