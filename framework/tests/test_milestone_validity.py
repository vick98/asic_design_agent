# 作者：vick 邮箱：ykun@yk9811.com

"""里程碑有效性"需复核"与放行签核的用例。

把"需复核"的探针固化成用例：
- 里程碑确认后上游被退回、覆盖停点产物变化 → milestone_valid 派生"需复核"
  （确认记录保留，不删）；
- tick 的"需要开发者"列出"里程碑 M2 需复核（规格冻结）：变更停点 …"，不再两边
  都 continue（旧缺陷：行 6 停在送审态，里程碑行与停点行都不报）；
- "需复核"的里程碑阻塞**未启动**的下游停点（默认：不重新阻塞已启动的），
  再次 confirm 把旧的确认记录压进 history 并把覆盖停点收尾置完成；
- 需复核的上游里程碑挡 M3：M3 确认被拒并报出是哪个上游需复核；
- 需复核的里程碑 `milestone show` 只出自上次确认以来的变化（增量审阅包）。

签核文件写上确认原话在 test_tick_milestone 的 M3 用例里断言。
"""

import os
import unittest

from framework.engine import (
    EngineError, add_problem, advance, close_problem, item_end, item_open, milestone_valid,
    record_run, tick_report,
)
from framework.flow import DONE, NOT_STARTED, PENDING, RUNNING
from framework.review_pack import milestone_report
from framework.state import init_sys, load_state, save, stop_row, sys_dir
from framework.tests.util import (
    RepoTest, confirm_milestone, decide, fake_terminal, force_done, plant_sample, review,
)


class MilestoneValidityBase(RepoTest):
    def _plant(self, name):
        init_sys(self.root, name)
        plant_sample(self.root, name)

    def _walk_to(self, name, upto):
        """只用 review + tick 走到 upto（含）；行 4 前确认 M1，行 6/7 不在此用。"""
        for sid in range(1, upto + 1):
            if sid == 4:
                confirm_milestone(self.root, name, "M1")
            tick_report(self.root, name)
            review(self.root, name, sid)
            tick_report(self.root, name)

    def _midend(self, name):
        """行 11 的综合与时序运行记录（送审闸门要它）。"""
        record_run(self.root, name, {
            "capability": "synth", "status": "pass", "summary": "synth pass",
            "profile_id": "example",
            "checks": {"errors": 0, "latches": 0, "setup_wns": 0.1,
                       "setup_violations": 0, "area": 1.0},
        })
        record_run(self.root, name, {
            "capability": "sta", "status": "pass", "summary": "sta pass",
            "profile_id": "example",
            "checks": {"corners": [{"setup_wns": 0.1, "hold_wns": 0.1,
                                    "setup_violations": 0, "hold_violations": 0}]},
        })

    def _append(self, name, rel, text):
        path = os.path.join(sys_dir(self.root, name), rel)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text)


