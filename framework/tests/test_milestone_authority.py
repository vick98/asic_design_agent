# 作者：vick 邮箱：ykun@yk9811.com

"""放行矩阵：终端照抄只留给 terminal 里程碑（M3）；放行令牌已删除，
红线动作的人按改成"点选来源"（`--from <问题号> --pick <选项>`，或 mark 收割）。

改写：原"关键停点要终端"改为"里程碑要终端"——行 6/11/12 的完成由里程碑
确认写入（动作表 stop_done_milestone），tick 只把它们置送审态（显示"待里程碑"），
advance 不再改这些状态；行 1–5、7–10 由 tick 自动完成，不要令牌与确认语句；
方向/数值裁决入库是红线动作，凭点选来源即入库（M1/M2 里程碑确认也只要 `--pick 通过`）。
"""

import unittest

from framework.engine import EngineError, advance, commit_decision, tick_report
from framework.flow import DONE, NOT_STARTED, PENDING, RUNNING, load
from framework.state import init_sys, load_state, stop_row
from framework.tests.util import (
    RepoTest, checkout_root, cli, confirm_milestone, decide, plant_sample, review,
)


class MilestonePolicyTests(RepoTest):
    """终端照抄只在 M3；行 6/11/12 的完成归属里程碑。"""

    def test_only_m3_is_terminal(self):
        from framework.flow import milestones
        terminals = [m["id"] for m in milestones() if m.get("terminal")]
        self.assertEqual(terminals, ["M3"])
        for item in milestones():
            self.assertIn("terminal", item, "里程碑 %s 缺 terminal 标记" % item["id"])
            self.assertIsInstance(item["terminal"], bool)

    def test_milestone_stops_are_covered(self):
        from framework.flow import milestone_of_stop
        for sid in (6, 11, 12):
            item = milestone_of_stop(sid)
            self.assertIsNotNone(item, "行 %d 应被里程碑覆盖" % sid)
            self.assertEqual(item["id"], "M2" if sid == 6 else "M3")


