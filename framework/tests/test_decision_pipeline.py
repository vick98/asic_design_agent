# 作者：vick 邮箱：ykun@yk9811.com

"""裁决两步链路、点选来源留痕、删队列与删令牌的验收。

覆盖：
- 端到端：待裁决问题经 `commit --from --pick` → 问题关闭、D 号入库、下游级联；
- `decision list` 不再有"修改队列"，state.json 里没有 queue / seq.T；
- `marks --harvest` 按原文直接产出 D 号（来源记 mark 文件:行）；
- 无来源的方向/数值入库被拒，`--force` 也不放行；
- M1/M2 缺 `--pick 通过` 被拒，确认记录里留下点选来源；
- 没有任何放行令牌也能走完两步链路（令牌已删除）；
- 保留项：重合度守卫、记录类防夹带提示、override 修订链、withdraw 只标已撤回。
"""

import os
import unittest

from framework.engine import (
    EngineError, _decision_exists, add_problem, commit_decision, content_overlaps,
    milestone_confirm, override_decision, record_kind_hints, tick_report, withdraw_decision,
)
from framework.marks import harvest_marks, list_marks, marks_plan
from framework.state import init_sys, load_state, stop_row, sys_dir
from framework.tests.util import (
    RepoTest, confirm_milestone, decide, plant_sample, review, write_milestone_notes,
)


class TwoStepDecisionTests(RepoTest):
    def test_pick_commits_closes_problem_and_cascades(self):
        name = "s2e2e"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        # 行 1–3 先走完，好让级联有"已完成的停点"可退。
        for sid in (1, 2, 3):
            review(self.root, name, sid)
            tick_report(self.root, name)
        self.assertEqual(stop_row(load_state(self.root, name), 3)["state"], "完成（审核通过）")
        pid = add_problem(self.root, name, "待裁决", 2, "接口归属取甲还是取乙", "审查",
                          options="取甲|取乙")
        did = commit_decision(self.root, name, kind="方向", from_problem=pid, pick="取乙")
        self.assertEqual(did, "D1-001")
        state = load_state(self.root, name)
        problem = next(item for item in state["problems"] if item["id"] == pid)
        row = next(item for item in state["decisions"]["1"] if item["id"] == did)
        # 问题自动关闭，证据就是这条裁决；裁决记下点选来源与停点。
        self.assertFalse(problem["open"])
        self.assertEqual(problem["evidence"], did)
        self.assertEqual(row["source"], "%s/取乙" % pid)
        self.assertEqual(row["stop"], 2)
        self.assertEqual(row["content"], "接口归属取甲还是取乙：取乙",
                         "缺省正文带问题原文与所选项")
        # 方向类级联：该停点下游里已完成的停点退回进行中（重推）。
        self.assertEqual(stop_row(state, 3)["state"], "进行中")
        # 事件日志同时记下问题原文与所选项。
        with open(os.path.join(sys_dir(self.root, name), "events.jsonl"), encoding="utf-8") as fh:
            events = [line for line in fh if "裁决入库" in line]
        self.assertIn(pid, events[-1])
        self.assertIn("取乙", events[-1])
        self.assertIn("接口归属取甲还是取乙", events[-1])

    def test_no_source_rejected_and_force_does_not_help(self):
        name = "s3nosrc"
        init_sys(self.root, name)
        for keyword in ({}, {"force": True, "reason": "就是想绕过"}):
            with self.assertRaises(EngineError) as ctx:
                commit_decision(self.root, name, content="位宽取 12 位", kind="数值",
                                stop=2, **keyword)
            self.assertIn("必须有点选来源", str(ctx.exception))
        self.assertEqual(load_state(self.root, name)["decisions"]["1"], [])

    def test_mark_harvest_yields_decisions(self):
        name = "s3marks"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        doc = os.path.join(sys_dir(self.root, name), "spec_doc", "%s_flow.md" % name)
        with open(doc, "a", encoding="utf-8") as fh:
            fh.write("\nmark: 位宽取 12 位\n@@ 缓存用乒乓\n")
        self.assertEqual(len(list_marks(self.root, name)), 2)
        fresh, known = marks_plan(self.root, name)
        self.assertEqual((len(fresh), len(known)), (2, 0))
        done = harvest_marks(self.root, name, "数值", 2)
        self.assertEqual([did for did, _line in done], ["D1-001", "D1-002"])
        state = load_state(self.root, name)
        rows = state["decisions"]["1"]
        self.assertEqual([row["kind"] for row in rows], ["数值", "数值"])
        self.assertTrue(all(row["source"].startswith("mark:") for row in rows))
        self.assertIn("%s_flow.md" % name, rows[0]["source"])
        # 同一处只算一条：再收割一次不重复入库。
        self.assertEqual(marks_plan(self.root, name)[0], [])
        self.assertEqual(harvest_marks(self.root, name, "数值", 2), [])

    def test_decision_list_has_no_queue(self):
        name = "s2list"
        init_sys(self.root, name)
        decide(self.root, name, "流程说明：没有数字", "记录", 2)
        state = load_state(self.root, name)
        self.assertNotIn("queue", state)
        self.assertNotIn("T", state["seq"])
        from script.framework import main
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["decision", name, "list"])
        self.assertEqual(code, 0)
        text = out.getvalue()
        self.assertIn("待裁决问题", text)
        self.assertNotIn("修改队列", text)
        self.assertIn("D1-001", text)


