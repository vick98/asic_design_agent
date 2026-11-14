# 作者：vick 邮箱：ykun@yk9811.com

"""开发者简报（<sys>/<sys>_brief.md）与 `status --brief`。

- 简报在每次事务后重渲染；第一行就是"需要你做的：…"（有/无两种情形）；
- 四节标题与顺序固定（需要你做的 / 自上一个里程碑以来 / 风险与在途事项 /
  最近 5 条运行记录）；
- "自上一个里程碑以来"收录自动完成、入库裁决、L0/L1 回修、关闭的阻断与复核恢复；
  里程碑确认后基准时间前移，旧条目不再出现；
- 内容只来自 events.jsonl 与 state.json（手工追加事件行后重渲染可见）；
- status --brief 只出前两节，不带 --brief 的 status 输出不变。
"""

import json
import os
import subprocess
import sys
import unittest

from framework.engine import (
    add_problem, close_problem,
    item_end, item_open, record_run, tick_report,
)
from framework.flow import PENDING
from framework.state import init_sys, load_state, now, save, stop_row, sys_dir
from framework.tests.util import (
    RepoTest, checkout_root, confirm_milestone, decide, plant_sample, review,
)


def _script():
    return os.path.join(checkout_root(), "script", "framework.py")


def _run(args, root):
    env = os.environ.copy()
    env["ADF_ROOT"] = root
    return subprocess.run([sys.executable, _script()] + args,
                          env=env, capture_output=True, text=True)


class BriefBase(RepoTest):
    def _brief(self, name):
        path = os.path.join(self.root, name, "%s_brief.md" % name)
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def _section(self, text, header):
        return text.split(header, 1)[1].split("\n## ", 1)[0]

    def _walk_auto(self, name, sid):
        """tick 口径把停点 sid 走到完成：补独立审查记录后由 tick 自动启动并完成
        （自动归属）；行 6/11/12 只到送审态。"""
        review(self.root, name, sid)
        tick_report(self.root, name)


class BriefStructureTests(BriefBase):
    def test_brief_exists_after_txn_first_line_no_todo(self):
        name = "briefnone"
        init_sys(self.root, name)
        text = self._brief(name)
        self.assertEqual(text.splitlines()[0], "需要你做的：无")

    def test_first_line_lists_needed_items(self):
        name = "briefneed"
        init_sys(self.root, name)
        add_problem(self.root, name, "待裁决", 5, "仲裁轮询还是固定优先级",
                    options="轮询|固定优先级")
        text = self._brief(name)
        self.assertTrue(text.startswith("需要你做的："))
        self.assertNotEqual(text.splitlines()[0], "需要你做的：无")
        self.assertIn("待裁决问题 I001", text.splitlines()[0])

    def test_four_section_headers_and_order(self):
        name = "brieforder"
        init_sys(self.root, name)
        text = self._brief(name)
        i_since = text.index("## 自上一个里程碑以来")
        i_risk = text.index("## 风险与在途事项")
        i_runs = text.index("## 最近 5 条运行记录")
        self.assertLess(text.index("需要你做的："), i_since)
        self.assertLess(i_since, i_risk)
        self.assertLess(i_risk, i_runs)

    def test_risk_lines_cover_items_blockers_and_blocked_work(self):
        name = "briefrisk"
        init_sys(self.root, name)
        item_open(self.root, name, "调试", "行 5 端位不齐", side="tb")
        add_problem(self.root, name, "阻断", 1, "行 2 停点缺前置输入")
        add_problem(self.root, name, "待裁决", 2, "缓存行宽选型", blocks="3")
        text = self._brief(name)
        risk = self._section(text, "## 风险与在途事项")
        self.assertIn("M001", risk)
        self.assertIn("侧 tb", risk)
        self.assertIn("第 0 轮", risk)
        self.assertIn("未关闭阻断 I001", risk)
        self.assertIn("停点 3 被 I002 阻塞", risk)


