# 作者：vick 邮箱：ykun@yk9811.com

"""第三轮 T4、T5：人确认先查后问（令牌已删除）；撤回只标已撤回、不回队列。"""

import unittest

from framework.engine import (
    EngineError, add_problem, add_waiver, advance, close_problem, commit_decision,
    override_decision, record_run, tick_report, withdraw_decision,
)
from framework.flow import PENDING, RUNNING
from framework.state import init_sys, load_state, stop_row, sys_dir
from framework.tests.util import RepoTest, decide, plant_sample, review


class NoPromptBeforeChecksTests(RepoTest):
    """T4 收缩版：交互只剩 M3 终端照抄；红线动作（方向/数值入库）的人按是
    "点选来源"（--from/--pick 或 mark 收割）——机器检查先做完，报错也只报
    点选来源的缺失，不再有"令牌"这道检查。"""

    def _running(self, name):
        """把停点 1 交给 tick 自动启动：它没有审查记录，停在"进行中"（可带违例送审）。"""
        init_sys(self.root, name)
        plant_sample(self.root, name)
        tick_report(self.root, name)
        self.assertEqual(stop_row(load_state(self.root, name), 1)["state"], RUNNING)
        return name

    def test_advance_gate_failure_blocks_completion(self):
        # 旧断言：闸门未过时 advance(→完成) 抛 EngineError。
        # 新断言：闸门未过时 tick 不完成该停点（停在"进行中"），清单报闸门规则号。
        name = self._running("t4adv")
        from framework.tests.util import review
        review(self.root, name, 1)
        path = "%s/info_input/%s_info_overview.md" % (sys_dir(self.root, name), name)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text.replace("## 5. 红线五问", "## 6. 别的"))
        out = tick_report(self.root, name)
        self.assertIn("[S1]", out)
        self.assertEqual(stop_row(load_state(self.root, name), 1)["state"], RUNNING)

    def test_waive_unknown_decision_rejected(self):
        name = "t4waive"
        init_sys(self.root, name)
        with self.assertRaises(EngineError) as ctx:
            add_waiver(self.root, name, "S1", "info_input/x.md", "D0-999")
        self.assertIn("已入库裁决", str(ctx.exception))
        self.assertEqual(load_state(self.root, name)["waivers"], [])

    def test_close_unknown_problem_rejected(self):
        name = "t4prob"
        init_sys(self.root, name)
        with self.assertRaises(EngineError):
            close_problem(self.root, name, "I999", evidence="R001")

    def test_human_decision_needs_a_pick_source_not_a_token(self):
        """红线动作：方向/数值类没有点选来源一律拒收，报"点选来源"而不是"令牌"；
        补上 `--from/--pick` 后不带任何令牌即入库。"""
        name = "t4token"
        init_sys(self.root, name)
        with self.assertRaises(EngineError) as ctx:
            commit_decision(self.root, name, content="接受缺章节", kind="方向", stop=1)
        message = str(ctx.exception)
        self.assertIn("必须有点选来源", message)
        self.assertNotIn("令牌", message)
        self.assertEqual(load_state(self.root, name)["decisions"]["0"], [])
        # 开发者点选入库：不要令牌、不要 --confirm，问题入库即关闭。
        pid = add_problem(self.root, name, "待裁决", 1, "接受缺章节", "审查",
                          options="接受|不接受")
        did = commit_decision(self.root, name, kind="方向", from_problem=pid, pick="接受")
        self.assertEqual(did, "D0-001")
        state = load_state(self.root, name)
        row = [item for item in state["decisions"]["0"] if item["id"] == did][0]
        self.assertEqual(row["source"], "%s/接受" % pid)
        self.assertEqual(next(p for p in state["problems"] if p["id"] == pid)["evidence"],
                         did)

    def test_allow_violation_needs_decision_id(self):
        # 红线：带违例送审（保留用法：--to 已送审 --allow-violation）
        # 必须带已入库方向/数值裁决号（令牌已删除））。
        name = "t4viold"
        self._running(name)
        with self.assertRaises(EngineError) as ctx:
            advance(self.root, name, 1, PENDING, allow_violation=True)
        self.assertIn("--decision", str(ctx.exception))
        with self.assertRaises(EngineError) as ctx:
            advance(self.root, name, 1, PENDING, allow_violation=True, decision="D0-077")
        self.assertIn("不存在", str(ctx.exception))

    def test_commit_with_unknown_problem_rejected(self):
        # `--temp` 随队列删除；"来源不存在"这条不变量改在点选来源 --from 上验。
        name = "t4commit"
        init_sys(self.root, name)
        with self.assertRaises(EngineError) as ctx:
            commit_decision(self.root, name, kind="数值", from_problem="I999", pick="接受")
        self.assertIn("没有待裁决问题 I999", str(ctx.exception))
        self.assertEqual(load_state(self.root, name)["decisions"]["0"], [])

    def test_review_record_stale_lint_rejected(self):
        name = "t4rev"
        init_sys(self.root, name)
        rtl = "%s/rtl/alu.sv" % sys_dir(self.root, name)
        import os
        os.makedirs(os.path.dirname(rtl), exist_ok=True)
        with open(rtl, "w", encoding="utf-8") as fh:
            fh.write("module alu; endmodule\n")
        record_run(self.root, name, {
            "capability": "lint", "status": "pass", "summary": "lint pass", "profile_id": "p",
            "scope": {"modules": ["alu"]}, "checks": {"errors": 0},
        })
        with open(rtl, "w", encoding="utf-8") as fh:
            fh.write("module alu(input logic a); endmodule\n")
        # 报告先备好（review() 会写并顶 mtime），拒的原因必须仍是 lint 陈旧。
        with self.assertRaises(EngineError) as ctx:
            review(self.root, name, 7, module="alu")
        self.assertIn("lint", str(ctx.exception))

    def test_withdraw_unknown_decision_rejected(self):
        name = "t4wd"
        init_sys(self.root, name)
        with self.assertRaises(EngineError) as ctx:
            withdraw_decision(self.root, name, "D0-999")
        self.assertIn("没有裁决 D0-999", str(ctx.exception))


