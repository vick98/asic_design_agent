# 作者：vick 邮箱：ykun@yk9811.com

"""第二轮 WP14：工具体验的复现测试。"""

import os
import subprocess
import sys
import unittest

from framework.engine import module_state
from framework.gates.numeric import scan_text
from framework.gates.tc import platform_names, scan_tc
from framework.state import init_sys, load_state, save, sys_dir
from framework.tests.util import RepoTest, checkout_root, plant_sample
from framework.tbgen import generate, plan
from framework.toolbox.fx import (
    addr_capacity, fmt_s, golden_tol, latency, line, mul, note_text, pack, parse_fmt,
    round_shr, sac_shift, sat_bounds,
)


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _run(root, home, *argv):
    env = os.environ.copy()
    env["ADF_ROOT"] = root
    env["HOME"] = home
    proc = subprocess.run(
        [sys.executable, os.path.join(checkout_root(), "script", "framework.py")] + list(argv),
        env=env, capture_output=True, text=True,
    )
    return proc


class FxValueTests(RepoTest):
    def test_f22_text_carries_values(self):
        bounds = sat_bounds((8, 3, "t"))
        self.assertIn("127", line("sat", "sat %s asymmetric" % fmt_s((8, 3, "t")), extra=bounds,
                                  note=note_text("sat", bounds))["text"])
        self.assertIn("-128", line("sat", "sat %s asymmetric" % fmt_s((8, 3, "t")), extra=bounds,
                                   note=note_text("sat", bounds))["text"])
        packed = pack([8, 3])
        self.assertIn("11", note_text("pack", packed))
        addr = addr_capacity([16, 32], 10)
        self.assertIn("48", note_text("addr", addr))
        self.assertIn("1024", note_text("addr", addr))
        self.assertIn("放得下", note_text("addr", addr))
        self.assertEqual(note_text("round", round_shr(-5, 1, "even")), "结果 -2")
        self.assertEqual(note_text("latency", latency([3, 4])), "拍数合计 7")
        self.assertEqual(note_text("sac", sac_shift((10, 3, "t"), (8, 1, "t"))), "移位 2")
        tol = golden_tol((8, 3, "t"), 1)
        self.assertIn("k=1", note_text("tol", tol))
        self.assertIn("2^-4", note_text("tol", tol))  # 新口径 f=W−I−1=4

    def test_f22_stamp_unchanged_by_note(self):
        plain = line("pack", "pack 8+8", extra={"widths": [8, 8], "total": 16})
        noted = line("pack", "pack 8+8", extra={"widths": [8, 8], "total": 16}, note="合计位宽 16")
        self.assertEqual(plain["stamp"], noted["stamp"])
        self.assertNotEqual(plain["text"], noted["text"])

    def test_f22_cli_prints_values(self):
        proc = _run(self.root, self.home, "fx", "sat", "<8,3,t>")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("127", proc.stdout)
        self.assertIn("-128", proc.stdout)
        self.assertIn("stamp:", proc.stdout)

    def test_f23_round_takes_negative_value(self):
        proc = _run(self.root, self.home, "fx", "round", "--value", "-5", "--n", "1", "--mode", "even")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("-2", proc.stdout)

    def test_f22_numeric_gate_checks_note_values(self):
        bounds = sat_bounds((8, 3, "t"))
        good = line("sat", "sat %s asymmetric" % fmt_s((8, 3, "t")), extra=bounds,
                    note=note_text("sat", bounds))
        text = "%s\nstamp: %s\n" % (good["text"], good["stamp"])
        self.assertFalse([item for item in scan_text(text, "sat") if item["rule"] == "fx"])
        tampered = text.replace("范围 -128..127", "范围 -128..126")
        self.assertTrue(any(item["rule"] == "fx" for item in scan_text(tampered, "sat")))
        packed = line("pack", "pack 8+8", extra={"widths": [8, 8], "total": 16},
                      note=note_text("pack", pack([8, 8])))
        self.assertFalse(scan_text("%s\nstamp: %s\n" % (packed["text"], packed["stamp"]), "pack"))
        bad_pack = "%s\nstamp: %s\n" % (packed["text"].replace("合计位宽 16", "合计位宽 24"),
                                        packed["stamp"])
        self.assertTrue(any(item["rule"] == "fx" for item in scan_text(bad_pack, "pack")))
        rnd = line("round", "round -5 >> 1 even", extra={"value": -2},
                   note=note_text("round", round_shr(-5, 1, "even")))
        self.assertFalse(scan_text("%s\nstamp: %s\n" % (rnd["text"], rnd["stamp"]), "round"))
        bad_round = "%s\nstamp: %s\n" % (rnd["text"].replace("结果 -2", "结果 -3"), rnd["stamp"])
        self.assertTrue(any(item["rule"] == "fx" for item in scan_text(bad_round, "round")))

    def test_old_documents_without_values_still_valid(self):
        plain = line("mul", "%s * %s" % (fmt_s((8, 2, "t")), fmt_s((8, 2, "t"))), mul((8, 2, "t"), (8, 2, "t")))
        text = "<8,2,t> * <8,2,t> → <15,4,t>\nstamp: %s\n" % plain["stamp"]
        self.assertEqual([item for item in scan_text(text, "old") if item["rule"].startswith("fx")], [])
        legacy = line("sat", "sat %s asymmetric" % fmt_s((8, 3, "t")), extra=sat_bounds((8, 3, "t")))
        self.assertNotIn("范围", legacy["text"])


