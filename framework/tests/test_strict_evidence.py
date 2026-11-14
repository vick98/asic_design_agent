# 作者：vick 邮箱：ykun@yk9811.com

"""对抗式验收指出的覆盖缺口补测。

本文件验收的需求条目与缺陷修复：
- 启动前置按 depends_on：行 12 的依赖是 [10, 11]——缺任何一个都不得启动；
  依赖停点属里程碑完成型（行 6/11/12）且已送审（状态名"已送审"）即算定稿，可以启动
  （engine._previous_done 的死锁修复前提：行 11 送审后行 12 必须起得来）。
- 证据严格"晚于"：问题登记时落登记序号 registered_seq（自己的"问题登记"事件的
  单调 seq）；证据能定位到事件 seq 时要求 证据 seq > registered_seq（严格大于，
  同一秒内登记之前的证据蒙混不过）；定位不到 seq（登记早于本机制、证据事件不在
  日志里）退回时间串"不早于"并留痕（"事件 seq 不可定位，按时间串（不早于）兜底判定"）。
- 不变量"判定看 RESULT 不看退出码"（反向用例）：退出码 0 但 RESULT 为 FAIL 判 fail。
- 不变量"编号只增不复用"：撤回只标已撤回（历史保留），重新入库领严格更大的新号。
- 不变量"检查顺序"（T4，反向用例）：M3 照抄原话不一致必须拒，且拒绝发生在
  机器检查（覆盖停点就绪、判据、送审摘要）之后的照抄环节（fake_terminal.calls == 1）。
- 不变量"退回与级联清掉确认痕迹"的姊妹口径：`item <sys> end` 不改任何停点
  状态与确认痕迹、不影响其它在途事项（补回 test_item_gating 改写中丢掉的不变性断言）。
"""

import contextlib
import importlib.util
import json
import os
import shutil
import unittest

from framework.engine import (
    EngineError, _decision_exists, _event_seq, _previous_done, add_problem, close_problem,
    commit_decision, item_end, item_open, milestone_confirm, record_run,
    tick_report, withdraw_decision,
)
from framework.flow import PENDING
from framework.profile_run import judge, load_profile
from framework.state import init_sys, load_state, save, stop_row
from framework.tests.util import (
    RepoTest, confirm_milestone, decide, fake_terminal, force_done,
    plant_sample, review,
)


def _frozen_now(value="2026-01-01 10:00:00"):
    """把 engine.now 冻结到同一秒：时间维度全部打平后，证据晚于登记的判定只剩
    事件 seq 一个变量——同一秒内"登记之前"的证据只有 seq 口径拦得住。"""
    return _patch(engine_module_attr="now", value=value)


@contextlib.contextmanager
def _patch(engine_module_attr, value):
    import framework.engine as eng
    saved = getattr(eng, engine_module_attr)
    setattr(eng, engine_module_attr, lambda *args, **kwargs: value)
    try:
        yield
    finally:
        setattr(eng, engine_module_attr, saved)


def _events(root, name):
    """events.jsonl 全文为 [(1-based 行号, 事件 dict)]。"""
    path = os.path.join(root, name, "events.jsonl")
    with open(path, encoding="utf-8") as fh:
        return [(lineno, json.loads(line))
                for lineno, line in enumerate(fh, 1) if line.strip()]


def _relocate_tb(root, name):
    """把 mini 夹具的 testbench/tc（旧布局，平台名"tb"）搬到 testbench/<dut>/tc。

    行 9 平台清单按 testbench/<平台>/tc 推导、通过态由平台目录名交给
    gates.tc.platform_state 推导；platform_state 只认 testbench/<平台名> 这一种路径，
    旧布局 testbench/tc 的"tb"名解析不到目录（会恒判"未开始"）。搬到 <dut>/tc 后
    行 9 完全靠文件与用例核对过闸门，不再需要手工登记 modules[9]。
    """
    tb = os.path.join(root, name, "testbench")
    src = os.path.join(tb, "tc")
    if os.path.isdir(src):
        dst = os.path.join(tb, name, "tc")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)


