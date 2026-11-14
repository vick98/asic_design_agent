# 作者：vick 邮箱：ykun@yk9811.com

"""DEV-07：行 9 的 tb_review（与 `tc` 闸门并列）。

- 无审查记录 → 行 9 不完成，判据点名 tb_review；
- 合规记录（作者≠审查者、阻断 0、`--report` 在 report/ 下且晚于 testbench/）→ tick 自动完成；
- 作者=审查者 / 阻断发现>0 / 报告缺失 / 报告早于产物 → 全被拒；
- 闸门与审查是并列关系：闸门不过时，有审查记录也不完成。
"""

import os
import time
import unittest

from framework.engine import (
    EngineError, auto_complete_check, review_record, tick_report,
)
from framework.state import init_sys, load_state, stop_row, sys_dir
from framework.tests.util import (
    AUTHOR, REVIEWER, RepoTest, force_done, plant_sample, review,
)


class TbReviewTests(RepoTest):
    def _row9_ready(self, name):
        """行 1–8 完成、行 9 的 tc 闸门可过——只差审查记录。"""
        init_sys(self.root, name)
        plant_sample(self.root, name)
        for sid in range(1, 9):
            force_done(self.root, name, sid)
        tick_report(self.root, name)          # 行 9 依赖 6、8 定稿 → 自动启动
        return sys_dir(self.root, name)

    def test_row9_needs_tb_review_then_completes(self):
        name = "tb9need"
        self._row9_ready(name)
        state = load_state(self.root, name)
        self.assertEqual(stop_row(state, 9)["state"], "进行中", "缺审查记录不得完成")
        check = auto_complete_check(self.root, name, state, 9)
        self.assertFalse(check["ok"])
        self.assertTrue(any("tb_review" in reason for reason in check["reasons"]), check)
        text = tick_report(self.root, name)
        self.assertIn("tb_review", text)
        self.assertEqual(stop_row(load_state(self.root, name), 9)["state"], "进行中")
        # 合规记录：与 tc 闸门并列的第二半 → tick 自动完成。
        review(self.root, name, 9)
        text = tick_report(self.root, name)
        state = load_state(self.root, name)
        self.assertEqual(stop_row(state, 9)["state"], "完成（审核通过）")
        self.assertIn("自动完成停点 9", text)
        record = load_state(self.root, name)["stops"][8]["reviews"][-1]
        self.assertEqual(record["kind"], "tb_review")
        self.assertTrue(record["report"])
        self.assertTrue(record["report_digest"])
        # 签核记录与 M3 审阅包按既有 F1/F3 口径展示这条记录（只引用记录种类/报告/派工号）。
        from framework.engine import render_signoff
        from framework.review_pack import milestone_report
        render_signoff(self.root, name, load_state(self.root, name))
        path = os.path.join(sys_dir(self.root, name), "signoff", "%s_signoff.md" % name)
        with open(path, encoding="utf-8") as fh:
            signoff = fh.read()
        self.assertIn("tb_review", signoff)
        self.assertIn(record["report"], signoff)
        self.assertIn("tb_review", milestone_report(self.root, name, "M3"))

    def test_row9_review_rejections(self):
        import framework.engine as engine
        name = "tb9bad"
        base = self._row9_ready(name)
        notes = os.path.join(base, "report", "row9_review.md")
        os.makedirs(os.path.dirname(notes), exist_ok=True)
        with open(notes, "w", encoding="utf-8") as fh:
            fh.write("| 发现编号 | 级别 | 位置 | 建议 | 处置 |\n|---|---|---|---|---|\n")
        later = time.time() + 30
        os.utime(notes, (later, later))
        # 作者=审查者。
        with self.assertRaises(EngineError) as ctx:
            review_record(self.root, name, 9, author="a", reviewer="a",
                          report="report/row9_review.md")
        self.assertIn("必须不同", str(ctx.exception))
        # 阻断发现 > 0。
        with self.assertRaises(EngineError) as ctx:
            review_record(self.root, name, 9, author=AUTHOR, reviewer=REVIEWER,
                          blocking=1, report="report/row9_review.md")
        self.assertIn("阻断", str(ctx.exception))
        # 报告缺失（F3 必填）与不在 report/ 下。
        with self.assertRaises(EngineError) as ctx:
            review_record(self.root, name, 9, author=AUTHOR, reviewer=REVIEWER)
        self.assertIn("--report", str(ctx.exception))
        with self.assertRaises(EngineError):
            review_record(self.root, name, 9, author=AUTHOR, reviewer=REVIEWER, report="doc/x.md")
        # 四条都拒了：行 9 没有留下任何审查记录，也不完成。
        state = load_state(self.root, name)
        self.assertFalse(stop_row(state, 9).get("reviews"))
        self.assertEqual(stop_row(state, 9)["state"], "进行中")
        self.assertFalse(auto_complete_check(self.root, name, state, 9)["ok"])
        self.assertTrue(engine.module_state(state, base, "9", "tb"))

    def test_report_must_be_later_than_testbench(self):
        name = "tb9old"
        base = self._row9_ready(name)
        rel = "report/row9_review.md"
        path = os.path.join(base, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("| 发现编号 | 级别 | 位置 | 建议 | 处置 |\n|---|---|---|---|---|\n")
        fresh = os.path.join(base, "testbench", "tc", "row9_extra_tc.sv")
        with open(fresh, "w", encoding="utf-8") as fh:
            fh.write("// 审查报告之后才改的 TB\n")
        later = time.time() + 30
        os.utime(fresh, (later, later))
        with self.assertRaises(EngineError) as ctx:
            review_record(self.root, name, 9, author=AUTHOR, reviewer=REVIEWER, report=rel)
        self.assertIn("早于产物", str(ctx.exception))

    def test_gate_and_review_are_parallel(self):
        name = "tb9gate"
        base = self._row9_ready(name)
        review(self.root, name, 9)            # 有合规审查记录
        # 把 TB 平台挪走：tc 闸门挂 → 有审查记录也不得完成。
        import shutil
        shutil.move(os.path.join(base, "testbench", "tc"), os.path.join(base, "testbench", "moved"))
        state = load_state(self.root, name)
        check = auto_complete_check(self.root, name, state, 9)
        self.assertFalse(check["ok"], "闸门没过时不得完成")
        reason = "；".join(check["reasons"])
        self.assertTrue("行 9" in reason or "testbench" in reason or "平台" in reason, check)
        tick_report(self.root, name)
        self.assertEqual(stop_row(load_state(self.root, name), 9)["state"], "进行中")


if __name__ == "__main__":
    unittest.main()
