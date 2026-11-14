# 作者：vick 邮箱：ykun@yk9811.com

"""引擎入口按动作策略表执行前提（framework/policy.require）的接线测试。

锁定三件事：

1. 各引擎入口真的走动作表：monkeypatch policy.require 记录动作号，入口调用必须出现在
   记录里（entry 与表的对应关系由策略表决定，引擎不再各写一套）；
2. 表内容被改坏时引擎拒绝执行：副本里删掉动作的前提，引擎入口必须报错/判据不通过，
   加回后恢复——这是"动作表是唯一事实源"的行为验收；
3. 自动完成判据仍返回展示用 reasons（执行层不通过时退回原因，不抛异常打断 tick/status）。
"""

import os
import unittest
from unittest import mock

from framework import engine, policy
from framework.engine import (
    EngineError, add_problem, add_waiver, auto_complete_check, close_problem,
    commit_decision, milestone_confirm, record_run, review_record, tick_report,
)
from framework.state import init_sys, load_state
from framework.tests.util import (
    RepoTest, decide, plant_sample, review, write_milestone_notes,
)

MODEL_PATH = os.path.join("framework", "flow_model.yaml")

WAIVE_REQUIRES = "    requires: [decision_exists_directional]\n"

# stop_done_auto 的完整表项（改表用）：删的是 requires 那一行，其余字段保持合法。
AUTO_REQUIRES = ("    requires: [gate_pass, no_blocking, no_open_item, review_record]\n")


def _read_model(root):
    with open(os.path.join(root, MODEL_PATH), encoding="utf-8") as fh:
        return fh.read()


def _write_model(root, text):
    with open(os.path.join(root, MODEL_PATH), "w", encoding="utf-8") as fh:
        fh.write(text)


class EnginePolicyWiringTests(RepoTest):
    """入口 → 动作号 的覆盖：每个接线的执行入口都必须经过 policy.require。"""

    def _spy(self):
        original = policy.require
        calls = []

        def wrapper(action_id, ctx):
            calls.append(action_id)
            return original(action_id, ctx)

        return calls, mock.patch.object(policy, "require", wrapper)

    def test_engine_entries_are_table_driven(self):
        name = "wirecall"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        calls, patcher = self._spy()
        with patcher:
            # 自动完成判据（stop_done_auto）
            auto_complete_check(self.root, name, load_state(self.root, name), 1)
            # 方向/数值裁决入库（decision_directional）
            did = decide(self.root, name, "接受缺章节", "方向", 1)
            # 豁免（waive_add）
            add_waiver(self.root, name, "S1", "info_input/x.md", did)
            # 审查记录（review_record）
            review(self.root, name, 1)
            # 关闭阻断问题（problem_close）
            pid = add_problem(self.root, name, "阻断", 1, "缺时钟", "复核")
            rid = record_run(self.root, name, {
                "capability": "sim", "status": "pass", "summary": "smoke pass",
                "profile_id": "p",
            })
            close_problem(self.root, name, pid, evidence=rid)
            # 关闭需要取舍的问题（problem_close_tradeoff + problem_close）
            trade = add_problem(self.root, name, "待裁决", 1, "取哪一档", "复核",
                                options="甲|乙")
            trade_did = decide(self.root, name, "取甲这一档", "方向", 1)
            close_problem(self.root, name, trade, evidence=trade_did)
            # 无来源的方向类入库被表拦住（decision_directional）
            with self.assertRaises(EngineError):
                commit_decision(self.root, name, content="位宽取 8", kind="数值", stop=1)
            # 带违例送审的裁决号校验（allow_violation）
            with self.assertRaises(EngineError):
                engine._require_violation_decision(load_state(self.root, name), "D0-999")
        expected = {
            "stop_done_auto", "decision_directional", "waive_add", "review_record",
            "problem_close", "problem_close_tradeoff", "allow_violation",
        }
        missing = expected - set(calls)
        self.assertEqual(missing, set(), "这些入口没有经过动作策略表：%s"
                         % "、".join(sorted(missing)))

    def test_milestone_confirm_is_table_driven(self):
        name = "wirems"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        for sid in (1, 2, 3):
            review(self.root, name, sid)
            tick_report(self.root, name)
        write_milestone_notes(self.root, name, "M1")
        calls, patcher = self._spy()
        with patcher:
            milestone_confirm(self.root, name, "M1", pick="通过")
        self.assertIn("milestone_confirm", calls,
                      "里程碑确认没有经过动作策略表（红线来源没有统一执行）")


