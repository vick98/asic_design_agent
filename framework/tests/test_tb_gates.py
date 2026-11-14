# 作者：vick 邮箱：ykun@yk9811.com

"""行 9 的 T5/T6 阻断闸门、行 4 的 leaf 接口三章的复现用例。

- T6：刚跑完 `tb-gen` 的平台仍是骨架（用例含 `骨架未填写`，参考模型含透传标记）→ 阻断。
- T5：测试要点逐条映射，缺哪条报哪条编号（不再只比条数，也不再是 hint）。
- 行 4 的 leaf 规格书要有模块功能、模块接口、模块处理流程（`leaf_iface`）。
"""

import os
import unittest

from framework.gates.docs import expected_chapters, scan_docs
from framework.gates.tc import scan_tc
from framework.state import init_sys, sys_dir
from framework.tbgen import PENDING, REFM_PENDING, generate
from framework.tests.util import RepoTest


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _spec(points):
    """模块规格书：接口三章 + 第 9 节 points 条测试要点。"""
    rows = "".join("| %d | 场景 %d | 激励 %d | 期望 %d |\n" % (i, i, i, i)
                   for i in range(1, points + 1))
    return ("# alu\n\n模块类型：leaf\n\n## 2. 模块功能\n\n饱和加法。\n\n"
            "## 3. 模块接口\n\n| 名字 | 方向 | 位宽 |\n|---|---|---|\n"
            "| clk_in | input | 1 |\n| o_y | output | 8 |\n\n"
            "## 4. 模块处理流程\n\n一拍出结果。\n\n"
            "## 9. 测试要点\n\n| 编号 | 场景 | 激励 | 期望 |\n|---|---|---|---|\n" + rows)


def _platform(root, name, cases, points, dut="alu", declared=None):
    """造一个结构完整、无骨架标记的 TB 平台（用例名由 cases 给定）。

    `declared` 是 {用例名: 测试要点号}，写进用例文件头注释声明 `testpoint: N`。
    """
    declared = declared or {}
    tb = os.path.join(sys_dir(root, name), "testbench", dut)
    tc = os.path.join(tb, "tc")
    _write(os.path.join(tc, "%s_tc_factory.svh" % dut),
           "".join('"%s": begin %s_tc_%s t = new("%s"); return t; end\n'
                   % (case, dut, case, case) for case in cases))
    body = "".join('    %s_tc_%s tc%d = new("tc%d");\n    tc%d.body();\n'
                   % (dut, case, i, i, i) for i, case in enumerate(cases, 1))
    _write(os.path.join(tc, "%s_tc_all.sv" % dut),
           "class %s_tc_all;\n  task body();\n%s  endtask\nendclass\n" % (dut, body))
    for case in cases:
        head = ""
        if case in declared:
            head = ("/*========================================FILE_HEADER========================="
                    "============\n# testpoint: %d\n================================"
                    "=========FILE_HEADER====================================*/\n" % declared[case])
        _write(os.path.join(tc, "%s_tc_%s.sv" % (dut, case)),
               head + "class %s_tc_%s;\n  task body();\n  endtask\nendclass\n" % (dut, case))
    _write(os.path.join(sys_dir(root, name), "spec_doc", "%s_spec.md" % dut), _spec(points))
    return tb


def _fill(path):
    """把生成骨架里的某个标记改掉，模拟开发者已填写。"""
    _write(path, _read(path).replace(PENDING, "按规格书填写").replace(
        REFM_PENDING, "参考模型已填写"))


class SkeletonGateTests(RepoTest):
    def test_fresh_tbgen_platform_reports_t6(self):
        name = "g6fresh"
        init_sys(self.root, name)
        _write(os.path.join(sys_dir(self.root, name), "spec_doc", "alu_spec.md"), _spec(2))
        generate(sys_dir(self.root, name), name, "alu")
        findings = scan_tc(sys_dir(self.root, name))
        self.assertTrue(any(item["rule"] == "T6" for item in findings), findings)
        # 阻断而非提示：行 9 不得凭骨架自动完成。
        blocking = [item for item in findings if item.get("level") != "hint"]
        self.assertEqual([item["rule"] for item in blocking if item["rule"] == "T6"],
                         ["T6", "T6", "T6"], findings)

    def test_refm_passthrough_alone_reports_t6(self):
        name = "g6refm"
        init_sys(self.root, name)
        _write(os.path.join(sys_dir(self.root, name), "spec_doc", "alu_spec.md"), _spec(2))
        generate(sys_dir(self.root, name), name, "alu")
        tb = os.path.join(sys_dir(self.root, name), "testbench", "alu")
        for case in ("tp1", "tp2"):
            _write(os.path.join(tb, "tc", "alu_tc_%s.sv" % case),
                   _read(os.path.join(tb, "tc", "alu_tc_%s.sv" % case))
                   .replace(PENDING, "按规格书填写"))
        findings = scan_tc(sys_dir(self.root, name))
        t6 = [item for item in findings if item["rule"] == "T6"]
        self.assertEqual(len(t6), 1, findings)
        self.assertIn("alu_tb_refm.svh", t6[0]["detail"])

    def test_filled_platform_passes_t5_and_t6(self):
        name = "g6filled"
        init_sys(self.root, name)
        _write(os.path.join(sys_dir(self.root, name), "spec_doc", "alu_spec.md"), _spec(2))
        generate(sys_dir(self.root, name), name, "alu")
        tb = os.path.join(sys_dir(self.root, name), "testbench", "alu")
        for case in ("tp1", "tp2"):
            _fill(os.path.join(tb, "tc", "alu_tc_%s.sv" % case))
        _fill(os.path.join(tb, "alu_tb_refm.svh"))
        findings = scan_tc(sys_dir(self.root, name))
        self.assertFalse(any(item["rule"] in ("T5", "T6") for item in findings), findings)


