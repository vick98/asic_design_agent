# 作者：vick 邮箱：ykun@yk9811.com

"""tick 与里程碑的用例。

- tick：可自动完成的停点被完成并记事件（事件带闸门结果与审查记录引用）；
  判据未满足时不完成且列出原因；两张清单标题固定；待裁决问题进"需要开发者"；
  调试事项轮数 ≥ 阈值进升级上报；--blocks 的停点出现在"被决策阻塞"。
- milestone：show 三档内容要点；confirm 把"待里程碑"停点置完成并写入确认语句
  与产物指纹；M1/M2 要点选 `pick="通过"`，M3 要终端照抄（放行令牌已删除）；
  pending_digest 不一致拒绝；reject 退回最早有问题的停点并把理由转成问题；
  blocks 未确认前停点不得启动。
- status 派生显示"待里程碑（Mn）"，内部状态仍是四个。
"""

import json
import os
import subprocess
import sys
import unittest

from framework.engine import (
    EngineError, advance, item_open, item_set, milestone_confirm, milestone_reject,
    record_run, status_report, tick_report,
)
from framework.flow import DONE, NOT_STARTED, PENDING, RUNNING
from framework.review_pack import milestone_report
from framework.state import init_sys, load_state, save, stop_row, sys_dir
from framework.tests.util import (
    RepoTest, checkout_root, confirm_milestone, decide, force_done, plant_sample, review,
    write_milestone_notes,
)


def _script():
    return os.path.join(checkout_root(), "script", "framework.py")


def _run(args, root):
    env = os.environ.copy()
    env["ADF_ROOT"] = root
    return subprocess.run([sys.executable, _script()] + args,
                          env=env, capture_output=True, text=True)


class TickMilestoneBase(RepoTest):
    def _plant(self, name):
        init_sys(self.root, name)
        plant_sample(self.root, name)

    def _confirmed(self, name, mid):
        return mid in (load_state(self.root, name).get("milestones") or {})

    def _walk_to(self, name, upto, module="alu"):
        """只用 review + tick 走到 upto（含）。行 6 不在此用：它由里程碑覆盖完成。

        tick 相位②自动启动依赖定稿的未开始停点，相位③判据齐备即完成——所以一次
        tick 就能把"产物已由夹具就位 + 审查记录已补"的停点推完。
        """
        for sid in range(1, upto + 1):
            if sid == 4 and not self._confirmed(name, "M1"):
                confirm_milestone(self.root, name, "M1")
            if sid == 7 and not self._confirmed(name, "M2"):
                confirm_milestone(self.root, name, "M2")
            tick_report(self.root, name)
            review(self.root, name, sid)
            tick_report(self.root, name)

    def _to_m2_ready(self, name):
        """行 1–5 自动完成、行 6 送审并补审查记录：M2 就绪（待里程碑）。"""
        self._plant(name)
        self._walk_to(name, 5)
        review(self.root, name, 6)
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

    def _to_m3_pending(self, name):
        """行 7–10 造完成态、行 11 由 tick 自动完成、行 12 由 tick 自动送审。

        启动与送审都归 tick——第一次 tick 启动行 11（依赖 7、8 已完成、综合与时序
        运行记录已就位）并在同一 tick 判据齐备即完成；第二次 tick 启动行 12、过 signoff
        闸门后置送审态（里程碑归属）。
        """
        self._plant(name)
        self._walk_to(name, 5)
        force_done(self.root, name, 6)
        confirm_milestone(self.root, name, "M2")
        for sid in (7, 8, 9, 10):
            force_done(self.root, name, sid)
        self._midend(name)
        tick_report(self.root, name)
        tick_report(self.root, name)

    def _events(self, name):
        path = os.path.join(self.root, name, "events.jsonl")
        with open(path, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]


