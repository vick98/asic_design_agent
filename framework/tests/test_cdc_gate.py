# 作者：vick 邮箱：ykun@yk9811.com

"""行 8 跨时钟域闸门：端口表出现两个以上时钟域时，要一条 cdc 通过记录，
或引用点选入库的裁决登记豁免。

本机与远端都没有 CDC 工具许可，所以闸门不跑工具，只认证据与豁免。
"""

import os
import unittest

from framework.engine import add_waiver, record_run
from framework.gates.run import run_gates
from framework.gates.specconn import scan_clock_domains, spec_clock_domains
from framework.state import init_sys, load_state, sys_dir
from framework.tests.util import RepoTest, decide


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _spec(*rows):
    return ("# demo\n\n## 3. 模块接口\n\n"
            "| 名字 | 方向 | 位宽 | 时钟域 | 说明 | 位宽依据 |\n|---|---|---|---|---|---|\n"
            + "".join(rows))


def _port(name, width, clock):
    return "| %s | input | %d | %s | 输入 | 约定 |\n" % (name, width, clock)


class ClockDomainParseTests(RepoTest):
    def test_placeholder_domains_are_ignored(self):
        text = _spec(_port("i_a", 8, "clk"), _port("i_b", 8, "—"),
                     _port("i_c", 8, "-"), _port("i_d", 8, ""))
        self.assertEqual(["clk"], spec_clock_domains(text))

    def test_domains_are_union_of_spec_files(self):
        base = os.path.join(self.root, "union")
        _write(os.path.join(base, "spec_doc", "alu_spec.md"), _spec(_port("i_a", 8, "clk")))
        _write(os.path.join(base, "spec_doc", "glue_spec.md"), _spec(_port("i_b", 8, "clk2")))
        self.assertEqual(["clk", "clk2"], scan_clock_domains(base))

    def test_missing_spec_dir_is_silent(self):
        self.assertEqual([], scan_clock_domains(os.path.join(self.root, "empty")))


class CdcGateTests(RepoTest):
    def _make(self, name, ports):
        init_sys(self.root, name)
        _write(os.path.join(sys_dir(self.root, name), "spec_doc", name + "_spec.md"),
               _spec(*ports))
        return name

    def _cdc(self, name):
        return [item for item in run_gates(self.root, name, 8, load_state(self.root, name))
                if item.get("rule") == "cdc"]

    def _two_domains(self):
        return [_port("i_a", 8, "clk"), _port("i_b", 8, "clk2")]

    def test_single_domain_is_not_blocked(self):
        name = self._make("cdcone", [_port("i_clk", 1, "clk"), _port("i_a", 8, "clk")])
        self.assertEqual([], self._cdc(name))

    def test_placeholder_clock_column_is_not_a_domain(self):
        name = self._make("cdcplace", [_port("i_clk", 1, "clk"), _port("i_a", 8, "—")])
        self.assertEqual([], self._cdc(name))

    def test_two_domains_without_evidence_are_blocked(self):
        name = self._make("cdctwo", self._two_domains())
        hits = self._cdc(name)
        self.assertEqual(1, len(hits))
        self.assertEqual("行 8", hits[0]["where"])
        self.assertIn("clk2", hits[0]["detail"])

    def test_pass_record_clears_the_gate(self):
        name = self._make("cdcpass", self._two_domains())
        record_run(self.root, name, {
            "capability": "cdc", "status": "pass", "summary": "cdc pass", "profile_id": "p"})
        self.assertEqual([], self._cdc(name))

    def test_failed_record_does_not_clear_the_gate(self):
        name = self._make("cdcfail", self._two_domains())
        record_run(self.root, name, {
            "capability": "cdc", "status": "fail", "summary": "cdc fail", "profile_id": "p"})
        hits = self._cdc(name)
        self.assertEqual(1, len(hits))
        self.assertIn("fail", hits[0]["detail"])

    def test_waiver_with_a_live_decision_clears_the_gate(self):
        name = self._make("cdcwaive", self._two_domains())
        content = "两个时钟域接受，登记豁免"
        did = decide(self.root, name, content, "方向", 1)
        self.assertEqual("D0-001", did)          # 停点 1 → 阶段 0
        add_waiver(self.root, name, "cdc", "行 8", did)
        self.assertEqual([], self._cdc(name))

    def test_waiver_for_another_rule_does_not_clear_the_gate(self):
        name = self._make("cdcother", self._two_domains())
        content = "别的规则接受"
        did = decide(self.root, name, content, "方向", 1)
        add_waiver(self.root, name, "S1", "info_input/x.md", did)
        self.assertEqual(1, len(self._cdc(name)))


if __name__ == "__main__":
    unittest.main()