class AutoStopTests(RepoTest):
    """行 1–5、7–10：闸门 + 独立审查记录齐备即完成，沙箱里没有终端也走得通。"""

    def _walk(self, name, upto):
        """走停点 1..upto：补独立审查记录后由 tick 自动启动并完成（四相位）。

        停点 4 被 M1 阻塞：确认 M1 之后 tick 才自动启动它。
        """
        for sid in range(1, upto + 1):
            if sid == 4:
                # 旧写法：直接 advance 启动 → 新写法：M1 确认前 tick 不启动停点 4，
                # 先补里程碑确认，再由 tick 自动启动/完成。
                confirm_milestone(self.root, name, "M1")
            review(self.root, name, sid)
            tick_report(self.root, name)

    def _plant(self, name):
        init_sys(self.root, name)
        plant_sample(self.root, name)

    def test_stops_one_to_five_complete_without_a_terminal(self):
        name = "c6early"
        self._plant(name)
        self._walk(name, 5)
        state = load_state(self.root, name)
        for sid in range(1, 6):
            self.assertEqual(stop_row(state, sid)["state"], DONE, "行 %d 没过" % sid)

    def test_done_is_recorded_without_a_quote(self):
        # 旧断言：row["confirm_quote"] == QUOTE 且 done_at 非空
        # → 新断言：done_at/fingerprint 落库，confirm_quote 保持空（确认语句只由
        #   里程碑确认写入）→ 依据自动完成判据。
        name = "c6quote"
        self._plant(name)
        self._walk(name, 1)
        row = stop_row(load_state(self.root, name), 1)
        self.assertEqual(row["state"], DONE)
        self.assertEqual(row["confirm_quote"], "")
        self.assertTrue(row["done_at"])
        self.assertTrue(row["fingerprint"])

    def test_token_is_not_required_for_auto_completion(self):
        # 旧断言：完成要放行令牌。令牌已删除 → 新断言：自动停点由 tick 按
        # 判据完成，环境里没有任何令牌也走得通。
        name = "c6token"
        self._plant(name)
        review(self.root, name, 1)
        tick_report(self.root, name)
        self.assertEqual(stop_row(load_state(self.root, name), 1)["state"], DONE)

    def test_confirm_is_ignored_for_auto_completion(self):
        # 旧断言：缺 --confirm 要拒 → 新断言：--confirm 参数已删——CLI 传它
        # argparse 报错、engine 的 advance() 也不再收；完成由 tick 按判据决定，
        # 且不写确认语句（"完成不靠确认语句"的原意保留，只是不再靠"忽略"实现）。
        name = "c6confirm"
        self._plant(name)
        proc = cli(self.root, "advance", name, "--stop", "1", "--to", "完成（审核通过）",
                   "--confirm", "什么都没写也要过")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("unrecognized", proc.stderr)
        with self.assertRaises(TypeError):
            advance(self.root, name, 1, DONE, confirm="什么都没写也要过")
        self.assertEqual(stop_row(load_state(self.root, name), 1)["state"], NOT_STARTED)
        review(self.root, name, 1)
        tick_report(self.root, name)
        row = stop_row(load_state(self.root, name), 1)
        self.assertEqual(row["state"], DONE)
        self.assertEqual(row["confirm_quote"], "")

    def test_missing_review_record_blocks_completion(self):
        # 旧补偿（闸门）之外：没有独立审查记录不得完成（质量补偿）。
        # tick 会先自动启动停点 1，缺审查记录时它停在"进行中"，清单点名 spec_review。
        name = "c6noreview"
        self._plant(name)
        out = tick_report(self.root, name)
        self.assertIn("spec_review", out)
        self.assertIn("自动完成", out)
        self.assertEqual(stop_row(load_state(self.root, name), 1)["state"], RUNNING)

    def test_status_tells_the_new_model(self):
        # 旧断言："代为执行" → 新断言：status 给出 tick 自动启动/送审/完成的下一步，
        # 且说明依赖已定稿时由 tick 自动置进行中；tick 完成后当前位置前移。
        from framework.engine import status_report
        name = "c6hint"
        self._plant(name)
        text = status_report(self.root, name)
        self.assertIn("下一停点：信息输入（行 1", text)
        self.assertIn("tick 自动启动/送审/完成", text)
        self.assertIn("依赖已定稿：跑 `tick` 即自动置进行中", text)
        review(self.root, name, 1)
        tick_report(self.root, name)
        self.assertEqual(stop_row(load_state(self.root, name), 1)["state"], DONE)
        self.assertIn("下一停点：处理流程梳理（行 2", status_report(self.root, name))

    def test_gates_still_run_first(self):
        # 旧断言：闸门未过时 advance 抛 EngineError。
        # 新断言：闸门未过时 tick 不完成该停点（停在"进行中"），清单报出闸门规则号。
        name = "c6gate"
        self._plant(name)
        from framework.state import sys_dir
        path = "%s/info_input/%s_info_overview.md" % (sys_dir(self.root, name), name)
        review(self.root, name, 1)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text.replace("## 5. 红线五问", "## 6. 别的"))
        out = tick_report(self.root, name)
        self.assertIn("[S1]", out)
        self.assertEqual(stop_row(load_state(self.root, name), 1)["state"], RUNNING)


