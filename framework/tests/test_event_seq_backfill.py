# 作者：vick 邮箱：ykun@yk9811.com

"""DEV-02：历史事件 seq 回填（代码里的 v3 迁移）+ 删净时间串兜底。

- 回填：按 events.jsonl 文件行序给缺 seq 的行赋单调递增 seq；已有 seq 不动；
  先备份（.state_backups/events_*.jsonl）再 mkstemp + os.replace 原子替换；
  二次加载不改变结果（幂等）。
- 只读路径（state_read，status 用）不得回填：它一个字都不能写。
- 删净兜底后，历史问题（无 registered_seq 字段）的"严格晚于"判定仍由回填后的 seq 兜住。
"""

import json
import os
import unittest

from framework.engine import EngineError, add_problem, close_problem, commit_decision
from framework.state import (
    EVENTS_FILE, STATE_BACKUP_DIR, init_sys, load_state, save, state_read, sys_dir,
)
from framework.tests.util import RepoTest


def _events_path(root, name):
    return os.path.join(sys_dir(root, name), EVENTS_FILE)


def _read_events(root, name):
    with open(_events_path(root, name), encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _strip_seq(root, name):
    """把事件日志改造成"S5 之前"的形态：每行都没有 seq。返回原始文本。"""
    path = _events_path(root, name)
    with open(path, encoding="utf-8") as fh:
        lines = [line for line in fh.read().splitlines() if line.strip()]
    stripped = []
    for line in lines:
        event = json.loads(line)
        event.pop("seq", None)
        stripped.append(json.dumps(event, ensure_ascii=False))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(stripped) + "\n")
    return "\n".join(stripped) + "\n"


def _backups(root, name):
    backup_dir = os.path.join(sys_dir(root, name), STATE_BACKUP_DIR)
    if not os.path.isdir(backup_dir):
        return []
    return sorted(fn for fn in os.listdir(backup_dir) if fn.startswith("events_"))


class EventSeqBackfillTests(RepoTest):
    def _legacy(self, name):
        """造一个"旧 events.jsonl（无 seq）+ 旧 state.json"的子系统。"""
        init_sys(self.root, name)
        did = commit_decision(self.root, name, content="接口归属取甲", kind="记录", stop=1)
        pid = add_problem(self.root, name, "阻断", 1, "缺时钟", "审查")
        state = load_state(self.root, name)
        next(p for p in state["problems"] if p["id"] == pid).pop("registered_seq")
        state["seq"]["event"] = 0
        save(self.root, name, state)
        _strip_seq(self.root, name)
        return pid, did

    def test_backfill_monotonic_idempotent_and_backed_up(self):
        name = "dev02"
        self._legacy(name)
        raw_before = _read_events(self.root, name)
        self.assertTrue(raw_before)
        self.assertTrue(all("seq" not in event for event in raw_before))
        state = load_state(self.root, name)          # 加载即迁移+回填
        events = _read_events(self.root, name)
        self.assertTrue(all(isinstance(event.get("seq"), int) for event in events))
        seqs = [event["seq"] for event in events]
        self.assertEqual(seqs, sorted(seqs))
        self.assertEqual(len(seqs), len(set(seqs)))
        self.assertEqual(seqs, list(range(1, len(seqs) + 1)))
        # 计数器抬到最大值，新事件接着往下排。
        self.assertGreaterEqual(int(state["seq"]["event"]), max(seqs))
        pid = add_problem(self.root, name, "待裁决", 1, "回填之后的新问题", "审查")
        fresh = _read_events(self.root, name)
        self.assertGreater(fresh[-1]["seq"], max(seqs))
        self.assertEqual(fresh[-1]["object"], pid)
        # 备份存在（回填前的原始文本）。
        backups = _backups(self.root, name)
        self.assertTrue(backups, "回填前必须留一份 events 备份")
        with open(os.path.join(sys_dir(self.root, name), STATE_BACKUP_DIR, backups[-1]),
                  encoding="utf-8") as fh:
            self.assertNotIn('"seq"', fh.read())
        # 幂等：再加载一次不改变事件日志（也不再产生新备份）。
        text = open(_events_path(self.root, name), encoding="utf-8").read()
        backups = _backups(self.root, name)
        load_state(self.root, name)
        load_state(self.root, name)
        self.assertEqual(open(_events_path(self.root, name), encoding="utf-8").read(), text)
        self.assertEqual(_backups(self.root, name), backups)

    def test_state_read_does_not_backfill(self):
        name = "dev02ro"
        self._legacy(name)
        raw = open(_events_path(self.root, name), encoding="utf-8").read()
        state_read(self.root, name)                  # status 走的只读路径
        self.assertEqual(open(_events_path(self.root, name), encoding="utf-8").read(), raw)
        self.assertEqual(_backups(self.root, name), [])
        load_state(self.root, name)                  # 写路径才回填
        self.assertNotEqual(open(_events_path(self.root, name), encoding="utf-8").read(), raw)
        self.assertTrue(_backups(self.root, name))

    def test_history_problem_and_evidence_strict_ordering_by_seq(self):
        name = "dev02order"
        pid, did = self._legacy(name)
        load_state(self.root, name)                  # 回填
        # 登记之前入库的裁决：回填后它的 seq 小于"问题登记"的 seq → 严格晚于拦住。
        with self.assertRaises(EngineError) as ctx:
            close_problem(self.root, name, pid, evidence=did)
        self.assertIn("不晚于问题", str(ctx.exception))
        # 登记之后产生的证据：seq 更大，照样能关。
        from framework.engine import record_run
        rid = record_run(self.root, name, {
            "capability": "sim", "status": "pass", "summary": "smoke pass",
        })
        self.assertEqual(close_problem(self.root, name, pid, evidence=rid), pid)

    def test_missing_seq_on_both_sides_is_refused(self):
        name = "dev02nolog"
        pid, did = self._legacy(name)
        load_state(self.root, name)
        # 日志被清过（两边都拿不到 seq）→ 直接拒，不再退回时间串口径。
        with open(_events_path(self.root, name), "w", encoding="utf-8") as fh:
            fh.write("")
        with self.assertRaises(EngineError) as ctx:
            close_problem(self.root, name, pid, evidence=did)
        self.assertIn("时序无法判定", str(ctx.exception))
        self.assertTrue(next(p for p in load_state(self.root, name)["problems"]
                             if p["id"] == pid)["open"])


if __name__ == "__main__":
    unittest.main()
