# 作者：vick 邮箱：ykun@yk9811.com

"""规格层跨时钟域连接检查 CD1。

规格书连接表里，源端与目标端的时钟域不同（时钟域先从端口表查，查不到用连接行的
时钟域列兜底）时，必须在说明列写出 `rules/pubip.md` 已登记的跨域单元名，或引用一条
仍在裁决表里、未撤回的裁决号〔D…〕；两者都没有就阻断。同域连接、占位时钟域
（`—`）与只出现一个时钟域的设计都不报。
"""

import os
import unittest

from framework import pubip_doc
from framework.engine import withdraw_decision
from framework.gates.run import run_gates
from framework.gates.specconn import registered_cdc_units, scan_spec_conn
from framework.state import init_sys, load_state, sys_dir
from framework.tests.util import RepoTest, decide, plant_sample

WHERE = "spec_doc/demo_spec.md"


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _port(name, direction, width, clock, desc="输入"):
    return "| %s | %s | %d | %s | %s | 约定 |\n" % (name, direction, width, clock, desc)


def _conn(src, dst, width, clock, desc):
    return "| %s | %s | %d | %s | %s |\n" % (src, dst, width, clock, desc)


def _spec(ports, conns):
    text = ("# demo\n\n## 3. 模块接口\n\n"
            "| 名字 | 方向 | 位宽 | 时钟域 | 说明 | 位宽依据 |\n"
            "|---|---|---|---|---|---|\n")
    text += "".join(_port(*item) for item in ports)
    text += ("\n## 6. 模块连接关系\n\n"
             "| 源 | 目标 | 位宽 | 时钟域 | 说明 |\n|---|---|---|---|---|\n")
    text += "".join(_conn(*item) for item in conns)
    return text


def _cdc(text, state=None):
    return [item for item in scan_spec_conn(text, WHERE, state) if item["rule"] == "CD1"]


TWO_DOMAINS = [("i_a", "input", 8, "clk_a"), ("i_b", "output", 8, "clk_b")]


class CdcConnRuleTests(RepoTest):
    def test_same_domain_connection_is_not_flagged(self):
        text = _spec([("i_a", "input", 8, "clk"), ("i_b", "output", 8, "clk")],
                     [("i_a", "i_b", 8, "clk", "直连")])
        self.assertEqual(_cdc(text), [])

    def test_cross_domain_ports_are_flagged_even_when_the_row_says_one_domain(self):
        text = _spec(TWO_DOMAINS, [("i_a", "i_b", 8, "clk_a", "直连")])
        hits = _cdc(text)
        self.assertEqual(1, len(hits))
        self.assertEqual(hits[0]["where"], WHERE)
        self.assertIn("clk_a", hits[0]["detail"])
        self.assertIn("clk_b", hits[0]["detail"])

    def test_row_clock_column_is_the_fallback_for_non_port_endpoints(self):
        """子模块端口不在本模块端口表里：用连接行的时钟域列兜底。"""
        text = _spec([("i_a", "input", 8, "clk_a"), ("o_y", "output", 8, "clk_a")],
                     [("i_a", "u_sub.i_x", 8, "clk_b", "直连")])
        hits = _cdc(text)
        self.assertEqual(1, len(hits))
        self.assertIn("u_sub.i_x", hits[0]["detail"])

    def test_placeholder_domain_is_not_a_crossing(self):
        text = _spec([("i_clk", "input", 1, "—"), ("i_a", "input", 1, "—")],
                     [("i_clk", "i_a", 1, "clk", "时钟直连")])
        self.assertEqual(_cdc(text), [])

    def test_registered_unit_in_the_description_clears_the_check(self):
        text = _spec(TWO_DOMAINS,
                     [("i_a", "i_b", 8, "clk_a", "经 pubip_cdc_sync 两级同步")])
        self.assertEqual(_cdc(text), [])

    def test_registered_units_come_from_the_rule_file_and_have_rtl(self):
        units = registered_cdc_units()
        self.assertIn("pubip_cdc_sync", units)
        self.assertIn("pubip_async_fifo", units)
        modules = set(pubip_doc.pubip_modules(self.root))
        self.assertTrue(set(units) <= modules, units)

    def test_live_decision_in_the_description_clears_the_check(self):
        name = "cdcdecision"
        init_sys(self.root, name)
        did = decide(self.root, name, "跨时钟域接受，登记豁免", "方向", 1)
        text = _spec(TWO_DOMAINS, [("i_a", "i_b", 8, "clk_a", "〔%s〕跨域接受" % did)])
        self.assertEqual(_cdc(text, load_state(self.root, name)), [])

    def test_withdrawn_decision_does_not_clear_the_check(self):
        name = "cdcwithdraw"
        init_sys(self.root, name)
        did = decide(self.root, name, "跨时钟域接受，登记豁免", "方向", 1)
        withdraw_decision(self.root, name, did)
        text = _spec(TWO_DOMAINS, [("i_a", "i_b", 8, "clk_a", "〔%s〕跨域接受" % did)])
        self.assertEqual(1, len(_cdc(text, load_state(self.root, name))))

    def test_unknown_decision_does_not_clear_the_check(self):
        name = "cdcunknown"
        init_sys(self.root, name)
        text = _spec(TWO_DOMAINS, [("i_a", "i_b", 8, "clk_a", "〔D9-999〕跨域接受")])
        hits = _cdc(text, load_state(self.root, name))
        self.assertEqual(1, len(hits))
        self.assertIn("D9-999", hits[0]["detail"])


class CdcConnGateWiringTests(RepoTest):
    def _make(self, name, ports, conns):
        init_sys(self.root, name)
        _write(os.path.join(sys_dir(self.root, name), "spec_doc", name + "_spec.md"),
               _spec(ports, conns))
        return name

    def _gate_cdc(self, name, stop):
        return [item for item in run_gates(self.root, name, stop, load_state(self.root, name))
                if item["rule"] == "CD1"]

    def test_conn_gate_reports_the_finding(self):
        name = self._make("cdcconn", TWO_DOMAINS,
                          [("i_a", "i_b", 8, "clk_a", "直连")])
        hits = self._gate_cdc(name, 8)
        self.assertEqual(1, len(hits))
        self.assertEqual("spec_doc/cdcconn_spec.md", hits[0]["where"])

    def test_spec_entry_reports_the_finding(self):
        name = self._make("cdcspec", TWO_DOMAINS,
                          [("i_a", "i_b", 8, "clk_a", "直连")])
        self.assertEqual(1, len(self._gate_cdc(name, 4)))

    def test_live_decision_clears_the_gate(self):
        name = self._make("cdcgateok", TWO_DOMAINS,
                          [("i_a", "i_b", 8, "clk_a", "〔D0-001〕跨域接受")])
        did = decide(self.root, name, "跨时钟域接受，登记豁免", "方向", 1)
        self.assertEqual("D0-001", did)
        _write(os.path.join(sys_dir(self.root, name), "spec_doc", name + "_spec.md"),
               _spec(TWO_DOMAINS, [("i_a", "i_b", 8, "clk_a", "〔%s〕跨域接受" % did)]))
        self.assertEqual(self._gate_cdc(name, 8), [])

    def test_sample_fixture_has_no_cross_domain_connection(self):
        name = "cdcsample"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        self.assertEqual(self._gate_cdc(name, 5), [])


if __name__ == "__main__":
    unittest.main()