class DecisionDispatchTests(RepoTest):
    """方向与数值类裁决是红线动作，凭点选来源（--from/--pick）即入库；
    不再要 --confirm、不再要任何放行令牌，无来源一律拒收。"""

    def test_direction_decision_commits_without_a_terminal_or_token(self):
        name = "dirdisp"
        init_sys(self.root, name)
        # 行 3 → 阶段 2；候选项写成正文本身，好断言入库正文。
        did = decide(self.root, name, "模块划分取甲", "方向", 3,
                     options="模块划分取甲|其他")
        self.assertEqual(did, "D2-001")
        row = load_state(self.root, name)["decisions"]["2"][0]
        self.assertEqual(row["kind"], "方向")
        self.assertEqual(row["content"], "模块划分取甲")
        self.assertEqual(row["stop"], 3, "裁决记下自己的停点（override 级联起点）")

    def test_direction_decision_needs_a_pick_source_not_a_token(self):
        # 旧断言：缺令牌时报"令牌" → 新断言：令牌已删除，拒收理由只有
        # "必须有点选来源"，且拦下不占 D 号。
        name = "dirneed"
        init_sys(self.root, name)
        with self.assertRaises(EngineError) as ctx:
            commit_decision(self.root, name, content="模块划分取甲", kind="方向", stop=3)
        message = str(ctx.exception)
        self.assertIn("必须有点选来源", message)
        self.assertNotIn("令牌", message)
        state = load_state(self.root, name)
        self.assertEqual(state["decisions"]["2"], [])
        self.assertEqual(state["seq"]["D"]["2"], 0)


class MilestoneStopTests(RepoTest):
    """行 6（还有 11、12）：tick 只置送审态"待里程碑"，完成留给 milestone confirm；
    advance 不置完成（已收窄）；终端照抄留给 M3。"""

    def _to_stop6_pending(self, name):
        init_sys(self.root, name)
        plant_sample(self.root, name)
        for sid in range(1, 6):
            if sid == 4:
                # 旧写法：直接 advance 启动 → 新写法：M1 确认前 tick 不启动停点 4。
                confirm_milestone(self.root, name, "M1")
            review(self.root, name, sid)
            tick_report(self.root, name)
        # 行 6 判据齐备：tick 把它置送审态（显示"待里程碑（M2）"）。
        review(self.root, name, 6)
        tick_report(self.root, name)
        self.assertEqual(stop_row(load_state(self.root, name), 6)["state"], PENDING)

    def test_milestone_stop_waits_for_milestone_confirm(self):
        # 旧断言：advance(→完成) 抛"待里程碑" → 新断言：advance 的
        # confirm 形参已删，置完成是 no-op；行 6 停在送审态、显示"待里程碑（M2）"，
        # tick 清单要求 milestone confirm。
        from framework.engine import display_state
        name = "c6tty"
        self._to_stop6_pending(name)
        with self.assertRaises(TypeError):
            advance(self.root, name, 6, DONE, confirm="通过")
        message = advance(self.root, name, 6, DONE)
        self.assertIn("已由 tick 自动处理", message)
        state = load_state(self.root, name)
        rowsix = stop_row(state, 6)
        self.assertEqual(rowsix["state"], PENDING)
        self.assertEqual(display_state(self.root, name, state, 6, rowsix), "待里程碑（M2）")
        self.assertIn("milestone %s confirm --id M2" % name, tick_report(self.root, name))

    def test_auto_complete_check_marks_waiting_milestone(self):
        from framework.engine import auto_complete_check
        name = "c6wait"
        self._to_stop6_pending(name)
        check = auto_complete_check(self.root, name, load_state(self.root, name), 6)
        # 判据齐备（ok=True、无原因），但归属里程碑：tick 只置送审态，不自动完成。
        self.assertTrue(check["ok"])
        self.assertEqual(check["reasons"], [])
        self.assertTrue(check["waiting_milestone"])
        self.assertEqual(check["milestone"], "M2")

    def test_criteria_run_before_the_milestone_refusal(self):
        # T4 保留：闸门没过时先报闸门，不报里程碑（顺序可查）。
        name = "c6order"
        self._to_stop6_pending(name)
        from framework.engine import auto_complete_check
        state = load_state(self.root, name)
        # 行 1–5 指纹未动、闸门应过：waiting_milestone 是唯一未满足项。
        check = auto_complete_check(self.root, name, state, 6)
        self.assertTrue(check["waiting_milestone"])
        self.assertEqual(check["reasons"], [])


if __name__ == "__main__":
    unittest.main()
