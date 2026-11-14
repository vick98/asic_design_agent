# 作者：vick 邮箱：ykun@yk9811.com

"""模块摘要覆盖 include 链与附属文件、override 也级联的用例。

改动前会失败的点：
- `module_digest()` 只哈希 `rtl/<module>.sv`，改被 include 的表文件摘要不变；
- `override_decision()` 不触发级联，改一条数值裁决后下游停点不被标"上游裁决变更"。
"""

import os
import unittest

from framework.engine import module_digest, override_decision
from framework.flow import DONE, RUNNING
from framework.state import init_sys, load_state, save, stop_row
from framework.tests.util import RepoTest


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


class ModuleDigestIncludeTests(RepoTest):
    def setUp(self):
        super().setUp()
        self.name = "d1"
        init_sys(self.root, self.name)
        self.base = os.path.join(self.root, self.name)
        self.rtl = os.path.join(self.base, "rtl")

    def _mod(self, text):
        _write(os.path.join(self.rtl, "m1.sv"), text)

    def test_include_change_moves_digest(self):
        _write(os.path.join(self.rtl, "tbl.svh"), "// v1\n")
        self._mod('`include "tbl.svh"\nmodule m1; endmodule\n')
        before = module_digest(self.base, "m1")
        _write(os.path.join(self.rtl, "tbl.svh"), "// v2\n")
        self.assertNotEqual(before, module_digest(self.base, "m1"),
                            "改了被 include 的表，模块摘要必须变")

    def test_nested_include_is_covered(self):
        _write(os.path.join(self.rtl, "c.svh"), "// c1\n")
        _write(os.path.join(self.rtl, "b.svh"), '`include "c.svh"\n')
        self._mod('`include "b.svh"\nmodule m1; endmodule\n')
        before = module_digest(self.base, "m1")
        _write(os.path.join(self.rtl, "c.svh"), "// c2\n")
        self.assertNotEqual(before, module_digest(self.base, "m1"),
                            "二层 include 也要覆盖")

    def test_missing_include_is_reflected(self):
        self._mod('`include "later.svh"\nmodule m1; endmodule\n')
        before = module_digest(self.base, "m1")
        _write(os.path.join(self.rtl, "later.svh"), "// 出现\n")
        self.assertNotEqual(before, module_digest(self.base, "m1"),
                            "include 目标从缺到有必须改变摘要")

    def test_digest_extra_file_is_covered(self):
        _write(os.path.join(self.rtl, "gen.py"), "# gen v1\n")
        self._mod("// digest-extra: gen.py\nmodule m1; endmodule\n")
        before = module_digest(self.base, "m1")
        _write(os.path.join(self.rtl, "gen.py"), "# gen v2\n")
        self.assertNotEqual(before, module_digest(self.base, "m1"),
                            "digest-extra 声明的生成脚本必须进摘要")

    def test_plain_file_digest_still_stable(self):
        self._mod("module m1; endmodule\n")
        self.assertEqual(module_digest(self.base, "m1"), module_digest(self.base, "m1"))


class OverrideCascadeTests(RepoTest):
    def test_override_cascades_like_commit(self):
        name = "o1"
        init_sys(self.root, name)
        state = load_state(self.root, name)
        # 裁决行自己带停点（级联起点读它，不再靠 STAGE_STOP 反查）。
        state["decisions"]["3"].append({
            "id": "D3-001", "content": "补零 37088", "note": "", "kind": "数值",
            "stop": 4, "source": "I001/补零",
        })
        stop_row(state, 4)["state"] = DONE
        stop_row(state, 7)["state"] = RUNNING
        save(self.root, name, state)

        override_decision(self.root, name, "D3-001", content="补零 37080", kind="数值")

        after = load_state(self.root, name)
        row7 = stop_row(after, 7)
        self.assertIn("D3-001", row7["remark"], "override 也要把下游标成上游裁决变更")
        self.assertEqual(RUNNING, row7["state"])
        self.assertIn("history", after["decisions"]["3"][0])
        self.assertEqual("补零 37088", after["decisions"]["3"][0]["history"][0]["content"])

    def test_record_kind_does_not_cascade(self):
        name = "o2"
        init_sys(self.root, name)
        state = load_state(self.root, name)
        state["decisions"]["3"].append({
            "id": "D3-001", "content": "记录一条", "note": "", "kind": "记录",
            "stop": 4, "source": "",
        })
        stop_row(state, 7)["state"] = RUNNING
        save(self.root, name, state)
        override_decision(self.root, name, "D3-001", content="记录改了", kind="记录")
        after = load_state(self.root, name)
        self.assertNotIn("D3-001", stop_row(after, 7)["remark"],
                         "记录类不承载变更语义，不级联")


if __name__ == "__main__":
    unittest.main()