class TestPointGateTests(RepoTest):
    def test_missing_point_names_the_number(self):
        name = "g5miss"
        init_sys(self.root, name)
        _platform(self.root, name, ["tp1", "tp3"], 3)
        findings = scan_tc(sys_dir(self.root, name))
        t5 = [item for item in findings if item["rule"] == "T5"]
        self.assertEqual(len(t5), 1, findings)
        self.assertIn("第 2 条", t5[0]["detail"])
        self.assertNotIn("第 1 条", t5[0]["detail"])
        self.assertNotIn("第 3 条", t5[0]["detail"])
        # 阻断而非提示。
        self.assertNotEqual(t5[0].get("level"), "hint")

    def test_header_declaration_covers_the_point(self):
        name = "g5decl"
        init_sys(self.root, name)
        _platform(self.root, name, ["ramp", "hold"], 2, declared={"ramp": 1, "hold": 2})
        findings = scan_tc(sys_dir(self.root, name))
        self.assertFalse(any(item["rule"] == "T5" for item in findings), findings)

    def test_more_cases_than_points_is_not_t5(self):
        name = "g5extra"
        init_sys(self.root, name)
        _platform(self.root, name, ["tp1", "tp2", "tp2b"], 2)
        findings = scan_tc(sys_dir(self.root, name))
        self.assertFalse(any(item["rule"] == "T5" for item in findings), findings)

    def test_no_points_needs_no_t5(self):
        name = "g5none"
        init_sys(self.root, name)
        _platform(self.root, name, ["basic"], 0)
        findings = scan_tc(sys_dir(self.root, name))
        self.assertFalse(any(item["rule"] == "T5" for item in findings), findings)

    def test_spec_outside_spec_doc_is_not_mapped(self):
        """逐条 T5 只认框架产物 `spec_doc/<dut>_spec.md`（rules/spec.md）。

        `<sys>/<dut>_spec.md` 是 `pub_code/` 那种外部输入材料布局，其测试要点
        只作参考，不参与逐条映射（否则 pub_code 参考平台会被误报）。
        """
        name = "g5root"
        init_sys(self.root, name)
        _platform(self.root, name, ["basic"], 3)
        src = os.path.join(sys_dir(self.root, name), "spec_doc", "alu_spec.md")
        _write(os.path.join(sys_dir(self.root, name), "alu_spec.md"), _read(src))
        os.remove(src)
        findings = scan_tc(sys_dir(self.root, name))
        self.assertFalse(any(item["rule"] == "T5" for item in findings), findings)


class LeafIfaceChapterTests(RepoTest):
    def _leaf(self, name, chapters):
        init_sys(self.root, name)
        lines = ["# alu", "", "模块类型：leaf", ""]
        for index, title in enumerate(chapters, 2):
            lines += ["## %d. %s" % (index, title), "", "正文。", ""]
        _write(os.path.join(sys_dir(self.root, name), "spec_doc", "alu_spec.md"), "\n".join(lines))
        return sys_dir(self.root, name)

    def test_stop4_leaf_without_iface_chapter_reports_s1(self):
        root = self._leaf("g4miss", ["模块功能", "模块处理流程"])
        findings = scan_docs(root, 4)
        s1 = [item for item in findings
              if item["rule"] == "S1" and "模块接口" in item.get("detail", "")]
        self.assertTrue(s1, findings)

    def test_stop4_leaf_with_iface_chapters_passes(self):
        root = self._leaf("g4ok", ["模块功能", "模块接口", "模块处理流程"])
        findings = scan_docs(root, 4)
        blocking = [item for item in findings
                    if item["rule"] == "S1" and item.get("level") != "hint"]
        self.assertEqual(blocking, [], findings)

    def test_chapter_sets_at_stop4_and_stop5(self):
        self.assertEqual(expected_chapters("spec_doc/alu_spec.md", 4, "模块类型：leaf", "s"),
                         ["模块功能", "模块接口", "模块处理流程"])
        self.assertEqual(len(expected_chapters("spec_doc/alu_spec.md", 5, "模块类型：leaf", "s")), 6)


if __name__ == "__main__":
    unittest.main()
