# 作者：vick 邮箱：ykun@yk9811.com

"""v3 迁移、事件 seq、模块状态推导的 schema 用例。

- v2 → v3 迁移：旧状态名"待人工审核"→"已送审"、删 problems[].registered_line、
  模块条目只留证据与显式"退回"、补 seq.event/seq.G/golden/allow_violation；
- 时间戳到秒；证据"严格晚于"比事件 seq——**同一秒内**登记之前的证据照样被拒、
  同一秒内登记之后的证据照样通过（这两条只有 seq 口径拦得住/放得行）；
- 模块状态由文件与证据推导，`module --state` 只接受"退回"；
- golden 登记段与读写助手（CLI 与行 10 新鲜度闸门留给后续棒）。
"""

import contextlib
import json
import os
import unittest

from framework import engine
from framework.engine import (
    EngineError, add_problem, close_problem, commit_decision, module_state,
    record_run, set_module, tick_report,
)
from framework.flow import PENDING
from framework.state import (
    SCHEMA_VERSION, golden_add, golden_find, golden_records, init_sys, load_state,
    migrate, now, save, stop_row, sys_dir,
)
from framework.tests.util import RepoTest, plant_sample, review


@contextlib.contextmanager
def _frozen(second="2026-01-01 10:00:00"):
    """把 engine 的 now() 冻结到同一秒：时间维度打平后，只剩 seq 一个变量。"""
    saved = engine.now
    engine.now = lambda *args, **kwargs: second
    try:
        yield
    finally:
        engine.now = saved


class SchemaV3MigrationTests(RepoTest):
    def test_v2_state_migrates_to_v3(self):
        name = "v2mig"
        init_sys(self.root, name)
        state = load_state(self.root, name)
        # 造一份 v2 形态：旧状态名（v2 历史数据，迁移后应为"已送审"）、registered_line、
        # 模块里存着派生的 state、缺新字段。
        state["schema"] = 2
        stop_row(state, 4)["state"] = "待人工审核"
        state["problems"] = [{
            "id": "I001", "kind": "提示", "stop": 1, "text": "旧问题", "source": "",
            "time": "2026-01-01 10:00", "open": True, "options": [], "blocks": [],
            "registered_line": 7,
        }]
        state["modules"] = {
            "7": [{"name": "alu", "state": "审查通过", "kind": "rtl_review",
                   "author": "a", "reviewer": "b", "digest": "d1"}],
            "8": [{"name": name + "_top", "state": "连接通过"}],
            "9": [{"name": "tb", "state": "骨架"}],
        }
        state.pop("golden", None)
        state["seq"].pop("event", None)
        state["seq"].pop("G", None)
        for row in state["stops"]:
            row.pop("allow_violation", None)
        save(self.root, name, state)

        state = load_state(self.root, name)
        self.assertEqual(state["schema"], SCHEMA_VERSION)
        self.assertEqual(SCHEMA_VERSION, 4)
        # 状态名换新、旧名只在迁移函数里出现。
        self.assertEqual(stop_row(state, 4)["state"], "已送审")
        self.assertEqual(PENDING, "已送审")
        # 停点行补 allow_violation。
        for row in state["stops"]:
            self.assertIs(row["allow_violation"], False)
        # registered_line 删除（证据时序改比 seq）。
        self.assertNotIn("registered_line", state["problems"][0])
        # 模块条目：派生的 state 删掉，证据字段保留；行 8/9 没有证据的条目只剩名字。
        self.assertNotIn("state", state["modules"]["7"][0])
        self.assertEqual(state["modules"]["7"][0]["digest"], "d1")
        self.assertEqual(state["modules"]["8"][0], {"name": name + "_top"})
        self.assertEqual(state["modules"]["9"][0], {"name": "tb"})
        # 新段与计数器就位。
        self.assertEqual(state["golden"], [])
        self.assertIn("event", state["seq"])
        self.assertIn("G", state["seq"])

    def test_migration_is_idempotent(self):
        name = "v3idem"
        init_sys(self.root, name)
        state = load_state(self.root, name)
        once = json.dumps(state, sort_keys=True, ensure_ascii=False)
        again = migrate(json.loads(once))
        self.assertEqual(json.dumps(again, sort_keys=True, ensure_ascii=False), once)
        self.assertEqual(again["schema"], SCHEMA_VERSION)


