# 作者：vick 邮箱：ykun@yk9811.com

"""`tick --json` / `status --json`：命令行输出的机器可读版。

两条路径复用引擎的结构（`tick_data` / `status_data`）：
- `tick --json` 与普通 `tick` 一样推进状态，只把动作摘要与两张清单换成一份 JSON；
- `status --json` 是只读路径，与 `status --brief` 同一只读语义：
  不得写 `state.json`，也不得写 `events.jsonl`；
- 文本路径不变，仍输出「可推进的工作：」与「需要开发者：」两张清单。
"""

import json
import os

from framework.state import init_sys, load_state, stop_row
from framework.tests.util import RepoTest, cli, plant_sample, review

ACTION_KEYS = {"done", "started", "sent", "recovered", "retreated"}
STATUS_KEYS = ("sys", "where", "next", "updated", "rule_version", "fingerprint",
               "done", "current", "stale", "cascaded", "stale_modules",
               "blocking", "waivers", "summaries", "todo", "human")
TODO_KEYS = {"stop", "kind", "reasons", "command", "id", "text"}
HUMAN_KEYS = {"kind", "id", "stop", "text", "command", "reasons"}
TODO_KINDS = {"start", "finish", "fix", "milestone"}
HUMAN_KINDS = {"decision", "milestone", "escalation", "deferred"}
COMMAND_PREFIX = "python3 script/framework.py "


class JsonCliTests(RepoTest):
    def setUp(self):
        super().setUp()
        # RepoTest 的仓库副本按类共享，init_sys 不会重置已有子系统：
        # 每个用例用独立子系统名，避免用例间的状态互相污染。
        self.name = "json_" + self._testMethodName
        init_sys(self.root, self.name)
        plant_sample(self.root, self.name)

    def _json(self, *argv):
        proc = cli(self.root, *argv)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(proc.stdout.lstrip().startswith("{"),
                        "带 --json 时 stdout 只应有 JSON：%r" % proc.stdout[:200])
        return json.loads(proc.stdout)

    def test_tick_json_parses_and_advances_state(self):
        review(self.root, self.name, 1)
        data = self._json("tick", self.name, "--json")
        self.assertEqual(data["sys"], self.name)
        self.assertEqual(set(data["actions"]), ACTION_KEYS)
        for value in data["actions"].values():
            self.assertIsInstance(value, list)
        self.assertEqual(data["actions"]["done"], [1])
        self.assertIsInstance(data["rounds"], int)
        self.assertGreaterEqual(data["rounds"], 1)
        self.assertIsInstance(data["refused"], list)
        self.assertIsInstance(data["todo"], list)
        self.assertIsInstance(data["human"], list)
        # 与普通 tick 同一语义：这次调用真的推进了状态。
        self.assertEqual(stop_row(load_state(self.root, self.name), 1)["state"],
                         "完成（审核通过）")
        # JSON 里只有结构，不混文本清单标题。
        self.assertNotIn("可推进的工作：", json.dumps(data, ensure_ascii=False))

    def test_status_json_has_position_fields(self):
        data = self._json("status", self.name, "--json")
        for key in STATUS_KEYS:
            self.assertIn(key, data)
        self.assertEqual(data["sys"], self.name)
        self.assertFalse(data["done"])
        self.assertTrue(data["where"])
        self.assertTrue(data["next"])
        current = data["current"]
        self.assertEqual(current["stop"], 1)
        self.assertEqual(current["name"], "信息输入")
        self.assertTrue(current["command"].startswith(COMMAND_PREFIX), current)
        self.assertIsInstance(data["todo"], list)
        self.assertIsInstance(data["human"], list)

    def test_status_json_is_read_only(self):
        # 与 status --brief 同一只读语义：state.json/events.jsonl 的字节与 mtime 不动。
        review(self.root, self.name, 1)
        base = os.path.join(self.root, self.name)
        state_path = os.path.join(base, "state.json")
        events_path = os.path.join(base, "events.jsonl")

        def snapshot():
            stat = os.stat(state_path)
            with open(state_path, "rb") as fh:
                state_bytes = fh.read()
            with open(events_path, "rb") as fh:
                events_bytes = fh.read()
            return stat.st_mtime_ns, stat.st_size, state_bytes, events_bytes

        before = snapshot()
        data = self._json("status", self.name, "--json")
        self.assertEqual(before, snapshot(), "status --json 必须纯只读：不写状态、不记事件")
        self.assertEqual(data["sys"], self.name)

    def test_json_wins_over_brief(self):
        # 两个开关同时给出时 --json 优先（只输出结构，不打印简报文本）。
        data = self._json("status", self.name, "--brief", "--json")
        self.assertEqual(data["sys"], self.name)

    def test_items_have_machine_fields(self):
        # 造出两张清单都有内容的局面：行 1 完成推进、行 2 有待裁决问题。
        review(self.root, self.name, 1)
        self._json("tick", self.name, "--json")
        data = self._json("status", self.name, "--json")
        for item in data["todo"]:
            self.assertEqual(TODO_KEYS, set(item), item)
            self.assertIn(item["kind"], TODO_KINDS, item)
            self.assertTrue(item["command"].startswith(COMMAND_PREFIX), item)
            self.assertTrue(item["text"])
        for item in data["human"]:
            self.assertEqual(HUMAN_KEYS, set(item), item)
            self.assertIn(item["kind"], HUMAN_KINDS, item)
            self.assertTrue(item["command"].startswith(COMMAND_PREFIX), item)
            self.assertTrue(item["text"])

    def test_text_paths_still_print_the_two_lists(self):
        review(self.root, self.name, 1)
        status_proc = cli(self.root, "status", self.name)
        self.assertEqual(status_proc.returncode, 0, status_proc.stderr)
        self.assertIn("可推进的工作：", status_proc.stdout)
        self.assertIn("需要开发者：", status_proc.stdout)
        tick_proc = cli(self.root, "tick", self.name)
        self.assertEqual(tick_proc.returncode, 0, tick_proc.stderr)
        self.assertIn("可推进的工作：", tick_proc.stdout)
        self.assertIn("需要开发者：", tick_proc.stdout)

    def test_json_is_pure_json(self):
        # 不带 --json 是文本；带 --json 时 stdout 能被 json 整体解析（没有混排）。
        proc = cli(self.root, "status", self.name, "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        parsed = json.loads(proc.stdout)
        self.assertNotIn("所处：", proc.stdout)
        self.assertEqual(parsed["sys"], self.name)
