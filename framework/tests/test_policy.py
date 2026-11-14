# 作者：vick 邮箱：ykun@yk9811.com

"""动作策略表前提校验层（framework/policy.py）的测试。

三条硬约束在这里锁住：

1. 表 → 代码：动作策略表里出现过的每个 requires 标识都必须有实现；
2. 代码 → 表：实现映射里不许有表外标识，require() 只认表里声明过的动作号；
3. 缺表不许放行：动作表里把某个强制动作的 requires 删掉（或改成别的标识）时，
   require() 必须报错，而不是恰好没有判据可跑就静默通过。

ctx 是调用方填的普通 dict，键的含义见 framework/policy.py 的模块 docstring；
这里的用例只按文档契约填键，不依赖引擎内部函数。
"""

import unittest
from unittest import mock

from framework import flow, policy


def _decision(did="D3-001", kind="方向", withdrawn=False):
    return {"id": did, "kind": kind, "withdrawn": withdrawn}


def _state(decisions=(), problems=(), items=()):
    return {"decisions": {"3": [dict(row) for row in decisions]},
            "problems": [dict(row) for row in problems],
            "items": [dict(row) for row in items]}


def _ctx(**over):
    """默认是一份"行 1 自动完成判据齐备"的空 ctx：各键都给了、内容干净。"""
    ctx = {
        "root": "/repo",
        "name": "demo",
        "state": _state(),
        "stop": 1,
        "findings": [],
        "problems": [],
        "items": [],
        "review": {"ok": True, "reason": "", "ref": "spec_review 停点 1"},
    }
    ctx.update(over)
    return ctx


class PolicyTableLockTests(unittest.TestCase):
    """动作表与实现映射的双向覆盖。"""

    def test_every_table_requires_ident_has_implementation(self):
        table = set()
        for act in flow.actions():
            table.update(act.get("requires") or [])
        implemented = set(policy.REQUIRE_CHECKS)
        self.assertEqual(table - implemented, set(),
                         "动作策略表里的前置标识没有实现：%s"
                         % "、".join(sorted(table - implemented)))
        self.assertEqual(implemented - table, set(),
                         "实现里存在动作策略表外的前置标识：%s"
                         % "、".join(sorted(implemented - table)))
        for ident, check in policy.REQUIRE_CHECKS.items():
            self.assertTrue(callable(check), "前置标识 %s 的实现不可调用" % ident)

    def test_mandatory_actions_are_in_table_and_keep_requires(self):
        table_ids = flow.action_ids()
        missing = set(policy.MANDATORY_ACTIONS) - table_ids
        self.assertEqual(missing, set(), "强制动作不在动作策略表里：%s"
                         % "、".join(sorted(missing)))
        for aid in sorted(policy.MANDATORY_ACTIONS):
            self.assertTrue(flow.requires_of(aid),
                            "动作 %s 的 requires 在动作策略表里缺失/为空" % aid)

    def test_require_rejects_action_not_in_table(self):
        for aid in ("no_such_action", "", "stop_done_autox"):
            with self.assertRaises(policy.PolicyError, msg=aid):
                policy.require(aid, _ctx())

    def test_unknown_requires_ident_is_rejected(self):
        original = flow.action

        def with_bogus(aid):
            act = original(aid)
            if act is not None and act.get("id") == "waive_add":
                act = dict(act)
                act["requires"] = ["no_such_requirement"]
            return act

        with mock.patch.object(flow, "action", with_bogus):
            with self.assertRaises(policy.PolicyError) as caught:
                policy.require("waive_add", _ctx())
        self.assertIn("no_such_requirement", str(caught.exception))

    def test_action_table_missing_requires_is_not_silently_passed(self):
        """动作表删掉 waive_add 的 requires 时，require() 必须报错（双保险之一）。

        另一道锁在 test_flow_model 的用例里：表的内容本身被断言过。这条用例模拟
        "表被改掉"的最坏情况——即使 ctx 里带了有效裁决，也不许因为无判据可跑就放行。
        """
        original = flow.action

        def stripped(aid):
            act = original(aid)
            if act is not None and act.get("id") == "waive_add":
                act = dict(act)
                act.pop("requires", None)
            return act

        valid_ctx = _ctx(state=_state(decisions=[_decision()]), decision="D3-001")
        with mock.patch.object(flow, "action", stripped):
            with self.assertRaises(policy.PolicyError) as caught:
                policy.require("waive_add", valid_ctx)
        self.assertIn("requires", str(caught.exception))

    def test_require_executes_table_not_hardcoded_action_list(self):
        """把表里 waive_add 的前提改成 gate_pass：执行的必须是表（报缺 findings），
        而不是代码里写死的 decision_exists_directional。"""
        original = flow.action

        def swapped(aid):
            act = original(aid)
            if act is not None and act.get("id") == "waive_add":
                act = dict(act)
                act["requires"] = ["gate_pass"]
            return act

        ctx = _ctx()
        ctx.pop("findings")
        with mock.patch.object(flow, "action", swapped):
            with self.assertRaises(policy.PolicyError) as caught:
                policy.require("waive_add", ctx)
        self.assertIn("findings", str(caught.exception))


