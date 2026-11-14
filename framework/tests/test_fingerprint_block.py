# 作者：vick 邮箱：ykun@yk9811.com

import os

from framework.engine import (
    _product_digest, advance, stale_stops, status_report, tick_report,
)
from framework.flow import DONE, RUNNING, load
from framework.gates.run import run_gates
from framework.state import init_sys, load_state, save, stop_row
from framework.tests.util import RepoTest, review

OVERVIEW = ["输入文档", "可信度", "冲突", "红线五问"]


def _write(root, name, rel, text):
    path = os.path.join(root, name, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _doc(root, name, rel, chapters, extra=""):
    lines = ["# t", "", "简介。", ""]
    for index, chapter in enumerate(chapters, 2):
        lines.extend(["## %d. %s" % (index, chapter), "", "正文。%s" % extra, ""])
    _write(root, name, rel, "\n".join(lines))


def _mark_done(root, name, sid):
    """直接把停点置为完成并按当前产物写指纹，只用于构造路径重叠的场景。"""
    state = load_state(root, name)
    stop = load()["by_id"][sid]
    row = stop_row(state, sid)
    row["state"] = DONE
    row["fingerprint"] = _product_digest(root, name, stop)
    save(root, name, state)


class FingerprintBlockTests(RepoTest):
    def _done_stop1(self, name):
        init_sys(self.root, name)
        rel = "info_input/%s_info_overview.md" % name
        _doc(self.root, name, rel, OVERVIEW)
        # 完成要一条对当前产物的独立审查记录；启动与完成由 tick 自动做。
        review(self.root, name, 1)
        tick_report(self.root, name)
        self.assertEqual(stop_row(load_state(self.root, name), 1)["state"], DONE)
        return rel

    def test_changed_done_product_retreats_cascades_and_gate(self):
        name = "fpblock"
        rel = self._done_stop1(name)
        # 再一次 tick：依赖已定稿的停点 2 自动启动（没有审查记录，停在"进行中"）。
        tick_report(self.root, name)
        self.assertEqual(stop_row(load_state(self.root, name), 2)["state"], RUNNING)
        _doc(self.root, name, rel, OVERVIEW, extra="完成后偷改。")
        # 闸门层面仍看得见：停点 2 的指纹规则判行 1 的产物完成后有改动。
        state = load_state(self.root, name)
        rules = [item["rule"] for item in run_gates(self.root, name, 2, state)]
        self.assertIn("fingerprint", rules)
        self.assertIn("阻断：停点 1 的产物在完成后有改动", status_report(self.root, name))
        # advance 不再改状态：退回进行中与级联由 tick 的"指纹失效退回"相位负责。
        message = advance(self.root, name, 2, "进行中")
        self.assertIn("已由 tick 自动处理", message)
        self.assertEqual(stop_row(load_state(self.root, name), 2)["state"], RUNNING)
        out = tick_report(self.root, name)
        self.assertIn("指纹失效退回停点 1", out)
        state = load_state(self.root, name)
        row1 = stop_row(state, 1)
        self.assertEqual(row1["state"], RUNNING)
        self.assertIn("指纹失效退回", row1["remark"])
        # 下游已启动的停点 2 按依赖级联退回，留待重推与复核恢复。
        row2 = stop_row(state, 2)
        self.assertEqual(row2["state"], RUNNING)
        self.assertIn("上游 停点 1 指纹失效 变更待重推", row2["remark"])
        self.assertEqual(row2["cascaded_from"], 1)
        with open(os.path.join(self.root, name, "events.jsonl"), encoding="utf-8") as fh:
            events = fh.read()
        self.assertIn("指纹失效退回", events)
        self.assertIn("级联退回", events)

    def test_retreat_clears_block(self):
        name = "fpretreat"
        rel = self._done_stop1(name)
        _doc(self.root, name, rel, OVERVIEW, extra="完成后偷改。")
        advance(self.root, name, 1, "进行中")   # 主动重做退回
        review(self.root, name, 1)              # 对改后的产物补审查记录
        tick_report(self.root, name)            # 重推完成：指纹阻断清除
        self.assertEqual(stale_stops(self.root, name, load_state(self.root, name)), [])
        out = tick_report(self.root, name)
        self.assertNotIn("指纹失效退回", out)
        self.assertNotIn("完成后有改动", status_report(self.root, name))
        self.assertEqual(stop_row(load_state(self.root, name), 2)["state"], RUNNING)

    def test_unchanged_product_not_blocked(self):
        name = "fpclean"
        self._done_stop1(name)
        tick_report(self.root, name)
        self.assertEqual(stop_row(load_state(self.root, name), 2)["state"], RUNNING)
        self.assertNotIn("完成后有改动", status_report(self.root, name))

    def test_later_stop_owned_subpath_not_in_digest(self):
        # 行 8 的顶层文件在行 7 的 rtl/ 之下：写顶层不算改了行 7 的产物
        name = "fpsubpath"
        init_sys(self.root, name)
        _write(self.root, name, "rtl/alu.sv", "module alu; endmodule\n")
        _mark_done(self.root, name, 7)
        _write(self.root, name, "rtl/%s_top.sv" % name, "module top; endmodule\n")
        self.assertEqual(stale_stops(self.root, name, load_state(self.root, name)), [])
        _write(self.root, name, "rtl/alu.sv", "module alu; wire a; endmodule\n")
        self.assertEqual(stale_stops(self.root, name, load_state(self.root, name)), [7])

    def test_covering_later_stop_takes_over_once_started(self):
        # 对称回滚（2026-10-18 裁决）：行 4 的子系统规格书在行 5 的 spec_doc/ 之下，
        # 行 5 启动与否不豁免行 4——已完成且指纹失效的停点一律列出，避免被豁免侧
        # 的指纹永久陈旧毒化里程碑复核。
        name = "fpcover"
        init_sys(self.root, name)
        rel = "spec_doc/%s_spec.md" % name
        _write(self.root, name, rel, "v1\n")
        _mark_done(self.root, name, 4)
        _write(self.root, name, rel, "v2\n")
        self.assertEqual(stale_stops(self.root, name, load_state(self.root, name)), [4])
        state = load_state(self.root, name)
        stop_row(state, 5)["state"] = RUNNING
        save(self.root, name, state)
        self.assertEqual(stale_stops(self.root, name, load_state(self.root, name)), [4])

    def test_sibling_stops_over_same_dir_roll_back_symmetrically(self):
        # 行 5/6 共用 spec_doc/：行 6 完成后改叶子规格书，两行都要退回，
        # 而不是只退行 6（旧行为会让行 5 的指纹永久陈旧）。
        name = "fpsym"
        init_sys(self.root, name)
        _write(self.root, name, "spec_doc/%s_spec.md" % name, "sys\n")
        leaf = "spec_doc/%s_mod_spec.md" % name
        _write(self.root, name, leaf, "v1\n")
        _mark_done(self.root, name, 5)
        _mark_done(self.root, name, 6)
        _write(self.root, name, leaf, "v2\n")
        self.assertEqual(stale_stops(self.root, name, load_state(self.root, name)), [5, 6])
