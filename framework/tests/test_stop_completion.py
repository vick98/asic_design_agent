# 作者：vick 邮箱：ykun@yk9811.com

"""第二轮 WP10：状态机与自动完成判据的复现测试。

按交互模型改写：停点送完成走自动完成判据（闸门 + 无阻断 +
无在途事项 + 独立审查记录），不要令牌与确认语句；行 6/11/12 由里程碑覆盖完成，
测试用 util.force_done 构造前置状态；代判删除；迭代降级删除。
"""

import os
import subprocess
import sys
import unittest

from framework.engine import (
    EngineError, add_problem, add_summary, add_waiver, advance, auto_complete_check,
    commit_decision, inputs_digest, item_open, override_decision, record_run,
    render_signoff, set_handoff, set_module, status_report, tick_report,
    withdraw_decision,
)
from framework.flow import DONE, NOT_STARTED, PENDING, RUNNING
from framework.gates.run import run_gates
from framework.state import blank, golden_add, init_sys, load_state, save, stop_row, sys_dir
from framework.tests.util import (
    RepoTest, checkout_root, confirm_milestone, decide, force_done,
    plant_sample, review,
)

QUOTE = "通过"

# 阶段号由停点推导（engine.stage_of_stop），测试里按阶段号找停点。
_STOP_OF_STAGE = {"0": 1, "1": 2, "2": 3, "3": 4, "5": 7}


def _plant(root, name):
    return plant_sample(root, name)


def _step(root, name, sid, quote=QUOTE, module=""):
    """把一个停点推到它该到的位置——补审查记录后跑 `tick`，不再用 advance。

    tick 相位②自动启动依赖定稿的未开始停点、相位③判据齐备即完成。行 6/11/12 由
    里程碑覆盖完成：这里仍用 force_done 构造里程碑确认之后的完成态。里程碑阻塞
    （行 4 前 M1、行 7 前 M2）用 confirm_milestone 补齐——此时它表现为 tick 不会
    自动启动，而不是 advance 抛错。
    """
    if sid == 4:
        confirm_milestone(root, name, "M1")
    if sid == 7:
        confirm_milestone(root, name, "M2")
    if sid in (6, 11, 12):
        force_done(root, name, sid)
        return
    if sid in (7, 8):
        review(root, name, sid, module=module)
    elif sid == 9:
        # DEV-07：行 9 要一条 tb_review（与 tc 闸门并列），卡见 rules/review/tb.md。
        review(root, name, sid)
    elif sid <= 6:
        review(root, name, sid)
    tick_report(root, name)


def _walk(root, name, upto, quote=QUOTE):
    for sid in range(1, upto + 1):
        _step(root, name, sid, quote, module="alu")


def _lint(root, name, modules):
    return record_run(root, name, {
        "capability": "lint", "status": "pass", "summary": "lint pass",
        "profile_id": "example", "scope": {"modules": list(modules)},
        "checks": {"errors": 0},
    })


def _sim(root, name, seeds, full=True):
    return record_run(root, name, {
        "capability": "sim", "status": "pass", "summary": "RESULT : PASS",
        "profile_id": "example",
        "scope": {"scenario": "sys", "module": "", "tc": "", "seeds": list(seeds)},
        "checks": {"result_pass": 1, "result_fail": 0, "full_regression": 1 if full else 0},
    })


def _coverage(root, name):
    return record_run(root, name, {
        "capability": "coverage", "status": "pass", "summary": "coverage pass",
        "profile_id": "example",
        "checks": {"line": 100.0, "cond": 100.0, "fsm": 100.0, "tgl": 100.0},
    })


def _midend(root, name):
    record_run(root, name, {
        "capability": "synth", "status": "pass", "summary": "synth pass",
        "profile_id": "example",
        "checks": {"errors": 0, "latches": 0, "setup_wns": 0.1, "setup_violations": 0, "area": 1.0},
    })
    record_run(root, name, {
        "capability": "sta", "status": "pass", "summary": "sta pass",
        "profile_id": "example",
        "checks": {"corners": [{"setup_wns": 0.1, "hold_wns": 0.1,
                                "setup_violations": 0, "hold_violations": 0}]},
    })


