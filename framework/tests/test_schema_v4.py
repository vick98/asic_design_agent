# 作者：vick 邮箱：ykun@yk9811.com

"""schema v4 迁移与三项收敛：

1. 删除问题类型"提示"：`PROBLEM_KINDS` 只剩"阻断""待裁决"，`problem add --kind` 必填；
   存量 state 里的"提示"问题在 v3→v4 迁移里置关闭（不删数据）并记事件；
2. 收割上限可配置：`state["thresholds"]["marks_cap"]`，缺省不限；
3. `handoff set` 写 `state["resume"]`（恢复入口）；交接渲染 = 恢复入口 + 最近小结；
   旧 `handoff` 文本在迁移里搬进 `resume`。
"""

import json
import os
import unittest

from framework import engine
from framework.engine import (
    EngineError, add_problem, add_summary, commit_decision, set_handoff,
)
from framework.marks import harvest_marks, marks_plan
from framework.state import (
    SCHEMA_VERSION, init_sys, load_state, save, state_path, sys_dir,
)
from framework.tests.util import RepoTest, cli


def _read_events(root, name):
    path = os.path.join(sys_dir(root, name), "events.jsonl")
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


class SchemaV4MigrationTests(RepoTest):
    def _v3_file(self, name):
        """造一份 v3 形态的 state：两条问题（提示+阻断）、旧 handoff、缺新段。"""
        init_sys(self.root, name)
        state = load_state(self.root, name)
        state["schema"] = 3
        state.pop("resume", None)
        state.pop("thresholds", None)
        state["handoff"] = "旧交接：先看行 2 的流程。"
        state["problems"] = [
            {"id": "I001", "kind": "提示", "stop": 1, "text": "仅供参考的旧提示",
             "source": "", "time": "2026-01-01 10:00", "open": True,
             "options": [], "blocks": []},
            {"id": "I002", "kind": "提示", "stop": 2, "text": "已关闭的旧提示",
             "source": "", "time": "2026-01-01 10:01", "open": False,
             "options": [], "blocks": []},
            {"id": "I003", "kind": "阻断", "stop": 3, "text": "仍未关闭的阻断",
             "source": "", "time": "2026-01-01 10:02", "open": True,
             "options": [], "blocks": []},
        ]
        save(self.root, name, state)
        with open(state_path(self.root, name), encoding="utf-8") as fh:
            raw = json.load(fh)
        self.assertEqual(raw["schema"], 3, "夹具必须是 v3 文件")
        self.assertNotIn("resume", raw)
        return name

    def test_v3_state_migrates_to_v4_and_closes_hint_problems(self):
        name = self._v3_file("migv4")
        state = load_state(self.root, name)
        self.assertEqual(state["schema"], SCHEMA_VERSION)
        self.assertEqual(SCHEMA_VERSION, 4)
        problems = {row["id"]: row for row in state["problems"]}
        # 提示类型退场：置关闭、数据保留（kind 原样留着，供审计）。
        self.assertFalse(problems["I001"]["open"], "存量提示问题应被迁移置关闭")
        self.assertEqual(problems["I001"]["kind"], "提示", "迁移不删数据，只置关闭")
        self.assertFalse(problems["I002"]["open"])
        self.assertTrue(problems["I003"]["open"], "阻断问题不受影响")
        # 旧 handoff 文本搬进 resume，旧字段不留在 v4 文件里。
        self.assertEqual(state["resume"], "旧交接：先看行 2 的流程。")
        self.assertNotIn("handoff", state)
        self.assertIsInstance(state.get("thresholds"), dict)

    def test_migration_writes_close_events_on_next_commit(self):
        name = self._v3_file("migev")
        add_summary(self.root, name, "触发一次写事务")
        state = load_state(self.root, name)
        self.assertEqual(state["schema"], SCHEMA_VERSION)
        events = _read_events(self.root, name)
        closed = [event for event in events
                  if event.get("action") == "问题关闭"
                  and event.get("object") == "I001"]
        self.assertTrue(closed, "迁移关闭存量问题要落事件：%s" % events)
        self.assertIn("v3→v4", str(closed[-1].get("evidence")))
        # 已关闭的提示不再重复记事件（幂等：再加载不产生新事件）。
        before = len(_read_events(self.root, name))
        load_state(self.root, name)
        load_state(self.root, name)
        self.assertEqual(len(_read_events(self.root, name)), before)

    def test_stray_handoff_on_v4_file_moves_to_resume(self):
        name = "stray"
        init_sys(self.root, name)
        state = load_state(self.root, name)
        state.pop("resume", None)
        state["handoff"] = "v4 文件里残留的旧字段"
        save(self.root, name, state)
        state = load_state(self.root, name)
        self.assertEqual(state["schema"], SCHEMA_VERSION)
        self.assertEqual(state["resume"], "v4 文件里残留的旧字段")
        self.assertNotIn("handoff", state)