class TbGenTests(RepoTest):
    def test_f24_generates_full_skeleton_from_ir(self):
        name = "tbrich"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        lines = generate(sys_dir(self.root, name), name, "alu")
        made = {item.split(" ", 1)[1] for item in lines if item.startswith("写入")}
        for expect in (
            "testbench/alu/alu_if.sv",
            "testbench/alu/alu_tb_pkg.sv",
            "testbench/alu/alu_tb_cfg.svh",
            "testbench/alu/alu_tb_item.svh",
            "testbench/alu/alu_tb_driver.svh",
            "testbench/alu/alu_tb_monitor.svh",
            "testbench/alu/alu_tb_refm.svh",
            "testbench/alu/alu_tb_scoreboard.svh",
            "testbench/alu/alu_tb_env.svh",
            "testbench/alu/alu_tb_cov.svh",
            "testbench/alu/alu_sim_top.sv",
            "testbench/alu/tc/alu_tc_base.sv",
            # T6：fixture 的 alu_spec.md 有 2 条测试要点 → 一测试点一用例。
            "testbench/alu/tc/alu_tc_tp1.sv",
            "testbench/alu/tc/alu_tc_tp2.sv",
            "testbench/alu/tc/alu_tc_factory.svh",
            "testbench/alu/tc/alu_tc_all.sv",
            "testbench/alu/alu_tb.f",
        ):
            self.assertIn(expect, made)
        # 模块级平台不再占用子系统级清单，它属于子系统顶层。
        self.assertNotIn("testbench/%s_tb.f" % name, made)
        base = os.path.join(sys_dir(self.root, name), "testbench", "alu")
        interface = open(os.path.join(base, "alu_if.sv"), encoding="utf-8").read()
        self.assertIn("interface alu_if (input logic clk_in);", interface)
        for port in ("i_a", "i_b", "o_y"):
            self.assertIn(port, interface)
        top = open(os.path.join(base, "alu_sim_top.sv"), encoding="utf-8").read()
        self.assertIn("tb_clk_rst_if", top)
        self.assertIn("`TB_TIMEOUT_INIT", top)
        self.assertIn(".i_a", top)
        self.assertNotIn("always #", top)
        case = open(os.path.join(base, "tc", "alu_tc_tp1.sv"), encoding="utf-8").read()
        self.assertIn("`TB_CASE_BEGIN", case)
        self.assertIn("`TB_CASE_END", case)
        self.assertNotIn("$display", case)
        filelist = open(os.path.join(base, "alu_tb.f"), encoding="utf-8").read()
        self.assertIn("+incdir+../../../tb_common", filelist)
        self.assertIn("../../../tb_common/tb_pkg.sv", filelist)
        self.assertIn("+incdir+../../testbench/alu", filelist)
        order = [line for line in filelist.splitlines() if line and not line.startswith(("+", "#"))]
        self.assertTrue(order[-1].endswith("alu_sim_top.sv"), order)
        self.assertLess(order.index("../../testbench/alu/tc/alu_tc_all.sv"),
                        order.index("../../testbench/alu/tc/alu_tc_factory.svh"))
        # 子系统级清单要由子系统顶层的 tb-gen 写出来。
        lines = generate(sys_dir(self.root, name), name, "%s_top" % name)
        made_top = {item.split(" ", 1)[1] for item in lines if item.startswith("写入")}
        self.assertIn("testbench/%s_tb.f" % name, made_top)
        syslist = open(os.path.join(sys_dir(self.root, name), "testbench", "%s_tb.f" % name),
                       encoding="utf-8").read()
        self.assertIn("+incdir+../../tb_common", syslist)
        self.assertIn("../testbench/%s_top/%s_top_sim_top.sv" % (name, name), syslist)

    def test_f24_generated_skeleton_passes_tc_gate(self):
        name = "tbdemo2"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        generate(sys_dir(self.root, name), name, "alu")
        blocking = [item for item in scan_tc(sys_dir(self.root, name))
                    if item.get("level") != "hint"]
        self.assertEqual(blocking, [], blocking)

    def test_f24_existing_files_are_not_overwritten(self):
        name = "tbkeep"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        generate(sys_dir(self.root, name), name, "alu")
        target = os.path.join(sys_dir(self.root, name), "testbench", "alu", "tc", "alu_tc_tp1.sv")
        _write(target, "// 开发者手改过\n")
        lines = generate(sys_dir(self.root, name), name, "alu")
        self.assertTrue(all(item.startswith("跳过") for item in lines), lines)
        self.assertEqual(open(target, encoding="utf-8").read(), "// 开发者手改过\n")
        lines = generate(sys_dir(self.root, name), name, "alu", force=True)
        self.assertTrue(all(item.startswith("写入") for item in lines), lines)
        self.assertNotEqual(open(target, encoding="utf-8").read(), "// 开发者手改过\n")

    def test_f24_compile_line_references_generated_files(self):
        name = "tbcompile"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        generate(sys_dir(self.root, name), name, "alu")
        filelist = os.path.join(sys_dir(self.root, name), "testbench", "alu", "alu_tb.f")
        self.assertTrue(os.path.isfile(filelist))
        body = open(filelist, encoding="utf-8").read()
        self.assertIn("alu_tc_all.sv", body)
        from framework.profile_run import run_sim
        result = run_sim({"scenario": "module", "sys": name, "module": "alu",
                          "dry_run": True, "compile_only": True})
        self.assertEqual(result["status"], "dry_run")
        self.assertIn("testbench/alu/alu_tb.f", result["summary"])

    def test_f24_cli_tb_gen_derives_row9_skeleton(self):
        # tb-gen 只落文件，不再登记 modules[9]；行 9 平台清单由
        # testbench/<平台>/tc 推导，状态由用例核对推导（骨架标记未清 → "骨架"）。
        name = "tbcli"
        init_sys(self.root, name)
        proc = _run(self.root, self.home, "tb-gen", name, "--dut", "alu")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        state = load_state(self.root, name)
        base = sys_dir(self.root, name)
        self.assertEqual(platform_names(base), ["alu"])
        self.assertEqual(module_state(state, base, "9", "alu"), "骨架")
        # 没有手工登记条目：平台清单与状态都由文件与用例核对推导。
        self.assertEqual(state["modules"].get("9", []), [])


