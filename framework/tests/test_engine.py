# 作者：vick 邮箱：ykun@yk9811.com

import os
import shutil
import unittest

from framework.engine import (
    auto_complete_check, module_state, record_run, set_module, tick_report,
)
from framework.flow import load
from framework.state import init_sys, load_state, root_of, stop_row, sys_dir
from framework.tests.util import RepoTest, checkout_root, confirm_milestone, force_done, review


def _doc(root, sys_name, rel, intro, chapters):
    from framework.gates.docs import expected_chapters
    if isinstance(chapters, str):
        chapters = expected_chapters(rel, 6, "", sys_name) or [chapters]
    path = os.path.join(root, sys_name, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = ["# %s" % os.path.basename(rel)[:-3], "", intro, ""]
    for index, name in enumerate(chapters, 2):
        lines.append("## %d. %s" % (index, name))
        lines.append("")
        lines.append("正文。")
        lines.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def _plant(root, sys_name):
    src = os.path.join(root, "framework", "fixtures", "mini")
    dst = os.path.join(root, sys_name)
    for dirpath, _dirs, files in os.walk(src):
        rel = os.path.relpath(dirpath, src)
        target = dst if rel == "." else os.path.join(dst, rel)
        os.makedirs(target, exist_ok=True)
        for fn in files:
            out = (sys_name + "_top.sv") if fn == "mini_top.sv" else fn
            shutil.copy(os.path.join(dirpath, fn), os.path.join(target, out))


class EngineTests(RepoTest):
    def test_root_follows_copy(self):
        from framework.paths import project_root
        self.assertEqual(os.path.realpath(project_root()), os.path.realpath(self.root))
        self.assertEqual(os.path.realpath(root_of()), os.path.realpath(self.root))

    def test_flow_reads_copy(self):
        path = os.path.join(self.root, "framework", "flow_model.yaml")
        with open(path, encoding="utf-8") as fh:
            original = fh.read()
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(original.replace("version: 2", "version: 99", 1))
            self.assertEqual(load()["version"], 99)
        finally:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(original)

    def test_stop_walk_uses_copy(self):
        # 启动/送审/完成全由 tick 四相位自动推进（产物已由夹具就位时同一 tick 内
        # 启动+完成）；行 6/11/12 是里程碑归属，tick 只置送审态"待里程碑"，
        # 用例用 force_done 构造 milestone confirm 之后的完成态；
        # --enter-structure 已删除，进入行 5 只看上一停点完成。
        name = "selftestsys"
        project = root_of()
        self.assertEqual(os.path.realpath(project), os.path.realpath(self.root))
        checkout = checkout_root()
        self.assertFalse(os.path.isdir(os.path.join(checkout, name)))
        init_sys(project, name)
        try:
            self.assertTrue(os.path.isdir(os.path.join(project, name)))
            self.assertFalse(os.path.isdir(os.path.join(checkout, name)))
            # 行 1 未定稿：tick 只自动启动行 1，依赖它的行 2 保持未开始。
            tick_report(project, name)
            state = load_state(project, name)
            self.assertEqual(stop_row(state, 1)["state"], "进行中")
            self.assertEqual(stop_row(state, 2)["state"], "未开始")
            _doc(project, name, "info_input/selftestsys_info_overview.md", "输入文档总览。",
                 ["输入文档", "可信度", "冲突", "红线五问"])
            review(project, name, 1)
            tick_report(project, name)
            self.assertEqual(stop_row(load_state(project, name), 1)["state"], "完成（审核通过）")
            bodies = {
                2: ("flow_doc/selftestsys_flow.md", "处理流程。",
                    ["输入输出", "步骤", "节点表", "运算定点化图", "边界点"]),
                3: ("plan_doc/selftestsys_plan.md", "系统方案。",
                    ["模块划分", "模块类型", "前后级与交互"]),
                4: ("spec_doc/selftestsys_spec.md", "子系统规格。",
                    ["子系统功能", "端口表", "寄存器", "模块摘要"]),
            }
            for sid in (2, 3):
                rel, intro, chapters = bodies[sid]
                _doc(project, name, rel, intro, chapters)
                review(project, name, sid)
                tick_report(project, name)
            # M1 确认前停点 4 不得启动；确认后才由 tick 自动启动。
            self.assertEqual(stop_row(load_state(project, name), 4)["state"], "未开始")
            confirm_milestone(project, name, "M1")
            rel, intro, chapters = bodies[4]
            _doc(project, name, rel, intro, chapters)
            review(project, name, 4)
            tick_report(project, name)
            # 行 5、6 的产物（spec_doc/ 结构文件、rtl/、testbench/）来自 mini 夹具。
            _plant(project, name)
            review(project, name, 5)
            tick_report(project, name)
            review(project, name, 6)
            tick_report(project, name)
            # 送审态名已由 flow.PENDING 定义为"已送审"（旧名只出现在 v2→v3 迁移数据里）。
            self.assertEqual(stop_row(load_state(project, name), 6)["state"], "已送审")
            force_done(project, name, 6)
            record_run(project, name, {
                "capability": "lint", "status": "pass", "summary": "ok",
                "profile_id": "example",
                "scope": {"modules": ["alu"]}, "checks": {"errors": 0},
            })
            # 行 7/8/9 不再手工登记模块——清单由 rtl/*.sv（mini 夹具给
            # alu、<sys>_top.sv）与 testbench/<平台>/tc 推导，状态由证据推导。
            # M2 确认前停点 7 不得启动。
            confirm_milestone(project, name, "M2")
            review(project, name, 7, module="alu")
            tick_report(project, name)
            state = load_state(project, name)
            base = sys_dir(project, name)
            self.assertEqual([item["name"] for item in state["modules"]["7"]], ["alu"])
            self.assertEqual(module_state(state, base, "7", "alu"), "审查通过")
            self.assertEqual(state["modules"]["7"][0]["kind"], "rtl_review")
            review(project, name, 8)
            tick_report(project, name)
            state = load_state(project, name)
            self.assertEqual(module_state(state, base, "8", name + "_top"), "连接通过")
            # DEV-07：行 9 的独立审查是 tb_review（与 tc 闸门并列）。
            review(project, name, 9)
            tick_report(project, name)
            state = load_state(project, name)
            self.assertEqual(module_state(state, base, "9", "tb"), "tc_check 通过")
            self.assertEqual(stop_row(state, 9)["state"], "完成（审核通过）")
            record_run(project, name, {
                "capability": "sim", "status": "fail", "summary": "RESULT: FAIL",
                "profile_id": "example",
            })
            # 闸门未过：tick 自动启动行 10，但不置完成，原因里带闸门判定。
            tick_report(project, name)
            state = load_state(project, name)
            self.assertEqual(stop_row(state, 10)["state"], "进行中")
            reasons = auto_complete_check(project, name, state, 10)["reasons"]
            self.assertTrue(any("闸门未过" in reason for reason in reasons), reasons)
            record_run(project, name, {
                "capability": "sim", "status": "pass", "summary": "RESULT : PASS",
                "profile_id": "example",
                "scope": {"scenario": "sys", "tc": "", "seeds": ["1"]},
                "checks": {"result_pass": 1, "result_fail": 0, "full_regression": 1},
            })
            record_run(project, name, {
                "capability": "coverage", "status": "pass", "summary": "cov",
                "profile_id": "example",
                "checks": {"line": 100.0, "cond": 100.0, "fsm": 100.0, "tgl": 100.0},
            })
            tick_report(project, name)
            self.assertEqual(stop_row(load_state(project, name), 10)["state"], "完成（审核通过）")
            record_run(project, name, {
                "capability": "synth", "status": "pass", "summary": "syn",
                "profile_id": "example",
            })
            record_run(project, name, {
                "capability": "sta", "status": "pass", "summary": "sta",
                "profile_id": "example",
            })
            tick_report(project, name)
            self.assertEqual(stop_row(load_state(project, name), 11)["state"], "已送审")
            force_done(project, name, 11)
            tick_report(project, name)
            signoff_path = os.path.join(project, name, "signoff", name + "_signoff.md")
            self.assertTrue(os.path.isfile(signoff_path))
            with open(signoff_path, encoding="utf-8") as fh:
                signoff = fh.read()
            self.assertIn("R", signoff)
            self.assertIn("放行", signoff)
            set_module(project, name, "7", "alu", "退回")
            state = load_state(project, name)
            self.assertEqual(stop_row(state, 7)["state"], "进行中")
            self.assertFalse(os.path.isdir(os.path.join(checkout, name)))
        finally:
            shutil.rmtree(os.path.join(project, name), ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