def _load_driver(root, filename):
    path = os.path.join(root, "toolchain", "profiles", "example",
                        "drivers", filename)
    spec = importlib.util.spec_from_file_location("drv_" + filename[:-3], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _lint(root, name, modules):
    return record_run(root, name, {
        "capability": "lint", "status": "pass", "summary": "lint pass",
        "profile_id": "example", "scope": {"modules": list(modules)},
        "checks": {"errors": 0},
    })


def _sim(root, name):
    return record_run(root, name, {
        "capability": "sim", "status": "pass", "summary": "RESULT : PASS",
        "profile_id": "example",
        "scope": {"scenario": "sys", "module": "", "tc": "", "seeds": ["1"]},
        "checks": {"result_pass": 1, "result_fail": 0, "full_regression": 1},
    })


def _coverage(root, name):
    return record_run(root, name, {
        "capability": "coverage", "status": "pass", "summary": "coverage pass",
        "profile_id": "example",
        "checks": {"line": 100.0, "cond": 100.0, "fsm": 100.0, "tgl": 100.0},
    })


def _midend(root, name):
    record_run(root, name, {
        "capability": "synth", "status": "pass", "summary": "synth pass",
        "profile_id": "example",
        "checks": {"errors": 0, "latches": 0, "setup_wns": 0.1,
                   "setup_violations": 0, "area": 1.0},
    })
    record_run(root, name, {
        "capability": "sta", "status": "pass", "summary": "sta pass",
        "profile_id": "example",
        "checks": {"corners": [{"setup_wns": 0.1, "hold_wns": 0.1,
                                "setup_violations": 0, "hold_violations": 0}]},
    })


class DependsOnStartTests(RepoTest):
    """启动前置按 flow_model.yaml 的 depends_on 全集检查。"""

    def test_stop12_blocked_by_undone_dep(self):
        # 行 12 depends_on [10, 11]：行 10 未完成 → tick 不会启动它；
        # 依赖检查要点名缺失的依赖（不能再按旧口径写死"上一行 11"）。
        name = "depmissing"
        init_sys(self.root, name)
        force_done(self.root, name, 11)
        tick_report(self.root, name)
        state = load_state(self.root, name)
        self.assertEqual(stop_row(state, 12)["state"], "未开始")
        self.assertEqual(_previous_done(state, 12), [10],
                         "行 12 只缺行 10：depends_on 全集检查，不是写死的上一行")

    def test_stop12_starts_with_milestone_pending_dep(self):
        # 死锁修复前提：行 10 已完成、行 11 属里程碑完成型（行 6/11/12）且已送审
        # → 行 11 已算定稿，行 12 必须能启动；否则行 12 起不来、
        # M3 确认不了、行 11 也完不成（M3 覆盖行 7–12 要求覆盖停点已送审）。
        name = "depmstone"
        init_sys(self.root, name)
        force_done(self.root, name, 7)
        force_done(self.root, name, 8)
        force_done(self.root, name, 10)
        tick_report(self.root, name)      # 行 11 依赖 7、8 已定稿 → 自动启动
        self.assertEqual(stop_row(load_state(self.root, name), 11)["state"], "进行中")
        _midend(self.root, name)
        # 行 11 判据齐备 → 自动送审；同一 tick 的下一轮行 12 依赖 10 完成、11 已送审
        # → 在同一 tick 里自动启动并送审（同一事务内连续推进）。
        text = tick_report(self.root, name)
        self.assertEqual(stop_row(load_state(self.root, name), 11)["state"], PENDING)
        self.assertEqual(stop_row(load_state(self.root, name), 12)["state"], PENDING)
        self.assertIn("自动送审停点 11、12", text)


class StrictEvidenceTests(RepoTest):
    """判定严格"晚于"：证据事件 seq 必须大于问题登记 seq（去行号补丁）。"""

    def test_decision_before_registration_rejected(self):
        name = "evdec"
        init_sys(self.root, name)
        with _frozen_now():
            did = commit_decision(self.root, name, content="接口归属取甲", kind="记录", stop=1)
            pid = add_problem(self.root, name, "阻断", 1, "接口归属未定", "审查")
            with self.assertRaises(EngineError) as ctx:
                close_problem(self.root, name, pid, evidence=did)
        # 同一秒内时间完全打平，只有登记序号口径拦得住登记之前的裁决。
        self.assertIn("严格晚于", str(ctx.exception), str(ctx.exception))
        self.assertTrue(load_state(self.root, name)["problems"][0]["open"])

    def test_same_second_run_before_registration_rejected(self):
        name = "evrun"
        init_sys(self.root, name)
        with _frozen_now():
            rid = record_run(self.root, name, {
                "capability": "sim", "status": "pass", "summary": "smoke pass",
            })
            pid = add_problem(self.root, name, "阻断", 1, "缺时钟", "审查")
            with self.assertRaises(EngineError) as ctx:
                close_problem(self.root, name, pid, evidence=rid)
        self.assertIn("严格晚于", str(ctx.exception), str(ctx.exception))
        self.assertTrue(load_state(self.root, name)["problems"][0]["open"])

    def test_same_second_evidence_ordering_uses_seq_not_time(self):
        """同一秒内登记与证据：顺序只由事件 seq 决定。

        时间串完全相同（engine.now 冻结到秒级同一值）时，登记**之前**入库的证据
        必须被拒、登记**之后**立刻产生的证据必须放行——两个方向都只有 seq 分得开。
        """
        name = "evsec"
        init_sys(self.root, name)
        with _frozen_now("2026-01-01 10:00:00"):
            early = record_run(self.root, name, {
                "capability": "sim", "status": "pass", "summary": "smoke pass",
            })
            pid = add_problem(self.root, name, "阻断", 1, "缺时钟", "审查")
            with self.assertRaises(EngineError) as ctx:
                close_problem(self.root, name, pid, evidence=early)
            self.assertIn("严格晚于", str(ctx.exception), str(ctx.exception))
            rid = record_run(self.root, name, {
                "capability": "sim", "status": "pass", "summary": "smoke pass",
            })
            self.assertEqual(pid, close_problem(self.root, name, pid, evidence=rid))
        state = load_state(self.root, name)
        problem = next(p for p in state["problems"] if p["id"] == pid)
        runs = {run["id"]: run for run in state["runs"]}
        # 登记与证据的时间串一模一样：判定只能来自 seq。
        self.assertEqual(runs[early]["time"], problem["time"])
        self.assertEqual(runs[rid]["time"], problem["time"])
        reg = _event_seq(self.root, name, "问题登记", pid)
        self.assertEqual(problem["registered_seq"], reg)
        self.assertLess(_event_seq(self.root, name, "运行记录", early), reg)
        self.assertGreater(_event_seq(self.root, name, "运行记录", rid), reg)
        self.assertFalse(problem["open"])

    def test_post_registration_evidence_closes(self):
        name = "evok"
        init_sys(self.root, name)
        # ① 运行记录：登记之后的 R 号可以关闭，返回值不带兜底字样。
        pid_run = add_problem(self.root, name, "阻断", 1, "缺时钟", "审查")
        rid = record_run(self.root, name, {
            "capability": "sim", "status": "pass", "summary": "smoke pass",
        })
        self.assertEqual(close_problem(self.root, name, pid_run, evidence=rid), pid_run)
        # ② 裁决：登记之后入库的 D 号可以关闭。
        pid_dec = add_problem(self.root, name, "阻断", 1, "口径未定", "审查")
        did = commit_decision(self.root, name, content="口径取甲", kind="记录", stop=1)
        close_problem(self.root, name, pid_dec, evidence=did)
        # ③ 审查记录：登记之后的 review:1 可以关闭。
        pid_rev = add_problem(self.root, name, "阻断", 1, "复核未过", "审查")
        # 审查记录要带 report/<文件>.md，用 review() 一步写报告再登记（作者≠审查者
        # 由 util 的 AUTHOR/REVIEWER 常量给出）。
        review(self.root, name, 1)
        close_problem(self.root, name, pid_rev, evidence="review:1")
        state = load_state(self.root, name)
        for pid in (pid_run, pid_dec, pid_rev):
            row = next(p for p in state["problems"] if p["id"] == pid)
            self.assertFalse(row["open"], pid)
            # 登记序号落进了 state.json（可正常序列化、可回读），且与"问题登记"
            # 事件自己的 seq 一致。
            self.assertIsInstance(row.get("registered_seq"), int, pid)
            self.assertGreaterEqual(row["registered_seq"], 1, pid)
            reg = _event_seq(self.root, name, "问题登记", pid)
            self.assertEqual(row["registered_seq"], reg, pid)
            # 证据事件 seq 确实严格大于登记 seq（不是靠时间口径过的）。
            if pid == pid_run:
                ev = _event_seq(self.root, name, "运行记录", rid)
            elif pid == pid_dec:
                ev = _event_seq(self.root, name, "裁决入库", did)
            else:
                ev = _event_seq(self.root, name, "审查记录", "停点 1")
            self.assertGreater(ev, reg, pid)

    def test_historical_problem_without_registered_seq_still_judged_by_seq(self):
        # DEV-02：时间串兜底删净——历史问题（没有 registered_seq 字段）的登记 seq
        # 从它自己的"问题登记"事件取（事件 seq 由迁移回填），判定仍是"严格晚于"。
        name = "evfall"
        init_sys(self.root, name)
        with _frozen_now():
            early = commit_decision(self.root, name, content="接口归属取甲", kind="记录", stop=1)
            pid = add_problem(self.root, name, "阻断", 1, "缺时钟", "审查")
            rid = record_run(self.root, name, {
                "capability": "sim", "status": "pass", "summary": "smoke pass",
            })
        state = load_state(self.root, name)
        next(p for p in state["problems"] if p["id"] == pid).pop("registered_seq")
        save(self.root, name, state)
        # 登记之前入库的证据：同一秒也不能蒙混（只比 seq）。
        with self.assertRaises(EngineError) as ctx:
            close_problem(self.root, name, pid, evidence=early)
        self.assertIn("不晚于问题", str(ctx.exception))
        # 登记之后的证据照样能关。
        self.assertEqual(close_problem(self.root, name, pid, evidence=rid), pid)
        self.assertFalse(next(p for p in load_state(self.root, name)["problems"]
                              if p["id"] == pid)["open"])


class JudgeResultTests(RepoTest):
    """不变量（反向用例）：判定看 RESULT 不看退出码。"""

    def test_sim_judge_uses_result_not_exit_code(self):
        profile = load_profile()
        drv = _load_driver(self.root, "sim.py")
        # 退出码 0 的进程（本平台 VCS 退出码恒 0，$finish 不映射退出码）也打得出
        # FAIL 汇总行：无 SEED_CRASH、无超时、无编译错，只有 RESULT : FAIL——
        # 必须判 fail，不能因"进程正常退出"判 pass。
        checks = drv.parse("sim", "SEED_RESULT seed=1 pass=0 fail=1\nRESULT : FAIL\n", "")
        self.assertEqual(checks.get("sim_crash"), 0, checks)
        self.assertEqual(checks.get("wall_timeout"), 0, checks)
        self.assertEqual(judge("sim", checks, profile), "fail")


class DecisionNumberTests(RepoTest):
    """不变量：裁决编号只增不复用（撤回只标已撤回，重入库领更大的 D 号）。"""

    def test_withdraw_then_recommit_increases_number(self):
        name = "dnum"
        init_sys(self.root, name)
        did1 = decide(self.root, name, "位宽取 8", "数值", 1)
        self.assertEqual(withdraw_decision(self.root, name, did1), did1)
        state = load_state(self.root, name)
        # 撤回的条目保留在原编号下（历史不丢），但不再是有效证据。
        row = next(item for item in state["decisions"]["0"] if item["id"] == did1)
        self.assertTrue(row["withdrawn"])
        self.assertFalse(_decision_exists(state, did1))
        did2 = commit_decision(self.root, name, content="位宽取 8（复核后维持）", kind="数值",
                               source="mark:rules/decision.md:1", stop=1,
                               force=True, reason="撤回后复核重入库，确属新结论")
        self.assertNotEqual(did1, did2)
        self.assertGreater(int(did2.split("-")[1]), int(did1.split("-")[1]),
                           "重新入库必须领严格更大的编号，不得复用 %s" % did1)
        state = load_state(self.root, name)
        self.assertTrue(_decision_exists(state, did2))
        self.assertFalse(_decision_exists(state, did1))


class M3QuoteTests(RepoTest):
    """不变量（T4，负路径）：M3 照抄原话不一致必须拒，且拒在机器检查之后。"""

    def _walk_to_m3_pending(self, name):
        """行 1–11 就绪、行 12 已送审：M3 机器检查全部通过的最小前置（tick 驱动）。"""
        plant_sample(self.root, name)
        _relocate_tb(self.root, name)
        for sid in (1, 2, 3):
            review(self.root, name, sid)
            tick_report(self.root, name)
        confirm_milestone(self.root, name, "M1")
        for sid in (4, 5):
            review(self.root, name, sid)
            tick_report(self.root, name)
        review(self.root, name, 6)
        tick_report(self.root, name)
        confirm_milestone(self.root, name, "M2")   # 覆盖行 4/5/6 置完成
        # 行 7/8/9 的模块与平台清单由文件推导、通过态由证据推导，不再手工登记。
        _lint(self.root, name, ["alu"])
        review(self.root, name, 7, module="alu")
        tick_report(self.root, name)
        review(self.root, name, 8, module=name + "_top")
        tick_report(self.root, name)
        # DEV-07：行 9 要一条 tb_review（与 tc 闸门并列）。
        review(self.root, name, 9)
        tick_report(self.root, name)
        _sim(self.root, name)
        _coverage(self.root, name)
        tick_report(self.root, name)
        _midend(self.root, name)
        tick_report(self.root, name)      # 行 11 判据齐备 → 完成
        # signoff 闸门要求行 11 已完成，行 12 才能送审；tick 自动启动行 12 并在同一次
        # tick 里过闸门后送审（待里程碑）。
        tick_report(self.root, name)

    def test_m3_wrong_quote_rejected_after_machine_checks(self):
        name = "m3quote"
        init_sys(self.root, name)
        self._walk_to_m3_pending(name)
        quote = "%s 签核放行" % name
        with fake_terminal("错误的原话，不是开发者的签核原话") as term:
            with self.assertRaises(EngineError) as ctx:
                milestone_confirm(self.root, name, "M3", confirm=quote)
        self.assertIn("不一致", str(ctx.exception), str(ctx.exception))
        # T4：机器检查（覆盖停点就绪、判据、送审摘要）全部做完才提示照抄；
        # 拒绝发生在照抄之后——终端被问了一次（calls == 1）。
        self.assertEqual(term.calls, 1,
                         "拒绝若发生在机器检查阶段，终端不应被提示照抄")
        state = load_state(self.root, name)
        self.assertEqual(stop_row(state, 12)["state"], PENDING, "照抄不一致不得放行")
        self.assertNotIn("M3", state.get("milestones") or {})

    def test_m3_matching_quote_passes(self):
        # 正向对照：同样的前置，照抄一致即放行（证明上面的拒绝不是前置不齐造成的）。
        name = "m3ok"
        init_sys(self.root, name)
        self._walk_to_m3_pending(name)
        quote = "%s 签核放行" % name
        with fake_terminal(quote) as term:
            milestone_confirm(self.root, name, "M3", confirm=quote)
        self.assertEqual(term.calls, 1)
        state = load_state(self.root, name)
        for sid in (7, 8, 9, 10, 11, 12):
            self.assertEqual(stop_row(state, sid)["state"], "完成（审核通过）",
                             "行 %d 应由 M3 确认置完成" % sid)


class ItemEndInvariantTests(RepoTest):
    """`item <sys> end` 的既有不变量：不改任何停点状态与确认痕迹、不影响其它在途
    事项（补回 test_item_gating 改写中丢掉的那类不变性断言）。"""

    def test_item_end_leaves_stops_and_other_items_untouched(self):
        name = "itemend"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        review(self.root, name, 1)
        tick_report(self.root, name)          # tick 自动启动 + 判据齐备即完成
        mid1 = item_open(self.root, name, "调试", "行 2 口径复核", side="rtl")
        mid2 = item_open(self.root, name, "调试", "另一条在途事项", side="tb")

        def snapshot(state):
            return (
                [(row["id"], row["state"], row["done_at"], row["confirm_quote"],
                  row["confirmed_at"], row["fingerprint"], row["remark"],
                  row["pending_digest"]) for row in state["stops"]],
                json.dumps(state["decisions"], sort_keys=True, ensure_ascii=False),
                json.dumps(state["problems"], sort_keys=True, ensure_ascii=False),
                [row["id"] for row in state["runs"]],
            )

        before = snapshot(load_state(self.root, name))
        item_end(self.root, name, mid1, "L0")
        after_state = load_state(self.root, name)
        self.assertEqual(snapshot(after_state), before,
                         "item end 不得改动停点状态、确认痕迹、裁决、问题与运行记录")
        # 闭合即从在途清单消失；另一条事项原样保留（字段一个都不动）。
        items = {item["id"]: item for item in after_state["items"]}
        self.assertNotIn(mid1, items)
        self.assertIn(mid2, items)
        other = items[mid2]
        self.assertEqual(other["side"], "tb")
        self.assertEqual(other["text"], "另一条在途事项")
        self.assertEqual(other["rounds"], 0)
        # 闭合动作与证据落在 events.jsonl。
        closes = [event for _lineno, event in _events(self.root, name)
                  if event.get("action") == "事项收尾" and event.get("object") == mid1]
        self.assertTrue(closes, "item end 缺'事项收尾'事件")
        self.assertIn("L0", closes[-1]["evidence"])


if __name__ == "__main__":
    unittest.main()
