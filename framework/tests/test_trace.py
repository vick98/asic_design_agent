# 作者：vick 邮箱：ykun@yk9811.com

"""需求追溯矩阵：输入要点 → 节点 → 模块 → 测试要点 → 用例 → 最近全量回归。

矩阵的锚点是各表最后一列「来源」。追溯沿来源列逐级向上解析：测试要点写上游
模块名或输入编号，模块清单/节点表写输入编号。矩阵输出、JSON 结构、TR1 闸门
（强约束输入要点没有测试要点追溯到 → 阻断，其余档位只提示）与 M2/M3 审阅包
里的覆盖率都在这里锁住。
"""

import json
import os
import unittest

from framework.engine import record_run
from framework.gates.docs import check_columns, load_chapter_model
from framework.gates.run import run_gates
from framework.review_pack import milestone_report
from framework.state import init_sys, load_state, sys_dir
from framework.tests.util import RepoTest, cli, plant_sample
from framework.trace import render_markdown, trace_matrix


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _drop_line(path, prefix):
    """删掉以 prefix 开头的一行（用来制造"某条测试要点没有追溯"）。"""
    kept = [line for line in _read(path).splitlines(True) if not line.startswith(prefix)]
    _write(path, "".join(kept))


class TraceMatrixTests(RepoTest):
    def _plant(self, name):
        init_sys(self.root, name)
        plant_sample(self.root, name)
        return load_state(self.root, name)

    def test_matrix_links_input_points_through_nodes_modules_test_points_and_cases(self):
        name = "tracematrix"
        state = self._plant(name)
        result = trace_matrix(sys_dir(self.root, name), state)
        self.assertEqual(result["sys"], name)
        self.assertEqual([row["input"] for row in result["rows"]], ["A001", "A002"])
        row = result["rows"][0]
        self.assertEqual(row["input_text"], "单时钟，低有效复位")
        self.assertEqual(row["credibility"], "强约束")
        self.assertIn("加数", row["nodes"])
        self.assertIn("alu", row["modules"])
        self.assertEqual(row["test_points"][0]["module"], "alu")
        self.assertEqual(row["test_points"][0]["number"], 1)
        self.assertEqual(result["summary"]["input_points"], 2)
        self.assertEqual(result["summary"]["traced_points"], 2)
        self.assertEqual(result["summary"]["strong_uncovered"], 0)
        text = render_markdown(result)
        self.assertIn("# %s 需求追溯矩阵" % name, text)
        self.assertIn("| 输入要点 | 节点 | 模块 | 测试要点 | 用例 | 最近结果 | 缺口说明 |", text)
        self.assertIn("A001", text)
        self.assertIn("A002", text)

    def test_rows_without_traced_test_points_name_the_input_id(self):
        name = "tracegap"
        state = self._plant(name)
        spec = os.path.join(sys_dir(self.root, name), "spec_doc", "alu_spec.md")
        # 第 1 条测试要点来源是上游模块 alu，删掉后 A001 没有任何测试要点追溯。
        _drop_line(spec, "| 1 |")
        result = trace_matrix(sys_dir(self.root, name), state)
        changed = [row for row in result["rows"] if row["input"] == "A001"][0]
        self.assertEqual(changed["test_points"], [])
        self.assertIn("无测试要点追溯", changed["gap"])
        self.assertIn("A001", [item["input"] for item in result["uncovered"]])
        self.assertEqual(result["summary"]["uncovered_points"], 1)
        self.assertIn("A001", render_markdown(result))
        # 缺一条测试要点后，行 6 的 TR1 阻断要直接报出输入编号。
        findings = run_gates(self.root, name, 6, load_state(self.root, name))
        tr1 = [item for item in findings if item.get("rule") == "TR1"]
        self.assertTrue(tr1, findings)
        self.assertTrue(any("A001" in item["detail"] for item in tr1), tr1)

    def test_generated_input_ids_are_stable_and_reported(self):
        name = "tracegen"
        init_sys(self.root, name)
        _write(os.path.join(sys_dir(self.root, name), "info_input", "%s_info_overview.md" % name),
               "# %s 信息总览\n\n前置材料的总览。\n\n## 2. 输入文档\n\n"
               "| 文件 | 要点 | 可信度 | 备注 |\n|---|---|---|---|\n"
               "| 口头约束 | 单时钟，低有效复位 | 强约束 | — |\n"
               "| 算法说明 | 两路输入饱和相加 | 参考 | — |\n\n"
               "## 3. 可信度\n\n强约束覆盖权威，权威覆盖参考。\n\n"
               "## 4. 冲突\n\n目前没有互相矛盾的输入。\n\n"
               "## 5. 红线五问\n\n时钟为单域。复位低有效且同步释放。接口为流式。"
               "吞吐由输入给定。溢出用饱和。\n" % name)
        state = load_state(self.root, name)
        first = trace_matrix(sys_dir(self.root, name), state)
        second = trace_matrix(sys_dir(self.root, name), state)
        self.assertEqual([row["input"] for row in first["rows"]], ["A001", "A002"])
        self.assertEqual([row["input"] for row in second["rows"]], ["A001", "A002"])
        self.assertTrue(any("编号" in notice for notice in first["notices"]),
                        first["notices"])
        self.assertEqual(first["rows"][0]["credibility"], "强约束")

    def test_matrix_marks_cases_without_per_case_results_as_not_regressed(self):
        name = "tracenores"
        self._plant(name)
        self._alu_platform(name)
        record_run(self.root, name, {
            "capability": "sim", "status": "pass", "summary": "全量回归通过",
            "profile_id": "p", "scope": {"scenario": "sys"},
            "checks": {"result_pass": 2, "result_fail": 0},
        })
        result = trace_matrix(sys_dir(self.root, name), load_state(self.root, name))
        row = result["rows"][0]
        self.assertEqual(row["cases"], ["alu_tc_tp1"])
        self.assertEqual(row["result"], "未回归")
        self.assertIn("逐用例", row["gap"])

    def test_matrix_reads_per_case_results_from_latest_full_regression(self):
        name = "tracecases"
        self._plant(name)
        self._alu_platform(name)
        record_run(self.root, name, {
            "capability": "sim", "status": "pass", "summary": "全量回归通过",
            "profile_id": "p", "scope": {"scenario": "sys"},
            "checks": {"result_pass": 2, "result_fail": 0,
                       "case_results": {"alu_tc_tp1": "PASS", "alu_tc_tp2": "PASS"}},
        })
        result = trace_matrix(sys_dir(self.root, name), load_state(self.root, name))
        rows = {row["input"]: row for row in result["rows"]}
        self.assertEqual(rows["A001"]["cases"], ["alu_tc_tp1"])
        self.assertEqual(rows["A001"]["result"], "PASS")
        self.assertEqual(rows["A002"]["result"], "PASS")
        self.assertEqual(rows["A001"]["run"], result["regression"]["id"])
        self.assertIn("R001", result["regression"]["id"])
        self.assertEqual(result["summary"]["cases"], 2)

    def _alu_platform(self, name):
        """补一个 alu 模块级 TB 平台：用例名与测试要点号一一对应。"""
        tc = os.path.join(sys_dir(self.root, name), "testbench", "alu", "tc")
        _write(os.path.join(tc, "alu_tc_factory.svh"),
               '"tc_tp1": begin alu_tc_tp1 t = new("tc_tp1"); return t; end\n'
               '"tc_tp2": begin alu_tc_tp2 t = new("tc_tp2"); return t; end\n')
        _write(os.path.join(tc, "alu_tc_all.sv"),
               "class alu_tc_all;\n  task body();\n"
               '    alu_tc_tp1 tc1 = new("tc_tp1");\n    tc1.body();\n'
               '    alu_tc_tp2 tc2 = new("tc_tp2");\n    tc2.body();\n'
               "  endtask\nendclass\n")
        for num in (1, 2):
            _write(os.path.join(tc, "alu_tc_tp%d.sv" % num),
                   "class alu_tc_tp%d;\n  task body();\n  endtask\nendclass\n" % num)


