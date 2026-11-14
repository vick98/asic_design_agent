# 作者：vick 邮箱：ykun@yk9811.com

"""模块 lint/审查标记失效要在状态文档与 status 里看得见，不能只有闸门知道。

模块状态由文件与证据推导（engine.module_state）：模块条目只存证据
（rtl_review 的 kind/digest/author/...，或显式 `state:"退回"`），派生的 state 值不进
state.json。所以夹具按证据写——lint 走运行记录（scope.modules）、审查走 review_record
产生的 kind/digest 条目，不再手工写"审查通过/lint 通过"这类派生状态。
"""

import hashlib
import os
import unittest

from framework.engine import record_run, status_report
from framework.state import init_sys, load_state, render, save
from framework.tests.util import RepoTest, review


class StaleModuleMarkTests(RepoTest):
    def setUp(self):
        super().setUp()
        self.name = "g04_" + self._testMethodName.replace("test_", "")
        init_sys(self.root, self.name)
        self.rtl = os.path.join(self.root, self.name, "rtl", "alu.sv")
        with open(self.rtl, "w", encoding="utf-8") as fh:
            fh.write("module alu #(parameter X = 1)(input [7:0] i_a, output [7:0] o_y);\nendmodule\n")
        self.digest = hashlib.sha256(open(self.rtl, "rb").read()).hexdigest()

    def _touch(self):
        with open(self.rtl, "a", encoding="utf-8") as fh:
            fh.write("// touched\n")

    def _lint(self):
        """行 7 的 lint 通过证据：逐模块的运行记录（record_run 顺带记模块摘要）。"""
        return record_run(self.root, self.name, {
            "capability": "lint", "status": "pass", "summary": "lint pass",
            "scope": {"modules": ["alu"]},
        })

    def _status_md(self):
        render(self.root, self.name, load_state(self.root, self.name))
        path = os.path.join(self.root, self.name, "%s_status.md" % self.name)
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def test_review_mark_stale_after_file_change(self):
        # 真实证据链：lint 运行记录 + 绑当前模块摘要的 rtl_review 条目。
        self._lint()
        review(self.root, self.name, 7, module="alu")
        before = self._status_md()
        self.assertIn("alu：审查通过", before)
        self.assertNotIn("文件已改", before)
        self._touch()
        text = self._status_md()
        # 审查证据对不上当前文件：派生状态退到"已生成"，并标出失效原因。
        self.assertIn("alu：已生成（文件已改，需重审）", text)
        self.assertIn("标记失效：1 个模块", text)
        self.assertIn("标记失效：1 个模块", status_report(self.root, self.name))
        # 原始 JSON（digest/confirm_quote）不再进状态文档。
        self.assertNotIn("confirm_quote", text)
        self.assertNotIn('"digest"', text)

    def test_lint_mark_stale_after_file_change(self):
        # 行 7 的 lint 通过由 runs 推导；模块条目里 v2 遗留的绑摘要证据（迁移后
        # 只剩 digest）在文件改动后仍要被标失效——否则状态文档看不出"需重跑 lint"。
        self._lint()
        state = load_state(self.root, self.name)
        state["modules"]["7"] = [{"name": "alu", "digest": self.digest}]
        save(self.root, self.name, state)
        before = self._status_md()
        self.assertIn("alu：lint 通过", before)
        self.assertNotIn("文件已改", before)
        self._touch()
        self.assertIn("alu：已生成（文件已改，需重跑 lint）", self._status_md())

    def test_fresh_mark_shows_nothing(self):
        self._lint()
        review(self.root, self.name, 7, module="alu")
        text = self._status_md()
        self.assertIn("alu：审查通过", text)
        self.assertNotIn("标记失效", text)
        self.assertNotIn("标记失效", status_report(self.root, self.name))

    def test_bare_name_entry_has_no_stale_note(self):
        # 条目只有名字、没登记过任何证据：没有可失效的标记，不报"文件已改"。
        state = load_state(self.root, self.name)
        state["modules"]["7"] = [{"name": "alu"}]
        save(self.root, self.name, state)
        text = self._status_md()
        self.assertIn("alu：已生成", text)
        self.assertNotIn("文件已改", text)
        self.assertNotIn("标记失效", text)

    def test_rows_8_9_have_no_stale_note(self):
        # 行 8/9 的通过态同样由证据推导，但不参与行 7 的陈旧标注
        #（module_stale_note 只对行 7 出文案）。
        top = os.path.join(self.root, self.name, "rtl", "%s_top.sv" % self.name)
        with open(top, "w", encoding="utf-8") as fh:
            fh.write("module %s_top; endmodule\n" % self.name)
        review(self.root, self.name, 8)
        state = load_state(self.root, self.name)
        state["modules"]["9"] = [{"name": "tb"}]
        save(self.root, self.name, state)
        text = self._status_md()
        self.assertIn("%s_top：连接通过" % self.name, text)
        self.assertIn("tb：未开始", text)
        self.assertNotIn("文件已改", text)
        self.assertNotIn("标记失效", text)


if __name__ == "__main__":
    unittest.main()
