# 作者：vick 邮箱：ykun@yk9811.com

"""按依赖级联 + 复核恢复，行 7 模块证据。

- 级联：停点退回进行中时，只把依赖闭包（depends_on 传递下游）内、已启动
  （进行中/已送审/完成）的停点退回进行中；未开始的不动。
- 复核恢复：被级联停点若自身产物指纹未变（与退回前记录的 cascaded_fingerprint
  一致）、闸门重跑通过、审查记录仍对得上当前产物，tick 自动恢复为完成并记
  "复核恢复"事件，不需要开发者重新确认；产物改过或判据不齐的保持进行中，
  由 tick 清单说明原因。里程碑覆盖完成的停点（行 6/11/12）不自动恢复。
- 复核恢复的节拍：级联（由 tick 指纹失效相位触发时）之后的第一次 tick
  只退回/级联、不恢复被新级联的下游，第二次 tick 才恢复指纹未变者——
  同一次 tick 里新级联出来的行不在本次恢复。
- 推进口径：夹具一律"补判据（lint/审查记录）→ 跑 tick"，由 tick 自动
  启动、送审与完成；advance 只用于从完成退回（主动重做）触发级联。
- 行 7 由模块证据判定：停点指纹是逐模块摘要的聚合；某个模块改动只让
  该模块的 lint/审查标记失效（module_stale_note），行的"就绪"= 所有模块都有
  当前证据。

端到端：行 10 调试中修改一个模块（L0）→ 只有该模块重新 lint 与审查，
行 8、9 自动复核恢复，开发者零打断（全程不装 fake_terminal）。
"""

import json
import os
import unittest

from framework.engine import (
    _dependent_closure, _product_digest, advance, item_end, item_open,
    module_stale_note, record_run, stale_module_count, stale_stops,
    status_report, tick_report,
)
from framework.flow import DONE, NOT_STARTED, PENDING, RUNNING, load
from framework.state import init_sys, load_state, save, stop_row, sys_dir
from framework.tests.util import (
    RepoTest, confirm_milestone, force_done, plant_sample, review,
)


def _lint(root, name, modules):
    return record_run(root, name, {
        "capability": "lint", "status": "pass", "summary": "lint pass",
        "profile_id": "example", "scope": {"modules": list(modules)},
        "checks": {"errors": 0},
    })


def _sim(root, name, seeds):
    return record_run(root, name, {
        "capability": "sim", "status": "pass", "summary": "RESULT : PASS",
        "profile_id": "example",
        "scope": {"scenario": "sys", "module": "", "tc": "", "seeds": list(seeds)},
        "checks": {"result_pass": 1, "result_fail": 0, "full_regression": 1},
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
        "checks": {"errors": 0, "latches": 0, "setup_wns": 0.1, "setup_violations": 0,
                   "area": 1.0},
    })
    record_run(root, name, {
        "capability": "sta", "status": "pass", "summary": "sta pass",
        "profile_id": "example",
        "checks": {"corners": [{"setup_wns": 0.1, "hold_wns": 0.1,
                                "setup_violations": 0, "hold_violations": 0}]},
    })


def _step(root, name, sid, module="alu"):
    """把一个停点推到它该到的位置——补审查记录后跑 `tick`；行 6/11/12 用
    force_done 构造里程碑覆盖完成的完成态。停点 4 前确认 M1。"""
    if sid == 4:
        confirm_milestone(root, name, "M1")
    if sid in (6, 11, 12):
        force_done(root, name, sid)
        return
    if sid == 8:
        review(root, name, sid, module=module)
    elif sid == 9:
        # DEV-07：行 9 要一条 tb_review（与 tc 闸门并列）。
        review(root, name, sid)
    elif sid <= 6:
        review(root, name, sid)
    tick_report(root, name)


def _finish_rtl_row(root, name, modules):
    """行 7：逐模块 lint → 逐模块审查 → tick 自动完成（模块清单由 rtl/ 文件推导）。"""
    confirm_milestone(root, name, "M2")
    _lint(root, name, modules)
    for mod in modules:
        review(root, name, 7, module=mod)
    tick_report(root, name)


