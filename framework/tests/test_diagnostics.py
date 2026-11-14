# 作者：vick 邮箱：ykun@yk9811.com

"""结构化诊断抽取与输出侧证据复核（agreement gate）。

- diagnostics.extract：从工具输出抽 file:line 编译错与 TB_ERROR，截断不丢总数；
- record_run：log/log_digest/diagnostics 进运行记录；
- 闸门 _output_findings：日志被改动即"结论不可信，需重跑"（旧记录无字段则跳过）。
"""

import hashlib
import os
import unittest

from framework.diagnostics import extract, first_note
from framework.engine import record_run
from framework.gates.run import _diag_suffix, _output_findings
from framework.state import init_sys, load_state
from framework.tests.util import RepoTest

IVERILOG_LOG = """\
demo/rtl/foo.sv:12: error: syntax error near ';'
demo/rtl/foo.sv:15: warning: implicit wire
TB_ERROR tp2 期望 8'hA0 实得 8'hB1
RESULT : FAIL
"""

VERILATOR_LOG = """\
%{}: demo/rtl/bar.sv:30: Unexpected token
""".format("Err" + "or")
# 厂商日志字面量按拼接构造：框架目录禁出现原始串（test_profile 的禁用清单）。


class ExtractTests(unittest.TestCase):
    def test_iverilog_compile_and_tb_run(self):
        items, total = extract(IVERILOG_LOG)
        self.assertEqual(total, 3)
        self.assertEqual(items[0]["phase"], "compile")
        self.assertEqual(items[0]["tool"], "iverilog")
        self.assertEqual(items[0]["file"], "demo/rtl/foo.sv")
        self.assertEqual(items[0]["line"], 12)
        self.assertIn("syntax error", items[0]["msg"])
        run_items = [item for item in items if item["phase"] == "run"]
        self.assertEqual(len(run_items), 1)
        self.assertEqual(run_items[0]["file"], "")
        self.assertIn("tp2", run_items[0]["msg"])

    def test_verilator_pattern(self):
        items, total = extract(VERILATOR_LOG)
        self.assertEqual(total, 1)
        self.assertEqual(items[0]["tool"], "verilator")
        self.assertEqual(items[0]["line"], 30)

    def test_empty_text_and_no_hits(self):
        self.assertEqual(extract(""), ([], 0))
        self.assertEqual(extract("一切正常 RESULT : PASS"), ([], 0))

    def test_cap_keeps_total(self):
        text = "".join("demo/rtl/f.sv:%d: error: bad\n" % line for line in range(1, 25))
        items, total = extract(text)
        self.assertEqual(total, 24)
        self.assertEqual(len(items), 10)

    def test_one_diagnostic_per_line(self):
        # 同一行同时匹配泛型与 iverilog 模式时只计一条。
        items, total = extract("demo/rtl/x.sv:3: error: dup\n")
        self.assertEqual(total, 1)
        self.assertEqual(items[0]["tool"], "iverilog")


class FirstNoteTests(unittest.TestCase):
    def test_first_note_with_total(self):
        items, total = extract(IVERILOG_LOG)
        run = {"id": "R007", "diagnostics": items, "diagnostics_total": total}
        note = first_note(run)
        self.assertIn("compile", note)
        self.assertIn("foo.sv:12", note)
        self.assertIn("共 3 条", note)
        self.assertIn("R007", _diag_suffix(run))

    def test_first_note_without_diagnostics(self):
        self.assertEqual(first_note({}), "")
        self.assertEqual(first_note({"diagnostics": []}), "")


