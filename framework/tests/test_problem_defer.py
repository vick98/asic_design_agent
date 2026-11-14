# 作者：vick 邮箱：ykun@yk9811.com

"""推迟决定：问题保持打开、不领 D 号，条件满足后再由 tick/status 重新列出。

- `problem defer --until <停点号|M1>` 只标推迟，不关问题；
- 推迟条件满足前不重复列进"需要开发者"；条件满足后以 `deferred` 项重新列出；
- 覆盖范围内还有推迟问题的里程碑确认被拒；
- "推迟决定"是保留词，不能当作裁决点选入库（含 mark 收割）。
"""

import os

from framework.engine import (
    EngineError, add_problem, commit_decision, milestone_confirm, problem_defer,
    status_data, tick_report,
)
from framework.marks import harvest_marks
from framework.state import init_sys, load_state, sys_dir
from framework.tests.util import (
    RepoTest, cli, confirm_milestone, force_done, plant_sample, review,
    write_milestone_notes,
)


class ProblemDeferTests(RepoTest):
    def _problem(self, name, stop=2, options="取甲|取乙", blocks=""):
        return add_problem(self.root, name, "待裁决", stop, "帧窗口取行 2 还是行 3 口径",
                           "测试夹具", options=options, blocks=blocks)

    def _m1_ready(self, name):
        init_sys(self.root, name)
        plant_sample(self.root, name)
        pid = self._problem(name)
        problem_defer(self.root, name, pid, until="M2", reason="等规格冻结")
        for sid in (1, 2, 3):
            review(self.root, name, sid)
        tick_report(self.root, name)
        write_milestone_notes(self.root, name, "M1")
        return pid

    def _human_ids(self, name):
        data = status_data(self.root, name)
        return [item for item in data["human"] if item["id"] == "I001"]

    def test_defer_keeps_problem_open_and_records_until(self):
        name = "deferbasic"
        init_sys(self.root, name)
        pid = self._problem(name)
        self.assertEqual(problem_defer(self.root, name, pid, until="4", reason="等接口定义"),
                         pid)
        problem = next(item for item in load_state(self.root, name)["problems"]
                       if item["id"] == pid)
        self.assertTrue(problem["open"], "推迟不是裁决，问题保持打开")
        deferred = problem["deferred"]
        self.assertEqual(deferred["until"], "4")
        self.assertEqual(deferred["reason"], "等接口定义")
        self.assertTrue(deferred["time"])
        with open(os.path.join(sys_dir(self.root, name), "events.jsonl"),
                  encoding="utf-8") as fh:
            self.assertIn("问题推迟", fh.read())

    def test_defer_rejects_unknown_closed_or_invalid_until(self):
        name = "deferbad"
        init_sys(self.root, name)
        with self.assertRaises(EngineError):
            problem_defer(self.root, name, "I999", until="4")
        pid = self._problem(name)
        for until in ("0", "13", "M9", ""):
            with self.assertRaises(EngineError, msg=until):
                problem_defer(self.root, name, pid, until=until)
        closed = add_problem(self.root, name, "阻断", 1, "仅供参考", "测试夹具")
        from framework.engine import close_problem, record_run
        rid = record_run(self.root, name, {
            "capability": "sim", "status": "pass", "summary": "smoke pass",
        })
        close_problem(self.root, name, closed, evidence=rid)
        with self.assertRaises(EngineError):
            problem_defer(self.root, name, closed, until="4")

    def test_deferred_problem_visible_while_blocking_unconfirmed_milestone(self):
        name = "deferstop"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        pid = self._problem(name)
        problem_defer(self.root, name, pid, until="1")
        items = self._human_ids(name)
        self.assertEqual(len(items), 1, items)
        self.assertEqual(items[0]["kind"], "deferred")
        self.assertIn("仍阻塞", items[0]["text"])

    def test_deferred_problem_stays_listed_until_milestone_confirmed(self):
        name = "deferms"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        pid = self._problem(name)
        problem_defer(self.root, name, pid, until="M1")
        for sid in (1, 2, 3):
            review(self.root, name, sid)
        tick_report(self.root, name)          # 行 1–3 完成；M1 缺结论摘要 → 未就绪
        self.assertEqual(len(self._human_ids(name)), 1)
        write_milestone_notes(self.root, name, "M1")
        items = self._human_ids(name)
        self.assertEqual(len(items), 1, items)
        self.assertEqual(items[0]["kind"], "deferred")

    def test_milestone_confirm_rejects_deferred_covered_problem(self):
        name = "deferconfirm"
        pid = self._m1_ready(name)
        with self.assertRaises(EngineError) as ctx:
            milestone_confirm(self.root, name, "M1", pick="通过")
        message = str(ctx.exception)
        self.assertIn(pid, message)
        self.assertIn("停点 2", message)
        self.assertIn("M2", message)

    def test_decision_commit_rejects_defer_reserved_pick(self):
        name = "deferpick"
        init_sys(self.root, name)
        pid = self._problem(name, options="取甲|推迟决定")
        with self.assertRaises(EngineError) as ctx:
            commit_decision(self.root, name, kind="方向", from_problem=pid, pick="推迟决定")
        message = str(ctx.exception)
        self.assertIn("problem", message)
        self.assertIn("defer", message)
        state = load_state(self.root, name)
        self.assertEqual(state["decisions"]["1"], [])
        problem = next(item for item in state["problems"] if item["id"] == pid)
        self.assertTrue(problem["open"], "被拒的点选不关问题、不领 D 号")

    def test_mark_harvest_rejects_defer_reserved_word(self):
        name = "defermark"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        doc = os.path.join(sys_dir(self.root, name), "flow_doc", "%s_flow.md" % name)
        with open(doc, "a", encoding="utf-8") as fh:
            fh.write("\nmark: 推迟决定\n")
        with self.assertRaises(EngineError) as ctx:
            harvest_marks(self.root, name, "记录", 2)
        self.assertIn("defer", str(ctx.exception))
        self.assertEqual(load_state(self.root, name)["decisions"]["1"], [])

    def test_decision_doc_separates_deferred_section(self):
        name = "deferdoc"
        init_sys(self.root, name)
        pid = self._problem(name)
        problem_defer(self.root, name, pid, until="M2", reason="等规格冻结")
        with open(os.path.join(sys_dir(self.root, name), "%s_decision.md" % name),
                  encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("已推迟问题", text)
        self.assertIn(pid, text)
        self.assertIn("M2", text)
        self.assertIn("等规格冻结", text)

    def test_status_doc_marks_deferred_problems_separately(self):
        name = "deferstatus"
        init_sys(self.root, name)
        open_pid = add_problem(self.root, name, "待裁决", 2, "普通未关闭问题", "测试夹具")
        pid = self._problem(name)
        problem_defer(self.root, name, pid, until="4", reason="等接口定义")
        with open(os.path.join(sys_dir(self.root, name), "%s_status.md" % name),
                  encoding="utf-8") as fh:
            text = fh.read()
        section = text.split("## 5. 待解决问题", 1)[1].split("\n## ", 1)[0]
        self.assertIn("| %s |" % open_pid, section, "普通问题仍在待解决表里")
        self.assertIn("已推迟", section)
        self.assertIn(pid, section)
        self.assertIn("4", section)
        self.assertNotIn("| %s |" % pid, section, "推迟问题不混进普通行")

    def test_cli_defer(self):
        name = "defercli"
        init_sys(self.root, name)
        pid = self._problem(name)
        proc = cli(self.root, "problem", name, "defer", "--id", pid, "--until", "4",
                   "--reason", "等接口定义")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        problem = next(item for item in load_state(self.root, name)["problems"]
                       if item["id"] == pid)
        self.assertEqual(problem["deferred"]["until"], "4")

    def test_deferred_until_unconfirmed_milestone_is_listed(self):
        name = "deferm2"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        for sid in (1, 2, 3):
            force_done(self.root, name, sid)
        confirm_milestone(self.root, name, "M1")
        for sid in (4, 5, 6):
            force_done(self.root, name, sid)
        pid = self._problem(name)
        problem_defer(self.root, name, pid, until="M2", reason="等规格冻结")
        items = self._human_ids(name)
        self.assertEqual(len(items), 1, items)
        self.assertIn(pid, items[0]["text"])
        self.assertIn("里程碑 M2", items[0]["text"])