class NeedsReviewTests(MilestoneValidityBase):
    def test_m1_m2_require_pick_and_never_ask_for_terminal(self):
        """M1/M2 必须带点选来源 `pick="通过"`，否则拒绝；
        点选路径不碰交互终端（终端照抄只留给 M3）。"""
        name = "mspick1"
        self._plant(name)
        self._walk_to(name, 3)          # M1 覆盖行 1–3
        with self.assertRaises(EngineError) as ctx:
            confirm_milestone(self.root, name, "M1", pick="")
        self.assertIn("点选", str(ctx.exception))
        self.assertNotIn("M1", load_state(self.root, name).get("milestones") or {})
        with fake_terminal("不该被问") as term:
            confirm_milestone(self.root, name, "M1", pick="通过")
        self.assertEqual(0, term.calls, "M1 是点选确认，不向终端要照抄")
        self.assertIn("M1", load_state(self.root, name)["milestones"])

        name2 = "mspick2"
        self._plant(name2)
        self._walk_to(name2, 5)         # 行 4 前确认 M1、行 6 补审查记录
        review(self.root, name2, 6)
        tick_report(self.root, name2)
        with self.assertRaises(EngineError) as ctx:
            confirm_milestone(self.root, name2, "M2", pick="")
        self.assertIn("点选", str(ctx.exception))
        self.assertNotIn("M2", load_state(self.root, name2).get("milestones") or {})
        confirm_milestone(self.root, name2, "M2", pick="通过")
        self.assertIn("M2", load_state(self.root, name2)["milestones"])

    def test_upstream_revert_marks_m2_needs_review_then_reconfirm_finishes_stop6(self):
        name = "msvalid"
        self._plant(name)
        self._walk_to(name, 5)
        review(self.root, name, 6)
        tick_report(self.root, name)
        confirm_milestone(self.root, name, "M2", confirm="规格冻结通过")
        state = load_state(self.root, name)
        self.assertTrue(milestone_valid(self.root, name, state, "M2")["valid"],
                        "刚确认的 M2 应当有效")

        # 确认之后入库一条记录类裁决、收尾一条 L0 回修、关闭一条问题：
        # 三类变化都要出现在增量包里。
        item = item_open(self.root, name, "调试", "行 4 接口变更同步到 RTL 写法", side="rtl")
        item_end(self.root, name, item, "L0")
        pid = add_problem(self.root, name, "阻断", 5, "行 5 时序口径待复核")
        # 记录类直接入库，停点 3 → 阶段 2，即下面关闭问题引用的 D2-001。
        did = decide(self.root, name, "接口位宽按 L2 变更取 16 位", "记录", 3)
        self.assertEqual("D2-001", did)
        close_problem(self.root, name, pid, evidence="D2-001")

        # L2 接口变更：改行 4 的产物，退回行 4（行 5、6 被级联退回进行中）。
        self._append(name, os.path.join("spec_doc", "%s_spec.md" % name),
                     "\n补记：接口位宽按 L2 变更调整。\n")
        advance(self.root, name, 4, RUNNING)
        state = load_state(self.root, name)
        self.assertEqual(stop_row(state, 5)["state"], RUNNING)
        self.assertEqual(stop_row(state, 6)["state"], RUNNING)
        # 行 4、5 重推：产物变了，复核恢复不接（相位③按改动后的产物与新鲜审查完成），
        # 行 6 重新补审查记录后由 tick 自动送审。
        for sid in (4, 5):
            review(self.root, name, sid)
            tick_report(self.root, name)
        review(self.root, name, 6)
        tick_report(self.root, name)

        text = tick_report(self.root, name)
        human = text.split("需要开发者：", 1)[1]
        self.assertIn("里程碑 M2 需复核", human)
        self.assertIn("变更停点 4", human)
        self.assertIn("milestone %s show --id M2" % name, human)
        # 确认记录保留（审计要留），派生状态是"需复核"。
        state = load_state(self.root, name)
        self.assertIn("M2", state.get("milestones") or {})
        valid = milestone_valid(self.root, name, state, "M2")
        self.assertTrue(valid["needs_review"])
        self.assertFalse(valid["valid"])
        self.assertEqual(valid["changed"], [4, 5, 6])
        self.assertEqual(valid["status"], "需复核")

        # 增量审阅包：只列自上次确认以来的变化，不再铺开整份全量审阅包。
        pack = milestone_report(self.root, name, "M2")
        self.assertIn("增量审阅包", pack)
        self.assertIn("变更停点 4、5、6", pack)
        self.assertIn("停点 4 接口定义", pack)
        self.assertIn("自上次确认以来入库/改写的裁决", pack)
        self.assertIn("接口位宽按 L2 变更取 16 位", pack)
        self.assertIn("自上次确认以来的 L0–L3 回修", pack)
        self.assertIn(item, pack)
        self.assertIn("自上次确认以来关闭的问题", pack)
        self.assertIn("行 5 时序口径待复核", pack)
        self.assertNotIn("抽样模块规格书", pack)
        self.assertNotIn("测试要点总数与覆盖关系", pack)
        self.assertNotIn("## 闸门摘要", pack)

        # 默认口径：需复核的 M2 只阻塞未启动的行 7（已启动的停点不重新阻塞）。
        tick_report(self.root, name)
        self.assertEqual(stop_row(load_state(self.root, name), 7)["state"], NOT_STARTED)

        # 再次确认：旧记录进 history，行 6 收尾置完成，M2 重新有效，行 7 可启动。
        confirm_milestone(self.root, name, "M2", pick="通过")
        state = load_state(self.root, name)
        self.assertEqual(stop_row(state, 6)["state"], DONE, "再次确认后行 6 应完成")
        record = state["milestones"]["M2"]
        # M1/M2 凭"点选来源"授权（pick 字段）；确认原话记开发者写的备注
        # （这一次没写备注 → 缺省"点选通过"）。
        self.assertEqual(record["quote"], "点选通过")
        self.assertEqual(record["pick"], "通过")
        self.assertFalse(record["terminal"])
        self.assertTrue(record.get("history"), "旧的确认记录应进 history")
        self.assertEqual(record["history"][0]["covered"], [4, 5, 6])
        self.assertEqual(record["history"][0]["quote"], "规格冻结通过")
        self.assertTrue(record["history"][0].get("time"))
        self.assertTrue(milestone_valid(self.root, name, state, "M2")["valid"])
        tick_report(self.root, name)
        self.assertEqual(stop_row(load_state(self.root, name), 7)["state"], RUNNING)

    def test_confirmed_milestone_with_pending_covered_stop_is_listed(self):
        # 确认后被级联退回、又原样重推到送审态（指纹未变）的覆盖停点不能被
        # 两个循环同时跳过：tick 必须给出"milestone confirm 收尾"。
        name = "mspend"
        self._plant(name)
        self._walk_to(name, 5)
        review(self.root, name, 6)
        tick_report(self.root, name)
        confirm_milestone(self.root, name, "M2", confirm="规格冻结通过")
        # 把行 6 直接退回进行中，再由 tick 原样重新送审（产物未变，避免级联到其它行）。
        state = load_state(self.root, name)
        row = stop_row(state, 6)
        row["state"] = RUNNING
        row["fingerprint"] = ""
        row["done_at"] = ""
        save(self.root, name, state)
        text = tick_report(self.root, name)
        human = text.split("需要开发者：", 1)[1]
        self.assertIn("里程碑 M2 规格冻结 已确认", human)
        self.assertIn("还停在送审态", human)
        self.assertIn("milestone %s confirm --id M2" % name, human)
        state = load_state(self.root, name)
        self.assertTrue(milestone_valid(self.root, name, state, "M2")["valid"],
                        "指纹未变，M2 仍然有效")
        self.assertEqual(stop_row(state, 6)["state"], PENDING)