class WithdrawSemanticsTests(RepoTest):
    """T5 保留意图（T 号回流已随队列删除）：撤回只标"已撤回"保留历史，
    不再放回任何队列，D 号不回收。"""

    def test_withdraw_marks_history_and_does_not_requeue(self):
        name = "t5wd"
        init_sys(self.root, name)
        did = decide(self.root, name, "接受缺章节", "记录", 1)
        self.assertEqual(did, "D0-001")
        self.assertEqual(withdraw_decision(self.root, name, did), did)
        state = load_state(self.root, name)
        row = [item for item in state["decisions"]["0"] if item["id"] == did][0]
        self.assertTrue(row["withdrawn"])
        self.assertTrue(row["withdrawn_at"])
        self.assertNotIn("queue", state)
        self.assertNotIn("dequeued", state)
        self.assertNotIn("T", state["seq"])
        # 撤回过的不回流：下一条照常领新号。
        self.assertEqual(decide(self.root, name, "另一条不同的记录内容", "记录", 1), "D0-002")

    def test_withdrawn_decision_cannot_be_a_source_or_rewritten(self):
        # 旧 test_committing_the_old_d_id_is_rejected：D 号与问题号是两个命名空间，
        # 撤回过的裁决更不能当点选来源或 override 的对象。
        name = "t5old"
        init_sys(self.root, name)
        did = decide(self.root, name, "接受缺章节", "记录", 1)
        withdraw_decision(self.root, name, did)
        with self.assertRaises(EngineError) as ctx:
            commit_decision(self.root, name, kind="数值", from_problem=did, pick="接受")
        self.assertIn("没有待裁决问题 %s" % did, str(ctx.exception))
        with self.assertRaises(EngineError) as ctx:
            override_decision(self.root, name, did, "改写一条已撤回的裁决")
        self.assertIn("已撤回", str(ctx.exception))

    def test_record_kind_withdraw_needs_no_human(self):
        """记录类撤回仍不要人确认，也不新增令牌要求。"""
        name = "t5rec"
        init_sys(self.root, name)
        did = decide(self.root, name, "接受缺章节", "记录", 1)
        self.assertEqual(withdraw_decision(self.root, name, did), did)


if __name__ == "__main__":
    unittest.main()