class TraceAnchorColumnTests(RepoTest):
    def test_chapter_model_declares_source_column_for_trace_tables(self):
        columns = load_chapter_model()["columns"]
        self.assertEqual(columns["节点表"][-1], "来源")
        self.assertEqual(columns["节点表"][0], "数据节点")
        for key in ("分组表", "模块清单", "前后级表", "交互表"):
            self.assertEqual(columns[key][-1], "来源", key)
        self.assertEqual(columns["测试要点"][-1], "来源")

    def test_missing_source_column_reports_s6(self):
        text = ("## 4. 节点表\n\n"
                "| 数据节点 | 对应步骤 | 动态范围/精度需求 | 定点格式 | 量化误差/资源取舍 |\n"
                "|---|---|---|---|---|\n"
                "| 加数 | 1. 对齐 | 输入满量程 | — | — |\n")
        findings = check_columns(text, "flow_doc/x_flow.md")
        s6 = [item for item in findings if item["rule"] == "S6"]
        self.assertTrue(s6, findings)
        self.assertIn("来源", s6[0]["detail"])


class TraceGateTests(RepoTest):
    def _plant(self, name):
        init_sys(self.root, name)
        plant_sample(self.root, name)

    def test_tr1_not_checked_before_row_six(self):
        name = "tr1early"
        self._plant(name)
        spec = os.path.join(sys_dir(self.root, name), "spec_doc", "alu_spec.md")
        _drop_line(spec, "| 1 |")
        findings = run_gates(self.root, name, 5, load_state(self.root, name))
        self.assertFalse([item for item in findings if item.get("rule") == "TR1"], findings)

    def test_tr1_blocks_strong_constraint_from_row_six(self):
        name = "tr1block"
        self._plant(name)
        spec = os.path.join(sys_dir(self.root, name), "spec_doc", "alu_spec.md")
        _drop_line(spec, "| 1 |")
        findings = run_gates(self.root, name, 6, load_state(self.root, name))
        tr1 = [item for item in findings if item.get("rule") == "TR1"]
        self.assertEqual(len(tr1), 1, findings)
        self.assertNotEqual(tr1[0].get("level"), "hint")
        self.assertIn("A001", tr1[0]["detail"])
        self.assertIn("强约束", tr1[0]["detail"])

    def test_tr1_is_hint_for_other_credibility_tiers(self):
        name = "tr1hint"
        self._plant(name)
        spec = os.path.join(sys_dir(self.root, name), "spec_doc", "alu_spec.md")
        # 两条测试要点都删掉：A001（强约束）阻断，A002（权威）只提示。
        _drop_line(spec, "| 1 |")
        _drop_line(spec, "| 2 |")
        findings = run_gates(self.root, name, 6, load_state(self.root, name))
        tr1 = {item["detail"]: item for item in findings if item.get("rule") == "TR1"}
        blocking = [item for item in tr1.values() if item.get("level") != "hint"]
        hints = [item for item in tr1.values() if item.get("level") == "hint"]
        self.assertEqual(len(blocking), 1, tr1)
        self.assertIn("A001", blocking[0]["detail"])
        self.assertEqual(len(hints), 1, tr1)
        self.assertIn("A002", hints[0]["detail"])


