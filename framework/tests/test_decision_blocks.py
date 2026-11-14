# 作者：vick 邮箱：ykun@yk9811.com

"""问题 --blocks 的执行语义：被决策阻塞的停点不得被 tick 自动启动/完成。"""

from framework.engine import (
    EngineError, add_problem, commit_decision, milestone_confirm, problem_defer,
    tick_report,
)
from framework.flow import DONE
from framework.state import init_sys, load_state, stop_row
from framework.tests.util import (
    RepoTest, confirm_milestone, force_done, plant_sample,
)


class DecisionBlockTests(RepoTest):
    def test_blocked_stop_is_not_auto_started_until_problem_cleared(self):
        name = "decblock"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        for sid in range(1, 5):
            force_done(self.root, name, sid)
        pid = add_problem(self.root, name, "待裁决", 5, "行 5 归属待定", "测试",
                          options="取甲|取乙", blocks="5")
        tick_report(self.root, name)
        state = load_state(self.root, name)
        self.assertNotEqual(stop_row(state, 5)["state"], DONE)
        self.assertNotEqual(stop_row(state, 5)["state"], "进行中")
        commit_decision(self.root, name, kind="方向", from_problem=pid, pick="取甲")
        tick_report(self.root, name)
        self.assertEqual(stop_row(load_state(self.root, name), 5)["state"], "进行中")

    def test_module_name_in_blocks_is_rejected(self):
        name = "decblockmod"
        init_sys(self.root, name)
        with self.assertRaises(EngineError):
            add_problem(self.root, name, "待裁决", 5, "模块级阻塞", "测试",
                        options="取甲|取乙", blocks="alu")

    def test_deferred_but_still_blocking_problem_stays_listed(self):
        name = "decblockdefer"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        for sid in range(1, 5):
            force_done(self.root, name, sid)
        pid = add_problem(self.root, name, "待裁决", 5, "行 5 归属待定", "测试",
                          options="取甲|取乙", blocks="5")
        problem_defer(self.root, name, pid, "M2", "等接口")
        text = tick_report(self.root, name)
        self.assertIn(pid, text)
        self.assertIn("推迟中", text)
        self.assertNotEqual(stop_row(load_state(self.root, name), 5)["state"], "进行中")

    def test_milestone_confirm_rejects_blocked_done_stop(self):
        name = "decblockconfirm"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        for sid in (1, 2, 3):
            force_done(self.root, name, sid)
        confirm_milestone(self.root, name, "M1")
        for sid in (4, 5, 6):
            force_done(self.root, name, sid)
        add_problem(self.root, name, "待裁决", 4, "停点 4 仍需裁决", "测试",
                    options="甲|乙", blocks="4")
        with self.assertRaises(EngineError) as ctx:
            milestone_confirm(self.root, name, "M2", pick="通过")
        self.assertIn("被决策阻塞", str(ctx.exception))

    def test_blocks_must_be_model_stop_and_is_normalized(self):
        name = "decblockid"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        for bad in ("99", "0", "alu"):
            with self.assertRaises(EngineError):
                add_problem(self.root, name, "待裁决", 5, "坏阻塞", "测试",
                            options="甲|乙", blocks=bad)
        pid = add_problem(self.root, name, "待裁决", 5, "前导零", "测试",
                          options="甲|乙", blocks="04")
        item = next(p for p in load_state(self.root, name)["problems"] if p["id"] == pid)
        self.assertEqual(item["blocks"], ["4"])

    def test_milestone_confirm_rejects_deferred_due_problem(self):
        name = "decblockdefer2"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        for sid in (1, 2, 3):
            force_done(self.root, name, sid)
        confirm_milestone(self.root, name, "M1")
        pid = add_problem(self.root, name, "待裁决", 2, "推迟到 M2", "测试",
                          options="甲|乙")
        problem_defer(self.root, name, pid, "M2", "等 M2")
        for sid in (4, 5, 6):
            force_done(self.root, name, sid)
        with self.assertRaises(EngineError) as ctx:
            milestone_confirm(self.root, name, "M2", pick="通过")
        self.assertIn("已推迟", str(ctx.exception))

    def test_milestone_confirm_rejects_open_blocking_on_done_stop(self):
        name = "decblockdone"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        for sid in (1, 2, 3):
            force_done(self.root, name, sid)
        confirm_milestone(self.root, name, "M1")
        for sid in (4, 5, 6):
            force_done(self.root, name, sid)
        add_problem(self.root, name, "阻断", 4, "已完成停点仍有阻断", "测试")
        with self.assertRaises(EngineError) as ctx:
            milestone_confirm(self.root, name, "M2", pick="通过")
        self.assertIn("未关闭阻断", str(ctx.exception))
