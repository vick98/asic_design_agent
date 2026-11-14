# 作者：vick 邮箱：ykun@yk9811.com

"""新交互模型的横向用例。

覆盖新增的场景：审查记录的作者/审查者/阻断发现校验与指纹绑定（`--report` 必填）、
自动完成判据（tick 的完成相位与 auto_complete_check 同源）、删掉的 advance 兼容
参数（`--confirm`/`--enter-structure`/`--loop-side`）必须 argparse 报错、在途事项挡
行 7–12、迁移把未闭合 loop_side 转成事项、记录类提示、关闭问题的证据口径。
"""

import contextlib
import importlib.util
import io
import os
import unittest

from framework.engine import (
    EngineError, add_problem, advance, auto_complete_check, close_problem, commit_decision,
    item_end, item_open, record_run, review_record, tick_report,
)
from framework.flow import DONE, NOT_STARTED, RUNNING
from framework.state import init_sys, load_state, save, stop_row
from framework.tests.util import RepoTest, checkout_root, cli, decide, review, write_report


def _script():
    return os.path.join(checkout_root(), "script", "framework.py")


def _load_cli():
    spec = importlib.util.spec_from_file_location(
        "cli_for_interaction", _script())
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    return cli


def _doc(root, name, rel, chapters):
    path = os.path.join(root, name, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = ["# t", "", "简介。", ""]
    for index, chapter in enumerate(chapters, 2):
        lines.extend(["## %d. %s" % (index, chapter), "", "正文。", ""])
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


class ReviewRecordModelTests(RepoTest):
    """审查记录自动登记，字段与指纹绑定。"""

    def _running(self, name, sid=1, chapters=None):
        """tick 相位②自动把未开始的行 1 置进行中（不再用 advance 启动）。"""
        init_sys(self.root, name)
        _doc(self.root, name, "info_input/%s_info_overview.md" % name,
             chapters or ["输入文档", "可信度", "冲突", "红线五问"])
        tick_report(self.root, name)

    def test_author_must_differ_from_reviewer(self):
        name = "irsame"
        self._running(name)
        # 报告先备好：动作表的审查记录前提在报告解析之后执行（发现数/阻断数以报告表为准）。
        rel = write_report(self.root, name, 1)
        with self.assertRaises(EngineError) as ctx:
            review_record(self.root, name, 1, author="agent-1", reviewer="agent-1",
                          report=rel)
        self.assertIn("必须不同", str(ctx.exception))
        with self.assertRaises(EngineError) as ctx:
            review_record(self.root, name, 1, author="", reviewer="agent-1", report=rel)
        self.assertIn("作者", str(ctx.exception))
        self.assertEqual(stop_row(load_state(self.root, name), 1).get("reviews"), None)

    def test_blocking_findings_must_be_zero(self):
        name = "irblock"
        self._running(name)
        unresolved = ("# 行 1 独立审查报告\n\n"
                      "| 发现编号 | 级别 | 位置 | 建议 | 处置 |\n"
                      "|---|---|---|---|---|\n"
                      "| F1 | 阻断 | 第 5 章 | 缺时钟域 | 待改 |\n")
        rel = write_report(self.root, name, 1, report=unresolved)
        with self.assertRaises(EngineError) as ctx:
            review_record(self.root, name, 1, author="a", reviewer="b", report=rel)
        self.assertIn("阻断", str(ctx.exception))
        self.assertFalse(stop_row(load_state(self.root, name), 1).get("reviews"))
        # 全部处置：发现数按报告表数据行计（3 行）。
        resolved = ("# 行 1 独立审查报告\n\n"
                    "| 发现编号 | 级别 | 位置 | 建议 | 处置 |\n"
                    "|---|---|---|---|---|\n"
                    "| F1 | 阻断 | 第 5 章 | 缺时钟域 | 已改（补同步器） |\n"
                    "| F2 | 建议 | 第 3 章 | 补一句口径 | 已改 |\n"
                    "| F3 | 建议 | 第 4 章 | 补图 | 已改 |\n")
        review(self.root, name, 1, report=resolved)
        rev = stop_row(load_state(self.root, name), 1)["reviews"][0]
        self.assertEqual(rev["kind"], "spec_review")
        self.assertEqual(rev["findings"], 3)
        self.assertTrue(rev["report"].startswith("report/"), rev)
        self.assertTrue(rev["report_digest"])

    def test_review_binds_current_product_digest(self):
        # 指纹不符不算数：登记审查后产物又改了，自动完成判据必须拦下。
        name = "irfp"
        self._running(name)
        review(self.root, name, 1)
        check = auto_complete_check(self.root, name, load_state(self.root, name), 1)
        self.assertTrue(check["ok"], check)
        path = os.path.join(self.root, name, "info_input", "%s_info_overview.md" % name)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("\n补一句。\n")
        check = auto_complete_check(self.root, name, load_state(self.root, name), 1)
        self.assertFalse(check["ok"])
        self.assertTrue(any("spec_review" in reason for reason in check["reasons"]), check)

    def test_rows_10_to_11_need_no_review_record_and_row9_does(self):
        # DEV-07：行 9 现在要一条 tb_review（与 tc 闸门并列）；行 10、11 的审查
        # 仍是闸门与运行记录本身。
        # 断言口径：_review_record_ok 返回 (ok, reason, ref) 三元，ref 是审查记录的
        # 引用描述（供 tick 自动完成事件带出）；行 10/11 的 ref 为空串。
        from framework.engine import _review_record_ok
        name = "irno9"
        init_sys(self.root, name)
        ok, reason, _ref = _review_record_ok(self.root, name, load_state(self.root, name), 9)
        self.assertFalse(ok)
        self.assertIn("tb_review", reason)
        for sid in (10, 11):
            ok, reason, ref = _review_record_ok(self.root, name, load_state(self.root, name), sid)
            self.assertTrue(ok, (sid, reason))
            self.assertEqual(ref, "")
        with self.assertRaises(EngineError) as ctx:
            review_record(self.root, name, 10, author="a", reviewer="b")
        self.assertIn("不需要 review record", str(ctx.exception))
        with self.assertRaises(EngineError):
            review_record(self.root, name, 12, author="a", reviewer="b")

    def test_cli_review_record_without_terminal(self):
        name = "ircli"
        self._running(name)
        rel = write_report(self.root, name, 1)
        proc = cli(self.root, "review", name, "record", "--stop", "1",
                   "--author", "a", "--reviewer", "b", "--blocking", "0", "--findings", "1",
                   "--report", rel)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        rev = stop_row(load_state(self.root, name), 1)["reviews"][0]
        self.assertEqual(rev["author"], "a")
        self.assertEqual(rev["report"], rel)
        # --report 是 argparse 必填，缺了直接报错。
        proc = cli(self.root, "review", name, "record", "--stop", "1",
                   "--author", "a", "--reviewer", "b")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("--report", proc.stderr)
        # 缺 --author/--reviewer 拒绝并提示新参数。
        proc = cli(self.root, "review", name, "record", "--stop", "1", "--report", rel)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("--author", proc.stderr)
        # --row 兼容别名已删（review 只用 --stop）→ argparse 报 unrecognized。
        proc = cli(self.root, "review", name, "record", "--stop", "1", "--row", "1",
                   "--author", "c", "--reviewer", "d", "--report", rel)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("unrecognized", proc.stderr)


class AutoCompleteCriteriaTests(RepoTest):
    """判据做成可复用函数；tick 的完成相位与判据函数用同一套。"""

    def test_check_and_tick_agree(self):
        name = "acagree"
        init_sys(self.root, name)
        _doc(self.root, name, "info_input/%s_info_overview.md" % name,
             ["输入文档", "可信度", "冲突", "红线五问"])
        tick_report(self.root, name)          # 自动启动行 1
        state = load_state(self.root, name)
        check = auto_complete_check(self.root, name, state, 1)
        self.assertFalse(check["ok"])
        text = tick_report(self.root, name)   # 判据不齐 → 不完成
        self.assertIn("未满足", text)
        self.assertEqual(stop_row(load_state(self.root, name), 1)["state"], RUNNING)
        review(self.root, name, 1)
        check = auto_complete_check(self.root, name, load_state(self.root, name), 1)
        self.assertTrue(check["ok"])
        tick_report(self.root, name)
        self.assertEqual(stop_row(load_state(self.root, name), 1)["state"], DONE)

    def test_criteria_report_every_unmet_reason(self):
        name = "acreasons"
        init_sys(self.root, name)
        _doc(self.root, name, "info_input/%s_info_overview.md" % name,
             ["输入文档", "可信度", "冲突", "红线五问"])
        tick_report(self.root, name)
        add_problem(self.root, name, "阻断", 1, "缺时钟", "审查")
        state = load_state(self.root, name)
        # 往文档里塞一条与 fx 输出矛盾的算式，让闸门也挂：
        # 多个原因（闸门、阻断、审查记录）一起报，便于 tick 一次性列清单。
        path = os.path.join(self.root, name, "info_input", "%s_info_overview.md" % name)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("\n算式 <8,2,t> * <8,2,t> → <16,4,t>\n")
        check = auto_complete_check(self.root, name, load_state(self.root, name), 1)
        reasons = "；".join(check["reasons"])
        self.assertIn("闸门未过", reasons)
        self.assertIn("未关闭阻断", reasons)
        self.assertIn("spec_review", reasons)


class ConfirmFlagRemovedTests(RepoTest):
    """忽略型 `--confirm` 已从参数表删除。

    双向断言：① CLI 传 `--confirm` 必须 argparse 报错（不是"忽略并提示"）；
    ② 完成本来就不靠确认语句——tick 补齐独立审查记录后照样自动完成，
    且 `confirm_quote` 始终为空。
    """

    def _running(self, name):
        init_sys(self.root, name)
        _doc(self.root, name, "info_input/%s_info_overview.md" % name,
             ["输入文档", "可信度", "冲突", "红线五问"])
        tick_report(self.root, name)

    def test_confirm_is_rejected_and_auto_completion_needs_no_confirm(self):
        name = "cfdemo"
        self._running(name)
        review(self.root, name, 1)
        # ① CLI 传 --confirm：参数已删，argparse 报错（退出码非 0、stderr 含 unrecognized）。
        proc = cli(self.root, "advance", name, "--stop", "1",
                   "--to", "完成（审核通过）", "--confirm", "原话")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("unrecognized", proc.stderr)
        # engine 的 advance() 也不再接受 confirm：收窄成主动退回 + 带违例送审。
        with self.assertRaises(TypeError):
            advance(self.root, name, 1, DONE, confirm="随便写什么")
        self.assertIn("已由 tick 自动处理", advance(self.root, name, 1, DONE))
        row = stop_row(load_state(self.root, name), 1)
        self.assertEqual(row["state"], RUNNING)
        self.assertEqual(row.get("confirm_quote", ""), "")
        # ② 完成不靠确认语句：tick 按判据自动完成，确认原话任何路径都不落库。
        text = tick_report(self.root, name)
        self.assertIn("自动完成停点 1", text)
        row = stop_row(load_state(self.root, name), 1)
        self.assertEqual(row["state"], DONE)
        self.assertEqual(row.get("confirm_quote", ""), "")

    def test_cli_rejects_removed_advance_flags(self):
        # 反向守卫：advance 的确认/兼容参数（--confirm/--enter-structure/--loop-side）
        # 一律不再被 argparse 接受，且被拒的调用不改状态。
        name = "cfcli"
        self._running(name)
        for flag, value in (("--confirm", "原话"), ("--enter-structure", None),
                            ("--loop-side", "tb")):
            argv = ["advance", name, "--stop", "1", "--to", "进行中", flag]
            if value is not None:
                argv.append(value)
            proc = cli(self.root, *argv)
            self.assertNotEqual(proc.returncode, 0, flag)
            self.assertIn("unrecognized", proc.stderr, flag)
        self.assertEqual(stop_row(load_state(self.root, name), 1)["state"], RUNNING)


class ItemStopInteractionTests(RepoTest):
    """常驻判据：在途调试事项挡被 blocked_by_items 覆盖的停点；tick 与判据函数同源。"""

    def _to_stop7_running(self, name):
        init_sys(self.root, name)
        state = load_state(self.root, name)
        for row in state["stops"]:
            row["state"] = "进行中" if int(row["id"]) == 7 else "完成（审核通过）"
        save(self.root, name, state)

    def test_open_item_blocks_and_check_reports_it(self):
        name = "it7"
        self._to_stop7_running(name)
        mid = item_open(self.root, name, "调试", "行 7 调试中", side="rtl")
        state = load_state(self.root, name)
        check = auto_complete_check(self.root, name, state, 7)
        self.assertFalse(check["ok"])
        self.assertTrue(any("在途调试事项" in r for r in check["reasons"]), check)
        # tick 相位③按同一判据拒绝完成，清单里点名在途调试事项。
        text = tick_report(self.root, name)
        self.assertIn("在途调试事项", text)
        self.assertEqual(stop_row(load_state(self.root, name), 7)["state"], RUNNING)
        item_end(self.root, name, mid, "L0")
        check = auto_complete_check(self.root, name, load_state(self.root, name), 7)
        self.assertFalse(any("在途调试事项" in r for r in check["reasons"]), check)


class ProblemCloseEvidenceTests(RepoTest):
    """证据口径补充：审查记录也可以当证据；带 blocks 的问题走取舍红线。"""

    def test_review_record_can_be_evidence(self):
        name = "pcrev"
        init_sys(self.root, name)
        _doc(self.root, name, "info_input/%s_info_overview.md" % name,
             ["输入文档", "可信度", "冲突", "红线五问"])
        tick_report(self.root, name)
        pid = add_problem(self.root, name, "阻断", 1, "缺时钟", "审查")
        # 严格口径：证据必须**晚于**问题登记（按 events.jsonl 行号判定），
        # 所以审查记录要在登记之后产生；本用例的意图"审查记录可作证据"不变。
        review(self.root, name, 1)
        close_problem(self.root, name, pid, evidence="review:1")
        self.assertFalse(
            [p for p in load_state(self.root, name)["problems"] if p["id"] == pid][0]["open"])

    def test_blocks_flag_marks_tradeoff(self):
        name = "pcblocks"
        init_sys(self.root, name)
        _doc(self.root, name, "info_input/%s_info_overview.md" % name,
             ["输入文档", "可信度", "冲突", "红线五问"])
        tick_report(self.root, name)
        review(self.root, name, 1)
        pid = add_problem(self.root, name, "阻断", 1, "接口归属", "审查", blocks="1,7")
        rid = record_run(self.root, name, {
            "capability": "sim", "status": "pass", "summary": "RESULT : PASS",
            "profile_id": "p",
            "scope": {"scenario": "sys", "module": "", "tc": "", "seeds": ["1"]},
            "checks": {"result_pass": 1, "result_fail": 0, "full_regression": 1},
        })
        with self.assertRaises(EngineError) as ctx:
            close_problem(self.root, name, pid, evidence=rid)
        self.assertIn("先转为决策", str(ctx.exception))
        # 方向类裁决走"登记待裁决问题 → 点选入库"，不再有令牌与队列。
        did = decide(self.root, name, "接口归属取甲", "方向", 1)
        close_problem(self.root, name, pid, evidence=did)
        self.assertFalse(
            [p for p in load_state(self.root, name)["problems"] if p["id"] == pid][0]["open"])


class RecordKindHintTests(RepoTest):
    """记录类入库的启发式提示。"""

    def test_hint_heuristics(self):
        name = "rkh"
        init_sys(self.root, name)
        from framework.engine import record_kind_hints
        self.assertEqual(record_kind_hints(self.root, name, "流程说明，没有数字"), [])
        self.assertTrue(any("位宽" in h for h in
                            record_kind_hints(self.root, name, "算式 <8,2,t> 落地记录")))
        self.assertTrue(any("单位" in h for h in
                            record_kind_hints(self.root, name, "时钟 32MHz 记录")))
        self.assertTrue(any("单位" in h for h in
                            record_kind_hints(self.root, name, "数据 16 位宽记录")))
        # spec_doc/ 有模块清单时，正文提到模块名也提示。
        _doc(self.root, name, "spec_doc/alu_spec.md",
             ["子系统功能", "端口表", "寄存器", "模块摘要"])
        self.assertTrue(any("模块名" in h for h in
                            record_kind_hints(self.root, name, "alu 的实现记录")))

    def test_cli_prints_hint_for_record_kind_only(self):
        name = "rkcli"
        init_sys(self.root, name)
        cli = _load_cli()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(["decision", name, "commit", "--kind", "记录",
                             "--content", "缓存 16 位的备案", "--stop", "1"])
        self.assertEqual(code, 0)
        self.assertIn("疑似方向或数值类", out.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.main(["decision", name, "commit", "--kind", "记录",
                      "--content", "纯文字记录", "--stop", "1"])
        self.assertNotIn("疑似方向或数值类", out.getvalue())


class LoopSideRemovedCliTests(RepoTest):
    """反向守卫：--loop-side 兼容层已删，CLI 传它必须 argparse 报错。"""

    def test_cli_loop_side_flag_is_gone(self):
        name = "loopcli"
        init_sys(self.root, name)
        proc = cli(self.root, "advance", name, "--stop", "10", "--to", "进行中",
                   "--loop-side", "tb")
        self.assertNotEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("unrecognized", proc.stderr)
        # 被拒的调用不留痕迹：没有事项、行 10 状态未动。
        state = load_state(self.root, name)
        self.assertEqual(state["items"], [])
        self.assertEqual(stop_row(state, 10)["state"], NOT_STARTED)


class MigrationInteractionTests(RepoTest):
    """迁移把未闭合 loop_side 转成事项（另一份在 test_state_atomic / test_item_gating）。"""

    def test_open_loop_side_becomes_an_item(self):
        name = "migloop"
        init_sys(self.root, name)
        state = load_state(self.root, name)
        state["loop_side"] = "tb"
        state.pop("schema", None)
        save(self.root, name, state)
        migrated = load_state(self.root, name)
        # 迁移把 state 盖到当前版本章（SCHEMA_VERSION 随引擎并行演进，这里断言
        # "已迁移到最新版"这一不变量，而不是钉死某个历史数字）。
        from framework.state import SCHEMA_VERSION
        self.assertEqual(migrated["schema"], SCHEMA_VERSION)
        self.assertNotIn("loop_side", migrated)
        items = migrated["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["kind"], "调试")
        self.assertEqual(items[0]["side"], "tb")
        self.assertIn("由旧回路侧", items[0]["text"])
        # 转出的在途事项随即挡住行 7 的完成（判据闭环）：tick 不完成它并点名事项。
        for row in migrated["stops"]:
            row["state"] = "进行中" if int(row["id"]) == 7 else "完成（审核通过）"
        save(self.root, name, migrated)
        text = tick_report(self.root, name)
        self.assertIn("在途调试事项", text)
        self.assertEqual(stop_row(load_state(self.root, name), 7)["state"], RUNNING)


if __name__ == "__main__":
    unittest.main()