class MarksTests(RepoTest):
    # 走查标记不再进 T 队列，`marks --harvest` 按原文直接入库（来源 mark:<文件>:<行>），
    # 已入库的标记不重复收割；收割上限读 state.thresholds.marks_cap，缺省不限。
    LINES = [
        "mark: 帧窗口按行 2 口径",
        "mark: 仲裁采用固定优先级",
        "mark: 缓存深度取 16 拍",
        "mark: 数据位宽取 8 位",
        "mark: 复位低有效",
        "mark: 输出饱和处理",
    ]

    def _plant(self, name):
        init_sys(self.root, name)

        _write(os.path.join(sys_dir(self.root, name), "info_input",
                            "%s_info_overview.md" % name),
               "\n".join(self.LINES) + "\n")
        return name

    def test_f25_harvest_skips_known_and_has_no_default_cap(self):
        name = self._plant("marknone")
        first = _run(self.root, self.home, "marks", name,
                     "--harvest", "--kind", "记录", "--stop", "1")
        self.assertEqual(first.returncode, 0, first.stderr)
        rows = load_state(self.root, name)["decisions"]["0"]
        self.assertEqual(len(rows), 6, "缺省不限：待收割的标记一次全部入库")
        self.assertEqual([row["kind"] for row in rows], ["记录"] * 6)
        self.assertTrue(all(row["source"].startswith("mark:") for row in rows), rows)
        self.assertIn("已收割 6 条，已收割过 0 条", first.stdout)
        self.assertNotIn("上限", first.stdout)
        # 已收割的不再重复：再跑一次是空操作。
        second = _run(self.root, self.home, "marks", name,
                      "--harvest", "--kind", "记录", "--stop", "1")
        self.assertEqual(second.returncode, 0, second.stderr)
        rows = [row for step in load_state(self.root, name)["decisions"].values() for row in step]
        self.assertEqual(len(rows), 6)
        self.assertEqual(len({row["content"] for row in rows}), 6, "同一条标记不重复入库")
        self.assertIn("已收割 0 条，已收割过 6 条", second.stdout)

    def test_f25_marks_cap_threshold_limits_one_run(self):
        name = self._plant("markcap")
        state = load_state(self.root, name)
        state["thresholds"]["marks_cap"] = 2
        save(self.root, name, state)
        first = _run(self.root, self.home, "marks", name,
                     "--harvest", "--kind", "记录", "--stop", "1")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(len(load_state(self.root, name)["decisions"]["0"]), 2)
        self.assertIn("已收割 2 条，已收割过 0 条，上限 2 条", first.stdout)
        self.assertIn("未收割（超过上限）", first.stdout)
        # 再跑两次拿走剩下的 4 条。
        for _ in range(2):
            proc = _run(self.root, self.home, "marks", name,
                        "--harvest", "--kind", "记录", "--stop", "1")
            self.assertEqual(proc.returncode, 0, proc.stderr)
        rows = [row for step in load_state(self.root, name)["decisions"].values() for row in step]
        self.assertEqual(len(rows), 6)
        self.assertEqual(len({row["content"] for row in rows}), 6, "同一条标记不重复入库")

    def test_f25_harvest_skips_already_harvested(self):
        name = "markdup"
        init_sys(self.root, name)
        _write(os.path.join(sys_dir(self.root, name), "info_input", "%s_info_overview.md" % name),
               "mark: 一处\n")
        from framework.marks import harvest_marks, marks_plan
        done = harvest_marks(self.root, name, "记录", 1)
        self.assertEqual(len(done), 1)
        self.assertEqual(done[0][0], "D0-001")
        fresh, known = marks_plan(self.root, name)
        self.assertEqual(fresh, [], "已入库的标记不再算待收割")
        self.assertEqual(len(known), 1)
        self.assertEqual(harvest_marks(self.root, name, "记录", 1), [],
                         "已收割的标记不再重复入库")