class WaiveAddTests(unittest.TestCase):
    """豁免动作：必须引用已入库的方向/数值类裁决。"""

    def _ctx(self, **over):
        return _ctx(**over)

    def test_without_decision_raises(self):
        with self.assertRaises(policy.PolicyError) as caught:
            policy.require("waive_add", self._ctx())
        self.assertIn("裁决", str(caught.exception))

    def test_with_valid_directional_decision_passes(self):
        policy.require("waive_add", self._ctx(
            state=_state(decisions=[_decision()]), decision="D3-001"))

    def test_with_numeric_decision_passes(self):
        policy.require("waive_add", self._ctx(
            state=_state(decisions=[_decision(kind="数值")]), decision="D3-001"))

    def test_with_record_decision_raises(self):
        with self.assertRaises(policy.PolicyError):
            policy.require("waive_add", self._ctx(
                state=_state(decisions=[_decision(kind="记录")]), decision="D3-001"))

    def test_with_withdrawn_decision_raises(self):
        with self.assertRaises(policy.PolicyError):
            policy.require("waive_add", self._ctx(
                state=_state(decisions=[_decision(withdrawn=True)]), decision="D3-001"))

    def test_with_unknown_decision_raises(self):
        with self.assertRaises(policy.PolicyError):
            policy.require("waive_add", self._ctx(
                state=_state(decisions=[_decision()]), decision="D3-999"))

    def test_missing_state_key_fails_closed(self):
        ctx = self._ctx(decision="D3-001")
        ctx.pop("state")
        with self.assertRaises(policy.PolicyError):
            policy.require("waive_add", ctx)


class ReviewRecordTests(unittest.TestCase):
    """审查记录动作：作者≠审查者、阻断发现为 0。"""

    def test_clean_record_passes(self):
        policy.require("review_record", _ctx(author="author-01", reviewer="reviewer-02",
                                             findings_count=3, blocking=0))

    def test_same_author_and_reviewer_raises(self):
        with self.assertRaises(policy.PolicyError):
            policy.require("review_record", _ctx(author="same-01", reviewer="same-01",
                                                 findings_count=0, blocking=0))

    def test_blocking_findings_raise(self):
        with self.assertRaises(policy.PolicyError):
            policy.require("review_record", _ctx(author="author-01", reviewer="reviewer-02",
                                                 findings_count=2, blocking=1))

    def test_missing_blocking_count_fails_closed(self):
        with self.assertRaises(policy.PolicyError):
            policy.require("review_record", _ctx(author="author-01", reviewer="reviewer-02"))

    def test_findings_count_is_optional(self):
        policy.require("review_record", _ctx(author="author-01", reviewer="reviewer-02",
                                             blocking=0))

    def test_negative_findings_count_raises(self):
        with self.assertRaises(policy.PolicyError):
            policy.require("review_record", _ctx(author="author-01", reviewer="reviewer-02",
                                                 findings_count=-1, blocking=0))

    def test_invalid_findings_count_raises(self):
        with self.assertRaises(policy.PolicyError):
            policy.require("review_record", _ctx(author="author-01", reviewer="reviewer-02",
                                                 findings_count="三", blocking=0))