class M3PreconditionTests(MilestoneValidityBase):
    def _to_m3_pending(self, name):
        """行 1–6 完成（M2 已确认）、行 7–10 造完成态、行 11 由 tick 完成、行 12 由 tick 送审。

        启动与送审都归 tick——第一次 tick 启动行 11 并在同一 tick 判据齐备即完成；
        第二次 tick 启动行 12、过 signoff 闸门后置送审态（里程碑归属）。
        """
        self._plant(name)
        self._walk_to(name, 5)
        review(self.root, name, 6)
        tick_report(self.root, name)
        confirm_milestone(self.root, name, "M2", confirm="规格冻结通过")
        for sid in (7, 8, 9, 10):
            force_done(self.root, name, sid)
        self._midend(name)
        tick_report(self.root, name)
        tick_report(self.root, name)
        self.assertEqual(stop_row(load_state(self.root, name), 12)["state"], PENDING)

    def test_m3_rejected_while_m2_needs_review(self):
        name = "msm3"
        self._to_m3_pending(name)
        # 让 M2 需复核：M2 覆盖的行 4 退回重做（这里只翻状态，隔离出"上游需复核"
        # 这一条前置——产物不动，行 12 的送审摘要与其余覆盖停点都不受影响）。
        state = load_state(self.root, name)
        row = stop_row(state, 4)
        row["state"] = RUNNING
        row["fingerprint"] = ""
        row["done_at"] = ""
        save(self.root, name, state)
        state = load_state(self.root, name)
        self.assertTrue(milestone_valid(self.root, name, state, "M2")["needs_review"])
        self.assertTrue(milestone_valid(self.root, name, state, "M1")["valid"],
                        "M1 不受影响，拒绝原因必须点名 M2")
        self.assertEqual(stop_row(state, 12)["state"], PENDING)

        quote = "%s 签核放行" % name
        with fake_terminal(quote) as term:
            with self.assertRaises(EngineError) as ctx:
                confirm_milestone(self.root, name, "M3", confirm=quote)
            self.assertEqual(term.calls, 0,
                             "上游里程碑不有效就必须在机器检查阶段拒绝，先不让开发者照抄")
        message = str(ctx.exception)
        self.assertIn("M2", message)
        self.assertIn("需复核", message)
        self.assertNotIn("M3", load_state(self.root, name).get("milestones") or {})

    def test_m3_accepted_after_reviewing_m2(self):
        # 正向对照：M2 复核完成后 M3 照常放行（证明上面的拒绝只由"需复核"造成）。
        name = "msm3ok"
        self._to_m3_pending(name)
        state = load_state(self.root, name)
        stop_row(state, 4)["state"] = RUNNING
        stop_row(state, 4)["fingerprint"] = ""
        stop_row(state, 4)["done_at"] = ""
        save(self.root, name, state)
        # 行 4 原样重推（产物未变，补审查记录后 tick 自动完成）、复核 M2。
        review(self.root, name, 4)
        tick_report(self.root, name)
        self.assertEqual(stop_row(load_state(self.root, name), 4)["state"], DONE)
        confirm_milestone(self.root, name, "M2", confirm="复核通过")
        quote = "%s 签核放行" % name
        with fake_terminal(quote) as term:
            confirm_milestone(self.root, name, "M3", confirm=quote)
            self.assertEqual(term.calls, 1)
        state = load_state(self.root, name)
        for sid in range(7, 13):
            self.assertEqual(stop_row(state, sid)["state"], DONE,
                             "行 %d 应由 M3 确认置完成" % sid)


if __name__ == "__main__":
    unittest.main()