class TraceReviewPackTests(RepoTest):
    def _plant(self, name):
        init_sys(self.root, name)
        plant_sample(self.root, name)

    def test_m2_pack_embeds_input_to_test_point_coverage(self):
        name = "tracem2"
        self._plant(name)
        pack = milestone_report(self.root, name, "M2")
        self.assertIn("输入要点→测试要点覆盖率", pack)
        self.assertIn("2/2", pack)
        self.assertIn("100%", pack)

    def test_m3_pack_embeds_matrix_stats_and_uncovered_list(self):
        name = "tracem3"
        self._plant(name)
        spec = os.path.join(sys_dir(self.root, name), "spec_doc", "alu_spec.md")
        _drop_line(spec, "| 1 |")
        pack = milestone_report(self.root, name, "M3")
        self.assertIn("需求追溯矩阵统计", pack)
        self.assertIn("未覆盖", pack)
        self.assertIn("A001", pack)
        self.assertIn("缺口说明", pack)


class TraceCliTests(RepoTest):
    def _plant(self, name):
        init_sys(self.root, name)
        plant_sample(self.root, name)

    def test_cli_prints_markdown_matrix_by_default(self):
        name = "tracecli"
        self._plant(name)
        proc = cli(self.root, "trace", name)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("# %s 需求追溯矩阵" % name, proc.stdout)
        self.assertIn("| 输入要点 | 节点 | 模块 | 测试要点 | 用例 | 最近结果 | 缺口说明 |",
                      proc.stdout)

    def test_cli_json_emits_matrix_structure(self):
        name = "tracejson"
        self._plant(name)
        proc = cli(self.root, "trace", name, "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual(data["sys"], name)
        self.assertEqual([row["input"] for row in data["rows"]], ["A001", "A002"])
        self.assertIn("summary", data)
        self.assertIn("notices", data)


if __name__ == "__main__":
    unittest.main()