class StopDoneAutoTests(unittest.TestCase):
    """自动完成动作的四条前提：闸门、无未关闭阻断、无在途事项、有独立审查记录。"""

    def test_all_criteria_met_passes(self):
        policy.require("stop_done_auto", _ctx())

    def test_blocking_gate_finding_raises(self):
        with self.assertRaises(policy.PolicyError):
            policy.require("stop_done_auto", _ctx(
                findings=[{"rule": "docs", "level": "error", "detail": "缺章节"}]))

    def test_hint_only_findings_pass(self):
        policy.require("stop_done_auto", _ctx(
            findings=[{"rule": "numeric", "level": "hint", "detail": "提示"}]))

    def test_gate_pass_boolean_is_accepted(self):
        ctx = _ctx()
        ctx.pop("findings")
        policy.require("stop_done_auto", dict(ctx, gate_pass=True))
        with self.assertRaises(policy.PolicyError):
            policy.require("stop_done_auto", dict(ctx, gate_pass=False))

    def test_missing_gate_verdict_fails_closed(self):
        ctx = _ctx()
        ctx.pop("findings")
        with self.assertRaises(policy.PolicyError):
            policy.require("stop_done_auto", ctx)

    def test_null_gate_findings_fail_closed(self):
        with self.assertRaises(policy.PolicyError):
            policy.require("stop_done_auto", _ctx(findings=None))

    def test_open_blocking_problem_raises(self):
        with self.assertRaises(policy.PolicyError):
            policy.require("stop_done_auto", _ctx(
                stop=7, problems=[{"id": "I001", "kind": "阻断", "stop": 7, "open": True}]))

    def test_closed_blocking_problem_passes(self):
        policy.require("stop_done_auto", _ctx(
            stop=7, problems=[{"id": "I001", "kind": "阻断", "stop": 7, "open": False}]))

    def test_later_stop_blocking_problem_does_not_block(self):
        policy.require("stop_done_auto", _ctx(
            stop=3, problems=[{"id": "I001", "kind": "阻断", "stop": 7, "open": True}]))

    def test_pending_item_blocks_stop_in_scope(self):
        with self.assertRaises(policy.PolicyError):
            policy.require("stop_done_auto", _ctx(
                stop=7, items=[{"id": "M001", "kind": "调试"}]))

    def test_pending_item_does_not_block_stop_out_of_scope(self):
        policy.require("stop_done_auto", _ctx(
            stop=1, items=[{"id": "M001", "kind": "调试"}]))

    def test_missing_review_record_raises(self):
        ctx = _ctx()
        ctx.pop("review")
        with self.assertRaises(policy.PolicyError):
            policy.require("stop_done_auto", ctx)

    def test_failed_review_record_raises(self):
        with self.assertRaises(policy.PolicyError):
            policy.require("stop_done_auto", _ctx(
                review={"ok": False, "reason": "缺审查记录", "ref": ""}))


class ProblemCloseTests(unittest.TestCase):
    """关闭问题动作：证据存在且严格晚于问题登记。"""

    def _problem(self, **over):
        row = {"id": "I001", "kind": "阻断", "stop": 3, "open": True,
               "time": "2026-01-02 10:00:00", "registered_seq": 5}
        row.update(over)
        return row

    def _evidence(self, **over):
        row = {"ref": "R001", "exists": True, "seq": 6, "time": "2026-01-02 10:00:01"}
        row.update(over)
        return row

    def test_later_evidence_passes(self):
        policy.require("problem_close", _ctx(problem=self._problem(),
                                             evidence=self._evidence()))

    def test_evidence_same_seq_raises(self):
        with self.assertRaises(policy.PolicyError):
            policy.require("problem_close", _ctx(problem=self._problem(),
                                                 evidence=self._evidence(seq=5)))

    def test_evidence_earlier_seq_raises(self):
        with self.assertRaises(policy.PolicyError):
            policy.require("problem_close", _ctx(problem=self._problem(),
                                                 evidence=self._evidence(seq=4)))

    def test_missing_evidence_seq_raises(self):
        with self.assertRaises(policy.PolicyError):
            policy.require("problem_close", _ctx(problem=self._problem(),
                                                 evidence=self._evidence(seq=None)))

    def test_unknown_evidence_raises(self):
        with self.assertRaises(policy.PolicyError):
            policy.require("problem_close", _ctx(problem=self._problem(),
                                                 evidence=self._evidence(exists=False)))

    def test_problem_without_registered_seq_raises(self):
        with self.assertRaises(policy.PolicyError):
            policy.require("problem_close", _ctx(problem=self._problem(registered_seq=None),
                                                 evidence=self._evidence()))

    def test_evidence_time_earlier_than_problem_raises(self):
        with self.assertRaises(policy.PolicyError):
            policy.require("problem_close", _ctx(
                problem=self._problem(time="2026-01-02 10:00:00"),
                evidence=self._evidence(seq=6, time="2026-01-02 09:59:59")))

    def test_problem_resolved_from_problems_list(self):
        policy.require("problem_close", _ctx(
            problems=[self._problem()], problem_id="I001", evidence=self._evidence()))