def _exempt(path):
    """blank() 里按定义抄入或按派生写入的字段，说明理由后不参与“必须变化”的断言。"""
    if path == ("sys_name",):
        return "子系统名由 init_sys 写入 blank()，之后不改写"
    if len(path) == 3 and path[0] == "stops" and path[2] == "id":
        return "停点号来自 flow_model.yaml，由 blank() 抄入"
    if path == ("position", "updated"):
        return "save() 每次都刷当前分钟，测试同分钟内看不出变化"
    if len(path) == 3 and path[0] == "stops" and path[2] == "allow_violation":
        # 带违例送审的授权标记：唯一写入路径是 advance --allow-violation（红线动作，
        # 要裁决号）。本包不跑违例流程，该路径由 test_advance_withdraw 覆盖。
        return "只由带违例送审写入；本包不跑违例流程（见 test_advance_withdraw）"
    if path == ("modules", "9"):
        # 行 9 平台清单由 testbench/ 推导，modules["9"] 只在显式
        # module --state 退回 时创建条目；正常流转下它保持空表是预期。
        return "行 9 平台清单由 testbench/ 推导，条目只在显式退回时创建"
    if len(path) == 3 and path[0] == "stops" and path[2] == "confirm_quote":
        # 豁免仍必要：收缩后 confirm_quote 的唯一写入路径是里程碑确认
        # （milestone confirm → _finish_stop(quote=...)），自动完成不写它。本包对
        # 行 6/11/12 用 util.force_done 直接构造完成态（绕开引擎的里程碑写入路径，
        # 见 _step 注释），全程不调 milestone confirm，该字段在本包没有写入机会。
        return "确认原话只由里程碑确认写入；本包用 force_done 构造行 6/11/12 完成态，不经该写入路径"
    return ""


def _leaves(node, path=()):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _leaves(value, path + (key,))
    elif isinstance(node, list) and node and isinstance(node[0], dict):
        for index, item in enumerate(node):
            yield from _leaves(item, path + (index,))
    else:
        yield path, node


def _at(state, path):
    node = state
    for key in path:
        node = node[key]
    return node


