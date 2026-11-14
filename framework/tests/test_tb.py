# 作者：vick 邮箱：ykun@yk9811.com

import os
import re
import unittest

from framework.gates.tc import scan_tc
from framework.profile_run import run_sim
from framework.tests.util import RepoTest, checkout_root


def _compile_line(script):
    for line in script.splitlines():
        if "-sverilog" in line and "-f " in line:
            return re.sub(r"\s+", " ", line).strip()
    return ""


class TbTests(RepoTest):
    def test_fsdb_compile_line_matches_sample(self):
        result = run_sim({
            "scenario": "pubip", "module": "pubip_counter", "wave": "fsdb", "dry_run": True,
        })
        got = _compile_line(result["summary"])
        sample = os.path.join(checkout_root(), "framework", "tests", "data", "pubip_counter_fsdb_compile.txt")
        with open(sample, encoding="utf-8") as fh:
            expect = re.sub(r"\s+", " ", fh.read()).strip()
        self.assertEqual(got, expect)

    def test_pub_code_tb_gate(self):
        findings = scan_tc(os.path.join(self.root, "pub_code"))
        blocking = [item for item in findings if item.get("level") != "hint"]
        self.assertEqual(blocking, [])

    def test_missing_factory_registration_fails(self):
        factory = os.path.join(
            self.root, "pub_code", "testbench", "pubip_counter", "tc", "pubip_counter_tc_factory.svh")
        with open(factory, encoding="utf-8") as fh:
            text = fh.read()
        try:
            with open(factory, "w", encoding="utf-8") as fh:
                fh.write(text.replace('"tc_basic":', '"tc_unused":', 1))
            findings = scan_tc(os.path.join(self.root, "pub_code"))
            self.assertTrue(any(item.get("rule") == "T2" and "tc_basic" in item.get("detail", "") for item in findings))
        finally:
            with open(factory, "w", encoding="utf-8") as fh:
                fh.write(text)


if __name__ == "__main__":
    unittest.main()
