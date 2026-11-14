# 作者：vick 邮箱：ykun@yk9811.com

"""审查记录挂报告原文：必填、晚于产物、记录挂摘要、审阅包抽样展示。

- `review record` 必须带 `report/report/…md`（缺失/不在 report/ 下/早于产物一律拒）；
- 记录里挂报告路径与内容摘要；
- 里程碑审阅包按记录取报告的"发现与处置"表抽样展示（不整份内嵌）。
"""

import os
import time
import unittest

from framework.engine import EngineError, review_record
from framework.review_pack import milestone_report
from framework.state import init_sys, load_state, sys_dir
from framework.tests.util import (
    AUTHOR, REVIEWER, RepoTest, decide, plant_sample, review, write_report,
)

TABLE = ("# 行 1 独立审查报告\n\n"
         "## 发现与处置\n\n"
         "| 发现编号 | 级别 | 位置 | 建议 | 处置 |\n"
         "|---|---|---|---|---|\n"
         "| F1 | 建议 | 第 3 章 | 补一句口径 | 已改 |\n"
         "| F2 | 阻断 | 第 5 章 | 缺时钟域 | 已改并复算 |\n")

TABLE_ALL_RESOLVED = TABLE
TABLE_UNRESOLVED = ("# 行 1 独立审查报告\n\n"
                    "| 发现编号 | 级别 | 位置 | 建议 | 处置 |\n"
                    "|---|---|---|---|---|\n"
                    "| F1 | 建议 | 第 3 章 | 补一句口径 | 已改 |\n"
                    "| F2 | 阻断 | 第 5 章 | 缺时钟域 | 待改 |\n")