class ProblemKindTests(RepoTest):
    def test_problem_kinds_are_two_and_hint_rejected(self):
        self.assertEqual(engine.PROBLEM_KINDS, ("阻断", "待裁决"))
        name = "kind"
        init_sys(self.root, name)
        with self.assertRaises(EngineError):
            add_problem(self.root, name, "提示", 1, "提示类型已退场")
        pid = add_problem(self.root, name, "阻断", 1, "缺前置输入")
        self.assertEqual(
            [row["id"] for row in load_state(self.root, name)["problems"]], [pid])

    def test_cli_kind_required_and_hint_not_a_choice(self):
        name = "kindcli"
        init_sys(self.root, name)
        missing = cli(self.root, "problem", name, "add", "--stop", "1", "--text", "缺输入")
        self.assertNotEqual(missing.returncode, 0, "problem add 的 --kind 必须必填")
        hint = cli(self.root, "problem", name, "add", "--kind", "提示",
                   "--stop", "1", "--text", "提示类型已退场")
        self.assertNotEqual(hint.returncode, 0, "提示不再是合法的问题类型")
        ok = cli(self.root, "problem", name, "add", "--kind", "待裁决",
                 "--stop", "1", "--text", "取甲还是取乙", "--options", "取甲|取乙")
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertIn("I001", ok.stdout)


class MarksCapTests(RepoTest):
    MARKS = ["mark: 第 %d 处意见" % index for index in range(1, 7)]

    def _plant(self, name):
        init_sys(self.root, name)
        _write(os.path.join(sys_dir(self.root, name), "info_input",
                            "%s_info_overview.md" % name),
               "\n".join(self.MARKS) + "\n")

    def test_default_harvest_has_no_cap(self):
        name = "markuncapped"
        self._plant(name)
        done = harvest_marks(self.root, name, "记录", 1)
        self.assertEqual(len(done), 6, "缺省不限：一次收割全部待收割标记")
        self.assertEqual(marks_plan(self.root, name)[0], [])

    def test_marks_cap_threshold_is_honored(self):
        name = "markcap"
        self._plant(name)
        state = load_state(self.root, name)
        state["thresholds"]["marks_cap"] = 2
        save(self.root, name, state)
        done = harvest_marks(self.root, name, "记录", 1)
        self.assertEqual(len(done), 2, "state.thresholds.marks_cap 生效")
        fresh, known = marks_plan(self.root, name)
        self.assertEqual((len(fresh), len(known)), (4, 2))

    def test_cli_harvest_output_reflects_no_cap(self):
        name = "markcli"
        self._plant(name)
        proc = cli(self.root, "marks", name, "--harvest", "--kind", "记录", "--stop", "1")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("已收割 6 条", proc.stdout)
        self.assertNotIn("上限", proc.stdout, "缺省口径下不再有固定上限")


class ResumeTests(RepoTest):
    def test_blank_uses_resume_not_handoff(self):
        from framework.state import blank
        state = blank("demo")
        self.assertIn("resume", state)
        self.assertNotIn("handoff", state)

    def test_set_handoff_writes_resume_and_status_renders_it(self):
        name = "resume"
        init_sys(self.root, name)
        add_summary(self.root, name, "本轮把闸门口径补齐。")
        set_handoff(self.root, name, "恢复入口：先核对行 4 的接口口径。")
        state = load_state(self.root, name)
        self.assertEqual(state["resume"], "恢复入口：先核对行 4 的接口口径。")
        self.assertNotIn("handoff", state)
        with open(os.path.join(sys_dir(self.root, name), "%s_status.md" % name),
                  encoding="utf-8") as fh:
            text = fh.read()
        section = text.split("## 6. 恢复入口", 1)[1]
        self.assertIn("恢复入口：先核对行 4 的接口口径。", section)
        self.assertIn("最近小结", section)
        self.assertIn("本轮把闸门口径补齐。", section)

    def test_cli_handoff_still_supported(self):
        name = "resumecli"
        init_sys(self.root, name)
        proc = cli(self.root, "handoff", name, "set", "--text", "命令行写恢复入口")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(load_state(self.root, name)["resume"], "命令行写恢复入口")


class DecisionBucketsStillModelDrivenTests(RepoTest):
    def test_commit_into_model_stage_bucket(self):
        name = "bucket"
        init_sys(self.root, name)
        did = commit_decision(self.root, name, content="位宽取 8", kind="记录", stop=1)
        self.assertEqual(did, "D0-001")
        self.assertEqual(load_state(self.root, name)["schema"], SCHEMA_VERSION)


if __name__ == "__main__":
    unittest.main()
