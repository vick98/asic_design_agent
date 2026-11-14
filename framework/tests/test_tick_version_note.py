# 作者：vick 邮箱：ykun@yk9811.com

"""tick todo 表提示工具版本不一致；cdc 输入集挂点。

- 运行记录 note 里"工具版本与 expect_versions 不一致"归入**可推进的工作**，
  不进"需要开发者"；别的 note（如 cov_unwaived）不会被误收成同一条。
- 交接挂点：`CAPABILITY_INPUTS["cdc"]` 定义后，cdc 记录的输入摘要只看
  RTL/SDC 这类输入，不再走"全量输入"旧口径。
"""

import os
import unittest

from framework.engine import CAPABILITY_INPUTS, _tick_lists, inputs_digest, record_run
from framework.state import init_sys, load_state, sys_dir
from framework.tests.util import RepoTest, plant_sample


class ToolVersionNoteTests(RepoTest):
    def test_version_mismatch_is_todo_not_human(self):
        name = "f2bnote"
        init_sys(self.root, name)
        record_run(self.root, name, {
            "capability": "synth", "status": "pass", "summary": "synth pass",
            "profile_id": "example",
            "note": "synth 的工具版本与 expect_versions 不一致：期望含 T-2022.03，实测 T-2020.03",
            "checks": {"errors": 0, "tool_versions": {"logic_synth": "T-2020.03"}},
        })
        todo, human = _tick_lists(self.root, name, load_state(self.root, name))
        todo_text, human_text = "\n".join(todo), "\n".join(human)
        self.assertIn("工具版本", todo_text)
        self.assertIn("expect_versions", todo_text)
        self.assertIn("R", todo_text)
        self.assertNotIn("工具版本", human_text)

    def test_other_notes_are_not_mixed_into_the_version_hint(self):
        name = "f2bother"
        init_sys(self.root, name)
        record_run(self.root, name, {
            "capability": "coverage", "status": "pass", "summary": "coverage pass",
            "profile_id": "example",
            "note": "cov_unwaived：line=50.0 低于默认 60.0",
            "checks": {"line": 50.0, "cond": 100.0, "fsm": 100.0, "tgl": 100.0},
        })
        todo, human = _tick_lists(self.root, name, load_state(self.root, name))
        self.assertNotIn("工具版本", "\n".join(todo))
        self.assertNotIn("工具版本", "\n".join(human))


class CdcInputSetTests(RepoTest):
    def test_cdc_has_its_own_input_set(self):
        self.assertEqual(CAPABILITY_INPUTS["cdc"], ("rtl", "pub_code", "sdc"))

    def test_cdc_digest_ignores_testbench_but_full_digest_does_not(self):
        name = "cdcset"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        base = sys_dir(self.root, name)
        full_before = inputs_digest(self.root, name)
        cdc_before = inputs_digest(self.root, name, capability="cdc")
        self.assertNotEqual(full_before, cdc_before, "cdc 不应走全量输入口径")
        # 改 TB：全量摘要变，cdc 摘要不变（cdc 只吃 rtl/pub_code/sdc）。
        tb = os.path.join(base, "testbench", "tc", "tc_extra.sv")
        os.makedirs(os.path.dirname(tb), exist_ok=True)
        with open(tb, "w", encoding="utf-8") as fh:
            fh.write("// cdc 输入集用例\n")
        self.assertNotEqual(full_before, inputs_digest(self.root, name))
        self.assertEqual(cdc_before, inputs_digest(self.root, name, capability="cdc"))
        # SDC 与 synth/sta 同款口径：走"显式附加路径"（绝对路径），给了才进摘要。
        sdc_dir = os.path.join(base, "sdc")
        os.makedirs(sdc_dir, exist_ok=True)
        sdc = os.path.join(sdc_dir, "top.sdc")
        with open(sdc, "w", encoding="utf-8") as fh:
            fh.write("create_clock -period 10 [get_ports clk]\n")
        with_sdc = inputs_digest(self.root, name, extra_paths=[sdc], capability="cdc")
        with open(sdc, "w", encoding="utf-8") as fh:
            fh.write("create_clock -period 8 [get_ports clk]\n")
        self.assertNotEqual(
            with_sdc, inputs_digest(self.root, name, extra_paths=[sdc], capability="cdc"))


if __name__ == "__main__":
    unittest.main()
