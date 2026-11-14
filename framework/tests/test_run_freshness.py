# 作者：vick 邮箱：ykun@yk9811.com

"""摘要时机、按能力分输入集、工作目录锁、裁决注记闸门只认裁决表。

改前会失败的点：
- record_run 在远端跑完拉回后才算 inputs_digest，运行期间改 RTL 记录仍判新鲜；
- inputs_digest 对所有能力统一哈希 rtl/testbench/spec_doc，改一处规格书措辞
  就把 lint/综合记录全部判"输入已变更"；
- 同一 (sys, scenario, module) 并行派工共用远端 <sys>/work，互相覆盖产物；
- replace_notes 用 Python 批量改写子系统 .md，可能改到已送审产物——该函数已删除：
  注记由作者直接写〔D…〕，闸门 W3（gates/specconn.scan_notes）只查裁决表，
  从不改写任何产物。
"""

import os
import subprocess
import threading
import time
import unittest

from framework.engine import CAPABILITY_INPUTS, inputs_digest, record_run
from framework.gates.run import run_gates
from framework.profile_run import run_other, run_sim
from framework.state import init_sys, load_state, sys_dir
from framework.tests.util import RepoTest, decide


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _append(path, text):
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(text)


class FakeProc:
    def __init__(self, stdout=""):
        self.stdout = stdout
        self.stderr = ""
        self.returncode = 0


def _md_snapshot(root, name):
    """子系统里全部 .md 的 {相对路径: 字节}，供注记闸门前后比对。"""
    base = sys_dir(root, name)
    snap = {}
    for dirpath, _dirs, files in os.walk(base):
        for fn in files:
            if fn.endswith(".md"):
                path = os.path.join(dirpath, fn)
                with open(path, "rb") as fh:
                    snap[os.path.relpath(path, base)] = fh.read()
    return snap


class CapabilityInputSetTests(RepoTest):
    """能力 → 输入路径集合的唯一事实源是 engine.CAPABILITY_INPUTS。"""

    def test_capability_input_table(self):
        self.assertEqual(CAPABILITY_INPUTS, {
            "lint": ("rtl", "pub_code"),
            "sim": ("rtl", "testbench", "tb_common", "pub_code"),
            "coverage": ("rtl", "testbench", "tb_common", "pub_code"),
            "synth": ("rtl", "pub_code", "sdc"),
            "sta": ("netlist", "sdc"),
            "conn": ("netlist", "sdc"),
            "signoff": ("netlist", "sdc"),
            # 时钟域交叉检查的输入集与 synth 同源（RTL + 公共代码 + SDC）。
            "cdc": ("rtl", "pub_code", "sdc"),
            # 等价性检查（CEC）：候选 RTL + 公共代码；黄金参考走 extra_paths 进摘要。
            "lec": ("rtl", "pub_code"),
        })

    def test_spec_doc_not_in_any_run_input_set(self):
        for items in CAPABILITY_INPUTS.values():
            self.assertNotIn("spec_doc", items)