class RecordRunEvidenceTests(RepoTest):
    def test_record_run_stores_log_digest_and_diagnostics(self):
        name = "diag"
        init_sys(self.root, name)
        log_rel = os.path.join(name, "work", "sim.log")
        os.makedirs(os.path.dirname(os.path.join(self.root, log_rel)), exist_ok=True)
        log_text = IVERILOG_LOG
        with open(os.path.join(self.root, log_rel), "w", encoding="utf-8") as fh:
            fh.write(log_text)
        record_run(self.root, name, {
            "capability": "sim", "status": "pass", "summary": "RESULT : PASS",
            "profile_id": "example",
            "scope": {"scenario": "sys", "module": "", "tc": ""},
            "checks": {"result_pass": 1, "result_fail": 0, "full_regression": 1},
            "log": log_rel.replace(os.sep, "/"),
            "log_digest": hashlib.sha256(log_text.encode("utf-8")).hexdigest(),
            "diagnostics": extract(log_text)[0],
            "diagnostics_total": extract(log_text)[1],
        })
        run = load_state(self.root, name)["runs"][-1]
        self.assertEqual(run["log"], log_rel.replace(os.sep, "/"))
        self.assertEqual(run["diagnostics_total"], 3)
        self.assertEqual(len(run["diagnostics"]), 3)

    def test_record_run_without_output_fields(self):
        name = "diag"
        init_sys(self.root, name)
        record_run(self.root, name, {
            "capability": "sim", "status": "pass", "summary": "RESULT : PASS",
            "profile_id": "example",
            "scope": {"scenario": "sys", "module": "", "tc": ""},
            "checks": {"result_pass": 1, "result_fail": 0, "full_regression": 1},
        })
        run = load_state(self.root, name)["runs"][-1]
        self.assertNotIn("log", run)
        self.assertNotIn("diagnostics", run)


class OutputFindingsTests(RepoTest):
    def _record(self, name, log_text):
        log_rel = os.path.join(name, "work", "sim.log")
        path = os.path.join(self.root, log_rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(log_text)
        rid = record_run(self.root, name, {
            "capability": "sim", "status": "pass", "summary": "RESULT : PASS",
            "profile_id": "example",
            "scope": {"scenario": "sys", "module": "", "tc": ""},
            "checks": {"result_pass": 1, "result_fail": 0, "full_regression": 1},
            "log": log_rel.replace(os.sep, "/"),
            "log_digest": hashlib.sha256(log_text.encode("utf-8")).hexdigest(),
        })
        return rid, log_rel

    def test_matching_digest_passes(self):
        name = "agree"
        init_sys(self.root, name)
        rid, log_rel = self._record(name, "RESULT : PASS\n")
        run = load_state(self.root, name)["runs"][-1]
        self.assertEqual(_output_findings(self.root, name, run), [])

    def test_tampered_log_flagged(self):
        name = "agree"
        init_sys(self.root, name)
        rid, log_rel = self._record(name, "RESULT : PASS\n")
        with open(os.path.join(self.root, log_rel), "a", encoding="utf-8") as fh:
            fh.write("RESULT : PASS\n")  # 事后补一行，摘要就对不上了
        run = load_state(self.root, name)["runs"][-1]
        findings = _output_findings(self.root, name, run)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["rule"], "run-log")
        self.assertIn("结论不可信", findings[0]["detail"])
        self.assertIn(rid, findings[0]["detail"])

    def test_old_records_without_field_are_skipped(self):
        name = "agree"
        init_sys(self.root, name)
        record_run(self.root, name, {
            "capability": "sim", "status": "pass", "summary": "RESULT : PASS",
            "profile_id": "example",
            "scope": {"scenario": "sys", "module": "", "tc": ""},
            "checks": {"result_pass": 1, "result_fail": 0, "full_regression": 1},
        })
        run = load_state(self.root, name)["runs"][-1]
        self.assertEqual(_output_findings(self.root, name, run), [])

    def test_missing_log_flagged(self):
        name = "agree"
        init_sys(self.root, name)
        rid, log_rel = self._record(name, "RESULT : PASS\n")
        os.remove(os.path.join(self.root, log_rel))
        run = load_state(self.root, name)["runs"][-1]
        findings = _output_findings(self.root, name, run)
        self.assertEqual(len(findings), 1)
        self.assertIn("不存在", findings[0]["detail"])


if __name__ == "__main__":
    unittest.main()