class TickTests(TickMilestoneBase):
    def test_tick_completes_ready_stop_and_records_event(self):
        name = "tickdone"
        self._plant(name)
        review(self.root, name, 1)
        text = tick_report(self.root, name)
        self.assertIn("可推进的工作：", text)
        self.assertIn("需要开发者：", text)
        # tick 相位②自动启动行 1、相位③判据齐备即完成；同一 tick 的下一轮把行 2
        # 自动启动（同一 tick 内连续推进），清单说明它进行中、判据齐备时自动完成。
        self.assertIn("停点 2 处理流程梳理：进行中，判据齐备时 tick 自动完成", text)
        self.assertEqual(stop_row(load_state(self.root, name), 2)["state"], RUNNING)
        state = load_state(self.root, name)
        self.assertEqual(stop_row(state, 1)["state"], DONE)
        self.assertTrue(stop_row(state, 1)["fingerprint"])
        # 事件带闸门结果与审查记录引用。
        events = [e for e in self._events(name) if e["action"] == "自动完成"
                  and e["object"] == "停点 1"]
        self.assertTrue(events, "缺自动完成事件")
        self.assertIn("闸门通过", events[-1]["evidence"])
        self.assertIn("spec_review", events[-1]["evidence"])

    def test_tick_does_not_complete_without_criteria(self):
        name = "tickwait"
        self._plant(name)
        text = tick_report(self.root, name)
        # 判据不齐：tick 相位②启动它，相位③不完成——停在"进行中"，不进入送审态。
        self.assertEqual(stop_row(load_state(self.root, name), 1)["state"], RUNNING)
        self.assertIn("判据齐备时 tick 自动完成", text)
        self.assertIn("spec_review", text)

    def test_tick_lists_decision_problems_and_blocked_work(self):
        name = "tickprob"
        self._plant(name)
        from framework.engine import add_problem
        add_problem(self.root, name, "待裁决", 2, "帧窗口取行 2 还是行 3 口径",
                    source="审查", options="行 2|行 3", blocks="3")
        text = tick_report(self.root, name)
        self.assertIn("待裁决问题 I001", text)
        self.assertIn("候选项：行 2 | 行 3", text)
        line = next(l for l in text.splitlines() if l.startswith("- 被决策阻塞"))
        self.assertIn("I001", line)
        self.assertIn("3", line)

    def test_tick_escalates_item_rounds(self):
        name = "tickesc"
        self._plant(name)
        mid = item_open(self.root, name, "调试", "行 7 建立时间违例", side="rtl")
        for _ in range(5):
            item_set(self.root, name, mid, "换约束重跑")
        text = tick_report(self.root, name)
        self.assertIn("升级上报", text)
        self.assertIn(mid, text)
        self.assertIn("5 轮", text)

    def test_item_round_threshold_is_configurable(self):
        name = "tickcfg"
        self._plant(name)
        state = load_state(self.root, name)
        state["thresholds"] = {"item_rounds": 2}
        save(self.root, name, state)
        mid = item_open(self.root, name, "调试", "行 7 建立时间违例", side="rtl")
        item_set(self.root, name, mid, "第一轮")
        self.assertNotIn("升级上报", tick_report(self.root, name))
        item_set(self.root, name, mid, "第二轮")
        self.assertIn("升级上报", tick_report(self.root, name))

    def test_tick_lists_ready_milestone_and_blocks_start(self):
        name = "tickms"
        self._plant(name)
        self._walk_to(name, 3)
        # M1 就绪还要有结论摘要（3–6 条）——否则 tick 清单给的是"未就绪"。
        write_milestone_notes(self.root, name, "M1")
        text = tick_report(self.root, name)
        self.assertIn("里程碑 M1 方案确认", text)
        self.assertIn("已就绪", text)
        self.assertIn("停点 4 不得启动", text)
        # 启动由 tick 负责；被未确认里程碑阻塞的停点跑 tick 也不会启动。
        tick_report(self.root, name)
        self.assertEqual(stop_row(load_state(self.root, name), 4)["state"], NOT_STARTED)
        confirm_milestone(self.root, name, "M1")
        tick_report(self.root, name)
        self.assertEqual(stop_row(load_state(self.root, name), 4)["state"], RUNNING)

    def test_tick_cli_exit_code_is_zero(self):
        name = "tickcli"
        self._plant(name)
        proc = _run(["tick", name], self.root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("可推进的工作：", proc.stdout)
        self.assertIn("需要开发者：", proc.stdout)


class MilestoneShowTests(TickMilestoneBase):
    def test_show_m1_sections(self):
        name = "m1show"
        self._plant(name)
        self._walk_to(name, 3)
        # 记录类直接入库：停点 3 → 阶段 2。
        decide(self.root, name, "帧样点数每帧 28456 样点", "记录", 3)
        # 结论摘要（milestone_notes/M1.md）是 M1 的唯一入口，包不再内嵌三份原文。
        write_milestone_notes(self.root, name, "M1")
        text = milestone_report(self.root, name, "M1")
        self.assertIn("里程碑 M1 方案确认", text)
        self.assertIn("结论摘要（milestone_notes/M1.md，原文只留链接）", text)
        # 摘要的条目逐条进包（审阅包读的就是这份摘要）。
        self.assertIn("1. 第 1 条结论：口径与依据见原文对应章节。", text)
        # 原文只留链接：三份产物各一条链接。
        self.assertIn("原文链接", text)
        for rel in ("info_input/%s_info_overview.md" % name,
                    "flow_doc/%s_flow.md" % name,
                    "plan_doc/%s_plan.md" % name):
            self.assertIn("- %s" % rel, text)
        # 不再整份内嵌：三份原文各自的独有长句都不出现在包里。
        for sentence in ("类别 A 到 F 按来源流水编号，空号不复用。",
                         "先对齐小数点，再相加，最后饱和。",
                         "能复用的公共模块优先于新写。"):
            self.assertNotIn(sentence, text)
        self.assertIn("全部方向/数值裁决", text)
        # M1 只放方向/数值类裁决；记录类条目（含"疑似方向/数值"高亮）
        # 不再进 M1 包——那份高亮表归 M2（见 test_show_m2_sections）。
        self.assertIn("（无方向/数值裁决）", text)
        self.assertNotIn("帧样点数每帧 28456 样点", text)
        self.assertIn("冲突与红线五问的处置", text)
        self.assertIn("独立审查发现及处置", text)
        self.assertIn("未决问题", text)
        self.assertIn("闸门摘要", text)

    def test_show_m2_sections(self):
        name = "m2show"
        self._to_m2_ready(name)
        # 记录类条目带"疑似方向/数值"高亮（M1 收紧后这张表是它的唯一落点）。
        decide(self.root, name, "alu 的样点位宽取 12 位", "记录", 4)
        text = milestone_report(self.root, name, "M2")
        self.assertIn("子系统规格书端口表", text)
        self.assertIn("模块清单与类型", text)
        self.assertIn("抽样模块规格书：alu", text)
        self.assertIn("测试要点总数与覆盖关系", text)
        self.assertIn("审查发现处置表", text)
        self.assertIn("记录类条目（疑似方向/数值高亮）", text)
        self.assertIn("【疑似方向/数值", text)

    def test_show_m3_sections(self):
        name = "m3show"
        self._to_m3_pending(name)
        text = milestone_report(self.root, name, "M3")
        self.assertIn("自动完成清单", text)
        self.assertIn("回修清单（L0/L1）", text)
        self.assertIn("综合与时序运行记录", text)
        self.assertIn("SDC 全文", text)
        self.assertIn("覆盖率", text)
        # 抽样口径可见（风险优先排序 + 可复现种子），抽样对象在走查章节里。
        self.assertIn("抽样口径（可复现）", text)
        self.assertIn("风险优先", text)
        self.assertIn("排序取前二（alu）", text)
        self.assertIn("种子 %s/M3" % name, text)
        self.assertIn("抽样模块的 RTL 走查", text)
        self.assertIn("- 模块 alu：", text)
        # 可复现：同一子系统连续出两次包，抽样口径与抽中的对象完全一致。
        again = milestone_report(self.root, name, "M3")
        first_note = next(l for l in text.splitlines() if l.startswith("抽样口径："))
        second_note = next(l for l in again.splitlines() if l.startswith("抽样口径："))
        self.assertEqual(first_note, second_note)
        self.assertIn("种子 %s/M3" % name, first_note)
        first_walk = sorted(l for l in text.splitlines() if l.startswith("- 模块 "))
        second_walk = sorted(l for l in again.splitlines() if l.startswith("- 模块 "))
        self.assertTrue(first_walk, "走查章节没有抽中的模块")
        self.assertEqual(first_walk, second_walk)
        self.assertIn("签核记录", text)

    def test_show_writes_the_pack_file_and_prints_path(self):
        name = "m1file"
        self._plant(name)
        self._walk_to(name, 3)
        proc = _run(["milestone", name, "show", "--id", "M1"], self.root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        path = os.path.join(self.root, name, "milestone_M1.md")
        self.assertTrue(os.path.isfile(path))
        self.assertIn(path, proc.stdout)
        with open(path, encoding="utf-8") as fh:
            self.assertIn("里程碑 M1 方案确认", fh.read())


class MilestoneConfirmTests(TickMilestoneBase):
    def test_confirm_m2_completes_waiting_stops(self):
        name = "m2ok"
        self._to_m2_ready(name)
        self.assertEqual(stop_row(load_state(self.root, name), 6)["state"], PENDING)
        message = milestone_confirm(self.root, name, "M2", confirm="规格冻结通过", pick="通过")
        self.assertIn("M2", message)
        state = load_state(self.root, name)
        for sid in (4, 5, 6):
            self.assertEqual(stop_row(state, sid)["state"], DONE, "行 %d 没被里程碑置完成" % sid)
        row6 = stop_row(state, 6)
        # M1/M2 凭"点选来源"授权（pick 字段），确认原话记开发者写的备注
        # （这次写了"规格冻结通过"；没写备注时缺省"点选通过"）。
        self.assertEqual(row6["confirm_quote"], "规格冻结通过")
        self.assertTrue(row6["fingerprint"])
        record = (state.get("milestones") or {}).get("M2") or {}
        self.assertEqual(record.get("quote"), "规格冻结通过")
        self.assertEqual(record.get("pick"), "通过")
        self.assertFalse(record.get("terminal"))
        self.assertTrue(record.get("time"))
        self.assertEqual([int(x) for x in record.get("covered") or []], [4, 5, 6])
        self.assertTrue(all(record.get("fingerprints", {}).get(str(s)) for s in (4, 5, 6)))
        events = [e for e in self._events(name) if e["action"] == "里程碑确认"]
        self.assertTrue(events and "规格冻结通过" in events[-1]["evidence"])
        # M2 确认后停点 7 才能启动：tick 自动启动它（闸门未过则停在"进行中"）。
        tick_report(self.root, name)
        self.assertEqual(stop_row(load_state(self.root, name), 7)["state"], RUNNING)

    def test_confirm_rejects_when_product_changed_after_review(self):
        # 送审摘要不一致 → 拒绝并提示重跑闸门/重送审。
        name = "m2digest"
        self._to_m2_ready(name)
        path = os.path.join(sys_dir(self.root, name), "spec_doc", "alu_spec.md")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text + "\n补充说明一句。\n")
        with self.assertRaises(EngineError) as ctx:
            milestone_confirm(self.root, name, "M2", confirm="规格冻结通过", pick="通过")
        self.assertIn("不一致", str(ctx.exception))
        self.assertEqual(stop_row(load_state(self.root, name), 6)["state"], PENDING)

    def test_confirm_refuses_unready_covered_stops(self):
        name = "m2early"
        self._plant(name)
        self._walk_to(name, 3)
        with self.assertRaises(EngineError) as ctx:
            milestone_confirm(self.root, name, "M2", confirm="早了", pick="通过")
        self.assertIn("停点 4", str(ctx.exception))
        self.assertNotIn("M2", load_state(self.root, name).get("milestones") or {})

    def test_m1_and_m2_confirm_without_terminal_or_token(self):
        name = "m1pick"
        self._plant(name)
        self._walk_to(name, 3)
        # 确认前先有结论摘要（3–6 条）——本用例测的是"点选即确认、无终端无令牌"。
        write_milestone_notes(self.root, name, "M1")
        # 没有放行令牌（已删除）、没有终端（RepoTest 缺省无 TTY）：点选即确认。
        milestone_confirm(self.root, name, "M1", pick="通过")
        self.assertIn("M1", load_state(self.root, name).get("milestones") or {})
        row3 = stop_row(load_state(self.root, name), 3)
        self.assertEqual(row3["state"], DONE)
        self.assertFalse(os.path.exists(os.path.join(self.home, ".asic_design_agent", "release")),
                         "M1/M2 确认不应要求或产生放行令牌文件")
        # 缺 pick 一律拒绝（人按改成点选来源）。
        with self.assertRaises(EngineError) as ctx:
            milestone_confirm(self.root, name, "M1", confirm="口头通过", pick="")
        self.assertIn("点选", str(ctx.exception))

    def test_m3_requires_terminal_after_machine_checks(self):
        name = "m3sign"
        self._to_m3_pending(name)
        from framework.tests.util import fake_terminal
        # 放行令牌已删除：M3 不再要令牌，只要开发者原话 + 交互终端照抄。
        self.assertFalse(os.path.exists(os.path.join(self.home, ".asic_design_agent", "release")))
        # 缺 --confirm 原话：拒绝（在照抄之前）。
        with self.assertRaises(EngineError) as ctx:
            milestone_confirm(self.root, name, "M3", confirm="")
        self.assertIn("--confirm", str(ctx.exception))
        # 有原话、无终端：拒绝，指名叫人去终端。
        with self.assertRaises(EngineError) as ctx:
            milestone_confirm(self.root, name, "M3", confirm="放行")
        self.assertIn("终端", str(ctx.exception))
        self.assertNotIn("M3", load_state(self.root, name).get("milestones") or {})
        # 有原话、有终端：签核通过，覆盖停点全部完成。
        with fake_terminal("放行") as term:
            milestone_confirm(self.root, name, "M3", confirm="放行")
            self.assertEqual(term.calls, 1)
        state = load_state(self.root, name)
        for sid in range(7, 13):
            self.assertEqual(stop_row(state, sid)["state"], DONE, "行 %d 没被 M3 置完成" % sid)
        record = state["milestones"]["M3"]
        self.assertTrue(record["terminal"])
        self.assertEqual(record["quote"], "放行")
        # 放行确认后签核文件必须写上确认原话（先重渲染、再算指纹），
        # 不再是送审时那句"待开发者在本停点确认"。
        signoff = os.path.join(sys_dir(self.root, name), "signoff", "%s_signoff.md" % name)
        with open(signoff, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("- 放行：放行", text)
        self.assertNotIn("待开发者", text)
        self.assertNotIn("里程碑 M3：未确认", text)

    def test_reject_returns_earliest_problematic_stop_and_creates_problem(self):
        name = "m2no"
        self._plant(name)
        self._walk_to(name, 3)
        message = milestone_reject(self.root, name, "M2", "端口表要按新口径重写")
        self.assertIn("停点 4", message)
        state = load_state(self.root, name)
        self.assertEqual(stop_row(state, 4)["state"], RUNNING)
        problems = [p for p in state["problems"] if p["text"] == "端口表要按新口径重写"]
        self.assertTrue(problems, "拒绝理由没有转成问题")
        self.assertEqual(problems[0]["kind"], "待裁决")
        self.assertEqual(problems[0]["stop"], 4)
        events = [e for e in self._events(name) if e["action"] == "里程碑拒绝"]
        self.assertTrue(events and events[-1]["object"] == "M2")

    def test_reject_with_explicit_stop(self):
        name = "m2stop"
        self._plant(name)
        self._walk_to(name, 5)
        review(self.root, name, 6)
        tick_report(self.root, name)
        self.assertEqual(stop_row(load_state(self.root, name), 6)["state"], PENDING)
        milestone_reject(self.root, name, "M2", "逻辑块口径要改", stop=6)
        state = load_state(self.root, name)
        self.assertEqual(stop_row(state, 6)["state"], RUNNING)
        self.assertEqual(stop_row(state, 5)["state"], DONE)


class DerivedDisplayTests(TickMilestoneBase):
    def test_status_shows_waiting_milestone_when_criteria_met(self):
        # 内部状态仍是"已送审"，显示层派生"待里程碑（M2）"。
        name = "dism2"
        self._to_m2_ready(name)
        state = load_state(self.root, name)
        self.assertEqual(stop_row(state, 6)["state"], PENDING)
        self.assertIn("待里程碑（M2）", status_report(self.root, name))

    def test_status_stays_plain_when_criteria_unmet(self):
        name = "dismraw"
        self._plant(name)
        self._walk_to(name, 5)
        tick_report(self.root, name)
        # 没有独立审查记录：判据未满足，tick 相位③不完成也不送审，停点停在"进行中"，
        # 显示层保持内部状态，不派生"待里程碑（M2）"。
        text = status_report(self.root, name)
        self.assertIn("行 6，进行中", text)
        self.assertNotIn("待里程碑（M2）", text)

    def test_states_unchanged_in_model(self):
        # 状态枚举仍是四个，"待里程碑"不进 states。
        from framework.flow import load as flow_load
        model = flow_load()
        self.assertEqual(model["states"], ["未开始", "进行中", "已送审", "完成（审核通过）"])
        self.assertNotIn("待里程碑", model["states"])


if __name__ == "__main__":
    unittest.main()