class FreshnessScopeTests(RepoTest):
    """实测口径：逐类改动只影响它所属能力的记录。"""

    def setUp(self):
        super().setUp()
        self.name = "fresh1"
        init_sys(self.root, self.name)
        self.base = sys_dir(self.root, self.name)
        self.rtl = os.path.join(self.base, "rtl", "alu.sv")
        self.tbl = os.path.join(self.base, "rtl", "tbl.svh")
        self.tb = os.path.join(self.base, "testbench", "alu_tb.sv")
        self.spec = os.path.join(self.base, "spec_doc", "fresh1_spec.md")
        self.sdc = os.path.join(self.base, "dc", "top.sdc")
        self.netlist = os.path.join(self.base, "dc", "top.v")
        _write(self.rtl, 'module alu;\n`include "tbl.svh"\nendmodule\n')
        _write(self.tbl, "// tbl v1\n")
        _write(self.tb, "module alu_tb; endmodule\n")
        _write(self.spec, "# fresh1 规格\n初版。\n")
        _write(self.sdc, "create_clock -period 1.0 [get_ports clk]\n")
        _write(self.netlist, "module top; endmodule\n")

    def _record(self, capability):
        result = {"capability": capability, "status": "pass", "summary": "ok", "profile_id": "p"}
        if capability == "lint":
            result["scope"] = {"modules": ["alu"]}
        elif capability == "sim":
            result["scope"] = {"scenario": "sys", "tc": ""}
        elif capability == "synth":
            result["sdc_paths"] = [self.sdc]
        elif capability == "sta":
            result["sdc_paths"] = [self.sdc]
            result["scope"] = {"scenario": "sys", "netlist": "%s/dc/top.v" % self.name}
        record_run(self.root, self.name, result)

    def _stale(self, row, where):
        findings = run_gates(self.root, self.name, row, load_state(self.root, self.name))
        return [item for item in findings
                if item.get("where") == where and "输入已变更" in item.get("detail", "")]

    def test_spec_doc_wording_keeps_lint_and_sim_fresh(self):
        self._record("lint")
        self._record("sim")
        _write(self.spec, "# fresh1 规格\n只改一处措辞。\n")
        self.assertEqual(self._stale(7, "lint"), [], "改规格书不应判 lint 陈旧")
        self.assertEqual(self._stale(10, "sim"), [], "改规格书不应判 sim 陈旧")

    def test_rtl_change_stales_lint(self):
        self._record("lint")
        _append(self.rtl, "// touch\n")
        self.assertTrue(self._stale(7, "lint"), "改 RTL 必须判 lint 陈旧")

    def test_include_chain_change_stales_lint(self):
        self._record("lint")
        _write(self.tbl, "// tbl v2\n")
        self.assertTrue(self._stale(7, "lint"), "改 include 链上的表文件必须判 lint 陈旧")

    def test_tb_change_hits_sim_not_lint(self):
        self._record("lint")
        self._record("sim")
        _append(self.tb, "// tb comment\n")
        self.assertEqual(self._stale(7, "lint"), [], "改 TB 不应影响 lint 记录")
        self.assertTrue(self._stale(10, "sim"), "改 TB 必须判 sim 陈旧")

    def test_sdc_change_hits_synth_and_sta_not_lint(self):
        self._record("lint")
        self._record("synth")
        self._record("sta")
        _write(self.sdc, "create_clock -period 2.0 [get_ports clk]\n")
        self.assertEqual(self._stale(7, "lint"), [], "改 SDC 不应影响 lint 记录")
        self.assertTrue(self._stale(11, "synth"), "改 SDC 必须判 synth 陈旧")
        self.assertTrue(self._stale(11, "sta"), "改 SDC 必须判 sta 陈旧")

    def test_sta_only_watches_netlist_and_sdc(self):
        self._record("sta")
        _append(self.rtl, "// rtl touch\n")
        _append(self.tb, "// tb touch\n")
        self.assertEqual(self._stale(11, "sta"), [], "时序只看网表与 SDC，RTL/TB 改动不判陈旧")
        _append(self.netlist, "// netlist touch\n")
        self.assertTrue(self._stale(11, "sta"), "改网表必须判 sta 陈旧")

    def test_legacy_digest_without_capability_unchanged(self):
        """不带 capability 的旧口径（停点指纹基线）仍含 spec_doc 与附加路径。"""
        before = inputs_digest(self.root, self.name)
        _write(self.spec, "# fresh1 规格\n改动。\n")
        self.assertNotEqual(inputs_digest(self.root, self.name), before)


class RunTimeDigestTests(RepoTest):
    """输入摘要在 rsync 前后各算一次，运行期间被改判 error。"""

    def setUp(self):
        super().setUp()
        self.name = "midrun"
        init_sys(self.root, self.name)
        self.base = sys_dir(self.root, self.name)
        self.rtl = os.path.join(self.base, "rtl", "alu.sv")
        _write(self.rtl, "module alu; endmodule\n")

    def _lint_run(self, mutate_mid_run):
        def fake_run(argv, **kwargs):
            if isinstance(argv, list):
                # ssh 分支 = 远端执行窗口：此时有人改 RTL。
                if mutate_mid_run:
                    _append(self.rtl, "// mid-run edit\n")
                return FakeProc("NLINT " + "RESULT: PASS\n")
            return FakeProc("")
        real = subprocess.run
        subprocess.run = fake_run
        try:
            result = run_other("lint", {"sys": self.name})
        finally:
            subprocess.run = real
        return result

    def test_input_changed_during_run_is_error(self):
        result = self._lint_run(mutate_mid_run=True)
        self.assertEqual(result["status"], "pass", "工具本身判 pass，错在运行期间输入被改")
        record_run(self.root, self.name, result)
        run = load_state(self.root, self.name)["runs"][-1]
        self.assertEqual(run["status"], "error")
        self.assertIn("输入在运行期间变更", run["summary"])
        findings = run_gates(self.root, self.name, 7, load_state(self.root, self.name))
        self.assertTrue(any(item.get("where") == "lint" and "需要最近一次 lint 为 pass" in item.get("detail", "")
                            for item in findings), findings)

    def test_input_unchanged_records_pass(self):
        result = self._lint_run(mutate_mid_run=False)
        record_run(self.root, self.name, result)
        run = load_state(self.root, self.name)["runs"][-1]
        self.assertEqual(run["status"], "pass")
        self.assertNotIn("输入在运行期间变更", run["summary"])
        findings = run_gates(self.root, self.name, 7, load_state(self.root, self.name))
        self.assertFalse(any("输入已变更" in item["detail"] for item in findings), findings)

    def test_dry_run_still_skips_state(self):
        result = run_other("lint", {"sys": self.name, "dry_run": True})
        self.assertEqual(result["status"], "dry_run")
        self.assertEqual(load_state(self.root, self.name)["runs"], [])