class KindAndConfirmTests(RepoTest):
    def test_f01_decision_commit_requires_kind(self):
        # 两步链路上：入库必须写明类别；没写类别就不落库（手工队列已删除）。
        name = "kinddemo"
        init_sys(self.root, name)
        with self.assertRaises(EngineError) as ctx:
            commit_decision(self.root, name, content="位宽取 8", stop=1)
        self.assertIn("类别", str(ctx.exception))
        state = load_state(self.root, name)
        self.assertEqual(state["decisions"]["0"], [], "没写类别的入库不能落库")
        self.assertNotIn("queue", state, "手工队列已删除")
        self.assertNotIn("dequeued", state, "手工队列已删除")
        self.assertNotIn("T", state["seq"], "T 序号已删除")
        # 正向：写明记录类与停点，不要任何令牌/确认就能入库。
        did = commit_decision(self.root, name, content="位宽取 8", kind="记录", stop=1)
        self.assertEqual(did, "D0-001")

    def test_f02_override_and_withdraw_respect_kind(self):
        # 方向/数值裁决的入库、改写、撤回是红线动作——点选即入库，不要 --confirm 与令牌；
        # 没有点选来源不许入库；类别不许在方向/数值与记录之间互改。
        name = "ovrdemo"
        init_sys(self.root, name)
        with self.assertRaises(EngineError) as ctx:
            commit_decision(self.root, name, content="位宽取 8", kind="数值", stop=1)
        self.assertIn("点选来源", str(ctx.exception))
        did = decide(self.root, name, "位宽取 8", "数值", 1,
                     options="位宽取 8|位宽取 16", pick="位宽取 8")
        with self.assertRaises(EngineError):
            override_decision(self.root, name, did, "位宽取 16", kind="记录")
        override_decision(self.root, name, did, "位宽取 16")
        with self.assertRaises(EngineError):
            withdraw_decision(self.root, name, "D0-999")
        withdraw_decision(self.root, name, did)

    def test_f03_module_self_attestation_rejected(self):
        # 模块清单由文件推导、通过态由证据推导，set_module 只接受"退回"。
        # 旧用例把"已生成/骨架/用例已装配"当合法登记值，现在它们与通过态一样必须被拒——
        # 断言只增不减（多覆盖三个旧登记值，并校验退回真的写覆盖、行退回进行中）。
        name = "moddemo"
        init_sys(self.root, name)
        for row, status in (("7", "审查通过"), ("7", "lint 通过"),
                            ("8", "连接通过"), ("9", "tc_check 通过"),
                            ("7", "已生成"), ("8", "已生成"),
                            ("9", "骨架"), ("9", "用例已装配")):
            with self.assertRaises(EngineError) as ctx:
                set_module(self.root, name, row, "alu", status)
            self.assertIn("只接受 退回", str(ctx.exception))
        set_module(self.root, name, "7", "alu", "退回")
        state = load_state(self.root, name)
        self.assertEqual(
            {item["name"]: item["state"] for item in state["modules"]["7"]},
            {"alu": "退回"})
        self.assertEqual(stop_row(state, 7)["state"], RUNNING)

    def test_f04_redline_commit_needs_no_token(self):
        """收到新事实上：放行令牌已删除，方向/数值类入库只认"点选来源"。
        工作区令牌、家目录令牌、环境变量都不再参与；缺的只是点选来源这一条。"""
        name = "tokdemo"
        init_sys(self.root, name)
        rogue = os.path.join(self.root, "release")
        with open(rogue, "w", encoding="utf-8") as fh:
            fh.write("ok\n")
        os.chmod(rogue, 0o700)
        os.environ["ADF_RELEASE_TOKEN"] = rogue
        try:
            with self.assertRaises(EngineError) as ctx:
                commit_decision(self.root, name, content="位宽取 8", kind="数值", stop=1)
            self.assertIn("点选来源", str(ctx.exception))
            self.assertNotIn("令牌", str(ctx.exception), "被拒的理由不是缺令牌")
            did = decide(self.root, name, "位宽取 8", "数值", 1,
                         options="位宽取 8|位宽取 16", pick="位宽取 8")
            self.assertEqual(did, "D0-001", "不需要任何令牌就能入库")
        finally:
            os.environ.pop("ADF_RELEASE_TOKEN", None)

    def test_f05_stop6_formula_error_keeps_rule_id(self):
        # 自动完成判据：tick 相位③跑闸门，规则号原样带出；行 6 是里程碑归属，判据不齐不送审。
        name = "f05formula"
        init_sys(self.root, name)
        _plant(self.root, name)
        _walk(self.root, name, 5)
        tick_report(self.root, name)          # 自动启动行 6（判据不齐 → 停在"进行中"）
        rel = "spec_doc/glue_spec.md"
        path = os.path.join(sys_dir(self.root, name), rel)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("\n算式 <8,2,t> * <8,2,t> → <16,4,t>\n")
        check = auto_complete_check(self.root, name, load_state(self.root, name), 6)
        self.assertFalse(check["ok"])
        self.assertTrue(any("[fx]" in reason for reason in check["reasons"]), check["reasons"])
        self.assertEqual(stop_row(load_state(self.root, name), 6)["state"], RUNNING)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        # 式子改回来后闸门不再报 fx（行 6 仍未送审：缺独立审查记录）。
        check = auto_complete_check(self.root, name, load_state(self.root, name), 6)
        self.assertFalse(any("[fx]" in reason for reason in check["reasons"]), check["reasons"])

    def test_f15_signoff_does_not_stale_runs(self):
        name = "freshdemo"
        init_sys(self.root, name)
        _plant(self.root, name)
        _walk(self.root, name, 6)
        _lint(self.root, name, ["alu"])
        # 行 7/8/9 不再手工登记：清单与状态由文件/证据推导。
        _step(self.root, name, 7, module="alu")
        _step(self.root, name, 8)
        _step(self.root, name, 9)
        _sim(self.root, name, ["1"])
        _coverage(self.root, name)
        _step(self.root, name, 10)
        _midend(self.root, name)
        state = load_state(self.root, name)
        before = run_gates(self.root, name, 11, state)
        _step(self.root, name, 11)
        state = load_state(self.root, name)
        render_signoff(self.root, name, state, "放行")
        after = run_gates(self.root, name, 12, load_state(self.root, name))
        self.assertFalse(any("输入已变更" in item["detail"] for item in before), before)
        self.assertFalse(any("输入已变更" in item["detail"] for item in after), after)
        text = status_report(self.root, name)
        self.assertNotIn("产物在完成后有改动", text)

    def test_review_record_needs_lint_first(self):
        # 此后审查记录还要带 report/<文件>.md：用 review() 备好报告，好让这条
        # 断言仍旧打在"没有针对当前文件的通过 lint 记录"这一真原因上。
        name = "revnolint"
        init_sys(self.root, name)
        with self.assertRaises(EngineError) as ctx:
            review(self.root, name, 7, module="alu")
        self.assertIn("lint", str(ctx.exception))

    def test_f05_completion_reruns_gates(self):
        # 自动完成判据：判据不齐不写指纹；tick 相位①在产物改动后退回已完成停点。
        name = "f05demo"
        init_sys(self.root, name)
        _plant(self.root, name)
        review(self.root, name, 1)
        tick_report(self.root, name)             # 判据齐备 → 完成
        self.assertTrue(stop_row(load_state(self.root, name), 1)["fingerprint"])
        rel = "info_input/%s_info_overview.md" % name
        path = os.path.join(sys_dir(self.root, name), rel)
        text = open(path, encoding="utf-8").read()
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text.replace("## 5. 红线五问", "## 6. 别的"))
        note = tick_report(self.root, name)      # 指纹失效退回 + 判据重跑报闸门规则号
        self.assertIn("S1", note)
        state = load_state(self.root, name)
        self.assertEqual(stop_row(state, 1)["state"], RUNNING)
        self.assertEqual(stop_row(state, 1).get("fingerprint"), "")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        tick_report(self.root, name)
        self.assertTrue(stop_row(load_state(self.root, name), 1)["fingerprint"])


