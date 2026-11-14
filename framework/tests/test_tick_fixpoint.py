# 作者：vick 邮箱：ykun@yk9811.com

"""一次 tick 推进到不动点：后一行的启动/完成与前行在同一事务内连续推进。

四相位在同一事务里循环：判据齐备的连续停点逐轮推进，某一轮没有动作为止；
动作按相位汇总返回，帮助文案只写现行口径（跑 tick 自动推进）。
"""

import inspect

from framework.engine import tick_data, tick_report
from framework.flow import DONE, RUNNING
from framework.state import init_sys, load_state, stop_row
from framework.tests.util import RepoTest, plant_sample, review


class TickFixpointTests(RepoTest):
    def _ready_two_rows(self, name):
        init_sys(self.root, name)
        plant_sample(self.root, name)
        # 行 1、2 的完成条件同时备好：一次 tick 应当连推两行。
        review(self.root, name, 1)
        review(self.root, name, 2)

    def test_one_tick_completes_two_ready_rows_and_starts_next(self):
        name = "fixpoint"
        self._ready_two_rows(name)
        text = tick_report(self.root, name)
        state = load_state(self.root, name)
        self.assertEqual(stop_row(state, 1)["state"], DONE)
        self.assertEqual(stop_row(state, 2)["state"], DONE)
        self.assertEqual(stop_row(state, 3)["state"], RUNNING)
        self.assertIn("自动完成停点 1、2", text)
        self.assertIn("自动启动停点", text)

    def test_actions_aggregate_across_rounds(self):
        name = "fixpointdata"
        self._ready_two_rows(name)
        data = tick_data(self.root, name)
        self.assertEqual(data["actions"]["done"], [1, 2])
        self.assertIn(1, data["actions"]["started"])
        self.assertIn(2, data["actions"]["started"])
        self.assertIn(3, data["actions"]["started"])
        self.assertGreaterEqual(data["rounds"], 3,
                                "两行完成 + 下一行启动至少要三轮才收敛")

    def test_second_tick_has_no_actions(self):
        name = "fixpointstill"
        self._ready_two_rows(name)
        tick_report(self.root, name)
        data = tick_data(self.root, name)
        self.assertEqual({key: value for key, value in data["actions"].items() if value}, {})
        self.assertEqual(stop_row(load_state(self.root, name), 3)["state"], RUNNING)

    def test_round_progress_phrase_is_gone(self):
        import framework.engine as engine
        self.assertNotIn("再跑一次 tick", inspect.getsource(engine))