class SeqOrderingTests(RepoTest):
    """同一秒内登记/证据的顺序只由事件 seq 决定。"""

    def test_same_second_evidence_before_and_after_registration(self):
        name = "seqsec"
        init_sys(self.root, name)
        with _frozen():
            # 先入库的裁决（同一秒内、登记之前）→ 不能当关闭证据。
            early = commit_decision(self.root, name, content="接口归属取甲", kind="记录", stop=1)
            pid = add_problem(self.root, name, "阻断", 1, "缺时钟", "审查")
            with self.assertRaises(EngineError) as ctx:
                close_problem(self.root, name, pid, evidence=early)
            self.assertIn("登记", str(ctx.exception))
            # 登记之后、同一秒内的运行记录 → 通过（时间串完全相同，只有 seq 放得行）。
            rid = record_run(self.root, name, {
                "capability": "lint", "status": "pass", "summary": "lint pass",
                "profile_id": "example", "scope": {"modules": ["alu"]},
                "checks": {"errors": 0},
            })
            self.assertEqual(close_problem(self.root, name, pid, evidence=rid), pid)
        state = load_state(self.root, name)
        problem = state["problems"][0]
        self.assertFalse(problem["open"])
        self.assertIsInstance(problem["registered_seq"], int)
        # 事件日志每行带单调 seq，且时间戳到秒。
        path = os.path.join(sys_dir(self.root, name), "events.jsonl")
        with open(path, encoding="utf-8") as fh:
            events = [json.loads(line) for line in fh if line.strip()]
        seqs = [event["seq"] for event in events]
        self.assertEqual(seqs, sorted(seqs))
        self.assertEqual(len(seqs), len(set(seqs)))
        self.assertRegex(events[-1]["time"], r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$")


class GoldenSchemaTests(RepoTest):
    """golden 持久化段：记录与读写助手（CLI/闸门留给后续棒）。"""

    def test_golden_add_find_and_validate(self):
        name = "goldenseg"
        init_sys(self.root, name)
        state = load_state(self.root, name)
        gid = golden_add(state, "testbench/alu/data/g.txt", "script/gen.py",
                         ["spec_doc/alu_spec.md"], "d1")
        self.assertEqual(gid, "G001")
        save(self.root, name, state)
        state = load_state(self.root, name)
        self.assertEqual([row["id"] for row in golden_records(state)], ["G001"])
        self.assertEqual(golden_find(state, "testbench/alu/data/g.txt")["gen"], "script/gen.py")
        self.assertEqual(state["seq"]["G"], 1)
        self.assertIn("time", golden_find(state, "testbench/alu/data/g.txt"))
        # 字段不齐直接拒绝：登记才可追溯。
        with self.assertRaises(ValueError):
            golden_add(state, "", "script/gen.py", ["a"], "d")
        with self.assertRaises(ValueError):
            golden_add(state, "d", "script/gen.py", [], "d")
        with self.assertRaises(ValueError):
            golden_add(state, "d", "script/gen.py", ["a"], "")


class ModuleDerivationTests(RepoTest):
    """模块清单由文件推导、状态由证据推导；`module --state` 只收"退回"。"""

    def test_module_state_derived_and_set_module_narrowed(self):
        name = "modder"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        base = sys_dir(self.root, name)
        state = load_state(self.root, name)
        # 没有任何登记：清单来自 rtl/，状态推导为"已生成"。
        self.assertEqual(module_state(state, base, "7", "alu"), "已生成")
        self.assertEqual(module_state(state, base, "8", name + "_top"), "已生成")
        for bad in ("已生成", "lint 通过", "审查通过", "连接通过", "骨架", "用例已装配"):
            with self.assertRaises(EngineError) as ctx:
                set_module(self.root, name, "7", "alu", bad)
            self.assertIn("只接受 退回", str(ctx.exception))
        set_module(self.root, name, "7", "alu", "退回")
        state = load_state(self.root, name)
        self.assertEqual(module_state(state, base, "7", "alu"), "退回")
        self.assertEqual(stop_row(state, 7)["state"], "进行中")
        # 新审查记录清掉退回覆盖：状态回到由证据推导（行 7 先要 lint 记录）。
        record_run(self.root, name, {
            "capability": "lint", "status": "pass", "summary": "lint pass",
            "profile_id": "example", "scope": {"modules": ["alu"]},
            "checks": {"errors": 0},
        })
        review(self.root, name, 7, module="alu")
        state = load_state(self.root, name)
        self.assertEqual(module_state(state, base, "7", "alu"), "审查通过")


if __name__ == "__main__":
    unittest.main()