class CascadeAndStatusTests(RepoTest):
    def test_f12_decision_cascade_uses_stop_not_stage(self):
        # 级联起点读该裁决自己的 stop 字段（不再靠阶段号反查）。
        name = "cascdemo"
        init_sys(self.root, name)
        _plant(self.root, name)
        _walk(self.root, name, 6)
        did = decide(self.root, name, "编码口径", "方向", 6)
        state = load_state(self.root, name)
        row = [item for item in state["decisions"]["3"] if item["id"] == did][0]
        self.assertEqual(row["stop"], 6, "裁决记下自己的停点")
        for sid in range(1, 7):
            self.assertEqual(stop_row(state, sid)["state"], DONE,
                             "行 %d 被 stop=6 的裁决动了（阶段 3 级联不该打到行 4/5/6）" % sid)
        decide(self.root, name, "信息口径", "方向", 1)
        state = load_state(self.root, name)
        self.assertEqual(stop_row(state, 1)["state"], DONE, "stop=1 的裁决不打回它自己的停点")
        self.assertEqual(stop_row(state, 2)["state"], RUNNING)

    def test_f13_status_next_command_and_position(self):
        name = "statdemo"
        init_sys(self.root, name)
        _plant(self.root, name)
        text = status_report(self.root, name)
        # 启动/送审/完成都归 tick，status 的下一条命令就是 tick。
        self.assertIn("framework.py tick statdemo", text)
        tick_report(self.root, name)             # 自动启动行 1
        text = status_report(self.root, name)
        self.assertIn("行 1，进行中", text)
        review(self.root, name, 1)
        tick_report(self.root, name)             # 判据齐备 → 完成行 1
        for sid in (2, 3, 4):
            _step(self.root, name, sid)
        text = status_report(self.root, name)
        self.assertIn("下一停点：结构生成（行 5", text)
        self.assertNotIn("--enter-structure", text, "--enter-structure 已删除")
        self.assertNotIn("--confirm", text.split("下一条命令：", 1)[1].split("\n", 1)[0],
                         "自动完成不需要确认语句")
        decide(self.root, name, "信息口径改", "方向", 1)
        text = status_report(self.root, name)
        where = text.split("所处：", 1)[1].split("\n", 1)[0]
        self.assertIn("停点 2", where)

    def test_f14_problem_stop_kind_and_retreat(self):
        name = "probdemo"
        init_sys(self.root, name)
        _plant(self.root, name)
        with self.assertRaises(EngineError):
            add_problem(self.root, name, "阻断", 0, "缺时钟", "审查")
        with self.assertRaises(EngineError):
            add_problem(self.root, name, "严重", 3, "缺时钟", "审查")
        _walk(self.root, name, 2)
        add_problem(self.root, name, "阻断", 2, "缺时序约定", "审查")
        advance(self.root, name, 2, RUNNING)     # 主动重做：退回进行中
        text = tick_report(self.root, name)
        # 未关闭阻断挡完成：tick 不置完成，清单点名。
        self.assertIn("存在未关闭阻断", text)
        self.assertEqual(stop_row(load_state(self.root, name), 2)["state"], RUNNING)
        close = load_state(self.root, name)["problems"][0]["id"]
        from framework.engine import close_problem
        # 关闭靠证据，不要终端；证据取登记之后的一次运行记录。
        rid = record_run(self.root, name, {
            "capability": "sim", "status": "pass", "summary": "RESULT : PASS",
            "profile_id": "example",
            "scope": {"scenario": "sys", "module": "", "tc": "", "seeds": ["1"]},
            "checks": {"result_pass": 1, "result_fail": 0, "full_regression": 1},
        })
        close_problem(self.root, name, close, evidence=rid)
        tick_report(self.root, name)             # 阻断清掉后判据齐备 → 完成
        self.assertEqual(stop_row(load_state(self.root, name), 2)["state"], DONE)
        env = os.environ.copy()
        env["ADF_ROOT"] = self.root
        env["HOME"] = self.home
        proc = subprocess.run(
            [sys.executable, os.path.join(checkout_root(), "script", "framework.py"),
             "problem", name, "add", "--kind", "阻断", "--text", "缺时钟"],
            env=env, capture_output=True, text=True,
        )
        self.assertNotEqual(proc.returncode, 0)

    def test_f15_signoff_outside_products(self):
        name = "signoffdemo"
        init_sys(self.root, name)
        _plant(self.root, name)
        _walk(self.root, name, 6)
        before = inputs_digest(self.root, name)
        state = load_state(self.root, name)
        render_signoff(self.root, name, state, "放行")
        self.assertTrue(os.path.isfile(
            os.path.join(sys_dir(self.root, name), "signoff", "%s_signoff.md" % name)))
        self.assertFalse(os.path.isfile(
            os.path.join(sys_dir(self.root, name), "spec_doc", "%s_signoff.md" % name)))
        self.assertEqual(inputs_digest(self.root, name), before)
        text = status_report(self.root, name)
        self.assertNotIn("产物在完成后有改动", text)

    def test_f21_summaries_capped_at_twenty(self):
        # 代判删除，原用例的代判部分随之删除；小结保留。
        name = "sumdemo"
        init_sys(self.root, name)
        for index in range(6):
            add_summary(self.root, name, "第 %d 条小结" % index)
        text = status_report(self.root, name)
        self.assertIn("第 5 条小结", text)
        self.assertNotIn("第 0 条小结", text)
        decide(self.root, name, "位宽取 8", "数值", 3)
        self.assertEqual(load_state(self.root, name)["decisions"]["2"][0]["kind"], "数值")

    def test_f13_cascade_remarks_in_status(self):
        name = "remarkdemo"
        init_sys(self.root, name)
        _plant(self.root, name)
        _walk(self.root, name, 3)
        decide(self.root, name, "上游口径改", "方向", 2)
        text = status_report(self.root, name)
        self.assertIn("上游 D1-001 变更待重推", text)


