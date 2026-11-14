# 作者：vick 邮箱：ykun@yk9811.com

"""docs 闸门：「待确认」标注必须带一个仍打开的问题号。"""

import os
import unittest

from framework.engine import add_problem, close_problem
from framework.gates.docs import pending_confirmations, scan_docs
from framework.gates.run import run_gates
from framework.state import init_sys, load_state, save, sys_dir
from framework.tests.util import RepoTest, decide, plant_sample


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _flow_doc(name, input_output_body):
    return (
        "# %s_flow\n\n简介。\n\n"
        "## 2. 输入输出\n\n%s\n\n"
        "## 3. 步骤\n\n正文。\n\n"
        "## 4. 节点表\n\n正文。\n\n"
        "## 5. 运算定点化图\n\n正文。\n\n"
        "## 6. 边界点\n\n正文。\n"
    ) % (name, input_output_body)


class PendingConfirmationTests(RepoTest):
    def _init(self, name):
        init_sys(self.root, name)
        return sys_dir(self.root, name)

    def _write_flow(self, name, body):
        path = os.path.join(sys_dir(self.root, name), "flow_doc", "%s_flow.md" % name)
        _write(path, _flow_doc(name, body))
        return path

    def _u1(self, name, stop=2):
        findings = run_gates(self.root, name, stop, load_state(self.root, name))
        return [item for item in findings if item["rule"] == "U1"]

    def test_helper_lists_pending_confirmation_lines(self):
        text = ("# 标题\n\n"
                "节点格式：`x` <16,8,u>（推断-待确认）\n"
                "普通正文。\n"
                "输入未给出精度，标（信息缺失-待确认）见第 2 节。\n")
        self.assertEqual(pending_confirmations(text), [
            "节点格式：`x` <16,8,u>（推断-待确认）",
            "输入未给出精度，标（信息缺失-待确认）见第 2 节。",
        ])
        self.assertEqual(pending_confirmations("没有标注的正文。\n"), [])

    def test_annotation_without_open_problem_is_blocked(self):
        name = "u1bare"
        self._init(name)
        self._write_flow(name, "格式 <16,8,u>（推断-待确认）。")
        hits = self._u1(name)
        self.assertEqual(len(hits), 1, hits)
        self.assertIn("问题号", hits[0]["detail"])
        self.assertIn("待确认", hits[0]["detail"])

    def test_annotation_referencing_unknown_problem_is_blocked(self):
        name = "u1unknown"
        self._init(name)
        self._write_flow(name, "格式 <16,8,u>（推断-待确认）〔I999〕。")
        self.assertEqual(len(self._u1(name)), 1, self._u1(name))

    def test_annotation_with_open_problem_reference_passes(self):
        name = "u1open"
        self._init(name)
        pid = add_problem(self.root, name, "阻断", 2, "输入格式待定", "审查")
        for ref in ("〔%s〕" % pid, "[%s]" % pid):
            with self.subTest(ref=ref):
                self._write_flow(name, "格式 <16,8,u>（推断-待确认）%s。" % ref)
                self.assertEqual(self._u1(name), [], ref)

    def test_closing_problem_makes_annotation_block_again(self):
        name = "u1closed"
        self._init(name)
        pid = add_problem(self.root, name, "阻断", 2, "输入格式待定", "审查")
        self._write_flow(name, "格式 <16,8,u>（推断-待确认）〔%s〕。" % pid)
        self.assertEqual(self._u1(name), [], "问题仍打开时不应报 U1")
        did = decide(self.root, name, "格式按有符号 16 位处理", "记录", 2)
        close_problem(self.root, name, pid, evidence=did)
        self.assertEqual(len(self._u1(name)), 1, "问题关闭后同一标注应报 U1")

    def test_problem_without_open_key_counts_as_open(self):
        name = "u1nokey"
        self._init(name)
        pid = add_problem(self.root, name, "阻断", 2, "输入格式待定", "审查")
        self._write_flow(name, "格式 <16,8,u>（推断-待确认）〔%s〕。" % pid)
        state = load_state(self.root, name)
        next(item for item in state["problems"] if item["id"] == pid).pop("open", None)
        save(self.root, name, state)
        self.assertEqual(self._u1(name), [], "open 缺省应视为打开")

    def test_scan_docs_without_state_skips_u1(self):
        name = "u1nostate"
        self._init(name)
        self._write_flow(name, "格式 <16,8,u>（推断-待确认）。")
        findings = scan_docs(sys_dir(self.root, name), 2)
        self.assertFalse([item for item in findings if item["rule"] == "U1"], findings)
        self.assertTrue(self._u1(name), "run_gates 传 state 后应报 U1")

    def test_sample_fixture_has_no_u1(self):
        name = "u1sample"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        for sid in range(1, 7):
            self.assertEqual(self._u1(name, sid), [], "停点 %d 不应误报 U1" % sid)


if __name__ == "__main__":
    unittest.main()
