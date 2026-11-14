# 作者：vick 邮箱：ykun@yk9811.com

"""端到端验收：fixtures/sample 从行 1 走到行 12，全程交互只有
「决策点选 + 3 个里程碑」，事件日志里每个自动完成都带闸门结果与审查记录引用。

本文件验收的交互口径：
- 行 1→12 端到端；交互通道只出现决策点选 + 3 个里程碑；每个自动
  完成的事件带闸门结果与审查记录引用。
- 交互模型：行 1–5、7–10 送完成全自动（自动完成判据：闸门 + 独立审查记录，
  不要 --confirm、不要令牌）；行 6/11/12 由里程碑覆盖完成；终端照抄只在 M3
  （terminal: true），且机器检查做完才提示照抄（T4）。
- 里程碑覆盖：M1 覆盖行 1–3 阻塞行 4，M2 覆盖行 4–6 阻塞行 7——行 4 前确认 M1、
  行 7 前确认 M2。
- 简报 <sys>/<sys>_brief.md 每次事务后重渲染，第一行"需要你做的：…"。
- schema 不变量：schema == SCHEMA_VERSION（已迁移到最新版）。

场景口径（与任务书一致）：
- 决策通道：2 条方向/数值裁决，走两步链路（`problem add --kind 待裁决` →
  `decision commit --from --pick`，点选即入库）。放行令牌已删除，方向/数值入库
  的红线凭据是"点选来源"。
- 里程碑通道：M1、M2 用 `--pick 通过` 点选确认；M3 签核要交互终端照抄（不再要令牌），
  fake_terminal 装一个，断言 calls == 1 且在机器检查之后才被调用。
- 行 1–5、7–10：补独立审查记录（行 1–6 spec_review、行 7/8 rtl_review、
  行 9 tb_review、行 10–12 不需要）→ 跑 `tick`——启动、送审与完成全由 tick 四相位自动做；
  行 6/11 由 tick 置送审态（待里程碑）。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
验收结论（2026-10，真机验收发现 / 主持者修复后复验）：两个用例都真断言、全过。

真机验收曾发现行 11→12 死锁并固化为 expectedFailure 钉子；修复后装饰器与钉子断言
已删除，两个用例都走正路：

- `test_walk_line1_to_line12_full_scenario`：完整走行 1→12（M3 终端照抄一次、
  12 个停点全完成、交互计数 ≤ 决策批次数 + 3）。
- `test_walk_line1_to_line11_no_extra_human_actions`：行 1→11 的交互计数、事件
  证据、简报、schema；末尾断言行 12 已可启动并送审、M3 只因缺终端/交互确认被拒。

已修缺陷（端到端验收 + 里程碑覆盖与阻塞）：
- 现象：行 11、12 都由 M3 覆盖完成，但行 12 在 M3 确认前既不能启动也不能送审，
  而 M3 确认又要求行 12 已送审——三条规定合成一个环：
  1) `engine._previous_done`：启动停点 12 要求停点 11 已完成；
  2) `gates/run.py` signoff 闸门：停点 12 置已送审要求停点 11 DONE；
  3) `engine._milestone_confirm_reasons`：M3 确认要求覆盖停点全部"完成或
     已送审"，停点 12 未开始即拒绝。
  而行 11 自身只能由 M3 确认置完成（动作表 stop_done_milestone，advance/tick
  都拒绝），于是 M3 永远不就绪。
- 修法（采用"放松前置"口径，不用"未开始也随里程碑完成"——那会跳过签核工作）：
  "由里程碑完成的依赖停点已送审即算定稿"，
  `engine._previous_done` 改按 `flow.depends_on` 全集判定，`gates/run.py` 的
  signoff 分支同样接受行 11 待 M3 确认；两处共用 `flow.milestone_done_stops()`。
  行 12 因此可以先启动、先送审，M3 再按既有口径确认行 11、12。
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import json
import os
import unittest

from framework.engine import (
    EngineError, advance, commit_decision, milestone_confirm,
    record_run, status_report, tick_report,
)
from framework.flow import DONE, NOT_STARTED, PENDING, RUNNING
from framework.state import SCHEMA_VERSION, init_sys, load_state, stop_row
from framework.tests.util import (
    AUTHOR, REVIEWER, RepoTest, confirm_milestone, decide, fake_terminal,
    plant_sample, review, write_milestone_notes,
)

AUTO_STOPS = (1, 2, 3, 4, 5, 7, 8, 9, 10)   # 动作表 stop_done_auto
MILESTONE_STOPS = (6, 11, 12)               # 动作表 stop_done_milestone
DONE_STATE = "完成（审核通过）"
# 流转类动作不得出现在"需要开发者"清单里（也不得出现在 tick
# 任何输出里）。里程碑通道的"milestone show/confirm"提示不算流转。
FORBIDDEN_IN_TICK = ("是否确认通过", "照抄", "确认通过", "确认语句")


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


class E2EHumanModelTests(RepoTest):
    """行 1→12 只用「决策点选 + 3 个里程碑」走完。"""

    def setUp(self):
        super().setUp()
        # RepoTest 的仓库副本是类级的：两个用例各用一份子系统目录，互不串状态。
        suffix = "full" if self._testMethodName.endswith("full_scenario") else "part"
        self.name = "e2ehuman" + suffix
        init_sys(self.root, self.name)
        plant_sample(self.root, self.name)
        # 行 9 的平台清单由 testbench/ 布局推导（不再手工登记）：把样例的
        # testbench/tc 挪成 testbench/tb/tc（平台名 tb），"tc_check 通过"由
        # 文件与用例核对推导。
        os.makedirs(os.path.join(self.root, self.name, "testbench", "tb"), exist_ok=True)
        os.rename(os.path.join(self.root, self.name, "testbench", "tc"),
                  os.path.join(self.root, self.name, "testbench", "tb", "tc"))
        self.tick_outputs = []       # 全程 tick 输出，供交互口径断言
        self.decision_batches = 0    # （a）决策批次数：每次 decision commit 点选
        self.milestone_confirms = [] # （b）里程碑确认：M1/M2/M3 各一次
        self.terminal_calls = 0      # （c）终端照抄次数（fake_terminal.calls）

    # ---------- 步骤助手（每步只做流转，不打断开发者） ----------

    def _tick(self):
        text = tick_report(self.root, self.name)
        self.tick_outputs.append(text)
        return text

    def _auto_stop(self, sid, module=""):
        """行 1–5、7–9：补独立审查记录 → tick 自动启动并完成。
        不用 --confirm、不用放行令牌：完成只由 tick 的判据写入。"""
        if sid <= 6:
            review(self.root, self.name, sid)
        elif sid == 7:
            review(self.root, self.name, 7, module=module)
        elif sid == 8:
            review(self.root, self.name, 8, module=module)
        elif sid == 9:
            # DEV-07：行 9 的独立审查是 tb_review（与 tc 闸门并列）。
            review(self.root, self.name, 9)
        # 行 10：审查就是闸门与运行记录本身，不需要审查记录。
        text = self._tick()
        state = load_state(self.root, self.name)
        self.assertEqual(stop_row(state, sid)["state"], DONE,
                         "行 %d 应由 tick 自动完成（判据齐备）" % sid)
        self.assertIn("自动完成停点", text)
        return text

    def _decide(self, content, kind):
        """决策通道（两步链路）：登记待裁决问题 → 开发者点选 → 入库。

        方向/数值入库是红线动作，靠"点选来源"（--from/--pick）留痕；没有令牌。
        """
        decide(self.root, self.name, content, kind, 2)
        self.decision_batches += 1

    def _confirm_milestone(self, mid, confirm="", terminal=None):
        if terminal is not None:
            with terminal:
                message = milestone_confirm(self.root, self.name, mid, confirm=confirm)
            self.terminal_calls += terminal.calls
        else:
            # M1/M2 用主持者的点选工具，--pick 通过 就是那一次点选。
            message = milestone_confirm(self.root, self.name, mid, confirm=confirm, pick="通过")
        self.milestone_confirms.append(mid)
        return message

    def _events(self):
        path = os.path.join(self.root, self.name, "events.jsonl")
        with open(path, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def _walk_to_rtl_ready(self):
        """行 1–6 完成（含 M1/M2 两次里程碑），返回到行 7 可启动的状态。"""
        # 决策批次：方案阶段推不出的 2 条（一条方向、一条数值），点选即入库。
        self._decide("帧样点缓存采用乒乓双缓冲结构，读写两侧各一份样点 RAM", "方向")
        self._decide("样点计数器位宽取 12 位，饱和上限按 fx 输出复核", "数值")
        for sid in (1, 2, 3):
            self._auto_stop(sid)
        # M1 确认前必须先有结论摘要（milestone_notes/M1.md，3–6 条）——
        # 这是主持者在"阅读原文后写摘要"那一步的产物，夹具在这里补上。
        write_milestone_notes(self.root, self.name, "M1")
        # 里程碑规则：M1 覆盖行 1–3、阻塞行 4——行 4 启动前必须确认 M1（点选，无终端）。
        # 启动由 tick 负责，所以这里断言"跑 tick 也不会启动行 4"。
        text = self._tick()
        self.assertEqual(stop_row(load_state(self.root, self.name), 4)["state"], NOT_STARTED,
                         "行 4 被未确认的 M1 阻塞，tick 不得启动")
        self.assertIn("M1", text)
        self.assertIn("不得启动", text)
        self._confirm_milestone("M1")
        state = load_state(self.root, self.name)
        for sid in (1, 2, 3):
            self.assertEqual(stop_row(state, sid)["state"], DONE_STATE)
        self._auto_stop(4)
        self._auto_stop(5)
        # 行 6：里程碑覆盖停点。补审查记录后 tick 只把它置送审态（待里程碑），不完成。
        review(self.root, self.name, 6)
        text = self._tick()
        state = load_state(self.root, self.name)
        self.assertEqual(stop_row(state, 6)["state"], PENDING,
                         "行 6 由 M2 覆盖完成，tick 不得自动完成")
        self.assertIn("里程碑 M2 规格冻结", text)
        self.assertIn("已就绪", text)
        # M2 覆盖行 4–6、阻塞行 7——行 7 启动前必须确认 M2。行 6 停在送审态，
        # M2 未确认时行 7 不得启动（M1 档在行 4 上已单独验证过消息文本）。
        text = self._tick()
        self.assertEqual(stop_row(load_state(self.root, self.name), 7)["state"], NOT_STARTED,
                         "行 7 被未确认的 M2 阻塞，tick 不得启动")
        self.assertIn("M2", text)
        self.assertIn("不得启动", text)
        self._confirm_milestone("M2", confirm="规格冻结通过")
        state = load_state(self.root, self.name)
        for sid in (4, 5, 6):
            self.assertEqual(stop_row(state, sid)["state"], DONE_STATE,
                             "行 %d 应被 M2 确认置完成" % sid)
        done_events = [e for e in self._events()
                       if e["action"] == "里程碑完成" and e["object"] == "停点 6"]
        self.assertTrue(done_events, "行 6 缺里程碑完成事件")
        self.assertIn("规格冻结通过", done_events[-1]["evidence"])

    def _walk_to_m3_pending(self):
        """行 7–10 自动完成、行 11 送审进"待里程碑"：M3 确认前的全部合法步骤。"""
        self._walk_to_rtl_ready()
        # 行 7：逐模块 lint → 逐模块独立审查 → tick（模块清单由 rtl/ 文件推导）。
        _lint(self.root, self.name, ["alu"])
        self._auto_stop(7, module="alu")
        # 行 8：顶层 wrapper，rtl_review 绑顶层产物指纹（顶层文件由 plant_sample 布好）。
        self._auto_stop(8, module=self.name + "_top")
        # 行 9：TB 平台的"tc_check 通过"由文件与用例核对推导（setUp 已布好布局）。
        self._auto_stop(9)
        # 行 10：全量 sys 回归 + 覆盖率（绑定该次回归），送审后 tick。
        _sim(self.root, self.name)
        _coverage(self.root, self.name)
        self._auto_stop(10)
        # 行 11：综合 + STA 运行记录 → tick 自动送审 → 待里程碑（M3 覆盖）。
        _midend(self.root, self.name)
        self._tick()
        state = load_state(self.root, self.name)
        self.assertEqual(stop_row(state, 11)["state"], PENDING)
        # 行 12：中端签核。它的前置是行 11 定稿——已完成，或（里程碑完成型）已送审
        # 待 M3 确认。后者是行 11/12 与 M3 不互相等待的关键（tick 同一次里启动
        # 行 12 并过 signoff 闸门后送审）。
        self._tick()
        state = load_state(self.root, self.name)
        self.assertEqual(stop_row(state, 12)["state"], PENDING)
        self.assertIn("待里程碑（M3）", status_report(self.root, self.name))

    # ---------- 用例 1：完整场景 ----------

    def test_walk_line1_to_line12_full_scenario(self):
        """行 1→12 全程：2 条决策点选 + M1/M2/M3 三个里程碑，终端只在 M3 一次。

        行 11→12 曾有一处死锁（真机验收发现、已修）：行 11 只能由 M3 置完成，行 12
        的启动与 signoff 闸门又要求行 11"已完成"，而 M3 确认要求行 12 先送审。
        修法是"由里程碑完成的依赖停点（动作表 stop_done_milestone）已送审即算定稿"
        （engine._previous_done 与 gates/run.py 的 signoff 分支共用 flow.milestone_done_stops）。
        """
        quote = "%s 签核放行" % self.name
        # T4：机器检查没做完之前不得提示终端照抄。令牌删掉后，机器检查的负路径
        # 用"覆盖停点还没就绪"（行 11/12 未送审）：被拒且一次都不提示照抄。
        with fake_terminal(quote) as term:
            with self.assertRaises(EngineError) as ctx:
                milestone_confirm(self.root, self.name, "M3", confirm=quote)
            self.assertIn("不能确认", str(ctx.exception))
            self.assertEqual(term.calls, 0, "机器检查没做完就提示照抄（T4）")
        self._walk_to_m3_pending()
        # 行 11、12 由 M3 覆盖完成：交互终端照抄一次（不再有放行令牌）。
        with fake_terminal(quote) as term:
            milestone_confirm(self.root, self.name, "M3", confirm=quote)
            self.assertEqual(term.calls, 1, "终端照抄只在 M3 发生一次")
        self.terminal_calls = 1
        self.milestone_confirms.append("M3")
        state = load_state(self.root, self.name)
        for sid in range(1, 13):
            self.assertEqual(stop_row(state, sid)["state"], DONE_STATE,
                             "行 %d 应为 %s" % (sid, DONE_STATE))
        self.assertEqual(state["schema"], SCHEMA_VERSION)
        self.assertEqual(self.terminal_calls, 1, "终端照抄全程只发生在 M3")
        self.assertEqual(self.milestone_confirms, ["M1", "M2", "M3"])
        # 总打断次数 ≤ 决策批次数 + 3（终端照抄含在 M3 那一次里）。
        self.assertLessEqual(self.decision_batches + len(self.milestone_confirms),
                             self.decision_batches + 3)
        self.assert_tick_lists_clean()
        self.assert_event_log_for_auto_stops()
        self.assert_brief()

    # ---------- 用例 2：能合法走到的部分，今天就必须全过 ----------

    def test_walk_line1_to_line11_no_extra_human_actions(self):
        """行 1→11：交互只有 2 条决策点选 + M1/M2；每个自动完成事件带闸门结果
        与审查记录引用；简报与 schema 达标；末尾断言行 12 已可启动送审。
        """
        self._walk_to_m3_pending()
        state = load_state(self.root, self.name)
        for sid in AUTO_STOPS:
            self.assertEqual(stop_row(state, sid)["state"], DONE_STATE,
                             "行 %d 应已自动完成" % sid)
        for sid in (1, 2, 3, 4, 5, 6):
            self.assertTrue(stop_row(state, sid)["fingerprint"],
                            "行 %d 完成时应写产物指纹" % sid)
        self.assertEqual(stop_row(state, 11)["state"], PENDING)
        self.assertIn("待里程碑（M3）", status_report(self.root, self.name))
        self.assertEqual(state["schema"], SCHEMA_VERSION)
        # （a）（b）交互计数：到这里只有 2 条决策点选 + 2 个里程碑，终端 0 次。
        self.assertEqual(self.decision_batches, 2)
        self.assertEqual(self.milestone_confirms, ["M1", "M2"])
        self.assertEqual(self.terminal_calls, 0, "M3 之前不应有任何终端照抄")
        self.assert_tick_lists_clean()
        self.assert_event_log_for_auto_stops()
        self.assert_brief()
        # 修复后的护栏（曾是死锁钉子）：行 12 已可启动并送审；M3 确认的前提是
        # 覆盖停点全部送审——行 12 已送审，故此处 M3 只因缺令牌/终端被拒，
        # 不再出现"未送审"。
        self.assertEqual(stop_row(state, 12)["state"], PENDING)
        with self.assertRaises(EngineError) as ctx:
            milestone_confirm(self.root, self.name, "M3", confirm="放行")
        self.assertNotIn("未送审", str(ctx.exception))

    # ---------- 共用断言 ----------

    def assert_tick_lists_clean(self):
        """tick 全程不向开发者要流转类动作（不出现"是否确认通过"
        "照抄"等字样）；流转只出现在"可推进的工作"清单里。"""
        for text in self.tick_outputs:
            for phrase in FORBIDDEN_IN_TICK:
                self.assertNotIn(phrase, text,
                                 "tick 输出出现了流转类打断用语：%r\n%s" % (phrase, text))

    def assert_event_log_for_auto_stops(self):
        """每个自动完成的停点在 events.jsonl 有对应事件，且 evidence
        同时含（i）闸门结果（ii）审查记录引用（行 10/11 以闸门与运行记录
        为审查依据，引用文案为"以闸门与运行记录为准"——不是放宽成"有事件就行"）。"""
        events = self._events()
        for sid in AUTO_STOPS:
            hits = [e for e in events
                    if e["action"] == "自动完成" and e["object"] == "停点 %d" % sid]
            self.assertTrue(hits, "行 %d 缺自动完成事件" % sid)
            event = hits[-1]
            self.assertEqual(event["cmd"], "tick", "行 %d 应由 tick 自动完成" % sid)
            self.assertIn("闸门通过", event["evidence"],
                          "行 %d 的自动完成事件缺闸门结果" % sid)
            if sid <= 6:
                self.assertIn("spec_review", event["evidence"],
                              "行 %d 的自动完成事件缺审查记录引用" % sid)
            elif sid in (7, 8):
                self.assertIn("rtl_review", event["evidence"],
                              "行 %d 的自动完成事件缺审查记录引用" % sid)
            elif sid == 9:
                # DEV-07：行 9 的独立审查是 tb_review，完成事件要带出这条引用。
                self.assertIn("tb_review", event["evidence"],
                              "行 9 的自动完成事件缺 tb_review 审查记录引用")
            else:
                self.assertIn("以闸门与运行记录为准", event["evidence"],
                              "行 %d 的自动完成事件缺审查依据引用" % sid)
            self.assertIn("指纹", event["evidence"])

    def assert_brief(self):
        """简报在每次事务后重渲染，第一行"需要你做的：…"。"""
        path = os.path.join(self.root, self.name, "%s_brief.md" % self.name)
        self.assertTrue(os.path.isfile(path), "缺简报 %s" % path)
        with open(path, encoding="utf-8") as fh:
            first = fh.readline().rstrip("\n")
        self.assertTrue(first.startswith("需要你做的："),
                        "简报第一行应以「需要你做的：」开头，实得：%r" % first)


if __name__ == "__main__":
    unittest.main()
