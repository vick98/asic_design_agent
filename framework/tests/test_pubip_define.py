# 作者：vick 邮箱：ykun@yk9811.com

"""pubip 变体编译宏透传——--define 校验、日志落 pub_code、闸门跳过非 sys 记录。"""

import os
import subprocess
import sys
import unittest

from framework.gates.run import _latest
from framework.paths import project_root
from framework.profile_run import _write_log, run_sim
from framework.state import init_sys
from framework.tests.util import RepoTest, checkout_root


def _script():
    return os.path.join(checkout_root(), "script", "framework.py")


def _run(args, root):
    env = os.environ.copy()
    env["ADF_ROOT"] = root
    return subprocess.run(
        [sys.executable, _script()] + args,
        env=env, capture_output=True, text=True,
    )


class DefineTests(RepoTest):
    def setUp(self):
        super().setUp()
        self.name = "define_" + self._testMethodName.replace("test_", "")
        init_sys(self.root, self.name)

    def test_pubip_define_dry_run(self):
        result = run_sim({
            "scenario": "pubip", "module": "pubip_round", "sys": self.name,
            "dry_run": True, "defines": ["PUBIP_ROUND_Z4"],
        })
        self.assertEqual(result["status"], "dry_run")
        summary = result["summary"]
        # 宏进编译行
        self.assertIn("+define+PUBIP_ROUND_Z4", summary)
        # 日志名带 define，且工作目录是 pub_code/work/<module>
        self.assertIn("sim_PUBIP_ROUND_Z4.log", summary)
        self.assertIn("pub_code/work/pubip_round", summary)

    def test_define_values_reach_compile_line(self):
        result = run_sim({
            "scenario": "pubip", "module": "pubip_round", "sys": self.name,
            "dry_run": True, "defines": ["WIDTH=64"],
        })
        self.assertIn("+define+WIDTH=64", result["summary"])

    def test_define_rejects_shell_metachars(self):
        for bad in ("A;rm", "A B", "A$(x)", "A|x", "A'B", 'A"B', "A\nB", "-A", "1A"):
            with self.assertRaises(ValueError, msg=bad):
                run_sim({
                    "scenario": "pubip", "module": "pubip_round", "sys": self.name,
                    "dry_run": True, "defines": [bad],
                })
        for good in ("PUBIP_ROUND_Z4", "_X", "WIDTH=64", "TAG=ucsw-1.5"):
            run_sim({
                "scenario": "pubip", "module": "pubip_round", "sys": self.name,
                "dry_run": True, "defines": [good],
            })

    def test_pubip_log_lands_under_pub_code(self):
        rel = _write_log(os.path.join("pub_code", "work", "pubip_round"),
                         "sim_PUBIP_ROUND_Z4", "hello")
        self.assertEqual(rel, ["pub_code/work/pubip_round/sim_PUBIP_ROUND_Z4.log"])
        path = os.path.join(project_root(), rel[0])
        self.assertTrue(os.path.isfile(path))
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "hello")

    def test_sys_sim_log_unchanged(self):
        rel = _write_log(os.path.join(self.name, "work"), "sim", "hello")
        self.assertEqual(rel, ["%s/work/sim.log" % self.name])

    def test_latest_sim_skips_non_sys_records(self):
        state = {"runs": [
            {"capability": "sim", "status": "pass", "scope": {"scenario": "sys"}},
            {"capability": "sim", "status": "pass",
             "scope": {"scenario": "pubip", "module": "pubip_round"}},
        ]}
        # pubip 记录在后也不顶掉：行 10 与覆盖率绑定都只认 sys。
        self.assertEqual(_latest(state, "sim")["scope"]["scenario"], "sys")
        state["runs"][0]["scope"]["scenario"] = "module"
        self.assertIsNone(_latest(state, "sim"))

    def test_cli_define_repeatable(self):
        proc = _run(["run", "sim", "--scenario", "pubip", "--module", "pubip_round",
                     "--sys", self.name, "--define", "A", "--define", "B=2",
                     "--dry-run"], self.root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("+define+A", proc.stdout)
        self.assertIn("+define+B=2", proc.stdout)

    def test_cli_define_bad_is_rejected(self):
        proc = _run(["run", "sim", "--scenario", "pubip", "--module", "pubip_round",
                     "--sys", self.name, "--define", "A;rm", "--dry-run"], self.root)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("只接受标识符", proc.stderr)


if __name__ == "__main__":
    unittest.main()