class BriefSinceTests(BriefBase):
    def _seed_events(self, name):
        """堆出四类"自上一个里程碑以来"条目：自动完成、裁决入库、L0 回修、阻断关闭。"""
        plant_sample(self.root, name)
        review(self.root, name, 1)
        tick_report(self.root, name)  # 停点 1 自动完成（记"自动完成"事件）
        # 记录类裁决直接入库（两步链路），停点 2 → 行 2。
        decide(self.root, name, "帧窗口按行 2 口径", "记录", 2)
        mid = item_open(self.root, name, "调试", "行 5 端位不齐", side="rtl")
        item_end(self.root, name, mid, "L0")
        pid = add_problem(self.root, name, "阻断", 2, "行 2 规格缺饱和口径")
        rid = record_run(self.root, name, {
            "capability": "sim", "status": "pass", "summary": "smoke sim pass",
        })
        close_problem(self.root, name, pid, evidence=rid)

    def test_since_lists_all_five_categories(self):
        name = "briefsince"
        init_sys(self.root, name)
        self._seed_events(name)
        # 复核恢复：本包阶段由测试注入事件行验证渲染口径（见 test_brief_reads_events_log），
        # 这里先验证已落的四类。
        text = self._brief(name)
        since = self._section(text, "## 自上一个里程碑以来")
        self.assertIn("自动完成", since)
        self.assertIn("停点 1", since)
        self.assertIn("裁决入库", since)
        self.assertIn("L0/L1 回修收尾", since)
        self.assertIn("阻断关闭", since)
        self.assertIn("（基准：开始）", since)

    def test_milestone_confirm_moves_base_forward(self):
        name = "briefbase"
        init_sys(self.root, name)
        self._seed_events(name)
        # 行 2、3 自动完成，M1（覆盖 1、2、3）即可确认。
        for sid in (2, 3):
            self._walk_auto(name, sid)
        confirm_milestone(self.root, name, "M1")
        text = self._brief(name)
        since = self._section(text, "## 自上一个里程碑以来")
        self.assertIn("里程碑 M1 方案确认", since)
        # 基准前移：确认前的条目不再出现。
        self.assertNotIn("停点 1", since)
        self.assertNotIn("裁决入库", since)
        self.assertNotIn("L0/L1 回修收尾", since)
        # 基准之后的新条目照常收录。
        decide(self.root, name, "仲裁采用固定优先级", "记录", 3)
        since = self._section(self._brief(name), "## 自上一个里程碑以来")
        self.assertIn("裁决入库", since)
        self.assertIn("里程碑 M1 方案确认", since)

    def test_l2_l3_item_end_not_listed_as_l0_l1_fix(self):
        name = "briefl2"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        review(self.root, name, 1)
        tick_report(self.root, name)
        mid = item_open(self.root, name, "调试", "接口口径不合，升级结构裁决", side="rtl")
        # L2 收尾要指向已入库裁决，这里只验证"非 L0/L1 的收尾不进 L0/L1 行"：
        # 直接往事件日志注入一条 L2 收尾（简报只从事件日志渲染，正好一并验证口径）。
        path = os.path.join(self.root, name, "events.jsonl")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "time": now(), "cmd": "item_end", "actor": "测试",
                "action": "事项收尾", "object": mid,
                "evidence": "L2；%s" % mid,
            }, ensure_ascii=False) + "\n")
        save(self.root, name, load_state(self.root, name))
        text = self._brief(name)
        since = self._section(text, "## 自上一个里程碑以来")
        self.assertNotIn("L0/L1 回修收尾", since)


class BriefRunsTests(BriefBase):
    def test_last_five_runs_with_conclusion(self):
        name = "briefruns"
        init_sys(self.root, name)
        for index in range(1, 8):
            record_run(self.root, name, {
                "capability": "sim" if index % 2 else "lint",
                "status": "pass", "summary": "run %d 全部通过" % index,
            })
        text = self._brief(name)
        runs = self._section(text, "## 最近 5 条运行记录")
        entries = [line for line in runs.splitlines() if line.startswith("- ")]
        self.assertEqual(len(entries), 5)
        self.assertIn("run 7 全部通过", runs)
        self.assertIn("run 3", runs)
        self.assertNotIn("run 1", runs)
        self.assertNotIn("run 2", runs)
        for line in entries:
            self.assertRegex(line, r"^- \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} (sim|lint) pass：run \d")


class BriefCliTests(BriefBase):
    def test_status_brief_prints_only_first_two_sections(self):
        name = "briefcli"
        init_sys(self.root, name)
        add_problem(self.root, name, "待裁决", 5, "缓冲深度选型")
        record_run(self.root, name, {"capability": "sim", "status": "pass",
                                     "summary": "smoke pass"})
        proc = _run(["status", name, "--brief"], self.root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("需要你做的：", proc.stdout)
        self.assertIn("## 自上一个里程碑以来", proc.stdout)
        self.assertNotIn("## 风险与在途事项", proc.stdout)
        self.assertNotIn("## 最近 5 条运行记录", proc.stdout)
        self.assertIn("待裁决问题 I001", proc.stdout)

    def test_status_without_brief_unchanged(self):
        name = "briefplain"
        init_sys(self.root, name)
        proc = _run(["status", name], self.root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("子系统 %s" % name, proc.stdout)
        self.assertNotIn("需要你做的：", proc.stdout)
        self.assertNotIn("## 自上一个里程碑以来", proc.stdout)

    def test_status_brief_missing_sys_fails_clean(self):
        proc = _run(["status", "nope", "--brief"], self.root)
        self.assertEqual(proc.returncode, 1)


class BriefSourceTests(BriefBase):
    def test_brief_reads_events_log_and_rerenders(self):
        name = "briefsrc"
        init_sys(self.root, name)
        path = os.path.join(self.root, name, "events.jsonl")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "time": now(), "cmd": "tick", "actor": "测试",
                "action": "复核恢复", "object": "停点 8",
                "evidence": "产物未变，闸门与审查记录仍对得上当前产物",
            }, ensure_ascii=False) + "\n")
        # 手工事件在重渲染前不可见；一次普通事务（save）触发重渲染后可见。
        self.assertNotIn("复核恢复", self._brief(name))
        save(self.root, name, load_state(self.root, name))
        text = self._brief(name)
        since = self._section(text, "## 自上一个里程碑以来")
        self.assertIn("复核恢复", since)
        self.assertIn("停点 8", since)

    def test_brief_uses_display_state_for_milestone_pending(self):
        """派生显示态："待里程碑（Mn）"用 engine.display_state 计算。"""
        name = "briefms"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        for sid in range(1, 6):
            if sid == 4:
                confirm_milestone(self.root, name, "M1")  # 停点 4 启动前 M1 须已确认
            self._walk_auto(name, sid)
        # 行 6 由里程碑覆盖完成：tick 只置送审态，简报显示"待里程碑（M2）"。
        self._walk_auto(name, 6)
        self.assertEqual(stop_row(load_state(self.root, name), 6)["state"], PENDING)
        text = self._brief(name)
        risk = self._section(text, "## 风险与在途事项")
        self.assertIn("停点 6", risk)
        self.assertIn("待里程碑（M2）", risk)
        self.assertIn("milestone %s confirm --id M2" % name, risk)


if __name__ == "__main__":
    unittest.main()
