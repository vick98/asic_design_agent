# 作者：vick 邮箱：ykun@yk9811.com

"""`tick` 四相位自动化 + `advance` 收窄的验收。

- 只用"产物已就位（夹具）→ review record → tick"从行 1 走到 M2 就绪，全程不调用 advance；
- 已完成产物被改动后跑 tick：自动退回最早一个并按依赖级联，记"指纹失效退回"事件；
  该 tick 内新级联的下游留到下一次 tick 复核恢复（与旧节拍一致）；
- `advance` 只保留"退回进行中"与"带违例送审"两种真用法，其余调用不改状态并按成功退出。
"""

import json
import os
import unittest

from framework.engine import advance, tick_report
from framework.flow import DONE, NOT_STARTED, PENDING, RUNNING
from framework.state import init_sys, load_state, stop_row, sys_dir
from framework.tests.util import RepoTest, confirm_milestone, plant_sample, review


class TickAutopilotTests(RepoTest):
    def _plant(self, name):
        init_sys(self.root, name)
        plant_sample(self.root, name)

    def _state(self, name):
        return load_state(self.root, name)

    def _events(self, name):
        path = os.path.join(self.root, name, "events.jsonl")
        with open(path, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def _append(self, name, rel, text):
        with open(os.path.join(sys_dir(self.root, name), rel), "a", encoding="utf-8") as fh:
            fh.write(text)

    def test_tick_only_walk_to_m2_ready_without_advance(self):
        """行 1→M2 就绪：只用 review record（产物来自夹具）+ tick，不调用 advance。"""
        name = "s1walk"
        self._plant(name)
        for sid in (1, 2, 3):
            review(self.root, name, sid)
            tick_report(self.root, name)
        state = self._state(name)
        for sid in (1, 2, 3):
            self.assertEqual(stop_row(state, sid)["state"], DONE, "行 %d 应由 tick 自动完成" % sid)
        # 行 4 被 M1 阻塞：tick 不会自动启动它。
        tick_report(self.root, name)
        self.assertEqual(stop_row(self._state(name), 4)["state"], NOT_STARTED)
        confirm_milestone(self.root, name, "M1")
        for sid in (4, 5):
            review(self.root, name, sid)
            tick_report(self.root, name)
        self.assertEqual(stop_row(self._state(name), 5)["state"], DONE)
        # 行 6 是里程碑归属：判据齐备时 tick 把它置送审态（下一棒改名为"已送审"）。
        review(self.root, name, 6)
        text = tick_report(self.root, name)
        state = self._state(name)
        self.assertEqual(stop_row(state, 6)["state"], PENDING)
        self.assertIn("自动送审停点 6", text)
        # M2 就绪：清单里出现里程碑提示，且没有"可推进"的停点遗留。
        self.assertIn("里程碑 M2", text)
        self.assertIn("已就绪", text)

    def test_tick_retreats_stale_completed_stop_and_cascades(self):
        name = "s1stale"
        self._plant(name)
        for sid in (1, 2, 3):
            review(self.root, name, sid)
            tick_report(self.root, name)
        self._append(name, os.path.join("flow_doc", "%s_flow.md" % name), "\n事后补记一行。\n")
        text = tick_report(self.root, name)
        state = self._state(name)
        # 最早一个指纹失效的已完成停点退回进行中，并按依赖级联下游已启动的行。
        self.assertEqual(stop_row(state, 2)["state"], RUNNING)
        self.assertEqual(stop_row(state, 3)["state"], RUNNING)
        self.assertIn("指纹失效退回停点 2", text)
        events = [e for e in self._events(name) if e["action"] == "指纹失效退回"]
        self.assertTrue(events, "缺指纹失效退回事件")
        self.assertEqual(events[-1]["object"], "停点 2")
        self.assertIn("级联退回 3", events[-1]["evidence"])
        # 本 tick 新级联的下游留到下一次 tick：产物未变的行 3 复核恢复。
        text = tick_report(self.root, name)
        state = self._state(name)
        self.assertEqual(stop_row(state, 2)["state"], RUNNING, "产物改过的行 2 不自动恢复")
        self.assertEqual(stop_row(state, 3)["state"], DONE, "产物未变的行 3 复核恢复")
        self.assertIn("复核恢复停点 3", text)

    def test_advance_only_keeps_retreat_and_violation_send(self):
        name = "s1adv"
        self._plant(name)
        # 启动不是 advance 的事：不改状态，按成功返回一句说明。
        note = advance(self.root, name, 1, RUNNING)
        self.assertIn("已由 tick 自动处理", note)
        self.assertEqual(stop_row(self._state(name), 1)["state"], NOT_STARTED)
        # 普通送审与置完成同理。
        review(self.root, name, 1)
        tick_report(self.root, name)
        self.assertEqual(stop_row(self._state(name), 1)["state"], DONE)
        note = advance(self.root, name, 1, DONE)
        self.assertIn("已由 tick 自动处理", note)
        self.assertEqual(stop_row(self._state(name), 1)["state"], DONE)
        # 主动重做仍走 advance：退回进行中，并按依赖级联。
        note = advance(self.root, name, 1, RUNNING)
        self.assertIn("进行中", note)
        self.assertEqual(stop_row(self._state(name), 1)["state"], RUNNING)


if __name__ == "__main__":
    unittest.main()
