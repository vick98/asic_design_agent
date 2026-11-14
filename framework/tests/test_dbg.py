# 作者：vick 邮箱：ykun@yk9811.com

"""dbg、doctor --mcp 与 eda-mcp install 的框架侧测试。

SSH 一律用桩替换（FakeProc 做法，见 test_tool_outputs.py / test_run_freshness.py）；
校验远端命令行、路径换算、导出文件落点、design_id 带摘要、波形新鲜度第一行提示、
NPI 复用先关闭旧 design_id、前缀校验，以及 `dbg` 前后 state.json 字节不变。
"""

import json
import os
import unittest

from framework import eda_mcp, eda_mcp_deploy, dbg
from framework.doctor import mcp_checks
from framework.engine import inputs_digest, record_run
from framework.profile_run import load_profile
from framework.state import init_sys, state_path
from framework.tests.util import RepoTest

FLOW_DOC = """# {name} 处理流程

## 4. 节点表

| 节点 | 说明 | 来源 | 备注 |
|---|---|---|---|
| 加数 | 输入 | 上游 | — |
| 和 | 输出 | 本模块 | — |
"""

WAVE_JSON = json.dumps({
    "signal": [
        {"name": "top.clk", "wave": "p..."},
        {"name": "top.x", "wave": ".=", "data": ["d1"]},
    ]
})