class EngineFollowsTableContentTests(RepoTest):
    """表内容改变时引擎行为随之改变：删前提必须变红，加回必须变绿。"""

    def test_waiver_requires_removed_then_restored(self):
        name = "waivereq"
        init_sys(self.root, name)
        did = decide(self.root, name, "接受缺章节", "方向", 1)
        add_waiver(self.root, name, "S1", "info_input/x.md", did)   # 表完整：通过
        text = _read_model(self.root)
        stripped = text.replace(WAIVE_REQUIRES, "")
        self.assertNotEqual(stripped, text, "没有定位到 waive_add 的 requires 行")
        _write_model(self.root, stripped)
        try:
            with self.assertRaises(EngineError) as caught:
                add_waiver(self.root, name, "S1", "info_input/y.md", did)
            self.assertIn("requires", str(caught.exception),
                          "删掉表里的前提后引擎没有拒绝，而是静默放行")
        finally:
            _write_model(self.root, text)
        add_waiver(self.root, name, "S1", "info_input/z.md", did)   # 加回：恢复通过

    def test_auto_complete_fails_closed_when_requires_removed(self):
        name = "autoreq"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        review(self.root, name, 1)
        state = load_state(self.root, name)
        self.assertTrue(auto_complete_check(self.root, name, state, 1)["ok"])
        text = _read_model(self.root)
        stripped = text.replace(AUTO_REQUIRES, "")
        self.assertNotEqual(stripped, text, "没有定位到 stop_done_auto 的 requires 行")
        _write_model(self.root, stripped)
        try:
            check = auto_complete_check(self.root, name, load_state(self.root, name), 1)
            self.assertFalse(check["ok"], "删掉表里的前提后自动完成仍放行")
            self.assertTrue(any("requires" in reason for reason in check["reasons"]),
                            "执行层拒绝的原因没有回到展示用 reasons：%s" % check["reasons"])
        finally:
            _write_model(self.root, text)
        check = auto_complete_check(self.root, name, load_state(self.root, name), 1)
        self.assertTrue(check["ok"], check)


class EnginePolicyErrorConversionTests(RepoTest):
    """policy.PolicyError 在引擎边界统一转成 EngineError；入口不向上暴露第三方异常。"""

    def test_policy_error_becomes_engine_error(self):
        name = "errconv"
        init_sys(self.root, name)
        with self.assertRaises(EngineError) as caught:
            add_waiver(self.root, name, "S1", "info_input/x.md", "D0-999")
        self.assertNotIsInstance(caught.exception, policy.PolicyError)
        self.assertIn("D0-999", str(caught.exception))
        self.assertEqual(load_state(self.root, name)["waivers"], [])

    def test_bare_pick_is_not_a_decision_source(self):
        # 方向/数值类入库的"点选来源"只有 --from/--pick 或 mark 收割；裸 --pick 不是来源。
        name = "barepick"
        init_sys(self.root, name)
        with self.assertRaises(EngineError) as caught:
            commit_decision(self.root, name, content="位宽取 8", kind="数值", stop=1,
                            pick="随便点一下")
        self.assertIn("必须有点选来源", str(caught.exception))
        self.assertEqual(load_state(self.root, name)["decisions"]["0"], [])

    def test_review_record_uses_parsed_findings_and_blocking(self):
        # 报告表解析出的计数就是动作前提的输入：无阻断 → 通过；阻断 → 拒绝。
        name = "revcount"
        init_sys(self.root, name)
        from framework.tests.util import AUTHOR, REVIEWER, write_report
        rel = write_report(self.root, name, 1)
        review_record(self.root, name, 1, author=AUTHOR, reviewer=REVIEWER, report=rel)
        unresolved = write_report(
            self.root, name, 1,
            report=("# 行 1 独立审查报告\n\n"
                    "| 发现编号 | 级别 | 位置 | 建议 | 处置 |\n"
                    "|---|---|---|---|---|\n"
                    "| F1 | 阻断 | 第 5 章 | 缺时钟域 | 待改 |\n"))
        with self.assertRaises(EngineError) as caught:
            review_record(self.root, name, 1, author=AUTHOR, reviewer=REVIEWER,
                          report=unresolved)
        self.assertIn("阻断", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
