# 作者：vick 邮箱：ykun@yk9811.com

"""第二轮 WP12：文档闸门口径的复现测试。"""

import os
import re
import unittest

from framework.gates.numeric import scan_params
from framework.gates.run import run_gates
from framework.gates.tc import scan_tc
from framework.state import init_sys, load_state, sys_dir
from framework.tests.util import RepoTest, checkout_root, plant_sample

RULE_LITERAL = re.compile(r'"rule"\s*:\s*"([^"]+)"')
FINDING_LITERAL = re.compile(r'_finding\(\s*"([^"]+)"')
TABLE_ROW = re.compile(r"^\|\s*([A-Za-z0-9][A-Za-z0-9\-]*)\s*\|")


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


class RawInputTests(RepoTest):
    def test_f16_raw_input_is_not_a_product(self):
        name = "rawdemo"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        _write(os.path.join(sys_dir(self.root, name), "info_input", "原始资料.md"),
               "# 原始资料\n\n## 1. 概述\n\n量化用 <12,0,t>，出处是甲方邮件。\n")
        findings = [item for item in run_gates(self.root, name, 1, load_state(self.root, name))
                    if item.get("level") != "hint"]
        self.assertEqual(findings, [], findings)

    def test_f16_overview_is_still_checked(self):
        name = "rawdemi"
        init_sys(self.root, name)
        _write(os.path.join(sys_dir(self.root, name), "info_input", "%s_info_overview.md" % name),
               "# 总览\n\n## 1. 概述\n\n自己写的，从第 1 节起。\n")
        findings = run_gates(self.root, name, 1, load_state(self.root, name))
        self.assertTrue(any(item["rule"] == "S3" for item in findings))
        self.assertTrue(any(item["rule"] == "S1" for item in findings))


class TestPointTests(RepoTest):
    def test_f27_testpoints_count_table_rows(self):
        name = "t5demo"
        init_sys(self.root, name)
        tb = os.path.join(sys_dir(self.root, name), "testbench", "alu", "tc")
        _write(os.path.join(tb, "alu_tc_basic.sv"),
               "class alu_tc_basic;\n  task body();\n  endtask\nendclass\n")
        _write(os.path.join(tb, "alu_tc_factory.svh"),
               '"tc_basic": begin alu_tc_basic t = new("tc_basic"); return t; end\n')
        _write(os.path.join(tb, "alu_tc_all.sv"),
               "class alu_tc_all;\n  task body();\n"
               "    alu_tc_basic tc1 = new(\"tc_basic\");\n    tc1.body();\n"
               "  endtask\nendclass\n")
        _write(os.path.join(sys_dir(self.root, name), "spec_doc", "alu_spec.md"),
               "# alu\n\n简介。\n\n## 9. 测试要点\n\n"
               "| 编号 | 用例 | 激励 | 期望 |\n|---|---|---|---|\n"
               "| T-1 | tc_basic | 加法规约 | o_y 正确 |\n"
               "| T-2 | tc_ovf | 溢出 | o_y 饱和 |\n"
               "| T-3 | tc_rst | 复位 | o_y 归零 |\n")
        findings = scan_tc(sys_dir(self.root, name))
        self.assertTrue(any(item["rule"] == "T5" for item in findings), findings)


class ParamScopeTests(RepoTest):
    def test_f29_module_specs_may_differ_per_instance(self):
        docs = {
            "spec_doc/alu_spec.md": "## 3. 模块接口\n\n存储深度 DEPTH = 16\n",
            "spec_doc/glue_spec.md": "## 3. 模块接口\n\n存储深度 DEPTH = 64\n",
        }
        findings = scan_params(docs, "demo")
        blocking = [item for item in findings if item.get("level") != "hint"]
        self.assertEqual(blocking, [], blocking)
        self.assertTrue(any(item["level"] == "hint" for item in findings), findings)

    def test_f29_global_param_still_blocks(self):
        docs = {
            "spec_doc/demo_spec.md": "## 4. 寄存器\n\n| 名字 | 值 |\n|---|---|\n| DEPTH | 16 |\n",
            "spec_doc/alu_spec.md": "## 3. 模块接口\n\n存储深度 DEPTH = 16\n",
            "spec_doc/glue_spec.md": "## 3. 模块接口\n\n存储深度 DEPTH = 64\n",
        }
        findings = scan_params(docs, "demo")
        self.assertTrue(any(item["rule"] == "D7" and item.get("level") != "hint"
                            for item in findings), findings)

    def test_f29_same_doc_still_blocks(self):
        docs = {"spec_doc/alu_spec.md": "## 3. 模块接口\n\n存储深度 DEPTH = 16\n位宽 DEPTH = 64\n"}
        findings = scan_params(docs, "demo")
        self.assertTrue(any(item["rule"] == "D7" and item.get("level") != "hint"
                            for item in findings), findings)


class RuleTableTests(RepoTest):
    # COV 是覆盖率阈值下调的豁免规则号（framework/coverage.py + rules/sim.md），
    # 由 coverage 判定消费，不在 gates/*.py 里产出；表里登记它，允许它在"代码之外"。
    EXTRA_TABLE_RULES = {"COV"}

    def test_f28_rule_table_matches_code(self):
        gates = os.path.join(checkout_root(), "framework", "gates")
        in_code = set()
        for name in sorted(os.listdir(gates)):
            if not name.endswith(".py"):
                continue
            with open(os.path.join(gates, name), encoding="utf-8") as fh:
                text = fh.read()
            in_code.update(RULE_LITERAL.findall(text))
            in_code.update(FINDING_LITERAL.findall(text))
        readme = open(os.path.join(gates, "README.md"), encoding="utf-8").read()
        in_table = set()
        for line in readme.splitlines():
            matched = TABLE_ROW.match(line)
            if not matched:
                continue
            key = matched.group(1)
            if key in ("编号",) or set(key) <= set("-"):
                continue
            in_table.add(key)
        self.assertEqual(sorted(in_code - in_table), [], "README 表里缺少代码中用到的规则号")
        self.assertEqual(sorted(in_table - in_code - self.EXTRA_TABLE_RULES), [],
                         "README 表里有代码中不存在（且非豁免登记）的规则号")
        self.assertIn("D3", in_code)
        self.assertIn("D5", in_code)


if __name__ == "__main__":
    unittest.main()
