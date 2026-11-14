# 作者：vick 邮箱：ykun@yk9811.com

"""控制信息的只读查询面：`decision list/similar`、`problem list`、`item list`、`events`。

口径（rules/decision.md「查询」、rules/documents.md「控制信息与渲染物」）：
- 文本视图给人读，`--json` 给 agent——stdout 只有一份 JSON（与 `status --json`
  同一约定），错误走 stderr、退出码非 0；
- 查询是纯只读路径，不得写 `state.json`，也不得写 `events.jsonl`；
- `--grep` 命中的排前，正文相近（重合度）的排后并标进匹配列；
- `similar` 与入库守卫同一套重合度算法（阈值不同），是"一个内容一条裁决"
  的入库前比对出口。
"""

import json
import os

from framework.engine import (
    add_problem, commit_decision, item_open, override_decision, problem_defer,
)
from framework.state import init_sys, load_state
from framework.tests.util import RepoTest, cli, plant_sample


class QueryCliTests(RepoTest):
    def setUp(self):
        super().setUp()
        # RepoTest 的仓库副本按类共享：每个用例用独立子系统名，避免状态互相污染。
        self.name = "query_" + self._testMethodName
        init_sys(self.root, self.name)
        plant_sample(self.root, self.name)

    def _json(self, *argv):
        proc = cli(self.root, *argv)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(proc.stdout.lstrip().startswith("{"),
                        "带 --json 时 stdout 只应有 JSON：%r" % proc.stdout[:200])
        return json.loads(proc.stdout)

    def _run(self, *argv):
        proc = cli(self.root, *argv)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout

    def _record(self, content, stop=2):
        return commit_decision(self.root, self.name, content=content,
                               kind="记录", stop=stop)

    def _directional(self, text, options="取甲|取乙", stop=2):
        pid = add_problem(self.root, self.name, "待裁决", stop, text, "测试夹具",
                          options=options)
        return pid, commit_decision(self.root, self.name, kind="方向",
                                    from_problem=pid, pick="取乙")

    # ---------------------------------------------------------------- list --json

    def test_decision_list_json_contains_decisions_and_problems(self):
        pid, did = self._directional("帧长取舍：深度取多少")
        data = self._json("decision", self.name, "list", "--json")
        for key in ("sys", "stages", "decisions", "open_problems", "deferred_problems"):
            self.assertIn(key, data)
        self.assertEqual(data["sys"], self.name)
        self.assertEqual([row["id"] for row in data["decisions"]], [did])
        row = data["decisions"][0]
        self.assertEqual(row["kind"], "方向")
        self.assertEqual(row["source"], "%s/取乙" % pid)
        self.assertFalse(row["withdrawn"])
        self.assertEqual(row["revisions"], 0)
        # 点选后问题自动关闭：不在未关闭清单里。
        self.assertEqual(data["open_problems"], [])

    def test_decision_list_filters_kind_stop_stage_limit(self):
        did_dir = self._directional("帧长取舍：深度取多少")[1]
        did_rec = self._record("缓冲深度取1024，防溢出", stop=3)
        by_kind = self._json("decision", self.name, "list", "--kind", "记录", "--json")
        self.assertEqual([row["id"] for row in by_kind["decisions"]], [did_rec])
        by_stop = self._json("decision", self.name, "list", "--stop", "2", "--json")
        self.assertEqual([row["id"] for row in by_stop["decisions"]], [did_dir])
        # stage 过滤按 D 号前缀：与停点 2 的裁决同阶段的只有它自己。
        stage_of_dir = next(row for row in
                            self._json("decision", self.name, "list", "--json")["decisions"]
                            if row["id"] == did_dir)["stage"]
        by_stage = self._json("decision", self.name, "list", "--stage",
                              stage_of_dir, "--json")
        self.assertIn(did_dir, [row["id"] for row in by_stage["decisions"]])
        self.assertNotIn(did_rec, [row["id"] for row in by_stage["decisions"]])
        limited = self._json("decision", self.name, "list", "--limit", "1", "--json")
        self.assertEqual(len(limited["decisions"]), 1)

    def test_decision_list_grep_exact_then_near(self):
        did = self._record("帧样点数每帧28456样点约1.42ms，缓冲深度取1024")
        data = self._json("decision", self.name, "list", "--grep", "缓冲深度", "--json")
        self.assertEqual([row["id"] for row in data["decisions"]], [did])
        self.assertEqual(data["decisions"][0]["match"], "命中")
        # 换一种说法（同义改写）：子串不命中，落进重合度相近。
        near = self._json("decision", self.name, "list", "--grep",
                          "缓冲深度取1024，每帧28456样点约1.42ms", "--json")
        self.assertEqual([row["id"] for row in near["decisions"]], [did])
        self.assertTrue(near["decisions"][0]["match"].startswith("相近"),
                        near["decisions"][0]["match"])
        # 文本视图把匹配列与过滤条件写出来，供人复核。
        text = self._run("decision", self.name, "list", "--grep", "缓冲深度")
        self.assertIn("过滤条件：grep=缓冲深度", text)
        self.assertIn("命中", text)

    def test_decision_list_open_only(self):
        pid_open = add_problem(self.root, self.name, "待裁决", 2, "还差一个取舍", "测试夹具",
                               options="取甲|取乙")
        pid_defer = add_problem(self.root, self.name, "待裁决", 2, "等覆盖率结果再定",
                                "测试夹具", options="取甲|取乙")
        problem_defer(self.root, self.name, pid_defer, "M1", reason="等回归")
        text = self._run("decision", self.name, "list", "--open")
        self.assertIn("待裁决问题", text)
        self.assertIn("已推迟问题", text)
        self.assertNotIn("分阶段裁决", text)
        data = self._json("decision", self.name, "list", "--open", "--json")
        self.assertEqual(data["decisions"], [])
        self.assertEqual([row["id"] for row in data["open_problems"]], [pid_open])
        self.assertEqual([row["id"] for row in data["deferred_problems"]], [pid_defer])

    # ---------------------------------------------------------------- 单条全档

    def test_decision_detail_text_and_json_with_history(self):
        did = self._record("帧样点数每帧28456样点约1.42ms")
        override_decision(self.root, self.name, did, "深度改取2048", note="回归后修订")
        text = self._run("decision", self.name, "list", "--id", did)
        self.assertIn(did, text)
        self.assertIn("深度改取2048", text)
        self.assertIn("修订历史[1]", text)
        self.assertIn("帧样点数每帧28456样点约1.42ms", text)
        data = self._json("decision", self.name, "list", "--id", did, "--json")
        self.assertEqual(data["id"], did)
        self.assertEqual(len(data["history"]), 1)
        self.assertEqual(data["history"][0]["content"], "帧样点数每帧28456样点约1.42ms")
        self.assertEqual(data["note"], "回归后修订")
        self.assertNotIn("closing_problem", data)  # 记录类没有点选来源问题

    def test_decision_detail_shows_closing_problem(self):
        pid, did = self._directional("帧长取舍：深度取多少")
        data = self._json("decision", self.name, "list", "--id", did, "--json")
        self.assertEqual(data["closing_problem"]["id"], pid)
        self.assertIn("取乙", data["closing_problem"]["options"])

    def test_decision_detail_unknown_id_fails_clean(self):
        proc = cli(self.root, "decision", self.name, "list", "--id", "D9-999")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("没有裁决 D9-999", proc.stderr)
        self.assertEqual(proc.stdout, "")

    # ---------------------------------------------------------------- similar

    def test_similar_ranks_by_overlap(self):
        did = self._record("帧样点数每帧28456样点约1.42ms，缓冲深度取1024")
        text = self._run("decision", self.name, "similar", "--content",
                         "缓冲深度取1024，帧样点数每帧28456样点约1.42ms")
        self.assertIn(did, text)
        self.assertIn("override", text)
        data = self._json("decision", self.name, "similar", "--content",
                          "缓冲深度取1024，帧样点数每帧28456样点约1.42ms", "--json")
        self.assertEqual(data["similar"][0]["id"], did)
        self.assertGreaterEqual(data["similar"][0]["score"], 0.25)

    def test_similar_short_content_is_rejected(self):
        self._record("帧样点数每帧28456样点约1.42ms")
        proc = cli(self.root, "decision", self.name, "similar", "--content", "太短")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("太短", proc.stderr)
        self.assertIn("--grep", proc.stderr)

    def test_similar_no_content_is_rejected(self):
        proc = cli(self.root, "decision", self.name, "similar")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("--content", proc.stderr)

    # ---------------------------------------------------------------- problem / item

    def test_problem_list_json_and_filters(self):
        pid_decide = add_problem(self.root, self.name, "待裁决", 2, "帧长取舍：深度取多少",
                                 "测试夹具", options="取甲|取乙")
        pid_block = add_problem(self.root, self.name, "阻断", 3, "xdc 违例待查",
                                "测试夹具")
        by_kind = self._json("problem", self.name, "list", "--kind", "阻断", "--json")
        self.assertEqual([row["id"] for row in by_kind["problems"]], [pid_block])
        by_stop = self._json("problem", self.name, "list", "--stop", "3", "--json")
        self.assertEqual([row["id"] for row in by_stop["problems"]], [pid_block])
        by_grep = self._json("problem", self.name, "list", "--grep", "违例", "--json")
        self.assertEqual([row["id"] for row in by_grep["problems"]], [pid_block])
        # 点选入库即关闭：缺省清单里不再有它，--all 连已关闭一起给。
        commit_decision(self.root, self.name, kind="方向", from_problem=pid_decide,
                        pick="取乙")
        after = self._json("problem", self.name, "list", "--json")
        self.assertEqual([row["id"] for row in after["problems"]], [pid_block])
        everything = self._json("problem", self.name, "list", "--all", "--json")
        self.assertEqual(len(everything["problems"]), 2)
        text = self._run("problem", self.name, "list", "--all")
        self.assertIn("已关闭，证据 D", text)

    def test_problem_open_and_all_conflict(self):
        proc = cli(self.root, "problem", self.name, "list", "--open", "--all")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("--open 与 --all", proc.stderr)

    def test_item_list_json_and_text(self):
        item_open(self.root, self.name, "调试", "回读数据错位", side="tb")
        data = self._json("item", self.name, "list", "--json")
        self.assertEqual([row["id"] for row in data["items"]], ["M001"])
        self.assertEqual(data["items"][0]["side"], "tb")
        text = self._run("item", self.name, "list")
        self.assertIn("M001 调试，侧 tb 回读数据错位", text)

    # ---------------------------------------------------------------- events

    def test_events_query_json_grep_limit(self):
        self._directional("帧长取舍：深度取多少")
        data = self._json("events", self.name, "--json")
        self.assertEqual(data["sys"], self.name)
        self.assertGreaterEqual(data["count"], 3)
        self.assertEqual(data["events"][0]["action"], "初始化")
        picked = self._json("events", self.name, "--grep", "裁决入库", "--json")
        self.assertTrue(picked["count"])
        self.assertTrue(all(row["action"] == "裁决入库" for row in picked["events"]))
        tail = self._json("events", self.name, "--limit", "1", "--json")
        self.assertEqual(tail["count"], 1)
        self.assertEqual(tail["events"][-1]["seq"], data["events"][-1]["seq"])
        text = self._run("events", self.name, "--grep", "裁决入库")
        self.assertIn("裁决入库", text)

    def test_events_unknown_sys_fails_clean(self):
        proc = cli(self.root, "events", "no_such_sys")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("先执行 init", proc.stderr)

    # ---------------------------------------------------------------- 只读语义

    def test_query_commands_do_not_write(self):
        def fingerprints():
            state_path = os.path.join(self.root, self.name, "state.json")
            events_path = os.path.join(self.root, self.name, "events.jsonl")
            with open(state_path, "rb") as fh:
                state = fh.read()
            with open(events_path, "rb") as fh:
                events = fh.read()
            return state, events

        self._directional("帧长取舍：深度取多少")
        before = fingerprints()
        for argv in (
            ("decision", self.name, "list", "--json"),
            ("decision", self.name, "list", "--grep", "深度"),
            ("decision", self.name, "list", "--open"),
            ("decision", self.name, "similar", "--content", "深度取多少呢，取1024吧"),
            ("problem", self.name, "list", "--json"),
            ("item", self.name, "list", "--json"),
            ("events", self.name, "--json"),
        ):
            self._run(*argv)
        self.assertEqual(before, fingerprints(), "查询命令不得写 state.json/events.jsonl")