class MilestonePickTests(RepoTest):
    def _ready_m1(self, name):
        init_sys(self.root, name)
        plant_sample(self.root, name)
        for sid in (1, 2, 3):
            review(self.root, name, sid)
            tick_report(self.root, name)

    def test_m1_needs_pick_and_records_it(self):
        name = "s3m1"
        self._ready_m1(name)
        # M1 确认前必须有 3–6 条结论摘要；缺摘要的拒绝路径另有用例，
        # 这里要测的是"缺 --pick 通过"那一条，所以先把摘要补齐。
        write_milestone_notes(self.root, name, "M1")
        with self.assertRaises(EngineError) as ctx:
            milestone_confirm(self.root, name, "M1")
        self.assertIn("--pick 通过", str(ctx.exception))
        with self.assertRaises(EngineError):
            milestone_confirm(self.root, name, "M1", pick="不通过")
        self.assertFalse(load_state(self.root, name).get("milestones"))
        confirm_milestone(self.root, name, "M1", pick="通过")
        record = load_state(self.root, name)["milestones"]["M1"]
        self.assertEqual(record["pick"], "通过")
        self.assertEqual(record["quote"], "点选通过")
        self.assertFalse(record["terminal"])


class RetainedDefencesTests(RepoTest):
    def test_overlap_guard_and_force_release(self):
        name = "s2guard"
        init_sys(self.root, name)
        text = "接口归属取甲：字节序按小端处理"
        first = decide(self.root, name, text, "方向", 2)
        self.assertTrue(first)
        with self.assertRaises(EngineError) as ctx:
            decide(self.root, name, text, "方向", 2)
        self.assertIn("重合", str(ctx.exception))
        forced = commit_decision(self.root, name, content=text + "（复核后维持）", kind="方向",
                                 source="mark:rules/decision.md:1", stop=2, force=True,
                                 reason="确属新内容")
        self.assertTrue(forced)
        self.assertTrue(content_overlaps(load_state(self.root, name), text))

    def test_record_kind_hint_still_warns(self):
        name = "s2hint"
        init_sys(self.root, name)
        self.assertTrue(record_kind_hints(self.root, name, "位宽取 16 位"))
        self.assertEqual(record_kind_hints(self.root, name, "纯文字说明"), [])

    def test_withdraw_keeps_history_without_queue(self):
        name = "s2wd"
        init_sys(self.root, name)
        did = decide(self.root, name, "接口归属取甲", "方向", 2)
        self.assertEqual(withdraw_decision(self.root, name, did), did)
        state = load_state(self.root, name)
        row = next(item for item in state["decisions"]["1"] if item["id"] == did)
        self.assertTrue(row["withdrawn"])
        self.assertNotIn("queue", state)
        # 撤回的裁决不再是有效证据。
        self.assertFalse(_decision_exists(state, did))
        with self.assertRaises(EngineError):
            withdraw_decision(self.root, name, did)

    def test_override_keeps_revision_chain(self):
        name = "s2ovr"
        init_sys(self.root, name)
        did = decide(self.root, name, "接口归属取甲", "方向", 2)
        override_decision(self.root, name, did, "接口归属取乙")
        row = next(item for item in load_state(self.root, name)["decisions"]["1"]
                   if item["id"] == did)
        self.assertEqual(row["content"], "接口归属取乙")
        self.assertEqual(row["history"][0]["content"], "接口归属取甲")


if __name__ == "__main__":
    unittest.main()