class ReviewReportTests(RepoTest):
    def _base(self, name):
        init_sys(self.root, name)
        plant_sample(self.root, name)
        return sys_dir(self.root, name)

    def test_report_is_required(self):
        name = "rvreq"
        self._base(name)
        with self.assertRaises(EngineError) as ctx:
            review_record(self.root, name, 1, author=AUTHOR, reviewer=REVIEWER)
        self.assertIn("--report", str(ctx.exception))

    def test_report_must_live_under_report_dir(self):
        name = "rvdir"
        base = self._base(name)
        outside = os.path.join(base, "doc_review.md")
        with open(outside, "w", encoding="utf-8") as fh:
            fh.write(TABLE)
        with self.assertRaises(EngineError) as ctx:
            review_record(self.root, name, 1, author=AUTHOR, reviewer=REVIEWER,
                          report="doc_review.md")
        self.assertIn("report/", str(ctx.exception))
        # 报告不在盘上也要拒。
        with self.assertRaises(EngineError) as ctx:
            review_record(self.root, name, 1, author=AUTHOR, reviewer=REVIEWER,
                          report="report/没有这份.md")
        self.assertIn("不存在", str(ctx.exception))

    def test_report_older_than_product_is_rejected(self):
        name = "rvold"
        base = self._base(name)
        rel = "report/%s_row1_review.md" % name
        path = os.path.join(base, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(TABLE)
        # 产物在报告之后又改过：报告不再代表这一版产物。
        product = os.path.join(base, "info_input", "%s_info_overview.md" % name)
        later = time.time() + 30
        os.utime(product, (later, later))
        with self.assertRaises(EngineError) as ctx:
            review_record(self.root, name, 1, author=AUTHOR, reviewer=REVIEWER, report=rel)
        self.assertIn("早于产物", str(ctx.exception))
        self.assertFalse(load_state(self.root, name)["stops"][0].get("reviews"))

    def test_record_carries_report_and_pack_samples_table(self):
        name = "rvok"
        self._base(name)
        review(self.root, name, 1, report=TABLE)
        row = load_state(self.root, name)["stops"][0]["reviews"][-1]
        self.assertEqual(row["report"], "report/%s_row1_review.md" % name)
        self.assertTrue(row["report_digest"])
        pack = milestone_report(self.root, name, "M1")
        self.assertIn("发现编号", pack)
        self.assertIn("F1", pack)
        self.assertIn("补一句口径", pack)
        # 抽样不是整份内嵌：报告标题那一行不进审阅包。
        self.assertNotIn("# 行 1 独立审查报告", pack)


    def test_table_row_count_is_findings(self):
        name = "rvcount"
        self._base(name)
        rel = write_report(self.root, name, 1, report=TABLE_ALL_RESOLVED)
        review_record(self.root, name, 1, author=AUTHOR, reviewer=REVIEWER, report=rel)
        row = load_state(self.root, name)["stops"][0]["reviews"][-1]
        self.assertEqual(row["findings"], 2, "发现数按报告表数据行计")

    def test_explicit_counts_must_match_parsed_table(self):
        name = "rvmismatch"
        self._base(name)
        rel = write_report(self.root, name, 1, report=TABLE_ALL_RESOLVED)
        with self.assertRaises(EngineError) as ctx:
            review_record(self.root, name, 1, author=AUTHOR, reviewer=REVIEWER,
                          findings=3, report=rel)
        self.assertIn("不一致", str(ctx.exception))
        with self.assertRaises(EngineError) as ctx:
            review_record(self.root, name, 1, author=AUTHOR, reviewer=REVIEWER,
                          blocking=1, report=rel)
        self.assertIn("不一致", str(ctx.exception))
        # 与解析一致时允许显式给。
        review_record(self.root, name, 1, author=AUTHOR, reviewer=REVIEWER,
                      findings=2, blocking=0, report=rel)
        row = load_state(self.root, name)["stops"][0]["reviews"][-1]
        self.assertEqual(row["findings"], 2)

    def test_unresolved_blocking_row_is_rejected(self):
        name = "rvunresolved"
        self._base(name)
        rel = write_report(self.root, name, 1, report=TABLE_UNRESOLVED)
        with self.assertRaises(EngineError) as ctx:
            review_record(self.root, name, 1, author=AUTHOR, reviewer=REVIEWER, report=rel)
        self.assertIn("阻断", str(ctx.exception))
        self.assertFalse(load_state(self.root, name)["stops"][0].get("reviews"))

    def test_accept_risk_needs_valid_decision(self):
        name = "rvriskbad"
        self._base(name)
        report = ("# 行 1 独立审查报告\n\n"
                  "| 发现编号 | 级别 | 位置 | 建议 | 处置 |\n"
                  "|---|---|---|---|---|\n"
                  "| F1 | 阻断 | 第 5 章 | 缺时钟域 | 接受风险（D9-999） |\n")
        rel = write_report(self.root, name, 1, report=report)
        with self.assertRaises(EngineError) as ctx:
            review_record(self.root, name, 1, author=AUTHOR, reviewer=REVIEWER, report=rel)
        self.assertIn("裁决", str(ctx.exception))
        self.assertFalse(load_state(self.root, name)["stops"][0].get("reviews"))

    def test_accept_risk_with_valid_decision_passes(self):
        name = "rvriskok"
        self._base(name)
        did = decide(self.root, name, "缺时钟域由上游同步保证", "数值", 2)
        report = ("# 行 1 独立审查报告\n\n"
                  "| 发现编号 | 级别 | 位置 | 建议 | 处置 |\n"
                  "|---|---|---|---|---|\n"
                  "| F1 | 阻断 | 第 5 章 | 缺时钟域 | 接受风险（%s） |\n" % did)
        rel = write_report(self.root, name, 1, report=report)
        review_record(self.root, name, 1, author=AUTHOR, reviewer=REVIEWER, report=rel)
        row = load_state(self.root, name)["stops"][0]["reviews"][-1]
        self.assertEqual(row["findings"], 1)
        self.assertEqual(row["findings"], 1, "接受风险算已处置，不计阻断")

    def test_no_table_requires_explicit_no_findings(self):
        name = "rvnotable"
        self._base(name)
        rel = write_report(self.root, name, 1, report="# 行 1 独立审查报告\n\n无发现。\n")
        review_record(self.root, name, 1, author=AUTHOR, reviewer=REVIEWER, report=rel)
        row = load_state(self.root, name)["stops"][0]["reviews"][-1]
        self.assertEqual(row["findings"], 0)
        bad = write_report(self.root, name, 1, report="# 行 1 独立审查报告\n\n正文说明。\n")
        with self.assertRaises(EngineError) as ctx:
            review_record(self.root, name, 1, author=AUTHOR, reviewer=REVIEWER, report=bad)
        self.assertIn("无发现", str(ctx.exception))

    def test_wrong_table_header_is_not_a_findings_table(self):
        name = "rvheader"
        self._base(name)
        swapped = ("# 行 1 独立审查报告\n\n"
                   "| 级别 | 发现编号 | 位置 | 建议 | 处置 |\n"
                   "|---|---|---|---|---|\n"
                   "| 阻断 | F1 | 第 5 章 | 缺时钟域 | 待改 |\n\n"
                   "无发现。\n")
        rel = write_report(self.root, name, 1, report=swapped)
        review_record(self.root, name, 1, author=AUTHOR, reviewer=REVIEWER, report=rel)
        row = load_state(self.root, name)["stops"][0]["reviews"][-1]
        self.assertEqual(row["findings"], 0, "列名顺序不对的表不算发现表，以“无发现”为准")

    def test_empty_table_means_zero_findings(self):
        name = "rvemptytable"
        self._base(name)
        empty = ("# 行 1 独立审查报告\n\n"
                 "| 发现编号 | 级别 | 位置 | 建议 | 处置 |\n"
                 "|---|---|---|---|---|\n")
        rel = write_report(self.root, name, 1, report=empty)
        review_record(self.root, name, 1, author=AUTHOR, reviewer=REVIEWER, report=rel)
        row = load_state(self.root, name)["stops"][0]["reviews"][-1]
        self.assertEqual(row["findings"], 0)


if __name__ == "__main__":
    unittest.main()
