# 作者：vick 邮箱：ykun@yk9811.com

"""第三轮 T6：tb-gen 一测试点一用例。"""

import os
import unittest

from framework.gates.tc import scan_tc
from framework.state import init_sys, sys_dir
from framework.tbgen import cases_for, generate
from framework.tests.util import RepoTest, plant_sample


def _write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


SPEC = """# alu

模块类型：leaf

## 3. 模块接口

| 名字 | 方向 | 位宽 |
|---|---|---|
| clk_in | input | 1 |
| i_a | input | 8 |
| o_y | output | 8 |

## 9. 测试要点

| 编号 | 场景 | 激励 | 期望 |
|---|---|---|---|
| 1 | 零 | 两端为 0 | 和为 0 |
| 2 | 极值 | 正最大与负最大 | 饱和在界内 |
| 3 | 随机 | 随机数对 | 与参考模型一致 |
"""


class CaseNamingTests(RepoTest):
    def test_no_points_falls_back_to_basic(self):
        self.assertEqual(cases_for([]), [("basic", None)])

    def test_one_case_per_point(self):
        points = [{"id": "1", "scene": "零"}, {"id": "2", "scene": "极值"}]
        cases = cases_for(points)
        self.assertEqual([name for name, _ in cases], ["tp1", "tp2"])
        self.assertEqual(cases[1][1], points[1])


class GeneratedCasesTests(RepoTest):
    def _sys(self, name, points=3):
        init_sys(self.root, name)
        rows = "".join("| %d | 场景 %d | 激励 %d | 期望 %d |\n" % (i, i, i, i)
                       for i in range(1, points + 1))
        text = SPEC.replace("| 1 | 零 | 两端为 0 | 和为 0 |\n"
                            "| 2 | 极值 | 正最大与负最大 | 饱和在界内 |\n"
                            "| 3 | 随机 | 随机数对 | 与参考模型一致 |\n", rows)
        _write(self.root, "%s/spec_doc/alu_spec.md" % name, text)
        return name

    def test_three_points_make_three_cases(self):
        name = self._sys("t6three")
        lines = generate(sys_dir(self.root, name), name, "alu")
        made = {item.split(" ", 1)[1] for item in lines if item.startswith("写入")}
        base = "testbench/alu"
        for case in ("tp1", "tp2", "tp3"):
            self.assertIn("%s/tc/alu_tc_%s.sv" % (base, case), made)
        self.assertNotIn("%s/tc/alu_tc_basic.sv" % base, made)
        self.assertNotIn("%s/tc/alu_tc_tp4.sv" % base, made)
        factory = open(os.path.join(sys_dir(self.root, name), base, "tc",
                                    "alu_tc_factory.svh"), encoding="utf-8").read()
        for case in ("tp1", "tp2", "tp3"):
            self.assertIn('"tc_%s":' % case, factory)
        tcall = open(os.path.join(sys_dir(self.root, name), base, "tc",
                                  "alu_tc_all.sv"), encoding="utf-8").read()
        for case in ("tp1", "tp2", "tp3"):
            self.assertIn("alu_tc_%s" % case, tcall)
            self.assertIn("tc_%s" % case, tcall)

    def test_every_generated_case_fails_until_filled(self):
        name = self._sys("t6fail")
        generate(sys_dir(self.root, name), name, "alu")
        folder = os.path.join(sys_dir(self.root, name), "testbench", "alu", "tc")
        for case in ("tp1", "tp2", "tp3"):
            text = open(os.path.join(folder, "alu_tc_%s.sv" % case), encoding="utf-8").read()
            self.assertIn("骨架未填写", text)
            self.assertIn("m_fail_cnt", text)
            self.assertIn("`TB_CASE_BEGIN", text)
            self.assertIn("`TB_CASE_END", text)
            self.assertNotIn("RESULT: PASS", text)
        first = open(os.path.join(folder, "alu_tc_tp1.sv"), encoding="utf-8").read()
        self.assertIn("测试要点 1", first)

    def test_tc_gate_reports_skeleton_marker(self):
        """行 9 不再凭骨架自动完成——用例与参考模型的骨架标记由 T6 阻断。

        断言必须从"骨架过闸门"反过来：生成完就是未填写状态，闸门必须报出来。
        """
        name = self._sys("t6gate")
        generate(sys_dir(self.root, name), name, "alu")
        findings = scan_tc(sys_dir(self.root, name))
        t6 = [item for item in findings if item.get("rule") == "T6"]
        self.assertEqual(len(t6), 4, findings)  # tp1/tp2/tp3 + 参考模型
        self.assertEqual([item for item in findings if item.get("level") != "hint"], t6, findings)
        self.assertFalse(any(item.get("rule") == "T5" for item in findings), findings)

    def test_no_points_keeps_a_single_basic_case(self):
        name = "t6none"
        init_sys(self.root, name)
        _write(self.root, "%s/spec_doc/alu_spec.md" % name,
               "# alu\n\n## 3. 模块接口\n\n| 名字 | 方向 | 位宽 |\n|---|---|---|\n"
               "| clk_in | input | 1 |\n| o_y | output | 8 |\n")
        lines = generate(sys_dir(self.root, name), name, "alu")
        made = {item.split(" ", 1)[1] for item in lines if item.startswith("写入")}
        self.assertIn("testbench/alu/tc/alu_tc_basic.sv", made)
        self.assertFalse(any("/alu_tc_tp" in item for item in made), made)

    def test_fixture_spec_drives_two_cases(self):
        name = "t6fixture"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        lines = generate(sys_dir(self.root, name), name, "alu")
        made = {item.split(" ", 1)[1] for item in lines if item.startswith("写入")}
        self.assertIn("testbench/alu/tc/alu_tc_tp1.sv", made)
        self.assertIn("testbench/alu/tc/alu_tc_tp2.sv", made)


if __name__ == "__main__":
    unittest.main()