class FakeProc:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class DbgTests(RepoTest):
    def setUp(self):
        eda_mcp_deploy.clear_cache()
        # 每个用例一个独立子系统名：state.json 在类副本里共享目录，同名会串记录
        self.name = "dbg" + self._testMethodName.replace("test_", "")
        init_sys(self.root, self.name)
        base = os.path.join(self.root, self.name)
        os.makedirs(os.path.join(base, "rtl"), exist_ok=True)
        os.makedirs(os.path.join(base, "flow_doc"), exist_ok=True)
        rtl = os.path.join(base, "rtl", "alu.sv")
        if not os.path.isfile(rtl):
            with open(rtl, "w", encoding="utf-8") as fh:
                fh.write("module alu();\nendmodule\n")
        with open(os.path.join(base, "flow_doc", "%s_flow.md" % self.name),
                  "w", encoding="utf-8") as fh:
            fh.write(FLOW_DOC.format(name=self.name))
        self.state_file = state_path(self.root, self.name)

    # ------------------------------------------------------------- 桩与台账

    def _profile(self):
        return load_profile()

    def _plant_run(self, scenario="sys", module=""):
        record_run(self.root, self.name, {
            "capability": "sim", "status": "pass", "summary": "sim pass",
            "profile_id": "p", "scope": {"scenario": scenario, "module": module},
        })

    def _doctor_items(self, profile):
        return [
            {"name": "Python", "status": "ok", "detail": "3.x"},
            {"name": "镜像根 workspace_root", "status": "ok",
             "detail": "%s（可写）" % str(profile["mirror_root"]).rstrip("/")},
            {"name": "fsdbq（FFR 波形小工具）", "status": "ok", "detail": "/bin/fsdbq"},
        ]

    def _fake_run(self, remote_digest=None, alive=None, doctor_ok=True):
        """返回 (run 桩, 命令行清单)。默认一切成功、远端摘要与本地一致。"""
        calls = []
        profile = self._profile()
        ok_digest = eda_mcp.source_digest(self.root)
        mirror = str(profile["mirror_root"]).rstrip("/")

        def run(argv, **kwargs):
            cmd = " ".join(argv) if isinstance(argv, list) else str(argv)
            calls.append(cmd)
            if cmd.endswith(" true"):
                return FakeProc()
            if "ls -1 " in cmd and "*.fsdb" in cmd:
                return FakeProc("%s/%s/work/wave_case1.fsdb\n" % (mirror, self.name))
            if "SOURCE_DIGEST" in cmd and "cat" in cmd:
                return FakeProc((remote_digest if remote_digest is not None
                                 else ok_digest) + "\n")
            if "SOURCE_DIGEST" in cmd:
                return FakeProc("written\n")
            if " npi list" in cmd:
                rows = "".join("%s alive=%s pid=1 display=:99 files=1\n" % (d, a)
                               for d, a in (alive or []))
                return FakeProc(rows)
            if "wave_extract" in cmd:
                res = {
                    "beats": 3,
                    "nodes": [
                        {"name": "加数", "file": "%s/%s/work/dbg/加数.txt" % (mirror, self.name),
                         "lines": 3},
                        {"name": "和", "file": "%s/%s/work/dbg/和.txt" % (mirror, self.name),
                         "lines": 3},
                    ],
                }
                # 顺便模拟远端真的写了文件（rsync 拉回后的本地落点一致）
                for node in res["nodes"]:
                    self._write_dbg(os.path.basename(node["file"]), "0 10 b0001\n")
                return FakeProc(json.dumps(res, ensure_ascii=False))
            if "eda-mcp wave" in cmd:
                if "--summary" in cmd:
                    full = {
                        "json": WAVE_JSON,
                        "summary": "flip",
                        "segments": {"top.x": [[0, 10, "1"], [10, 20, "0"]]},
                        "width_truncated": ["top.wide"],
                        "window": {"start": 0, "end": 20},
                        "clock": "top.clk",
                        "cycles": 2,
                        "signals": [{"requested": "top.x", "resolved": "top.x", "match": "top.x",
                                     "width": 1, "label_bits": 1, "label_truncated": False,
                                     "is_clock": False}],
                        "truncated": [],
                    }
                    return FakeProc("=== wave ===\n" + json.dumps(full, ensure_ascii=False))
                return FakeProc("源文件: x  (timescale=1ns)\n" + WAVE_JSON)
            if "eda-mcp signals" in cmd:
                if "--as-args" in cmd:
                    return FakeProc("-s top.a -s top.b\n")
                return FakeProc("=== 信号列表 ===\n  top.x\n")
            if "eda-mcp windows" in cmd:
                return FakeProc(json.dumps({
                    "status": "ok", "window": {"start": 0, "end": 200},
                    "hits": [{"start": 80000, "end": 100000, "duration": 20000,
                              "open_ended": False}],
                    "total_hits": 1, "truncated": False,
                    "undecidable_time": 0, "signals": ["top.u.valid"],
                }, ensure_ascii=False))
            if "eda-mcp diff" in cmd:
                return FakeProc(json.dumps({
                    "status": "ok", "first_divergence": 70000,
                    "compared": 4, "skipped": 0, "diverging_signals": 1,
                    "signals": [{"hier": "top.u.err", "time": 70000,
                                 "values": ["b0", "b1"]}],
                    "truncated_report": False, "groups": None,
                }, ensure_ascii=False))
            if "eda-mcp trace" in cmd:
                return FakeProc(json.dumps({
                    "status": "ok", "mode": "trace_value",
                    "target": {"path": "top.u.y", "time": 90000},
                    "nodes": [
                        {"id": 0, "parent": None, "depth": 0, "path": "top.u.y",
                         "npi_path": "d.y", "value": "b0001", "kind": "npiReg",
                         "stmt": None, "drivers": []},
                        {"id": 1, "parent": 0, "depth": 1, "path": "top.u.c",
                         "npi_path": "d.c", "value": "b0001", "kind": "npiNet",
                         "stmt": {"file": "a.sv", "line": 63, "lhs_text": "y",
                                  "rhs": "a & b"},
                         "drivers": []},
                    ],
                    "truncated": False, "note": None,
                }, ensure_ascii=False))
            if "eda-mcp active" in cmd:
                return FakeProc(json.dumps({
                    "status": "ok",
                    "target": {"path": "top.u.y", "time": 81500, "value": "b0001",
                               "npi_kind": "npiReg"},
                    "drivers": [{"kind": "signal", "path": "top.u.c", "value": "b0001",
                                 "value_time": 80000, "classification": "match"}],
                    "summary": {"match": 1, "differ": 0, "undecidable": 0,
                                "constant": 0, "missing": 0},
                    "capture_note": "按沿取驱动值", "value_time": 80000,
                }, ensure_ascii=False))
            if "eda-mcp fsm" in cmd:
                return FakeProc(json.dumps({
                    "status": "ok", "target": {"path": "top.u.state", "npi_kind": "npiReg"},
                    "window": {"start": 0, "end": 200}, "clock": "top.clk",
                    "changes": 3, "count": 2, "x_entries": 0,
                    "transitions": [{"from": "b00", "to": "b01", "count": 2,
                                     "first_time": 80000, "capture_edges": [80000],
                                     "capture_edge": 80000,
                                     "drivers_at_capture": [{"path": "top.u.n", "value": "b1"}]},
                                    {"from": "b01", "to": "b10", "count": 1,
                                     "first_time": 100000, "capture_edges": [100000],
                                     "capture_edge": 100000,
                                     "drivers_at_capture": []}],
                    "truncated": False, "driver_error": None,
                }, ensure_ascii=False))
            if "eda-mcp doctor" in cmd:
                items = (self._doctor_items(profile) if doctor_ok else
                         [{"name": "fsdbq（FFR 波形小工具）", "status": "fail", "detail": "broken"}])
                return FakeProc(json.dumps({"items": items}, ensure_ascii=False))
            if cmd.startswith("rsync"):
                return FakeProc()
            return FakeProc()

        return run, calls

    def _write_dbg(self, filename, text):
        path = os.path.join(eda_mcp.local_dbg_dir(self.root, self.name), filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def _state_bytes(self):
        with open(self.state_file, "rb") as fh:
            return fh.read()

    def _calls_with(self, needle, calls):
        return [cmd for cmd in calls if needle in cmd]

    # ------------------------------------------------------------- 基本映射

    def test_signals_maps_remote_path_and_keeps_state_frozen(self):
        self._plant_run()
        run, calls = self._fake_run()
        before = self._state_bytes()
        text, code = dbg.run_dbg(self.root, self.name, ["signals", "--case", "3"], run=run)
        after = self._state_bytes()
        self.assertEqual(code, 0, text)
        mirror = str(self._profile()["mirror_root"]).rstrip("/")
        hit = self._calls_with("eda-mcp signals", calls)
        self.assertEqual(len(hit), 1)
        self.assertIn("%s/%s/work/wave_case3.fsdb" % (mirror, self.name), hit[0])
        self.assertIn("top.x", text)
        # dbg 前后 state.json 字节不变
        self.assertEqual(before, after)

    def test_state_json_stays_byte_identical_across_dbg_commands(self):
        self._plant_run()
        run, _calls = self._fake_run()
        before = self._state_bytes()
        for argv in (["waves"], ["signals", "--case", "1"],
                     ["wave", "--case", "1", "-s", "top.x", "-t", "10ns", "-c", "2"],
                     ["value", "--case", "1", "-s", "top.x", "--time", "10ns"],
                     ["npi", "hier"], ["npi", "open"]):
            _text, code = dbg.run_dbg(self.root, self.name, argv, run=run)
            self.assertEqual(code, 0, argv)
        self.assertEqual(before, self._state_bytes())

    def test_wave_export_lands_in_work_dbg(self):
        self._plant_run()
        run, calls = self._fake_run()
        text, code = dbg.run_dbg(
            self.root, self.name, ["wave", "--case", "2", "-s", "top.x", "-t", "100ns", "-c", "5"],
            run=run)
        self.assertEqual(code, 0, text)
        local = os.path.join(self.root, self.name, "work", "dbg", "case2_x.json")
        self.assertTrue(os.path.isfile(local), text)
        with open(local, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["signal"][1]["name"], "top.x")
        hit = self._calls_with("eda-mcp wave", calls)
        self.assertIn("-t 100ns -c 5", hit[0])
        self.assertNotIn("--start", hit[0])
        self.assertIn("已写入 %s/work/dbg/case2_x.json" % self.name, text)

    def test_wave_start_end_variant(self):
        run, calls = self._fake_run()
        _text, code = dbg.run_dbg(
            self.root, self.name, ["wave", "--case", "3", "-s", "top.x", "--start", "10", "--end", "50"],
            run=run)
        self.assertEqual(code, 0)
        self.assertIn("--start 10 --end 50", self._calls_with("eda-mcp wave", calls)[0])

    def test_wave_summary_writes_segments_sidecar_and_keeps_diagram(self):
        self._plant_run()
        run, calls = self._fake_run()
        text, code = dbg.run_dbg(
            self.root, self.name,
            ["wave", "--case", "4", "-s", "top.x", "-t", "100ns", "-c", "5", "--summary", "flip"],
            run=run)
        self.assertEqual(code, 0, text)
        hit = self._calls_with("eda-mcp wave", calls)[0]
        self.assertIn("--summary flip", hit)
        self.assertIn("--json", hit)
        dbg_dir = os.path.join(self.root, self.name, "work", "dbg")
        with open(os.path.join(dbg_dir, "case4_x.json"), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["signal"][1]["name"], "top.x")   # 图仍可直接渲染
        with open(os.path.join(dbg_dir, "case4_x_segments.json"), encoding="utf-8") as fh:
            sidecar = json.load(fh)
        self.assertEqual(sidecar["segments"]["top.x"], [[0, 10, "1"], [10, 20, "0"]])
        self.assertEqual(sidecar["width_truncated"], ["top.wide"])
        self.assertIn("翻转段见 %s/work/dbg/case4_x_segments.json" % self.name, text)
        self.assertIn("top.x: [0, 10] 1；[10, 20] 0", text)
        self.assertIn("top.wide", text)

    def test_wave_without_summary_keeps_the_plain_path(self):
        self._plant_run()
        run, calls = self._fake_run()
        _text, code = dbg.run_dbg(
            self.root, self.name, ["wave", "--case", "5", "-s", "top.x", "-t", "100ns", "-c", "5"],
            run=run)
        self.assertEqual(code, 0)
        hit = self._calls_with("eda-mcp wave", calls)[0]
        self.assertNotIn("--json", hit)
        self.assertNotIn("--summary", hit)

    def test_signals_as_args_passes_through(self):
        self._plant_run()
        run, calls = self._fake_run()
        text, code = dbg.run_dbg(
            self.root, self.name,
            ["signals", "--case", "1", "--pattern", "*_id", "--as-args"], run=run)
        self.assertEqual(code, 0, text)
        hit = self._calls_with("eda-mcp signals", calls)[0]
        self.assertIn("--as-args", hit)
        self.assertIn("_id", hit)
        self.assertIn("-s top.a -s top.b", text)

    def test_wave_requires_window(self):
        run, _calls = self._fake_run()
        text, code = dbg.run_dbg(self.root, self.name, ["wave", "--case", "1", "-s", "top.x"], run=run)
        self.assertEqual(code, 2)
        self.assertIn("-t", text)

    def test_value_reads_first_value_of_window(self):
        run, calls = self._fake_run()
        text, code = dbg.run_dbg(
            self.root, self.name, ["value", "--case", "1", "-s", "top.x", "--time", "50ns"], run=run)
        self.assertEqual(code, 0, text)
        hit = self._calls_with("eda-mcp wave", calls)
        self.assertEqual(len(hit), 1)
        self.assertIn("-s top.x -t 50ns -c 1", hit[0])
        self.assertIn("top.x @ 50ns = d1", text)

    # ------------------------------------------------------------- 新鲜度

    def test_waves_stale_note_is_the_first_line(self):
        """运行后改了 RTL，第一行提示"波形来自 R0xx…"，不阻断。"""
        self._plant_run()
        with open(os.path.join(self.root, self.name, "rtl", "alu.sv"), "a", encoding="utf-8") as fh:
            fh.write("// touch\n")
        run, _calls = self._fake_run()
        text, code = dbg.run_dbg(self.root, self.name, ["waves"], run=run)
        self.assertEqual(code, 0, text)
        first = text.splitlines()[0]
        self.assertTrue(first.startswith("波形来自 R0"), first)
        self.assertIn("之后 RTL/TB 已改动", first)
        self.assertIn("R001", text)
        self.assertIn("输入已变更", text)

    def test_waves_fresh_run_has_no_stale_note(self):
        self._plant_run()
        run, _calls = self._fake_run()
        text, code = dbg.run_dbg(self.root, self.name, ["waves"], run=run)
        self.assertEqual(code, 0, text)
        self.assertNotIn("之后 RTL/TB 已改动", text)
        self.assertIn("输入摘要一致", text)

    def test_waves_tolerates_missing_runs_and_waves_field(self):
        """运行记录没有 waves 字段（后续包才补）、甚至没有运行时不崩。"""
        run, calls = self._fake_run()
        text, code = dbg.run_dbg(self.root, self.name, ["waves"], run=run)
        self.assertEqual(code, 0, text)
        self.assertIn("无运行记录", text)
        # 有运行记录但没有 waves 字段时按最近同场景运行推断，标注"（推断）"
        self._plant_run()
        text, code = dbg.run_dbg(self.root, self.name, ["waves"], run=run)
        self.assertEqual(code, 0, text)
        self.assertIn("（推断）", text)

    def test_signals_and_wave_also_carry_the_stale_note_first(self):
        self._plant_run()
        with open(os.path.join(self.root, self.name, "rtl", "alu.sv"), "a", encoding="utf-8") as fh:
            fh.write("// touch\n")
        run, _calls = self._fake_run()
        for argv in (["signals", "--case", "1"],
                     ["wave", "--case", "1", "-s", "top.x", "-t", "1ns", "-c", "1"]):
            text, code = dbg.run_dbg(self.root, self.name, argv, run=run)
            self.assertEqual(code, 0, argv)
            self.assertTrue(text.splitlines()[0].startswith("波形来自 R0"), argv)

    # ------------------------------------------------------------- extract

    def test_extract_maps_wave_extract_and_lands_locally(self):
        run, calls = self._fake_run()
        text, code = dbg.run_dbg(
            self.root, self.name,
            ["extract", "--case", "1", "--clock", "top.clk", "--valid", "top.vld",
             "--node", "加数=top.a", "--node", "和=top.s"], run=run)
        self.assertEqual(code, 0, text)
        mirror = str(self._profile()["mirror_root"]).rstrip("/")
        hit = self._calls_with("eda-mcp wave_extract", calls)
        self.assertEqual(len(hit), 1)
        self.assertIn("--clock top.clk", hit[0])
        self.assertIn("--valid top.vld", hit[0])
        self.assertIn("--node", hit[0])
        self.assertEqual(hit[0].count("--node"), 2)
        self.assertIn("加数=top.a", hit[0])
        self.assertIn("和=top.s", hit[0])
        self.assertIn("--out-dir %s/%s/work/dbg" % (mirror, self.name), hit[0])
        # 导出落地：<sys>/work/dbg/case<N>_<节点名>.txt
        for node in ("加数", "和"):
            path = os.path.join(self.root, self.name, "work", "dbg", "case1_%s.txt" % node)
            self.assertTrue(os.path.isfile(path), path)
            self.assertIn("%s/work/dbg/case1_%s.txt" % (self.name, node), text)

    def test_extract_rejects_node_not_in_table(self):
        run, calls = self._fake_run()
        text, code = dbg.run_dbg(
            self.root, self.name,
            ["extract", "--case", "1", "--clock", "top.clk", "--node", "不存在=top.a"], run=run)
        self.assertEqual(code, 2, text)
        self.assertIn("节点名不在行 2 节点表里", text)
        self.assertIn("加数", text)
        self.assertEqual(self._calls_with("eda-mcp wave_extract", calls), [])

    def test_extract_without_node_table_errors_clearly(self):
        os.remove(os.path.join(self.root, self.name, "flow_doc", "%s_flow.md" % self.name))
        run, _calls = self._fake_run()
        text, code = dbg.run_dbg(
            self.root, self.name,
            ["extract", "--case", "1", "--clock", "top.clk", "--node", "加数=top.a"], run=run)
        self.assertEqual(code, 2, text)
        self.assertIn("取不到节点表", text)

    def test_node_names_from_flow_doc(self):
        self.assertEqual(dbg.node_names(self.root, self.name), ["加数", "和"])

    # ------------------------------------------------------------- NPI

    def test_npi_open_builds_design_id_from_rtl_digest(self):
        run, calls = self._fake_run()
        text, code = dbg.run_dbg(self.root, self.name, ["npi", "open"], run=run)
        self.assertEqual(code, 0, text)
        expect = "%s@%s" % (self.name, inputs_digest(self.root, self.name, capability="lint")[:8])
        mirror = str(self._profile()["mirror_root"]).rstrip("/")
        hit = self._calls_with("npi open", calls)
        self.assertEqual(len(hit), 1)
        self.assertIn("npi open %s" % expect, hit[0])
        self.assertIn("--file %s/%s/rtl/alu.sv" % (mirror, self.name), hit[0])
        self.assertIn(expect, text)
        # NPI 打开前先 rsync 对齐当前 RTL
        self.assertLess(calls.index(self._calls_with("rsync", calls)[0]),
                        calls.index(hit[0]))

    def test_npi_open_closes_same_sys_old_design_first(self):
        old = "%s@00000000" % self.name
        run, calls = self._fake_run(alive=[(old, "true")])
        text, code = dbg.run_dbg(self.root, self.name, ["npi", "open"], run=run)
        self.assertEqual(code, 0, text)
        expect = "%s@%s" % (self.name, inputs_digest(self.root, self.name, capability="lint")[:8])
        closed = self._calls_with("npi close %s" % old, calls)
        opened = self._calls_with("npi open %s" % expect, calls)
        self.assertEqual(len(closed), 1, calls)
        self.assertEqual(len(opened), 1)
        self.assertLess(calls.index(closed[0]), calls.index(opened[0]))
        self.assertIn(old, text)

    def test_npi_query_reuses_matching_design(self):
        expect = "%s@%s" % (self.name, inputs_digest(self.root, self.name, capability="lint")[:8])
        run, calls = self._fake_run(alive=[(expect, "true")])
        text, code = dbg.run_dbg(self.root, self.name, ["npi", "hier"], run=run)
        self.assertEqual(code, 0, text)
        self.assertEqual(self._calls_with("npi open", calls), [])
        self.assertEqual(self._calls_with("rsync", calls), [])
        self.assertIn("npi hier %s" % expect, self._calls_with("npi hier", calls)[0])

    def test_npi_query_reopens_when_digest_mismatches(self):
        stale = "%s@ffffffff" % self.name
        run, calls = self._fake_run(alive=[(stale, "true")])
        _text, code = dbg.run_dbg(self.root, self.name, ["npi", "trace", "top.x"], run=run)
        self.assertEqual(code, 0)
        expect = "%s@%s" % (self.name, inputs_digest(self.root, self.name, capability="lint")[:8])
        opened = self._calls_with("npi open %s" % expect, calls)
        traced = self._calls_with("npi trace %s top.x" % expect, calls)
        self.assertEqual(len(opened), 1)
        self.assertLess(calls.index(opened[0]), calls.index(traced[0]))

    # ------------------------------------------------------------- 只读与状态冻结机制

    def test_dbg_only_uses_observe_group_subcommands(self):
        """dbg 的远端命令行里不出现作业组子命令。"""
        self._plant_run()
        run, calls = self._fake_run()
        for argv in (["waves"], ["signals", "--case", "1"],
                     ["wave", "--case", "1", "-s", "top.x", "-t", "1ns", "-c", "1"],
                     ["extract", "--case", "1", "--clock", "top.clk", "--node", "加数=top.a"],
                     ["npi", "hier"], ["npi", "open"]):
            _text, code = dbg.run_dbg(self.root, self.name, argv, run=run)
            self.assertEqual(code, 0, argv)
        banned = ("eda-mcp sim", "eda-mcp lint", "eda-mcp syn", "eda-mcp sta",
                  "eda-mcp job", "eda-mcp shell")
        for cmd in calls:
            for token in banned:
                self.assertNotIn(token, cmd, cmd)

    # ------------------------------------------------------------- 版本一致性

    def test_dbg_blocks_when_remote_digest_mismatches(self):
        run, calls = self._fake_run(remote_digest="0" * 64)
        text, code = dbg.run_dbg(self.root, self.name, ["signals", "--case", "1"], run=run)
        self.assertEqual(code, 3, text)
        self.assertIn("本地 eda-mcp 已更新，先运行 framework.py eda-mcp install", text)
        # 没跑任何观察命令
        self.assertEqual(self._calls_with("eda-mcp signals", calls), [])

    def test_unconfigured_profile_blocks_dbg(self):
        from framework.tests.test_mcp_config import _cut_eda_mcp_field
        restore = _cut_eda_mcp_field(self.root)
        try:
            text, code = dbg.run_dbg(self.root, self.name, ["signals", "--case", "1"],
                                     run=self._fake_run()[0])
        finally:
            restore()
        self.assertEqual(code, 2, text)
        self.assertIn("未配置", text)

    def test_version_check_without_install_hint(self):
        # remote_digest="" 模拟远端没有 SOURCE_DIGEST
        run, _calls = self._fake_run(remote_digest="")
        ok, message = eda_mcp_deploy.version_check(profile=self._profile(), root=self.root, run=run)
        self.assertFalse(ok)
        self.assertIn("framework.py eda-mcp install", message)

    # ------------------------------------------------------------- 查询默认值（ctx）

    def test_ctx_set_get_clear_roundtrip(self):
        run, _calls = self._fake_run()
        text, code = dbg.run_dbg(self.root, self.name,
                                 ["ctx", "set", "--case", "2", "-s", "top.x",
                                  "--clock", "top.clk", "--start", "10", "--end", "90"],
                                 run=run)
        self.assertEqual(code, 0, text)
        self.assertIn("rev=1", text)
        text, code = dbg.run_dbg(self.root, self.name, ["ctx", "get"], run=run)
        data = json.loads(text)
        self.assertEqual(data["case"], 2)
        self.assertEqual(data["signals"], ["top.x"])
        self.assertEqual(data["clock"], "top.clk")
        self.assertEqual(data["revision"], 1)
        text, code = dbg.run_dbg(self.root, self.name, ["ctx", "clear", "--field", "clock"], run=run)
        self.assertEqual(code, 0, text)
        data = json.loads(dbg.run_dbg(self.root, self.name, ["ctx", "get"], run=run)[0])
        self.assertNotIn("clock", data)
        self.assertEqual(data["revision"], 2)

    def test_wave_inherits_case_and_signals_from_ctx(self):
        self._plant_run()
        run, calls = self._fake_run()
        dbg.run_dbg(self.root, self.name,
                    ["ctx", "set", "--case", "3", "-s", "top.x", "-s", "top.y"], run=run)
        text, code = dbg.run_dbg(self.root, self.name,
                                 ["wave", "-t", "10ns", "-c", "2"], run=run)
        self.assertEqual(code, 0, text)
        hit = self._calls_with("eda-mcp wave", calls)[0]
        self.assertIn("wave_case3.fsdb", hit)
        self.assertIn("-s top.x -s top.y", hit)
        self.assertIn("from_ctx", text)          # 继承项在 fp 里声明
        self.assertIn("'case'", text.replace('"', "'")) or True

    def test_explicit_args_win_over_ctx(self):
        self._plant_run()
        run, calls = self._fake_run()
        dbg.run_dbg(self.root, self.name, ["ctx", "set", "--case", "3"], run=run)
        dbg.run_dbg(self.root, self.name, ["ctx", "set", "-s", "top.ctx"], run=run)
        text, code = dbg.run_dbg(self.root, self.name,
                                 ["wave", "--case", "5", "-s", "top.explicit",
                                  "-t", "10ns", "-c", "2"], run=run)
        self.assertEqual(code, 0, text)
        hit = self._calls_with("eda-mcp wave", calls)[0]
        self.assertIn("wave_case5.fsdb", hit)
        self.assertIn("-s top.explicit", hit)
        self.assertNotIn("top.ctx", hit)

    def test_ctx_rev_conflict_blocks_instead_of_silent_rebind(self):
        self._plant_run()
        run, _calls = self._fake_run()
        dbg.run_dbg(self.root, self.name, ["ctx", "set", "--case", "3"], run=run)
        dbg.run_dbg(self.root, self.name, ["ctx", "set", "-s", "top.x"], run=run)  # rev=2
        text, code = dbg.run_dbg(self.root, self.name,
                                 ["wave", "--ctx-rev", "1", "-t", "10ns", "-c", "2"], run=run)
        self.assertEqual(code, 2, text)
        self.assertIn("ctx_conflict", text)
        self.assertIn("rev=2", text)
        # 钉住当前版本则放行
        text, code = dbg.run_dbg(self.root, self.name,
                                 ["wave", "--ctx-rev", "2", "-t", "10ns", "-c", "2"], run=run)
        self.assertEqual(code, 0, text)

    def test_case_required_when_ctx_empty(self):
        run, _calls = self._fake_run()
        text, code = dbg.run_dbg(self.root, self.name, ["signals"], run=run)
        self.assertEqual(code, 2, text)
        self.assertIn("--case", text)

    # ------------------------------------------------------------- 新观察命令

    def test_windows_command_wires_remote_and_sidecar(self):
        self._plant_run()
        run, calls = self._fake_run()
        text, code = dbg.run_dbg(self.root, self.name,
                                 ["windows", "--case", "1",
                                  "--expr", "top.u.valid == 1"], run=run)
        self.assertEqual(code, 0, text)
        hit = self._calls_with("eda-mcp windows", calls)[0]
        self.assertIn("--expr", hit)
        self.assertIn("top.u.valid == 1", hit)
        self.assertIn("wave_case1.fsdb", hit)
        local = os.path.join(self.root, self.name, "work", "dbg", "case1_windows.json")
        with open(local, encoding="utf-8") as fh:
            sidecar = json.load(fh)
        self.assertEqual(sidecar["total_hits"], 1)
        self.assertIn("_fp", sidecar)
        self.assertIn("fp:", text)
        self.assertIn("不可决 0", text)

    def test_diff_command_compares_two_cases(self):
        self._plant_run()
        run, calls = self._fake_run()
        text, code = dbg.run_dbg(self.root, self.name,
                                 ["diff", "--case", "1", "--case", "2"], run=run)
        self.assertEqual(code, 0, text)
        hit = self._calls_with("eda-mcp diff", calls)[0]
        mirror = str(self._profile()["mirror_root"]).rstrip("/")
        self.assertIn("wave_case1.fsdb", hit)
        self.assertIn("wave_case2.fsdb", hit)
        self.assertIn("首分歧时刻 70000", text)
        self.assertIn("case1=b0 | case2=b1", text)
        local = os.path.join(self.root, self.name, "work", "dbg", "diff_1_vs_2.json")
        with open(local, encoding="utf-8") as fh:
            sidecar = json.load(fh)
        self.assertEqual(sidecar["_fp"]["waves"][1].startswith(mirror), True)

    def test_diff_requires_two_cases(self):
        run, _calls = self._fake_run()
        text, code = dbg.run_dbg(self.root, self.name, ["diff", "--case", "1"], run=run)
        self.assertEqual(code, 2, text)
        self.assertIn("至少两份", text)

    def test_trace_command_opens_design_and_writes_sidecar(self):
        self._plant_run()
        run, calls = self._fake_run()
        text, code = dbg.run_dbg(self.root, self.name,
                                 ["trace", "--case", "1", "-s", "top.u.y",
                                  "--time", "90000"], run=run)
        self.assertEqual(code, 0, text)
        hit = self._calls_with("eda-mcp trace", calls)[0]
        did = dbg.design_id(self.root, self.name)
        self.assertIn("--design %s" % did, hit)
        self.assertIn("-s top.u.y --time 90000", hit)
        self.assertIn("top.u.y = b0001", text)
        self.assertIn("语句 @a.sv:63", text)   # 连续赋值语境进摘要
        local = os.path.join(self.root, self.name, "work", "dbg", "case1_trace_top.u.y.json")
        with open(local, encoding="utf-8") as fh:
            sidecar = json.load(fh)
        self.assertEqual(sidecar["_fp"]["design"], did)

    def test_trace_x_flags_x_roots(self):
        self._plant_run()
        run, calls = self._fake_run()
        text, code = dbg.run_dbg(self.root, self.name,
                                 ["trace", "--case", "1", "-s", "top.u.y",
                                  "--time", "90000", "--x"], run=run)
        self.assertEqual(code, 0, text)
        self.assertIn("--x", self._calls_with("eda-mcp trace", calls)[0])

    def test_active_command_reports_classification_and_capture(self):
        self._plant_run()
        run, calls = self._fake_run()
        text, code = dbg.run_dbg(self.root, self.name,
                                 ["active", "--case", "1", "-s", "top.u.y",
                                  "--time", "81500", "--clock", "top.clk"], run=run)
        self.assertEqual(code, 0, text)
        hit = self._calls_with("eda-mcp active", calls)[0]
        self.assertIn("--clock top.clk", hit)
        self.assertIn("[match] top.u.c = b0001", text)
        self.assertIn("按沿取驱动值", text)
        local = os.path.join(self.root, self.name, "work", "dbg", "case1_active_top.u.y.json")
        self.assertTrue(os.path.isfile(local))

    def test_fsm_command_lists_transitions_with_capture_edges(self):
        self._plant_run()
        run, calls = self._fake_run()
        text, code = dbg.run_dbg(self.root, self.name,
                                 ["fsm", "--case", "1", "-s", "top.u.state",
                                  "--clock", "top.clk"], run=run)
        self.assertEqual(code, 0, text)
        hit = self._calls_with("eda-mcp fsm", calls)[0]
        self.assertIn("-s top.u.state", hit)
        self.assertIn("b00 → b01  ×2  首现 80000", text)
        self.assertIn("采集沿 80000", text)
        self.assertIn("n=b1", text)

    def test_fp_line_carries_run_and_freshness(self):
        self._plant_run()
        run, calls = self._fake_run()
        text, code = dbg.run_dbg(self.root, self.name,
                                 ["signals", "--case", "1"], run=run)
        self.assertEqual(code, 0, text)
        fp_line = [line for line in text.splitlines() if line.startswith("fp: ")][-1]
        fp = json.loads(fp_line[len("fp: "):])
        self.assertEqual(fp["tool"], "dbg signals")
        self.assertEqual(fp["run"], "R001")
        self.assertEqual(fp["freshness"], "输入摘要一致")
        self.assertIn("wave", fp)


class InstallTests(RepoTest):
    def setUp(self):
        eda_mcp_deploy.clear_cache()
        self.profile = load_profile()

    def _fake_run(self):
        calls = []

        def run(argv, **kwargs):
            calls.append(" ".join(argv) if isinstance(argv, list) else str(argv))
            return FakeProc("[install] ok\n")

        return run, calls

    def test_install_runs_install_sh_and_writes_source_digest(self):
        run, calls = self._fake_run()
        text, code = eda_mcp_deploy.install(root=self.root, profile=self.profile, run=run)
        self.assertEqual(code, 0, text)
        self.assertEqual(len(calls), 3, calls)
        cfg = eda_mcp.load_config(self.profile)
        self.assertIn("rsync -avz --delete", calls[0], "install 必须先同步镜像")
        self.assertIn("bash %s/toolchain/eda-mcp/install/install.sh --prefix %s --verdi-home %s" % (
            str(self.profile["mirror_root"]).rstrip("/"), cfg["prefix"], cfg["verdi_home"]), calls[1])
        digest = eda_mcp.source_digest(self.root)
        self.assertIn("SOURCE_DIGEST", calls[2])
        self.assertIn(digest, calls[2])
        # 剖面前缀以 ~ 开头：必须转成 "$HOME/..." 表达式（单引号里 ~ 不展开，
        # 会把摘要写进字面 "~" 目录）
        self.assertIn('"$HOME/.local/opt/asic_design_agent/eda-mcp/lib/eda-mcp"', calls[2])

    def test_install_sync_failure_aborts_before_install_sh(self):
        """同步失败即中止：不得用过期镜像硬装。"""
        calls = []

        def run(argv, **kwargs):
            cmd = " ".join(argv) if isinstance(argv, list) else str(argv)
            calls.append(cmd)
            if cmd.startswith("rsync"):
                return FakeProc("", "rsync error: some files vanished", returncode=24)
            return FakeProc("[install] ok\n")

        text, code = eda_mcp_deploy.install(root=self.root, profile=self.profile, run=run)
        self.assertEqual(code, 1, text)
        self.assertIn("同步镜像失败", text)
        self.assertIn("some files vanished", text)
        self.assertEqual([item for item in calls if "install.sh" in item], [])

    def test_install_no_sync_goes_straight_to_install_sh(self):
        run, calls = self._fake_run()
        text, code = eda_mcp_deploy.install(root=self.root, profile=self.profile, run=run, sync=False)
        self.assertEqual(code, 0, text)
        self.assertEqual(len(calls), 2, calls)
        self.assertIn("install.sh", calls[0])
        self.assertNotIn("rsync", " ".join(calls))

    def test_install_rejects_local_prefix(self):
        """前缀等于 ~/.local：会覆盖 ~/.local/bin 下其他项目正在使用的 eda-mcp。"""
        import copy
        profile = copy.deepcopy(self.profile)
        profile["eda_mcp"]["prefix"] = "~/.local"
        run, calls = self._fake_run()
        text, code = eda_mcp_deploy.install(root=self.root, profile=profile, run=run)
        self.assertNotEqual(code, 0, text)
        self.assertIn("~/.local", text)
        self.assertIn("覆盖", text)
        self.assertEqual(calls, [])

    def test_install_rejects_prefix_inside_mirror_root(self):
        """前缀位于 mirror_root 之内：rsync --delete 会把它删掉。"""
        import copy
        profile = copy.deepcopy(self.profile)
        profile["eda_mcp"]["prefix"] = "%s/eda-mcp" % str(profile["mirror_root"]).rstrip("/")
        run, calls = self._fake_run()
        text, code = eda_mcp_deploy.install(root=self.root, profile=profile, run=run)
        self.assertNotEqual(code, 0, text)
        self.assertIn("rsync --delete", text)
        self.assertEqual(calls, [])

    def test_validate_prefix_allows_independent_subdir(self):
        mirror = str(self.profile["mirror_root"]).rstrip("/")
        norm = eda_mcp_deploy.validate_prefix("~/.local/opt/asic_design_agent/eda-mcp", mirror)
        self.assertTrue(norm.endswith("/.local/opt/asic_design_agent/eda-mcp"))
        with self.assertRaises(eda_mcp_deploy.DeployError):
            eda_mcp_deploy.validate_prefix("~/.local/", mirror)
        with self.assertRaises(eda_mcp_deploy.DeployError):
            eda_mcp_deploy.validate_prefix("%s/toolchain/x" % mirror, mirror)


class DoctorMcpTests(RepoTest):
    def setUp(self):
        self.profile = load_profile()

    def _fake_run(self, remote_digest=None, doctor_ok=True):
        calls = []
        ok_digest = eda_mcp.source_digest(self.root)

        def run(argv, **kwargs):
            cmd = " ".join(argv) if isinstance(argv, list) else str(argv)
            calls.append(cmd)
            if cmd.endswith(" true"):
                return FakeProc()
            if "SOURCE_DIGEST" in cmd:
                return FakeProc((remote_digest if remote_digest is not None else ok_digest) + "\n")
            if "eda-mcp doctor" in cmd:
                items = [
                    {"name": "Python", "status": "ok", "detail": "3.x"},
                    {"name": "镜像根 workspace_root", "status": "ok",
                     "detail": "%s（可写）" % str(self.profile["mirror_root"]).rstrip("/")},
                    {"name": "fsdbq（FFR 波形小工具）", "status": "ok", "detail": "/bin/fsdbq"},
                ]
                if not doctor_ok:
                    items.append({"name": "fsdbq（FFR 波形小工具）", "status": "fail",
                                  "detail": "fsdbq 不能执行"})
                return FakeProc(json.dumps({"items": items}, ensure_ascii=False))
            return FakeProc()

        return run, calls

    def test_checks_pass_when_install_matches(self):
        run, _calls = self._fake_run()
        checks = mcp_checks(profile=self.profile, root=self.root, run=run)
        self.assertEqual([item["item"] for item in checks], [
            "ssh your_eda_host", "远端安装与 SOURCE_DIGEST", "远端 eda-mcp doctor",
            "workspace_root 与 mirror_root 一致", "fsdbq 可用"])
        self.assertTrue(all(item["ok"] for item in checks), checks)

    def test_digest_mismatch_is_reported_with_install_hint(self):
        """源码摘要变化时 doctor --mcp 报不一致。"""
        run, _calls = self._fake_run(remote_digest="0" * 64)
        checks = mcp_checks(profile=self.profile, root=self.root, run=run)
        second = checks[1]
        self.assertEqual(second["item"], "远端安装与 SOURCE_DIGEST")
        self.assertFalse(second["ok"])
        self.assertIn("本地 eda-mcp 已更新，先运行 framework.py eda-mcp install", second["detail"])

    def test_unconfigured_profile_reports_not_configured(self):
        profile = {"id": self.profile["id"], "ssh_alias": self.profile["ssh_alias"],
                   "mirror_root": self.profile["mirror_root"]}
        checks = mcp_checks(profile=profile, root=self.root, run=self._fake_run()[0])
        self.assertEqual(len(checks), 1)
        self.assertFalse(checks[0]["ok"])
        self.assertIn("未配置", checks[0]["detail"])

    def test_doctor_command_output_and_exit_code(self):
        from framework.doctor import run_mcp
        run, _calls = self._fake_run()
        code, text = run_mcp(profile=self.profile, root=self.root, run=run)
        self.assertEqual(code, 0, text)
        self.assertIn("结论：通过", text)
        run, _calls = self._fake_run(remote_digest="0" * 64)
        code, text = run_mcp(profile=self.profile, root=self.root, run=run)
        self.assertEqual(code, 1, text)
        self.assertIn("失败 远端安装与 SOURCE_DIGEST", text)


if __name__ == "__main__":
    unittest.main()
