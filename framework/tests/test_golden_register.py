# 作者：vick 邮箱：ykun@yk9811.com

"""golden 登记（CLI 与引擎）与行 10 新鲜度闸门的正反用例。

- 反：`testbench/**/data/**` 下的数据没登记 → 闸门报"参考数据未登记"；
- 正：登记后不再报；生成脚本/输入在登记之后改过 → 报"需重新生成"；
- CLI：`golden <sys> register/list`；登记前校验产物在 testbench/ 下且存在。
"""

import os
import time
import unittest

from framework.engine import EngineError, register_golden
from framework.gates.run import run_gates
from framework.state import init_sys, load_state, sys_dir
from framework.tests.util import RepoTest, cli, plant_sample

DATA = "testbench/alu/data/g.txt"
GEN = "script/gen_golden.py"


class GoldenRegisterTests(RepoTest):
    def _fixture(self, name):
        init_sys(self.root, name)
        plant_sample(self.root, name)
        base = sys_dir(self.root, name)
        os.makedirs(os.path.join(base, "testbench", "alu", "data"), exist_ok=True)
        os.makedirs(os.path.join(base, "script"), exist_ok=True)
        with open(os.path.join(base, DATA), "w", encoding="utf-8") as fh:
            fh.write("0 1 2 3\n")
        with open(os.path.join(base, GEN), "w", encoding="utf-8") as fh:
            fh.write("print('golden')\n")
        return base

    def _golden_findings(self, name):
        return [item for item in run_gates(self.root, name, 10, load_state(self.root, name))
                if item.get("rule") == "golden"]

    def test_gate_flags_unregistered_then_stale(self):
        name = "golden10"
        base = self._fixture(name)
        findings = self._golden_findings(name)
        self.assertTrue(findings, "行 10 必须查参考数据登记")
        self.assertIn("参考数据未登记", findings[0]["detail"])
        self.assertIn(DATA, findings[0]["detail"])
        spec = "spec_doc/%s_spec.md" % name
        self.assertEqual(register_golden(self.root, name, DATA, GEN, [spec]), "G001")
        self.assertEqual(self._golden_findings(name), [])
        # 生成脚本在登记之后改过 → 需重新生成（不新增字段：比 mtime 与登记时间）。
        gen_path = os.path.join(base, GEN)
        later = time.time() + 30
        os.utime(gen_path, (later, later))
        findings = self._golden_findings(name)
        self.assertEqual(len(findings), 1)
        self.assertIn("参考数据需重新生成", findings[0]["detail"])
        self.assertIn(GEN, findings[0]["detail"])

    def test_register_validates_paths(self):
        name = "goldenbad"
        base = self._fixture(name)
        with self.assertRaises(EngineError) as ctx:
            register_golden(self.root, name, "doc/g.txt", GEN, [])
        self.assertIn("testbench/", str(ctx.exception))
        with self.assertRaises(EngineError):
            register_golden(self.root, name, "testbench/alu/data/没有.txt", GEN, [])
        with self.assertRaises(EngineError):
            register_golden(self.root, name, DATA, "script/没有.py", [])
        with self.assertRaises(EngineError):
            register_golden(self.root, name, DATA, GEN, ["spec_doc/没有.md"])
        self.assertEqual(load_state(self.root, name)["golden"], [])

    def test_cli_register_and_list(self):
        name = "goldencli"
        self._fixture(name)
        proc = cli(self.root, "golden", name, "register", "--data", DATA,
                   "--gen", GEN, "--inputs", "spec_doc/%s_spec.md" % name)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("G001", proc.stdout)
        proc = cli(self.root, "golden", name, "list")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("G001", proc.stdout)
        self.assertIn(DATA, proc.stdout)
        self.assertIn(GEN, proc.stdout)


if __name__ == "__main__":
    unittest.main()