def _walk(root, name, upto, modules=("alu",)):
    """按自动完成口径走到 upto（含）。行 7 由 _finish_rtl_row 按模块证据完成。"""
    for sid in range(1, min(upto, 6) + 1):
        _step(root, name, sid)
    if upto >= 7:
        _finish_rtl_row(root, name, list(modules))
    for sid in range(8, upto + 1):
        if sid == 9:
            _nest_tb(root, name)
        if sid == 10:
            _sim(root, name, ["1"])
            _coverage(root, name)
        if sid == 11:
            _midend(root, name)
        _step(root, name, sid)


def _nest_tb(root, name):
    """行 9 的平台清单由 testbench/ 布局推导（不再手工登记）：把样例的
    testbench/tc 挪成 testbench/tb/tc（平台名 tb），"tc_check 通过"由文件与
    用例核对推导。"""
    base = sys_dir(root, name)
    os.makedirs(os.path.join(base, "testbench", "tb"), exist_ok=True)
    os.rename(os.path.join(base, "testbench", "tc"),
              os.path.join(base, "testbench", "tb", "tc"))


def _add_module(root, name, mod):
    """按 alu 的规格书与 RTL 复制出第二个 leaf 模块（"只标该模块"需要 >1 个模块）。"""
    base = sys_dir(root, name)
    for src, head in (("rtl", "alu.sv"), ("spec_doc", "alu_spec.md")):
        with open(os.path.join(base, src, head), encoding="utf-8") as fh:
            text = fh.read().replace("alu", mod)
        with open(os.path.join(base, src, mod + head[3:]), "w", encoding="utf-8") as fh:
            fh.write(text)


def _append(root, name, rel, text):
    with open(os.path.join(sys_dir(root, name), rel), "a", encoding="utf-8") as fh:
        fh.write(text)


def _events(root, name):
    path = os.path.join(root, name, "events.jsonl")
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _cascaded(state):
    return [int(row["id"]) for row in state["stops"] if row.get("cascaded_at")]


