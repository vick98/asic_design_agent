# 作者：vick 邮箱：ykun@yk9811.com

"""state 写路径、修订链渲染、并发写、模块条目合并、
事件日志与 schema 迁移的用例。

改前会失败的观察点：
- `save()` 是原地覆盖写：编码异常会把 `state.json` 留成半截文件（2026-10-14 事故）；
- 没有滚动备份；
- 没有只读校验入口 `verify_state`；
- `override` 过的裁决在渲染物里看不出被改过；
- `_atomic_write` 用固定临时名 `state.json.tmp`：3 个进程并发 `record_run`
  互相踩踏，2 个报 FileNotFoundError，120 条记录只剩 40 条；
- 模块条目的写入路径整条替换条目，审查证据全丢（现在条目只存证据，
  `set_module` 收窄为只接受"退回"，状态由 `module_state` 推导）；
- 没有 events.jsonl，"谁在何时做了什么"无从查起（现在每行带单调递增 seq）。
"""

import json
import os
import shutil
import subprocess
import sys
import unittest

from framework.engine import (
    EngineError, advance, module_state, record_event, record_run, set_module,
    tick_report,
)
from framework.state import (
    EVENTS_FILE, EVENT_STAGING_KEY, SCHEMA_VERSION, STATE_BACKUP_DIR, StateEncodingError,
    init_sys, load_state, migrate, save, state_path, state_read, state_txn, stop_row, sys_dir,
    verify_state,
)
from framework.tests.util import RepoTest, force_done, review


def _read_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