class WorkdirLockTests(RepoTest):
    """同一 (sys, scenario, module) 的并行 profile_run 串行完成。"""

    def test_parallel_sims_serialize_on_workdir_lock(self):
        name = "locksys"
        init_sys(self.root, name)
        spans = []
        results = {}

        def fake_run(argv, **kwargs):
            if isinstance(argv, list):
                start = time.monotonic()
                time.sleep(0.3)
                spans.append((start, time.monotonic()))
                return FakeProc("       RESULT       : PASS\n")
            return FakeProc("")

        def worker(tag):
            results[tag] = run_sim({"scenario": "sys", "sys": name, "seed": "1"})

        real = subprocess.run
        subprocess.run = fake_run
        try:
            threads = [threading.Thread(target=worker, args=(tag,)) for tag in ("a", "b")]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        finally:
            subprocess.run = real

        self.assertEqual(sorted(results), ["a", "b"])
        for tag, result in results.items():
            self.assertEqual(result["status"], "pass", (tag, result["summary"]))
            self.assertIn("lock", result, "锁信息要写进结果")
        self.assertEqual(len(spans), 2)
        spans.sort()
        # 两次远端执行在时间上不重叠：后一次等前一次释放工作目录锁后才开跑。
        self.assertGreaterEqual(spans[1][0], spans[0][1] - 0.02,
                                "同一工作目录上的两次运行必须串行")
        self.assertGreater(max(result["lock"]["waited_s"] for result in results.values()), 0.0)
        locks = [fn for fn in os.listdir(sys_dir(self.root, name)) if fn.startswith(".run.lock.")]
        self.assertEqual(locks, [".run.lock.sys."], "锁文件按 <scenario>.<module> 命名")
        with open(os.path.join(sys_dir(self.root, name), "events.jsonl"), encoding="utf-8") as fh:
            self.assertTrue(any("运行锁" in line for line in fh), "锁等待要写进事件日志")


class DecisionNoteGateTests(RepoTest):
    """修改队列退场后注记直接写〔D…〕；闸门 W3 只认裁决表，且从不改写产物。"""

    def _scan(self, name):
        from framework.gates.specconn import scan_notes
        return scan_notes(sys_dir(self.root, name), load_state(self.root, name))

    def test_known_d_note_passes_and_gate_never_writes(self):
        name = "b7known"
        init_sys(self.root, name)
        did = decide(self.root, name, "数据位宽取 9", "数值", 1,
                     options="数据位宽取 9|数据位宽取 8", pick="数据位宽取 9")
        self.assertTrue(did.startswith("D0-"), did)
        doc = os.path.join(sys_dir(self.root, name), "flow_doc", "note.md")
        _write(doc, "见〔%s〕。\n" % did)
        before = _md_snapshot(self.root, name)
        self.assertEqual(self._scan(name), [], "注记指向已入库裁决，W3 不该报")
        self.assertEqual(_md_snapshot(self.root, name), before,
                         "闸门只报告，一个字节都不写")

    def test_unknown_d_note_is_flagged(self):
        name = "b7unknown"
        init_sys(self.root, name)
        _write(os.path.join(sys_dir(self.root, name), "flow_doc", "note.md"),
               "见〔D9-999〕。\n")
        before = _md_snapshot(self.root, name)
        findings = self._scan(name)
        self.assertEqual([item["rule"] for item in findings], ["W3"])
        self.assertEqual(findings[0]["where"], os.path.join("flow_doc", "note.md"))
        self.assertIn("D9-999", findings[0]["detail"])
        self.assertEqual(_md_snapshot(self.root, name), before,
                         "闸门只报告，一个字节都不写")

    def test_clean_tree_reports_empty_and_t_notes_are_not_decision_notes(self):
        name = "b7clean"
        init_sys(self.root, name)
        _write(os.path.join(sys_dir(self.root, name), "info_input", "a.md"), "正文\n")
        # T 序号已删除：〔T001〕不再被当作裁决注记认（只认 〔D…〕）。
        _write(os.path.join(sys_dir(self.root, name), "info_input", "t.md"), "旧注记〔T001〕。\n")
        before = _md_snapshot(self.root, name)
        self.assertEqual(self._scan(name), [])
        self.assertEqual(_md_snapshot(self.root, name), before)


if __name__ == "__main__":
    unittest.main()
