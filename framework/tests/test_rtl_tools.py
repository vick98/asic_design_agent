# 作者：vick 邮箱：ykun@yk9811.com

import os
import subprocess
import sys

from framework.digest import dump
from framework.engine import EngineError, status_report
from framework.gates.rtl import compare_ports, module_decl
from framework.gates.run import run_gates
from framework.gates.tc import scan_tc
from framework.ircheck import validate_ir
from framework.state import init_sys, load_state, sys_dir
from framework.tbgen import generate
from framework.tests.util import RepoTest, checkout_root, cli, decide, fake_terminal


class RtlParseTests(RepoTest):
    def test_six_verilog_fragments(self):
        many = "module m(input clk, rst_n, output [7:0] a, b); endmodule\n"
        _params, ports = module_decl(many, "m")
        widths = {row["name"]: row["width"] for row in ports}
        self.assertEqual(widths, {"clk": 1, "rst_n": 1, "a": 8, "b": 8})

        commented = "module m(input /* hidden */ [7:0] a); endmodule\n"
        _params, ports = module_decl(commented, "m")
        self.assertEqual(ports[0]["width"], 8)

        non_ansi = "module m(a, b);\n  input [7:0] a;\n  output b;\nendmodule\n"
        _params, ports = module_decl(non_ansi, "m")
        self.assertEqual({row["name"]: row["width"] for row in ports}, {"a": 8, "b": 1})

        packed = "module m(input [3:0][7:0] bus); endmodule\n"
        _params, ports = module_decl(packed, "m")
        self.assertEqual(ports[0]["width"], 32)

        param = "module m #(parameter W = 8) (input [W-1:0] a); endmodule\n"
        _params, ports = module_decl(param, "m")
        self.assertEqual(ports[0]["width"], 8)

        iface = "module m(axi_if.slave bus); endmodule\n"
        findings = compare_ports("## 3. 端口表\n", iface, "m")
        self.assertTrue(any("未支持" in item["detail"] for item in findings))


class ToolTests(RepoTest):
    def test_doctor_without_ssh(self):
        env = os.environ.copy()
        env["ADF_ROOT"] = self.root
        proc = subprocess.run(
            [sys.executable, os.path.join(checkout_root(), "script", "framework.py"), "doctor"],
            env=env, capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("通过", proc.stdout)
        self.assertIn("跳过 ssh", proc.stdout)

    def test_doctor_ssh_failure_is_diagnosable(self):
        """ssh 失败时必须给出别名、退出码与 stderr，不能只写“失败 ssh”。"""
        import framework.doctor as doctor
        calls = {}

        class FakeProc:
            returncode = 255
            stdout = ""
            stderr = "ssh: connect to host eda.example port 22: Operation timed out\n"

        def fake_run(argv, **kwargs):
            calls["argv"] = argv
            return FakeProc()

        import subprocess
        original = subprocess.run
        subprocess.run = fake_run
        try:
            code, text = doctor.run_doctor(ssh=True)
        finally:
            subprocess.run = original
        self.assertEqual(code, 1)
        self.assertIn("失败 ssh your_eda_host", text)
        self.assertIn("255", text)
        self.assertIn("Operation timed out", text)
        self.assertIn("ConnectTimeout=10", calls["argv"])
        self.assertIn("ssh -o BatchMode=yes your_eda_host true", text)

    def test_review_pack_lists_gate_and_runs(self):
        name = "revdemo"
        init_sys(self.root, name)
        # 查看审阅包只出审核清单，不登记审查记录，不需要 --report。
        proc = cli(self.root, "review", name, "--stop", "1")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("闸门", proc.stdout)
        self.assertIn("最近运行", proc.stdout)
        # 登记审查记录必须带报告：缺 --report 时命令拒绝并点名该参数。
        proc = cli(self.root, "review", name, "record", "--stop", "1",
                   "--author", "a", "--reviewer", "b")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("--report", proc.stderr)

    def test_tb_gen_skeleton_is_blocked(self):
        """tb-gen 出来的骨架不是可放行状态，行 9 由 T6 阻断（原来断言"过闸门"）。"""
        name = "tbdemo"
        init_sys(self.root, name)
        generate(sys_dir(self.root, name), name, "alu")
        findings = scan_tc(sys_dir(self.root, name))
        t6 = [item for item in findings if item.get("rule") == "T6"]
        self.assertEqual(len(t6), 2, findings)  # tc_basic + 参考模型
        self.assertEqual([item for item in findings if item.get("level") != "hint"], t6, findings)

    def test_digest_validates_schema(self):
        text = dump(os.path.join(checkout_root(), "framework", "fixtures", "sample"), "sample")
        import json
        data = json.loads(text)
        self.assertEqual(validate_ir(data), [])
        detail = data["module_details"][0]
        self.assertIn("clock", detail["ports"][0])
        self.assertIn("connections", detail)
        self.assertIn("logic_blocks", detail)
        self.assertIn("kind", detail)
        self.assertIn("peak_words", detail["memory"])
        self.assertIn("addr_bits", detail["memory"])
        self.assertIn("flow_nodes", data)

    def test_waiver_needs_decision_and_status_lists_it(self):
        name = "waivedemo"
        init_sys(self.root, name)
        where = "info_input/%s_info_overview.md" % name
        path = os.path.join(self.root, name, where)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("# t\n\n简介。\n")
        before = run_gates(self.root, name, 1, load_state(self.root, name))
        self.assertTrue(any(item["rule"] == "S1" and item["where"] == where for item in before))
        from framework.engine import add_waiver
        with self.assertRaises(EngineError):
            add_waiver(self.root, name, "S1", where, "D0-999")
        # 豁免引用的裁决必须是方向/数值类（点选入库）；记录类不可豁免。
        did = decide(self.root, name, "接受缺章节", "方向", 1)
        add_waiver(self.root, name, "S1", where, did)
        after = run_gates(self.root, name, 1, load_state(self.root, name))
        self.assertFalse(any(item["rule"] == "S1" and item["where"] == where for item in after))
        text = status_report(self.root, name)
        self.assertIn(did, text)

    def test_marks_list_and_harvest(self):
        """走查标记收割：按原文直接入库（T 队列已删），同一处只收一次。"""
        name = "markdemo"
        init_sys(self.root, name)
        overview = os.path.join(self.root, name, "info_input", "%s_info_overview.md" % name)
        spec = os.path.join(self.root, name, "spec_doc", "demo_spec.md")
        for path, text in ((overview, "这里 mark: 第一处意见，接受缺章节\n"),
                           (spec, "@@ 第二处意见，换用流水线结构\n")):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
        from framework.marks import harvest_marks, list_marks
        listed = list_marks(self.root, name)
        self.assertEqual(len(listed), 2)
        harvested = harvest_marks(self.root, name, "记录", 1)
        self.assertEqual(len(harvested), 2)
        state = load_state(self.root, name)
        self.assertNotIn("queue", state)       # 手工队列与放行令牌一起删除
        self.assertNotIn("dequeued", state)
        self.assertNotIn("T", state["seq"])    # T 序号已删除
        rows = state["decisions"]["0"]         # 停点 1 → 阶段 0
        self.assertEqual([did for did, _line in harvested], [row["id"] for row in rows])
        self.assertTrue(all(row["source"].startswith("mark:") for row in rows))
        # 已入库的标记不再重复收割。
        self.assertEqual([], harvest_marks(self.root, name, "记录", 1))
        self.assertEqual(2, len(state["decisions"]["0"]))
