# 作者：vick 邮箱：ykun@yk9811.com

"""里程碑审阅包减负：结论摘要为唯一入口、条数闸门、风险优先抽样可复现。"""

import os
import unittest

from framework.engine import EngineError, milestone_confirm, tick_report
from framework.review_pack import _doc_section, milestone_report
from framework.state import init_sys, load_state, sys_dir
from framework.tests.util import RepoTest, plant_sample, review, write_milestone_notes


class MilestoneNotesGateTests(RepoTest):
    def _m1_ready(self, name):
        init_sys(self.root, name)
        plant_sample(self.root, name)
        for sid in (1, 2, 3):
            review(self.root, name, sid)
            tick_report(self.root, name)

    def test_m1_confirm_requires_three_to_six_notes(self):
        name = "f4notes"
        self._m1_ready(name)
        with self.assertRaises(EngineError) as ctx:
            milestone_confirm(self.root, name, "M1", pick="通过")
        self.assertIn("结论摘要", str(ctx.exception))
        for count in (2, 7):
            write_milestone_notes(self.root, name, "M1", count=count)
            with self.assertRaises(EngineError) as ctx:
                milestone_confirm(self.root, name, "M1", pick="通过")
            self.assertIn("3–6 条", str(ctx.exception))
        write_milestone_notes(self.root, name, "M1", count=3)
        milestone_confirm(self.root, name, "M1", pick="通过")
        self.assertEqual(load_state(self.root, name)["milestones"]["M1"]["pick"], "通过")

    def test_tick_lists_the_missing_summary(self):
        name = "f4list"
        self._m1_ready(name)
        text = tick_report(self.root, name)
        self.assertIn("结论摘要", text)

    def test_m1_pack_uses_summary_and_links_not_full_text(self):
        name = "f4pack"
        self._m1_ready(name)
        write_milestone_notes(self.root, name, "M1", count=4,
                              extra="- 方案：结论摘要里的一句独有标记 F4-SUMMARY。")
        # 原文里塞一句独有标记：结论摘要版审阅包不得把它整份内嵌进来。
        plan = os.path.join(sys_dir(self.root, name), "plan_doc", "%s_plan.md" % name)
        with open(plan, "a", encoding="utf-8") as fh:
            fh.write("\n原文独有标记：F4-NOT-EMBEDDED。\n")
        pack = milestone_report(self.root, name, "M1")
        self.assertIn("结论摘要（milestone_notes/M1.md，原文只留链接）", pack)
        self.assertIn("原文链接", pack)
        self.assertIn("F4-SUMMARY", pack)
        self.assertIn("info_input/%s_info_overview.md" % name, pack)
        self.assertIn("全部方向/数值裁决", pack)
        self.assertIn("冲突与红线五问的处置", pack)
        self.assertNotIn("F4-NOT-EMBEDDED", pack)


class RiskSampleTests(RepoTest):
    def _m2_ready(self, name):
        init_sys(self.root, name)
        plant_sample(self.root, name)
        # 第三份模块规格书：让"前二 + 随机一"这条路径真的被走到。
        spec_dir = os.path.join(sys_dir(self.root, name), "spec_doc")
        with open(os.path.join(spec_dir, "mod2_spec.md"), "w", encoding="utf-8") as fh:
            fh.write("# mod2 模块规格书\n\n模块类型：组合\n\n## 端口表\n\n"
                     "| 名字 | 方向 | 位宽 | 时钟域 | 说明 | 位宽依据 |\n"
                     "|---|---|---|---|---|---|\n| a | in | 8 | clk | 输入 | 规格书 |\n")

    def test_sampling_note_records_seed_and_is_reproducible(self):
        name = "f4sample"
        self._m2_ready(name)
        first = milestone_report(self.root, name, "M2")
        second = milestone_report(self.root, name, "M2")
        self.assertIn("抽样口径（可复现）", first)
        self.assertIn("风险优先", first)
        self.assertIn("种子 %s/M2" % name, first)
        # 同一子系统两次出包，抽样口径与抽中的对象完全一致。
        def note(text):
            return [line for line in text.splitlines() if "风险优先" in line][0]
        self.assertEqual(note(first), note(second))
        for token in ("抽样模块规格书：",):
            self.assertEqual([line for line in first.splitlines() if line.startswith(token)],
                             [line for line in second.splitlines() if line.startswith(token)])

    def test_m3_sampling_uses_its_own_seed(self):
        name = "f4m3"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        pack = milestone_report(self.root, name, "M3")
        self.assertIn("抽样口径（可复现）", pack)
        self.assertIn("种子 %s/M3" % name, pack)