def _log_events(root, name):
    """events.jsonl 全量为事件 dict 列表（每次状态变更一行，行带单调 seq）。"""
    with open(os.path.join(root, name, EVENTS_FILE), encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


class StateWritePathTests(RepoTest):
    def setUp(self):
        super().setUp()
        self.name = "w1"
        init_sys(self.root, self.name)
        self.path = state_path(self.root, self.name)

    def test_encoding_error_leaves_old_file_intact(self):
        before = _read_bytes(self.path)
        state = load_state(self.root, self.name)
        # 模拟 --confirm 里的中文经 shell 变量展开成 lone surrogate 的情形。
        state["summary"].append({"time": "x", "text": "坏字符 \udcbc\udc88"})
        with self.assertRaises(StateEncodingError) as ctx:
            save(self.root, self.name, state)
        self.assertIn("未写入任何文件", str(ctx.exception))
        self.assertEqual(before, _read_bytes(self.path), "编码失败时旧文件必须字节不变")
        json.loads(_read_bytes(self.path).decode("utf-8"))  # 仍可解析
        self.assertFalse(os.path.exists(self.path + ".tmp"), "临时文件不得残留")

    def test_save_is_atomic_and_leaves_no_tmp(self):
        state = load_state(self.root, self.name)
        state["resume"] = "第二轮"
        save(self.root, self.name, state)
        self.assertFalse(os.path.exists(self.path + ".tmp"))
        self.assertEqual("第二轮", load_state(self.root, self.name)["resume"])

    def test_rolling_backups_keep_three(self):
        backup_dir = os.path.join(os.path.dirname(self.path), STATE_BACKUP_DIR)
        for index in range(4):
            state = load_state(self.root, self.name)
            state["resume"] = "第 %d 轮" % index
            save(self.root, self.name, state)
        names = sorted(fn for fn in os.listdir(backup_dir) if fn.endswith(".json"))
        self.assertEqual(3, len(names), "只保留最近 3 版：%s" % names)
        # 最新一版备份应等于"第 2 轮"（最后一次写入前的内容是第 2 轮）
        latest = os.path.join(backup_dir, names[-1])
        with open(latest, encoding="utf-8") as fh:
            self.assertEqual("第 2 轮", json.load(fh)["resume"])

    def test_verify_state_ok_and_failures(self):
        ok, message = verify_state(self.root, self.name)
        self.assertTrue(ok, message)
        self.assertIn("OK", message)

        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write('{"sys_name": "w1", ')
        ok, message = verify_state(self.root, self.name)
        self.assertFalse(ok)
        self.assertIn("不是合法 JSON", message)

        # 上一步已把文件写坏：删掉重来，再制造"缺必需键"的情形。
        os.remove(self.path)
        init_sys(self.root, self.name)
        state = load_state(self.root, self.name)
        del state["runs"]
        save(self.root, self.name, state)
        ok, message = verify_state(self.root, self.name)
        self.assertFalse(ok)
        self.assertIn("缺必需键", message)

    def test_verify_state_on_missing_sys(self):
        ok, message = verify_state(self.root, "nope")
        self.assertFalse(ok)
        self.assertIn("没有", message)


class DecisionHistoryRenderTests(RepoTest):
    def test_history_is_rendered(self):
        name = "w2"
        init_sys(self.root, name)
        state = load_state(self.root, name)
        state["decisions"]["0"].append({
            "id": "D0-001",
            "kind": "数值",
            "content": "补零 37080",
            "note": "来源 T009",
            "confirm_quote": "确认入库：x",
            "history": [{"content": "补零 37088", "note": "", "kind": "数值"}],
        })
        save(self.root, name, state)
        text = open(os.path.join(self.root, name, "%s_decision.md" % name),
                    encoding="utf-8").read()
        self.assertIn("已修订 1 次", text)
        self.assertIn("修订链", text)
        self.assertIn("补零 37088", text)


# ---------- 3 进程并发 record_run（事务语义验收） ----------

_CHILD = """
import sys
from framework.engine import record_run
root, name, count = sys.argv[1], sys.argv[2], int(sys.argv[3])
for _ in range(count):
    record_run(root, name, {"capability": "sim", "status": "pass", "summary": "并发写入"})
"""


class ConcurrentRecordRunTests(RepoTest):
    def test_three_processes_forty_record_runs_each(self):
        """3 个真进程各 40 次 record_run，runs 正好 120 条、seq.R=120、零报错。"""
        name = "conc1"
        init_sys(self.root, name)
        env = dict(os.environ, ADF_ROOT=self.root)
        procs = [subprocess.Popen(
            [sys.executable, "-c", _CHILD, self.root, name, "40"],
            cwd=self.root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            for _ in range(3)]
        failures = []
        for proc in procs:
            _out, err = proc.communicate(timeout=600)
            if proc.returncode != 0:
                failures.append(err.decode("utf-8", "replace"))
        self.assertEqual([], failures, "并发进程报错：%s" % failures)
        state = load_state(self.root, name)
        self.assertEqual(120, len(state["runs"]), "120 条记录一条不少")
        self.assertEqual(120, state["seq"]["R"])
        self.assertEqual(["R%03d" % i for i in range(1, 121)],
                         [run["id"] for run in state["runs"]],
                         "编号在锁内分配，无丢失无重复")


# ---------- 模块条目：只存证据，set_module 收窄为"退回" ----------

class ModuleEntryMergeTests(RepoTest):
    """模块条目只存证据（rtl_review 的 kind/digest/...）或显式"退回"；
    派生状态由 `module_state` 从文件与证据推出，`set_module` 其它状态一律拒绝。"""

    def setUp(self):
        super().setUp()
        self.name = "me1"
        shutil.rmtree(os.path.join(self.root, self.name), ignore_errors=True)
        init_sys(self.root, self.name)
        state = load_state(self.root, self.name)
        state["modules"]["7"].append({
            "name": "mod_a", "kind": "rtl_review", "digest": "digest-1",
            "findings": 3, "author": "作者A", "reviewer": "审查B",
            "time": "2026-01-01 10:00:00",
        })
        save(self.root, self.name, state)

    def _entries(self, mod, row="7"):
        state = load_state(self.root, self.name)
        return [item for item in state["modules"][row] if item.get("name") == mod]

    def test_set_module_retreat_preserves_review_fields(self):
        set_module(self.root, self.name, "7", "mod_a", "退回")
        entries = self._entries("mod_a")
        self.assertEqual(1, len(entries), "不得出现重名条目")
        entry = entries[0]
        self.assertEqual("退回", entry["state"])
        for key, want in (("kind", "rtl_review"), ("digest", "digest-1"), ("findings", 3),
                          ("author", "作者A"), ("reviewer", "审查B"),
                          ("time", "2026-01-01 10:00:00")):
            self.assertEqual(want, entry.get(key), "%s 被整条替换弄丢" % key)
        # 退回把该行打回进行中，并落"模块退回"事件（action 由"模块状态"改名）。
        self.assertEqual("进行中", stop_row(load_state(self.root, self.name), 7)["state"])
        retreats = [event for event in _log_events(self.root, self.name)
                    if event["action"] == "模块退回"]
        self.assertEqual(1, len(retreats), retreats)
        self.assertIn("mod_a", retreats[0]["object"])

    def test_new_retreat_entry_holds_only_name_and_override(self):
        set_module(self.root, self.name, "8", "top", "退回")
        entry = self._entries("top", "8")[0]
        # 不再凭空补 author/reviewer 这类审查字段：条目只留名字与显式退回覆盖。
        self.assertEqual({"name": "top", "state": "退回"}, entry)

    def test_set_module_rejects_manual_states(self):
        for bad in ("已生成", "lint 通过", "审查通过", "连接通过", "骨架", "用例已装配"):
            with self.assertRaises(EngineError) as ctx:
                set_module(self.root, self.name, "7", "mod_a", bad)
            self.assertIn("只接受 退回", str(ctx.exception))
        # 被拒的调用不改条目、不加派生的 state。
        entry = self._entries("mod_a")[0]
        self.assertNotIn("state", entry)
        self.assertEqual("未开始", stop_row(load_state(self.root, self.name), 7)["state"])

    def test_module_state_derived_from_lint_and_review_evidence(self):
        # `_mark_module` 已删除：状态改由证据推导——lint 运行记录 → "lint 通过"，
        # 对得上当前模块摘要的 rtl_review 条目 → "审查通过"。
        base = sys_dir(self.root, self.name)
        rtl = os.path.join(base, "rtl")
        os.makedirs(rtl, exist_ok=True)
        with open(os.path.join(rtl, "mod_a.sv"), "w", encoding="utf-8") as fh:
            fh.write("module mod_a; endmodule\n")
        state = load_state(self.root, self.name)
        self.assertEqual("已生成", module_state(state, base, "7", "mod_a"))
        record_run(self.root, self.name, {
            "capability": "lint", "status": "pass", "summary": "lint pass",
            "scope": {"modules": ["mod_a"]},
        })
        state = load_state(self.root, self.name)
        self.assertEqual("lint 通过", module_state(state, base, "7", "mod_a"))
        # 审查记录要带 report/<文件>.md，review() 会写好报告并把 mtime 顶到模块文件之后。
        review(self.root, self.name, 7, module="mod_a")
        state = load_state(self.root, self.name)
        self.assertEqual("审查通过", module_state(state, base, "7", "mod_a"))
        entry = [item for item in state["modules"]["7"] if item["name"] == "mod_a"][0]
        self.assertEqual("rtl_review", entry["kind"])
        self.assertNotIn("state", entry, "派生的状态值不进 state.json")


# ---------- 事件日志 ----------

class EventLogTests(RepoTest):
    def setUp(self):
        super().setUp()
        self.name = "ev1"
        shutil.rmtree(os.path.join(self.root, self.name), ignore_errors=True)
        init_sys(self.root, self.name)
        self.log = os.path.join(self.root, self.name, EVENTS_FILE)

    def _events(self):
        with open(self.log, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def test_init_and_record_run_append_exactly_one_line_each(self):
        first = self._events()
        self.assertEqual(1, len(first))
        self.assertEqual("init_sys", first[0]["cmd"])
        self.assertEqual("初始化", first[0]["action"])
        self.assertEqual(self.name, first[0]["object"])
        self.assertRegex(first[0]["time"], r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$",
                         "S5：时间戳精确到秒")
        os.environ["ADF_ACTOR"] = "代理-07"
        try:
            rid = record_run(self.root, self.name,
                             {"capability": "sim", "status": "pass", "summary": "ok"})
        finally:
            os.environ.pop("ADF_ACTOR", None)
        events = self._events()
        self.assertEqual(2, len(events), "一次状态变更恰好追加一行")
        event = events[-1]
        self.assertEqual({"time", "seq", "cmd", "actor", "action", "object", "evidence"},
                         set(event))
        self.assertEqual("record_run", event["cmd"])
        self.assertEqual("代理-07", event["actor"])
        self.assertEqual("运行记录", event["action"])
        self.assertEqual(rid, event["object"])
        # 每行 seq 单调递增（问题登记/证据时序据此判定，不再看事件行号）。
        self.assertEqual(1, first[0]["seq"])
        self.assertEqual(2, event["seq"])

    def test_default_actor_is_host(self):
        os.environ.pop("ADF_ACTOR", None)
        record_run(self.root, self.name,
                   {"capability": "sim", "status": "pass", "summary": "ok"})
        self.assertEqual("主持者", self._events()[-1]["actor"])

    def test_staging_key_never_enters_state_json(self):
        with state_txn(self.root, self.name, cmd="x") as state:
            record_event(state, "测试动作", obj="对象", evidence=["R001", "D0-001"])
        raw = open(state_path(self.root, self.name), encoding="utf-8").read()
        self.assertNotIn(EVENT_STAGING_KEY, raw)
        self.assertNotIn("测试动作", raw)
        event = self._events()[-1]
        self.assertEqual(["R001", "D0-001"], event["evidence"])

    def test_stop_change_logged_by_tick_and_advance(self):
        # 停点状态变更照样落事件日志（cmd/action/object/evidence 四件套齐全）。
        # 启动由 tick 自动做（cmd=tick、action=自动启动）；主动重做
        # （完成 → 进行中）仍是 advance 的真用法，日志口径不变。
        text = tick_report(self.root, self.name)
        self.assertIn("自动启动停点 1", text)
        event = self._events()[-1]
        self.assertEqual("tick", event["cmd"])
        self.assertEqual("自动启动", event["action"])
        self.assertEqual("停点 1", event["object"])
        self.assertTrue(event["evidence"], event)
        force_done(self.root, self.name, 1)
        advance(self.root, self.name, 1, "进行中")
        self.assertEqual("进行中", stop_row(load_state(self.root, self.name), 1)["state"])
        event = self._events()[-1]
        self.assertEqual("advance", event["cmd"])
        self.assertEqual("停点状态", event["action"])
        self.assertEqual("停点 1", event["object"])
        self.assertEqual("完成（审核通过） → 进行中", event["evidence"])


# ---------- 事务语义 ----------

class StateTxnTests(RepoTest):
    def setUp(self):
        super().setUp()
        self.name = "tx1"
        shutil.rmtree(os.path.join(self.root, self.name), ignore_errors=True)
        init_sys(self.root, self.name)
        self.path = state_path(self.root, self.name)
        self.log = os.path.join(self.root, self.name, EVENTS_FILE)

    def _state_bytes(self):
        with open(self.path, "rb") as fh:
            return fh.read()

    def _event_count(self):
        with open(self.log, encoding="utf-8") as fh:
            return sum(1 for line in fh if line.strip())

    def test_exception_writes_nothing_and_releases_lock(self):
        before = self._state_bytes()
        events = self._event_count()
        with self.assertRaises(RuntimeError):
            with state_txn(self.root, self.name, cmd="boom") as state:
                state["resume"] = "不得落盘"
                raise RuntimeError("事务中途失败")
        self.assertEqual(before, self._state_bytes(), "异常退出不写任何文件")
        self.assertEqual(events, self._event_count(), "异常退出不写事件日志")
        # 锁已释放：下一个事务正常提交
        with state_txn(self.root, self.name, cmd="ok") as state:
            state["resume"] = "第二轮"
        self.assertEqual("第二轮", load_state(self.root, self.name)["resume"])

    def test_txn_commit_refreshes_position_and_renders(self):
        with state_txn(self.root, self.name, cmd="x") as state:
            state["resume"] = "第三轮"
        state = load_state(self.root, self.name)
        self.assertTrue(state["position"]["updated"])
        self.assertTrue(state["position"]["rule_version"])
        text = open(os.path.join(self.root, self.name, "%s_status.md" % self.name),
                    encoding="utf-8").read()
        self.assertIn("第三轮", text)

    def test_atomic_write_leaves_no_tmp_leftovers(self):
        with state_txn(self.root, self.name, cmd="x") as state:
            state["resume"] = "第四轮"
        leftovers = [fn for fn in os.listdir(os.path.dirname(self.path)) if fn.endswith(".tmp")]
        self.assertEqual([], leftovers)
        self.assertFalse(os.path.exists(self.path + ".tmp"), "固定临时名不得再出现")

    def test_state_read_is_readonly_snapshot(self):
        before = self._state_bytes()
        state = state_read(self.root, self.name)
        self.assertEqual(self.name, state["sys_name"])
        self.assertEqual(SCHEMA_VERSION, state["schema"])
        self.assertEqual(before, self._state_bytes(), "只读助手不得写盘")

    def test_txn_on_missing_sys_fails_without_creating_state(self):
        with self.assertRaises(FileNotFoundError):
            with state_txn(self.root, "nope", cmd="x") as state:
                state["resume"] = "x"
        self.assertFalse(os.path.isfile(state_path(self.root, "nope")))


# ---------- schema 版本与迁移 ----------

class MigrationTests(RepoTest):
    def setUp(self):
        super().setUp()
        self.name = "mg1"
        shutil.rmtree(os.path.join(self.root, self.name), ignore_errors=True)
        init_sys(self.root, self.name)
        self.path = state_path(self.root, self.name)

    def _raw(self):
        with open(self.path, encoding="utf-8") as fh:
            return json.load(fh)

    def test_v1_state_is_migrated_on_load(self):
        state = load_state(self.root, self.name)
        row = stop_row(state, 6)
        row["human"] = True
        row["completed_once"] = True
        row["remark"] = "原备注保留"
        state["modules"]["7"].append({"name": "mod_a", "state": "审查通过", "digest": "d1"})
        state.pop("schema", None)
        save(self.root, self.name, state)
        raw = self._raw()
        self.assertNotIn("schema", raw, "构造的 v1 文件不应带 schema 键")
        self.assertIn("completed_once", raw["stops"][5])
        migrated = load_state(self.root, self.name)
        row = stop_row(migrated, 6)
        self.assertNotIn("human", row)
        self.assertNotIn("completed_once", row)
        self.assertEqual("原备注保留", row["remark"], "迁移只剥指定键，其余保留")
        entry = [item for item in migrated["modules"]["7"] if item["name"] == "mod_a"][0]
        self.assertEqual("", entry["author"])
        self.assertEqual("", entry["reviewer"])
        self.assertEqual("d1", entry["digest"])
        self.assertNotIn("state", entry, "派生的模块状态在 v3 迁移里删掉")
        self.assertIs(stop_row(migrated, 6)["allow_violation"], False, "v3 补齐 allow_violation")
        self.assertEqual(SCHEMA_VERSION, migrated["schema"])
        self.assertNotIn("schema", self._raw(), "load 只迁移内存副本，不写盘")

    def test_v2_file_migrates_to_v3_without_re_running_v1_rules(self):
        # 迁移按版本门槛逐级叠加：v2 文件只跑 v2→v3（旧状态名换新、registered_line
        # 删除、模块条目剥派生 state、补 seq/golden），v1 的剥键规则不再作用到它——
        # 未知键不被反复清洗；load 只迁移内存副本，不写盘。
        state = load_state(self.root, self.name)
        state["schema"] = 2
        stop_row(state, 4)["state"] = "待人工审核"
        stop_row(state, 6)["completed_once"] = True
        state["problems"] = [{
            "id": "I001", "kind": "提示", "stop": 1, "text": "旧问题", "source": "",
            "time": "2026-01-01 10:00", "open": True, "options": [], "blocks": [],
            "registered_line": 7,
        }]
        state["modules"]["7"] = [{"name": "mod_a", "state": "审查通过", "digest": "d1"}]
        state.pop("golden", None)
        state["seq"].pop("event", None)
        state["seq"].pop("G", None)
        for row in state["stops"]:
            row.pop("allow_violation", None)
        save(self.root, self.name, state)
        raw = self._raw()
        self.assertEqual(2, raw["schema"])
        self.assertEqual("待人工审核", raw["stops"][3]["state"])
        self.assertIn("completed_once", raw["stops"][5])
        migrated = load_state(self.root, self.name)
        self.assertEqual(SCHEMA_VERSION, migrated["schema"])
        self.assertEqual("已送审", stop_row(migrated, 4)["state"])
        self.assertNotIn("registered_line", migrated["problems"][0],
                         "证据时序改比事件 seq，registered_line 删除")
        self.assertNotIn("state", migrated["modules"]["7"][0])
        self.assertEqual("d1", migrated["modules"]["7"][0]["digest"])
        self.assertEqual([], migrated["golden"])
        self.assertIn("event", migrated["seq"])
        self.assertIn("G", migrated["seq"])
        self.assertTrue(stop_row(migrated, 6)["completed_once"], "v1 剥键规则不再作用")
        self.assertEqual(2, self._raw()["schema"], "load 只迁移内存副本，不写盘")

    def test_v1_migration_strips_delegate_loop_side_enter_structure(self):
        # 完整迁移：position.delegate 删除；未闭合 loop_side 转调试事项、
        # 已闭合丢弃；enter_structure 删除。
        state = load_state(self.root, self.name)
        state["position"]["delegate"] = "范围 阶段 3，到期 2999-12-31"
        state["enter_structure"] = True
        state["loop_side"] = "rtl"
        state.pop("schema", None)
        save(self.root, self.name, state)
        migrated = load_state(self.root, self.name)
        self.assertEqual(SCHEMA_VERSION, migrated["schema"])
        self.assertNotIn("delegate", migrated["position"])
        self.assertNotIn("enter_structure", migrated)
        self.assertNotIn("loop_side", migrated)
        self.assertEqual(len(migrated["items"]), 1)
        self.assertEqual(migrated["items"][0]["kind"], "调试")
        self.assertEqual(migrated["items"][0]["side"], "rtl")

    def test_v1_closed_loop_side_is_discarded(self):
        state = load_state(self.root, self.name)
        state["loop_side"] = "closed"
        state["loop_closed_at"] = "2026-10-15 10:00"
        state.pop("schema", None)
        save(self.root, self.name, state)
        migrated = load_state(self.root, self.name)
        self.assertNotIn("loop_side", migrated)
        self.assertNotIn("loop_closed_at", migrated)
        self.assertEqual(migrated["items"], [])

    def test_migration_change_leaves_an_extra_backup(self):
        # 迁移确实改动了内容时，事务提交在写盘前多留一份迁移前的备份
        #（引擎的所有写入都走 state_txn，备份因此覆盖全部真实路径）。
        state = load_state(self.root, self.name)
        state["loop_side"] = "spec"
        state.pop("schema", None)
        save(self.root, self.name, state)
        with state_txn(self.root, self.name, cmd="mig") as st:
            st["resume"] = "迁移后写一次"
        backup_dir = os.path.join(os.path.dirname(self.path), ".state_backups")
        names = sorted(fn for fn in os.listdir(backup_dir)
                       if fn.startswith("state_") and fn.endswith(".json"))
        self.assertGreaterEqual(len(names), 2, "迁移提交应留下多份备份")
        # 至少有一份备份是迁移前的旧版：还带着 loop_side。
        olds = []
        for fn in names:
            with open(os.path.join(backup_dir, fn), encoding="utf-8") as fh:
                olds.append(json.load(fh))
        self.assertTrue(any(old.get("loop_side") == "spec" for old in olds), olds)
        migrated = load_state(self.root, self.name)
        self.assertNotIn("loop_side", migrated)
        self.assertEqual(migrated["items"][0]["side"], "spec")

    def test_migrate_is_idempotent_and_extensible(self):
        state = {"stops": [{"id": 1, "human": True}], "modules": {"7": [{"name": "m"}]}}
        migrate(state)
        once = json.dumps(state, sort_keys=True)
        migrate(state)
        self.assertEqual(once, json.dumps(state, sort_keys=True))
        self.assertEqual(SCHEMA_VERSION, state["schema"])
        # v1→v2 的剥键与字段补齐、v2→v3 的停点行/计数器/golden 段、v3→v4 的
        # 问题类型退场与 thresholds 段都就位。
        self.assertNotIn("human", state["stops"][0])
        self.assertIs(state["stops"][0]["allow_violation"], False)
        self.assertEqual(0, state["seq"]["event"])
        self.assertEqual(0, state["seq"]["G"])
        self.assertEqual([], state["golden"])


if __name__ == "__main__":
    unittest.main()
