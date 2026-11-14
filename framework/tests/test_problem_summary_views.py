# 作者：vick 邮箱：ykun@yk9811.com

"""人读渲染面的三处可见性：裁决正文、待解决问题、最近小结。

- 点选入库不给显式正文时，正文是"问题原文：所选项"，`decision list` 与
  `*_decision.md` 都能看出这条裁决对应哪件问题；
- `*_status.md` 第 5 节只列仍未关闭的问题，关闭后即消失；
- `summary add` 写进 state 之后，`*_status.md` 第 6 节与 `*_brief.md` 的
  "自上一个里程碑以来"都能读到（最新 5 条，带时间），且渲染链只读不写盘。
"""

import contextlib
import io
import os
import re

from framework.engine import (
    EngineError, add_problem, add_summary, close_problem, commit_decision,
    record_run, status_report,
)
from framework.state import brief_report, init_sys, load_state
from framework.tests.util import RepoTest

_TIME_LINE = re.compile(r"^- \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} ")


class ViewBase(RepoTest):
    """读渲染物的共用入口：文档都是 state 事务提交时刷新的。"""

    def _doc(self, name, kind):
        path = os.path.join(self.root, name, "%s_%s.md" % (name, kind))
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def _status_section(self, name, header):
        text = self._doc(name, "status")
        return text.split(header, 1)[1].split("\n## ", 1)[0]

    def _decision_list(self, name):
        from script.framework import main
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["decision", name, "list"])
        self.assertEqual(code, 0, out.getvalue())
        return out.getvalue()


class DecisionDefaultContentTests(ViewBase):
    """点选入库的正文缺省值：问题原文加所选项，两边都能看见。"""

    TEXT = "帧样点数每帧 28456 样点约 1.42 ms"

    def test_default_content_keeps_problem_text_and_pick(self):
        name = "dcdefault"
        init_sys(self.root, name)
        pid = add_problem(self.root, name, "待裁决", 4, self.TEXT, "测试夹具",
                          options="取甲|取乙")
        did = commit_decision(self.root, name, kind="方向", from_problem=pid, pick="取乙")
        self.assertEqual(did, "D3-001")
        row = load_state(self.root, name)["decisions"]["3"][0]
        self.assertEqual(row["content"], "%s：取乙" % self.TEXT)
        decision_md = self._doc(name, "decision")
        self.assertIn(self.TEXT, decision_md)
        self.assertIn("取乙", decision_md)
        listed = self._decision_list(name)
        self.assertIn(self.TEXT, listed)
        self.assertIn("取乙", listed)

    def test_explicit_content_stays_as_written(self):
        name = "dcexplicit"
        init_sys(self.root, name)
        pid = add_problem(self.root, name, "待裁决", 4, self.TEXT, "测试夹具",
                          options="取甲|取乙")
        commit_decision(self.root, name, kind="方向", from_problem=pid, pick="取甲",
                        content="定稿：取甲")
        row = load_state(self.root, name)["decisions"]["3"][0]
        self.assertEqual(row["content"], "定稿：取甲")

    def test_default_content_goes_through_overlap_guard(self):
        # 只选一个短的选项标签时不构成"同一内容"，带上问题原文之后才拦得住
        # 同一件事的第二次点选——守卫比对的是真正落库的正文。
        name = "dcguard"
        init_sys(self.root, name)
        first = add_problem(self.root, name, "待裁决", 4, self.TEXT, "测试夹具",
                            options="取甲|取乙")
        commit_decision(self.root, name, kind="方向", from_problem=first, pick="取甲")
        second = add_problem(self.root, name, "待裁决", 4, self.TEXT, "测试夹具",
                             options="取甲|取乙")
        with self.assertRaises(EngineError) as ctx:
            commit_decision(self.root, name, kind="方向", from_problem=second, pick="取乙")
        self.assertIn("D3-001", str(ctx.exception))
        self.assertEqual(len(load_state(self.root, name)["decisions"]["3"]), 1)


class StatusProblemSectionTests(ViewBase):
    """状态文档第 5 节只列仍未关闭的问题。"""

    HEADER = "## 5. 待解决问题"

    def test_closed_problem_disappears(self):
        name = "spclose"
        init_sys(self.root, name)
        kept = add_problem(self.root, name, "阻断", 1, "行 2 缺前置输入")
        closed = add_problem(self.root, name, "阻断", 1, "行 2 规格写法待统一")
        rid = record_run(self.root, name, {
            "capability": "sim", "status": "pass", "summary": "smoke pass",
        })
        close_problem(self.root, name, closed, evidence=rid)
        section = self._status_section(name, self.HEADER)
        self.assertIn(kept, section)
        self.assertIn("行 2 缺前置输入", section)
        self.assertNotIn(closed, section)
        self.assertNotIn("行 2 规格写法待统一", section)

    def test_picked_problem_disappears(self):
        name = "sppicked"
        init_sys(self.root, name)
        pid = add_problem(self.root, name, "待裁决", 4, "仲裁轮询还是固定优先级",
                          "测试夹具", options="轮询|固定优先级")
        commit_decision(self.root, name, kind="方向", from_problem=pid, pick="轮询")
        section = self._status_section(name, self.HEADER)
        self.assertNotIn(pid, section)
        self.assertIn("（无）", section)


class SummaryVisibilityTests(ViewBase):
    """`summary add` 写入的小结在状态文档与简报里可见。"""

    def test_status_doc_shows_latest_five_with_time(self):
        name = "svstatus"
        init_sys(self.root, name)
        for index in range(7):
            add_summary(self.root, name, "第 %d 条小结" % index)
        section = self._status_section(name, "## 6. 恢复入口")
        self.assertIn("最近小结", section)
        self.assertIn("第 6 条小结", section)
        self.assertIn("第 2 条小结", section)
        self.assertNotIn("第 1 条小结", section)
        self.assertNotIn("第 0 条小结", section)
        lines = [line for line in section.splitlines() if "条小结" in line]
        self.assertEqual(len(lines), 5)
        for line in lines:
            self.assertTrue(_TIME_LINE.match(line), line)

    def test_brief_since_section_includes_summaries(self):
        name = "svbrief"
        init_sys(self.root, name)
        add_summary(self.root, name, "本轮把闸门口径补齐。")
        text = self._doc(name, "brief")
        since = text.split("## 自上一个里程碑以来", 1)[1].split("\n## ", 1)[0]
        self.assertIn("本轮把闸门口径补齐。", since)
        line = [row for row in since.splitlines() if "本轮把闸门口径补齐。" in row][0]
        self.assertTrue(_TIME_LINE.match(line), line)

    def test_status_and_brief_reads_do_not_write_files(self):
        name = "svreadonly"
        init_sys(self.root, name)
        add_summary(self.root, name, "只读渲染检查。")

        def snapshot():
            base = os.path.join(self.root, name)
            rows = {}
            for dirpath, dirnames, files in os.walk(base):
                dirnames.sort()
                for fn in sorted(files):
                    path = os.path.join(dirpath, fn)
                    keep = (os.path.relpath(path, base),
                            os.path.getsize(path), os.path.getmtime(path))
                    rows[keep[0]] = keep
            return rows

        before = snapshot()
        status_report(self.root, name)
        brief_report(self.root, name)
        self.assertEqual(before, snapshot())