class RedlineSourceTests(unittest.TestCase):
    """红线动作：必须有点选来源或已入库裁决号；记录类动作不要求。"""

    SOURCES = {
        "decision_directional": {"pick": "取甲"},
        "problem_close_tradeoff": {"decision": "D3-001"},
        "allow_violation": {"decision": "D3-001"},
        "cov_threshold_down": {"decision": "D3-001"},
        "milestone_confirm": {"confirm": "开发者原话"},
        "flow_policy_change": {"decision": "D3-001"},
    }

    def test_every_redline_action_has_a_source_case(self):
        table = {act["id"] for act in flow.actions_by_class("redline")}
        self.assertEqual(set(self.SOURCES) - table, set(),
                         "红线动作表里有动作没覆盖来源用例：%s"
                         % "、".join(sorted(set(self.SOURCES) - table)))

    def test_redline_actions_reject_missing_source(self):
        for act in flow.actions_by_class("redline"):
            with self.assertRaises(policy.PolicyError, msg=act["id"]):
                policy.require(act["id"], _ctx(state=_state()))

    def test_redline_actions_accept_their_source(self):
        for aid, source in self.SOURCES.items():
            ctx = _ctx(state=_state(decisions=[_decision()]))
            ctx.update(source)
            policy.require(aid, ctx)

    def test_pick_from_problem_passes(self):
        policy.require("decision_directional", _ctx(
            state=_state(problems=[{"id": "I001", "open": True}]),
            from_problem="I001", pick="取甲"))

    def test_from_problem_without_pick_raises(self):
        with self.assertRaises(policy.PolicyError):
            policy.require("decision_directional", _ctx(
                state=_state(problems=[{"id": "I001", "open": True}]),
                from_problem="I001"))

    def test_from_problem_unknown_raises(self):
        with self.assertRaises(policy.PolicyError):
            policy.require("decision_directional", _ctx(
                state=_state(), from_problem="I999", pick="取甲"))

    def test_from_problem_closed_raises(self):
        with self.assertRaises(policy.PolicyError):
            policy.require("decision_directional", _ctx(
                state=_state(problems=[{"id": "I001", "open": False}]),
                from_problem="I001", pick="取甲"))

    def test_withdrawn_decision_as_source_raises(self):
        with self.assertRaises(policy.PolicyError):
            policy.require("problem_close_tradeoff", _ctx(
                state=_state(decisions=[_decision(withdrawn=True)]),
                decision="D3-001"))

    def test_record_action_does_not_require_source(self):
        policy.require("decision_record", _ctx(state=_state()))

    def test_no_requires_auto_action_passes(self):
        policy.require("git_snapshot", {"state": _state()})


class PolicyImportBoundaryTests(unittest.TestCase):
    """policy 不得 import engine（引擎之后 import policy，反过来会成环）。"""

    def test_policy_does_not_import_engine(self):
        import ast
        import os
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "policy.py")
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
        self.assertNotIn("framework.engine", imported,
                         "policy 不得 import engine（引擎之后 import policy，会成环）")


if __name__ == "__main__":
    unittest.main()