class DeadFieldTests(RepoTest):
    def test_no_dead_field_in_blank_state(self):
        # schema 迁移报告：旧形态的 position.delegate、loop_side、loop_closed_at、
        # enter_structure 已从 blank() 删除；停点行
        # 无 human/completed_once；confirm_quote 只由里程碑确认写入（见 _exempt）。
        name = "sample"
        init_sys(self.root, name)
        _plant(self.root, name)
        template = blank(name)
        self.assertNotIn("loop_side", template)
        self.assertNotIn("loop_closed_at", template)
        self.assertNotIn("enter_structure", template)
        self.assertNotIn("delegate", template["position"])
        # 手工队列与 T 序号已从状态里删除，不留兼容壳。
        self.assertNotIn("queue", template)
        self.assertNotIn("dequeued", template)
        self.assertNotIn("T", template["seq"])
        # golden 登记段（golden[] 与 seq.G）也要有写入路径：本包只跑登记助手，
        # `golden register` CLI 与行 10 新鲜度闸门留给后续棒。
        golden_state = load_state(self.root, name)
        golden_add(golden_state, "testbench/alu/data/g.txt", "script/gen.py",
                   ["spec_doc/alu_spec.md"], "d1")
        save(self.root, name, golden_state)
        _walk(self.root, name, 5)
        # 行 6/11/12 由里程碑覆盖完成：先用 tick 送到送审态（写 pending_digest），
        # 再用 force_done 构造里程碑确认之后的完成态。
        review(self.root, name, 6)
        tick_report(self.root, name)
        force_done(self.root, name, 6)
        _lint(self.root, name, ["alu"])
        # 行 7/8/9 不再手工登记：清单与状态由文件/证据推导。
        _step(self.root, name, 7, module="alu")
        _step(self.root, name, 8)
        _step(self.root, name, 9)
        _sim(self.root, name, ["1", "2"])
        _coverage(self.root, name)
        _step(self.root, name, 10)
        _midend(self.root, name)
        tick_report(self.root, name)          # 行 11 送审
        force_done(self.root, name, 11)
        tick_report(self.root, name)          # 行 12 送审（signoff 闸门渲染签核文件）
        force_done(self.root, name, 12)
        for step in ("0", "1", "2", "3", "5"):
            # step 0 用方向类：级联写 remark 的路径须有真实来源（记录类不级联）
            kind = "方向" if step == "0" else "记录"
            did = decide(self.root, name, "阶段 %s 口径" % step, kind, _STOP_OF_STAGE[step])
            if step == "0":
                add_waiver(self.root, name, "S9", "空", did)
        set_handoff(self.root, name, "恢复入口说明。")
        add_summary(self.root, name, "本轮小结。")
        add_problem(self.root, name, "待裁决", 1, "仅供参考", "复核")
        # 事项字段也要有写入路径；开在送审之后，不挡该行的送审/完成。
        item_open(self.root, name, "调试", "调试期事项：字段有写入路径", side="rtl")
        final = load_state(self.root, name)
        self.assertNotIn("queue", final, "手工队列已删除")
        self.assertNotIn("dequeued", final, "手工队列已删除")
        self.assertNotIn("T", final["seq"], "T 序号已删除")
        missing = []
        done_states = ("完成（审核通过）",)
        # 退回进行中的行本来就没有确认痕迹（引擎退回时清掉），
        # 但完成态的行必须留着，这样才还能证明这些字段有写入路径。
        confirm_fields = ("done_at", "confirmed_at", "fingerprint")
        for path, value in _leaves(template):
            if _exempt(path):
                continue
            if (len(path) == 3 and path[0] == "stops" and path[2] in confirm_fields
                    and final["stops"][path[1]]["state"] not in done_states):
                continue
            got = _at(final, path)
            if isinstance(value, list):
                if got == value:
                    missing.append(".".join(str(item) for item in path))
            elif got == value:
                missing.append(".".join(str(item) for item in path))
        self.assertEqual(sorted(missing), [], "以下字段没有任何写入路径")


if __name__ == "__main__":
    unittest.main()
