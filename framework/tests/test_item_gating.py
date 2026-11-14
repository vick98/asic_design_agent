# 作者：vick 邮箱：ykun@yk9811.com

"""回路侧并入调试事项（`--loop-side` 兼容层已删）。

命令行瘦身删掉了 `advance --loop-side` 参数与 `engine._loop_side_compat`：本文件
不再测兼容转换，改为**反向守卫**（CLI 传 `--loop-side` 必须 argparse 报错）。旧判据
"行 10 退回侧未闭合不得送审"的有效意图保留在"存在在途调试事项时行 7–12 不得送审/
完成"上——事项改由 `item open --side` 开，判据由 tick 的完成相位执行。
v1 → 当前章迁移里"未闭合 loop_side 转调试事项"的存活行为继续保留断言。
"""

import os
import unittest

from framework.engine import auto_complete_check, item_end, item_open, tick_report
from framework.flow import DONE, NOT_STARTED, RUNNING
from framework.state import init_sys, load_state, render, save, stop_row
from framework.tests.util import RepoTest, cli


class LoopSideRemovedTests(RepoTest):
    """--loop-side 兼容层已删；在途事项挡停点的常驻判据改由 item 驱动。"""

    def setUp(self):
        super().setUp()
        # init_sys 不重置已存在的 state.json，测试之间用独立子系统名隔离。
        self.name = "loop_" + self._testMethodName.replace("test_", "")
        init_sys(self.root, self.name)

    def _state(self):
        return load_state(self.root, self.name)

    def _rows_7_to_12_running(self):
        """把 1..6 置完成、7..12 置进行中：只测常驻判据，不测闸门（无指纹不判陈旧）。"""
        state = self._state()
        for row in state["stops"]:
            sid = int(row["id"])
            row["state"] = RUNNING if sid >= 7 else DONE
        save(self.root, self.name, state)

    def _reasons(self, sid):
        check = auto_complete_check(self.root, self.name, self._state(), sid)
        return "；".join(check["reasons"])

    def _status_text(self):
        render(self.root, self.name, self._state())
        with open(os.path.join(self.root, self.name, "%s_status.md" % self.name),
                  encoding="utf-8") as fh:
            return fh.read()

    def test_loop_side_flag_is_gone(self):
        # 反向守卫：--loop-side（连同 --confirm 兼容）整条链路已删，CLI 必须报错。
        proc = cli(self.root, "advance", self.name, "--stop", "10", "--to", "进行中",
                   "--loop-side", "tb")
        self.assertNotEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("unrecognized", proc.stderr, proc.stderr)
        # 被拒的调用不留任何痕迹：没有事项，行 10 未动。
        self.assertEqual(self._state()["items"], [])
        self.assertEqual(stop_row(self._state(), 10)["state"], NOT_STARTED)

    def test_open_item_blocks_stops_marked_blocked_by_items(self):
        # 旧判据"行 10 回路侧未闭合不得送审"的替身：常驻判据挪到事项上，事项由
        # `item open --side` 开。有在途调试事项时 tick 既不完成也不送审，7–12 停在
        # "进行中"；事项闭合后同一判据不再报事项（挡它的是闸门）。
        self._rows_7_to_12_running()
        mid = item_open(self.root, self.name, "调试", "行 10 退回侧未闭合", side="tb")
        out = tick_report(self.root, self.name)
        self.assertIn("在途调试事项", out)
        for sid in (7, 10, 12):
            self.assertEqual(stop_row(self._state(), sid)["state"], RUNNING,
                             "行 %d 不该被送审/完成" % sid)
            self.assertIn("在途调试事项", self._reasons(sid))
        item_end(self.root, self.name, mid, "L0")
        for sid in (7, 10, 12):
            self.assertNotIn("在途调试事项", self._reasons(sid))

    def test_status_renders_open_item_side(self):
        # 旧断言：状态文档有"行 9/10 回路侧"行 → 新断言：在途事项行带侧别与轮数
        # （事项由 `item open --side` 开，依据 schema 迁移后的状态文档）。
        mid = item_open(self.root, self.name, "调试", "行 10 退回侧未闭合", side="tb")
        text = self._status_text()
        self.assertIn("侧 tb", text)
        self.assertNotIn("回路侧", text)
        item_end(self.root, self.name, mid, "L0")
        self.assertIn("在途事项：（无）", self._status_text())


class LoopSideMigrationTests(RepoTest):
    """v1 的 loop_side 字段仍要被迁移成调试事项（字段删了，存量数据不能丢）。"""

    def test_migration_converts_open_loop_side(self):
        name = "loopmig"
        init_sys(self.root, name)
        state = load_state(self.root, name)
        state["loop_side"] = "rtl"
        state.pop("schema", None)
        save(self.root, name, state)
        migrated = load_state(self.root, name)
        self.assertEqual(migrated["schema"], 4)
        self.assertNotIn("loop_side", migrated)
        self.assertEqual(len(migrated["items"]), 1)
        self.assertEqual(migrated["items"][0]["side"], "rtl")
        self.assertIn("由旧回路侧", migrated["items"][0]["text"])
        self.assertNotIn("已闭合", self._status_text(name))

    def _status_text(self, name):
        render(self.root, name, load_state(self.root, name))
        with open(os.path.join(self.root, name, "%s_status.md" % name), encoding="utf-8") as fh:
            return fh.read()


if __name__ == "__main__":
    unittest.main()