class CascadeRecoverTests(RepoTest):
    def test_dependent_closure_follows_depends_on(self):
        # 闭包口径直接对 depends_on 表：退回 9 只覆盖 10、12（11 只依赖 7、8）；
        # 退回 7 覆盖 8..12；退回 3 覆盖 4..12；行 8 依赖含 4 与 7，故被 3 的闭包覆盖。
        self.assertEqual(_dependent_closure(9), {10, 12})
        self.assertEqual(_dependent_closure(7), {8, 9, 10, 11, 12})
        self.assertEqual(_dependent_closure(8), {9, 10, 11, 12})
        self.assertEqual(_dependent_closure(12), set())
        self.assertEqual(_dependent_closure(3), set(range(4, 13)))

    def test_retract_7_cascades_started_downstream_only(self):
        name = "cas7"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        _walk(self.root, name, 12)
        fps = {sid: stop_row(load_state(self.root, name), sid)["fingerprint"]
               for sid in range(8, 13)}
        advance(self.root, name, 7, RUNNING)
        state = load_state(self.root, name)
        # 依赖闭包内已启动的 8..12 全部级联退回；确认痕迹清掉、退回前指纹另存。
        self.assertEqual(_cascaded(state), [8, 9, 10, 11, 12])
        for sid in range(8, 13):
            row = stop_row(state, sid)
            self.assertEqual(row["state"], RUNNING)
            self.assertEqual(row["cascaded_from"], 7)
            self.assertEqual(row["cascaded_fingerprint"], fps[sid])
            self.assertEqual(row["done_at"], "", "行 %d 的确认痕迹没清掉" % sid)
            self.assertEqual(row["fingerprint"], "")
            self.assertIn("上游 停点 7 变更待重推", row["remark"])
        events = [e for e in _events(self.root, name) if e["action"] == "级联退回"]
        self.assertEqual(sorted(int(e["object"].split()[1]) for e in events),
                         list(range(8, 13)))
        for e in events:
            self.assertIn("由 7", e["evidence"])
            self.assertIn("依赖闭包", e["evidence"])

    def test_retract_9_cascades_only_10_and_12(self):
        name = "cas9"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        _walk(self.root, name, 12)
        advance(self.root, name, 9, RUNNING)
        state = load_state(self.root, name)
        # 行 11 只依赖 7、8，不在 9 的下游：编号更大也不级联（旧口径会误退回）。
        self.assertEqual(_cascaded(state), [10, 12])
        self.assertEqual(stop_row(state, 11)["state"], DONE)
        self.assertTrue(stop_row(state, 11)["fingerprint"])
        self.assertEqual(stop_row(state, 8)["state"], DONE)

    def test_retract_3_cascades_4_to_12_skipping_not_started(self):
        name = "cas3"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        _walk(self.root, name, 12)
        state = load_state(self.root, name)
        stop_row(state, 5)["state"] = NOT_STARTED
        save(self.root, name, state)
        advance(self.root, name, 3, RUNNING)
        state = load_state(self.root, name)
        # 行 8 的依赖含 4 与 7，被 3 的闭包覆盖；未开始的行 5 不动。
        self.assertEqual(_cascaded(state), [4, 6, 7, 8, 9, 10, 11, 12])
        row5 = stop_row(state, 5)
        self.assertEqual(row5["state"], NOT_STARTED)
        self.assertEqual(row5.get("cascaded_at", ""), "")
        self.assertEqual(row5.get("cascaded_fingerprint", ""), "")

    def test_row10_module_fix_only_relints_module_and_recovers_8_9(self):
        # 行 10 调试中修改一个模块（L0）→ 只有该模块重新 lint 与审查，
        # 行 8、9 自动复核恢复，开发者零打断（全程没有终端交互：本用例不装 fake_terminal）。
        name = "l0fix"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        _add_module(self.root, name, "mod2")
        _walk(self.root, name, 10, modules=("alu", "mod2"))
        fps = {sid: stop_row(load_state(self.root, name), sid)["fingerprint"]
               for sid in (7, 8, 9, 10)}
        # 行 10 调试中改一个模块（L0）：开调试事项 → 改 rtl/alu.sv → L0 收尾。
        mid = item_open(self.root, name, "调试", "行 10 调试：alu 一处 L0 级写法要改",
                        side="rtl")
        _append(self.root, name, os.path.join("rtl", "alu.sv"),
                "// L0 修正：位拼接写法调整。\n")
        item_end(self.root, name, mid, "L0")
        # 行 7 指纹随被改模块的摘要变化（提示退回），但模块级失效只标 alu，
        # 不让整行的模块证据失效。
        state = load_state(self.root, name)
        self.assertEqual(stale_stops(self.root, name, state), [7])
        self.assertEqual(stale_module_count(state, sys_dir(self.root, name)), 1)
        notes = {m["name"]: module_stale_note(state, sys_dir(self.root, name), "7", m)
                 for m in state["modules"]["7"]}
        self.assertEqual({k for k, v in notes.items() if v}, {"alu"})
        # 触发退回/级联：跑 tick，指纹失效相位把行 7 退回进行中并按依赖闭包
        # 级联已启动的 8、9、10、11（行 11 的依赖 7、8 在 walk 到 10 时已定稿，
        # tick 会把它一并自动启动，所以它也在闭包里——不是断言放宽，而是夹具在
        # tick 驱动下确实多启动了一行）。
        text = tick_report(self.root, name)
        state = load_state(self.root, name)
        self.assertEqual(_cascaded(state), [8, 9, 10, 11])
        # 复核恢复的节拍：同一次 tick 里新级联出来的下游不在本次恢复。
        self.assertIn("指纹失效退回停点 7", text)
        self.assertNotIn("复核恢复停点", text)
        for sid in (8, 9):
            row = stop_row(state, sid)
            self.assertEqual(row["cascaded_fingerprint"], fps[sid])
            self.assertEqual(_product_digest(self.root, name, load()["by_id"][sid]),
                             fps[sid], "行 %d 的产物指纹未变" % sid)
        # 第二次 tick：行 8、9 产物未变、闸门重跑通过、审查记录对版 → 自动复核恢复；
        # 行 10 的仿真输入已变（rtl 改了），保持进行中并说明原因。
        text = tick_report(self.root, name)
        self.assertIn("复核恢复停点 8、9", text)
        self.assertIn("复核判据未满足", text)
        state = load_state(self.root, name)
        for sid in (8, 9):
            row = stop_row(state, sid)
            self.assertEqual(row["state"], DONE)
            self.assertEqual(row["fingerprint"], fps[sid])
            self.assertEqual(row.get("cascaded_at", ""), "")
        self.assertEqual(stop_row(state, 10)["state"], RUNNING)
        events = [e for e in _events(self.root, name) if e["action"] == "复核恢复"]
        self.assertEqual(sorted(e["object"] for e in events), ["停点 8", "停点 9"])
        for e in events:
            self.assertIn("指纹未变", e["evidence"])
            self.assertIn("闸门重跑通过", e["evidence"])
            self.assertIn("对得上当前产物", e["evidence"])
        # 只有被改的模块重新 lint 与审查，行 7 即可由 tick 自动完成——不要求任何行级重审。
        _lint(self.root, name, ["alu"])
        review(self.root, name, 7, module="alu")
        text = tick_report(self.root, name)
        self.assertIn("自动完成停点 7", text)
        state = load_state(self.root, name)
        self.assertEqual(stop_row(state, 7)["state"], DONE)
        self.assertEqual(stop_row(state, 8)["state"], DONE, "行 8 不应被打扰")
        self.assertEqual(stop_row(state, 9)["state"], DONE, "行 9 不应被打扰")

    def test_recover_skips_stops_whose_product_changed(self):
        # 复核恢复只对指纹未变的停点生效：产物改过的停点不自动恢复。
        # 节拍：行 1、2 的产物都在完成后被改过，tick 指纹失效相位退回最早的
        # 行 1 并级联 2、3；第一次 tick 不恢复新级联的下游，第二次 tick 恢复
        # 产物未变的行 3，产物改过的行 2 保持进行中并说明原因。
        name = "fpchg"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        _walk(self.root, name, 3)
        _append(self.root, name, os.path.join("flow_doc", "%s_flow.md" % name),
                "\n事后补记一行。\n")
        _append(self.root, name, os.path.join("info_input", "%s_info_overview.md" % name),
                "\n事后补记一行。\n")
        text = tick_report(self.root, name)
        state = load_state(self.root, name)
        self.assertEqual(_cascaded(state), [2, 3])
        self.assertIn("指纹失效退回停点 1", text)
        self.assertNotIn("复核恢复停点", text)
        self.assertEqual(stop_row(state, 1)["state"], RUNNING, "行 1 指纹失效退回")
        text = tick_report(self.root, name)
        state = load_state(self.root, name)
        self.assertEqual(stop_row(state, 3)["state"], DONE, "产物未变的行 3 复核恢复")
        self.assertEqual(stop_row(state, 2)["state"], RUNNING, "产物改过的行 2 不恢复")
        self.assertEqual(stop_row(state, 1)["state"], RUNNING, "产物改过的行 1 不恢复")
        self.assertIn("产物已改动", text)
        events = [e for e in _events(self.root, name) if e["action"] == "复核恢复"]
        self.assertEqual([e["object"] for e in events], ["停点 3"])

    def test_milestone_stops_are_not_auto_recovered(self):
        # 里程碑覆盖完成的停点（行 6/11/12）被级联退回后不走复核恢复：tick 不把
        # 它恢复成完成，判据齐备后置送审态（待里程碑），按原规则 milestone confirm。
        name = "msrec"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        _walk(self.root, name, 5)
        force_done(self.root, name, 6)
        advance(self.root, name, 5, RUNNING)
        state = load_state(self.root, name)
        # 闭包内已启动的只有行 6（7..12 未开始，不级联）。
        self.assertEqual(_cascaded(state), [6])
        self.assertEqual(stop_row(state, 6).get("cascaded_from"), 5)
        text = tick_report(self.root, name)
        # tick 不把它恢复成完成，只在清单里说明它按原规则走里程碑。
        self.assertNotIn("复核恢复停点", text)
        self.assertEqual([e for e in _events(self.root, name)
                          if e["action"] == "复核恢复"], [])
        self.assertIn("不走复核恢复", text)
        self.assertEqual(stop_row(load_state(self.root, name), 6)["state"], RUNNING)
        # 判据（审查记录）补齐后再跑 tick：行 6 仍不被恢复成完成，而是按原规则
        # 被置为送审态（待里程碑），由 milestone confirm 收口。
        review(self.root, name, 6)
        text = tick_report(self.root, name)
        self.assertNotIn("复核恢复停点", text)
        self.assertEqual([e for e in _events(self.root, name)
                          if e["action"] == "复核恢复"], [])
        state = load_state(self.root, name)
        self.assertEqual(stop_row(state, 6)["state"], PENDING,
                         "行 6 不走复核恢复，判据齐备后由 tick 置送审态待里程碑")
        self.assertIn("待里程碑（M2）", status_report(self.root, name))
        confirm_milestone(self.root, name, "M2")
        self.assertEqual(stop_row(load_state(self.root, name), 6)["state"], DONE)


if __name__ == "__main__":
    unittest.main()
