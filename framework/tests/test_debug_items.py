# 作者：vick 邮箱：ykun@yk9811.com

"""调试/综合优化事项：开/改/删、侧别、轮数与证据、结束即删、
L1 带 --sync、L2/L3 带 --decision、送审限制。"""

import os
import subprocess
import sys
import unittest

from framework.engine import (
    EngineError, advance, auto_complete_check, item_end, item_open, item_set, open_items,
    tick_report,
)
from framework.state import init_sys, load_state, render, save, stop_row
from framework.tests.util import RepoTest, checkout_root


def _script():
    return os.path.join(checkout_root(), "script", "framework.py")


def _run(args, root):
    env = os.environ.copy()
    env["ADF_ROOT"] = root
    return subprocess.run(
        [sys.executable, _script()] + args,
        env=env, capture_output=True, text=True,
    )


class ItemsTest(RepoTest):
    def setUp(self):
        super().setUp()
        # init_sys 不重置已存在的 state.json，测试之间用独立子系统名隔离。
        self.name = "items_" + self._testMethodName.replace("test_", "")
        init_sys(self.root, self.name)

    def _status_text(self):
        render(self.root, self.name, load_state(self.root, self.name))
        path = os.path.join(self.root, self.name, "%s_status.md" % self.name)
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def _set_rows(self, row10="进行中"):
        state = load_state(self.root, self.name)
        for row in state["stops"]:
            sid = int(row["id"])
            if sid <= 9:
                row["state"] = "完成（审核通过）"
            elif sid == 10:
                row["state"] = row10
        save(self.root, self.name, state)

    def test_open_set_end_and_render(self):
        mid = item_open(self.root, self.name, "调试", "rx_costas 环路轨迹异常", side="rtl")
        self.assertTrue(mid.startswith("M"))
        self.assertEqual([i["id"] for i in open_items(load_state(self.root, self.name))], [mid])
        text = self._status_text()
        self.assertIn(mid, text)
        self.assertIn("rx_costas 环路轨迹异常", text)
        self.assertIn("（未写）", text)
        self.assertIn("侧 rtl", text)
        self.assertIn("第 0 轮", text)
        # set 覆盖当前做法：事项行数不变，旧句子被顶掉；每 set 一轮数加一。
        before = text.count(mid)
        item_set(self.root, self.name, mid, "先抓 phi 首符号拍")
        after = self._status_text()
        self.assertIn("先抓 phi 首符号拍", after)
        self.assertNotIn("（未写）", after)
        self.assertIn("第 1 轮", after)
        self.assertEqual(after.count(mid), before)
        item_set(self.root, self.name, mid, "再看鉴相器误差")
        self.assertIn("第 2 轮", self._status_text())
        # 结束即删，状态文档不留墓碑。
        message = item_end(self.root, self.name, mid, "L0")
        self.assertIn("收尾", message)
        self.assertEqual(open_items(load_state(self.root, self.name)), [])
        self.assertNotIn(mid, self._status_text())

    def test_kind_text_and_side_validated(self):
        with self.assertRaises(EngineError) as ctx:
            item_open(self.root, self.name, "优化", "x")
        self.assertIn("--kind", str(ctx.exception))
        with self.assertRaises(EngineError) as ctx:
            item_open(self.root, self.name, "调试", "  ")
        self.assertIn("--text", str(ctx.exception))
        # 调试事项必须写明侧别。
        with self.assertRaises(EngineError) as ctx:
            item_open(self.root, self.name, "调试", "缺侧别")
        self.assertIn("--side", str(ctx.exception))
        with self.assertRaises(EngineError) as ctx:
            item_open(self.root, self.name, "调试", "侧别拼错", side="wave")
        self.assertIn("--side", str(ctx.exception))
        # 只有调试事项带侧别。
        with self.assertRaises(EngineError) as ctx:
            item_open(self.root, self.name, "综合优化", "x", side="rtl")
        self.assertIn("--side", str(ctx.exception))
        self.assertTrue(item_open(self.root, self.name, "综合优化", "不带侧别").startswith("M"))

    def test_evidence_accumulates_deduplicated(self):
        # --evidence 可重复，累加去重；end 时全部证据进事件日志（事件日志
        # 口径在 test_interaction_model 里验，这里验条目字段）。
        mid = item_open(self.root, self.name, "调试", "整帧比对不过", side="tb")
        item_set(self.root, self.name, mid, "抓 wave",
                 evidence=["work/dbg/case1_phi.json", "R001"])
        item_set(self.root, self.name, mid, "比对节点",
                 evidence=["work/dbg/case1_phi.json", "work/dbg/case1_nodes.txt"])
        item = load_state(self.root, self.name)["items"][0]
        self.assertEqual(item["evidence"],
                         ["work/dbg/case1_phi.json", "R001", "work/dbg/case1_nodes.txt"])
        self.assertEqual(item["rounds"], 2)

    def test_in_flight_limit_four(self):
        ids = [item_open(self.root, self.name, "调试", "事项 %d" % index, side="rtl")
               for index in range(4)]
        with self.assertRaises(EngineError) as ctx:
            item_open(self.root, self.name, "综合优化", "第五条")
        self.assertIn("先结束一条", str(ctx.exception))
        item_end(self.root, self.name, ids[0], "L0")
        self.assertTrue(item_open(self.root, self.name, "综合优化", "第五条").startswith("M"))

    def test_end_l1_requires_sync_and_item_survives_rejection(self):
        mid = item_open(self.root, self.name, "调试", "x", side="rtl")
        with self.assertRaises(EngineError) as ctx:
            item_end(self.root, self.name, mid, "L1")
        self.assertIn("--sync", str(ctx.exception))
        self.assertEqual(len(open_items(load_state(self.root, self.name))), 1)
        item_end(self.root, self.name, mid, "L1", sync="回修 rx_costas 逻辑块章")
        self.assertEqual(open_items(load_state(self.root, self.name)), [])
        state = load_state(self.root, self.name)
        # L1 不产生 D 号：--sync 不落库。
        self.assertEqual([row for rows in state["decisions"].values() for row in rows], [])

    def test_end_l2_l3_require_existing_decision(self):
        mid = item_open(self.root, self.name, "调试", "x", side="rtl")
        with self.assertRaises(EngineError) as ctx:
            item_end(self.root, self.name, mid, "L2", sync="回修端口表")
        self.assertIn("--decision", str(ctx.exception))
        with self.assertRaises(EngineError) as ctx:
            item_end(self.root, self.name, mid, "L2", sync="回修端口表", decision="D5-099")
        self.assertIn("不存在", str(ctx.exception))
        self.assertEqual(len(open_items(load_state(self.root, self.name))), 1)
        state = load_state(self.root, self.name)
        state["decisions"]["5"].append({
            "id": "D5-001", "content": "延迟缓冲两块改三块", "note": "",
            "kind": "方向", "time": "2026-10-15 10:00",
        })
        save(self.root, self.name, state)
        item_end(self.root, self.name, mid, "L2", sync="回修端口表与模块摘要", decision="D5-001")
        self.assertEqual(open_items(load_state(self.root, self.name)), [])

    def test_end_bad_level_rejected(self):
        mid = item_open(self.root, self.name, "调试", "x", side="rtl")
        with self.assertRaises(EngineError) as ctx:
            item_end(self.root, self.name, mid, "L4")
        self.assertIn("--level", str(ctx.exception))

    def test_unknown_item_rejected(self):
        with self.assertRaises(EngineError) as ctx:
            item_set(self.root, self.name, "M099", "x")
        self.assertIn("没有在途事项", str(ctx.exception))
        with self.assertRaises(EngineError):
            item_end(self.root, self.name, "M099", "L0")

    def _reasons(self, sid):
        """停点 sid 当前未完成的原因（tick 完成相位的同一判据）。"""
        check = auto_complete_check(self.root, self.name, load_state(self.root, self.name), sid)
        return "；".join(check["reasons"])

    def test_pending_rows_7_to_12_blocked_by_open_items(self):
        # 7–12 都置进行中：都允许送审，有在途调试事项时 tick 既不送审也不完成。
        state = load_state(self.root, self.name)
        for row in state["stops"]:
            row["state"] = "进行中" if int(row["id"]) >= 7 else "完成（审核通过）"
        save(self.root, self.name, state)
        mid = item_open(self.root, self.name, "调试", "x", side="rtl")
        out = tick_report(self.root, self.name)
        self.assertIn("在途调试事项", out)
        for sid in (7, 10, 12):
            self.assertEqual(stop_row(load_state(self.root, self.name), sid)["state"], "进行中")
            self.assertIn("在途调试事项", self._reasons(sid))
        item_end(self.root, self.name, mid, "L0")
        # 事项清零后，同一判据不再报事项；报什么由闸门决定，这里只看不是事项。
        for sid in (7, 10, 12):
            self.assertNotIn("在途调试事项", self._reasons(sid))

    def test_retreat_and_design_rows_ignore_items(self):
        self._set_rows(row10="已送审")
        item_open(self.root, self.name, "调试", "x", side="rtl")
        # 退回进行中不受事项限制。
        advance(self.root, self.name, 10, "进行中")
        self.assertEqual(load_state(self.root, self.name)["stops"][9]["state"], "进行中")
        # 行 1–6 不读事项表：同一判据里没有事项。
        self.assertNotIn("在途调试事项", self._reasons(6))

    def test_cli_roundtrip(self):
        proc = _run(["item", self.name, "open", "--kind", "综合优化",
                     "--text", "rx_mf 建立时间收紧"], self.root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        mid = proc.stdout.strip()
        proc = _run(["item", self.name, "set", "--id", mid, "--text", "流水线加一级寄存",
                     "--evidence", "work/dbg/a.json"], self.root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        proc = _run(["item", self.name, "list"], self.root)
        self.assertIn(mid, proc.stdout)
        self.assertIn("流水线加一级寄存", proc.stdout)
        self.assertIn("work/dbg/a.json", proc.stdout)
        proc = _run(["item", self.name, "end", "--id", mid, "--level", "L1"], self.root)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("--sync", proc.stderr)
        proc = _run(["item", self.name, "end", "--id", mid, "--level", "L1",
                     "--sync", "回修实现结构章"], self.root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        proc = _run(["item", self.name, "list"], self.root)
        self.assertEqual(proc.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