class DecisionListTests(RepoTest):
    def test_f25_decision_list_is_a_table(self):
        name = "listdemo"
        init_sys(self.root, name)
        from framework.engine import add_problem
        from framework.tests.util import decide
        did = decide(self.root, name, "位宽取 8", "记录", 1)
        add_problem(self.root, name, "待裁决", 2, "缓存取多大", options="8|16|32")
        proc = _run(self.root, self.home, "decision", name, "list")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        # 两步链路第一步的待办：待裁决问题表（手工 T 队列已删除）。
        self.assertIn("## 待裁决问题", proc.stdout)
        self.assertIn("| 问题号 | 停点 | 问题原文 | 候选 |", proc.stdout)
        self.assertIn("缓存取多大", proc.stdout)
        self.assertIn("8|16|32", proc.stdout)
        # 分阶段裁决表。
        self.assertIn("| 阶段 | 编号 | 类别 | 裁决内容 | 来源/备注 |", proc.stdout)
        self.assertIn(did, proc.stdout)
        self.assertIn("| 记录 |", proc.stdout)
        self.assertIn("位宽取 8", proc.stdout)
        self.assertNotIn("临时编号", proc.stdout)
        self.assertNotRegex(proc.stdout, r"T\d{3}")


if __name__ == "__main__":
    unittest.main()