class DocSectionTests(RepoTest):
    def test_same_keyword_subsections_are_all_kept(self):
        name = "docsec"
        init_sys(self.root, name)
        spec_dir = os.path.join(self.root, name, "spec_doc")
        os.makedirs(spec_dir, exist_ok=True)
        path = os.path.join(spec_dir, "alu_spec.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("# alu\n\n## 8. 模块逻辑块描述\n\n"
                     "### 逻辑块 1：加法\n\n第一块正文。\n\n"
                     "### 逻辑块 2：饱和\n\n第二块正文。\n")
        text = _doc_section(self.root, name, "spec_doc/alu_spec.md", "逻辑块")
        self.assertIn("第一块正文", text)
        self.assertIn("第二块正文", text)


if __name__ == "__main__":
    unittest.main()


class TestPointParserConsistencyTests(RepoTest):
    def _spec(self, name, body):
        init_sys(self.root, name)
        spec_dir = os.path.join(self.root, name, "spec_doc")
        os.makedirs(spec_dir, exist_ok=True)
        path = os.path.join(spec_dir, "alu_spec.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body)
        return path

    def test_adjacent_tables_skip_repeated_header(self):
        from framework.trace import _parse_test_points
        from framework.gates.tc import _testpoints
        from framework.digest import _structured_tests
        body = ("# alu\n\n## 9. 测试要点\n\n"
                "| 编号 | 场景 | 来源 | 激励 | 期望 |\n|---|---|---|---|---|\n"
                "| T1 | 零 | S1 | a | b |\n"
                "| 编号 | 场景 | 来源 | 激励 | 期望 |\n|---|---|---|---|---|\n"
                "| T2 | 极值 | S2 | c | d |\n")
        path = self._spec("ptcontig", body)
        points, _ = _parse_test_points(os.path.join(self.root, "ptcontig"))
        self.assertEqual(len(points), 2)
        self.assertEqual(_testpoints(path), 2)
        self.assertEqual(len(_structured_tests(body)), 2)

    def test_empty_table_does_not_fall_back_to_list(self):
        from framework.trace import _parse_test_points
        from framework.gates.tc import _testpoints
        from framework.digest import _structured_tests
        body = ("# alu\n\n## 9. 测试要点\n\n"
                "| 编号 | 场景 | 来源 | 激励 | 期望 |\n|---|---|---|---|---|\n"
                "- 补充项\n")
        path = self._spec("ptempty", body)
        points, _ = _parse_test_points(os.path.join(self.root, "ptempty"))
        self.assertEqual(len(points), 0)
        self.assertEqual(_testpoints(path), 0)
        self.assertEqual(len(_structured_tests(body)), 0)

    def test_table_without_separator_row_still_counts(self):
        from framework.trace import _parse_test_points
        from framework.gates.tc import _testpoints
        from framework.digest import _structured_tests
        body = ("# alu\n\n## 9. 测试要点\n\n"
                "| 编号 | 场景 | 来源 | 激励 | 期望 |\n"
                "| T1 | 零 | S1 | a | b |\n"
                "| T2 | 极值 | S2 | c | d |\n")
        path = self._spec("ptnosep", body)
        points, _ = _parse_test_points(os.path.join(self.root, "ptnosep"))
        self.assertEqual(len(points), 2)
        self.assertEqual(_testpoints(path), 2)
        self.assertEqual(len(_structured_tests(body)), 2)
