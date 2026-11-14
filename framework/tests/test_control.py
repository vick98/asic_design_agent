# 作者：vick 邮箱：ykun@yk9811.com

import os

from framework.engine import (
    add_problem, advance, close_problem, tick_report,
)
from framework.state import init_sys, load_state, save, stop_row
from framework.tests.util import RepoTest, cli, decide, review


def _doc(root, name, rel, chapters):
    path = os.path.join(root, name, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = ["# t", "", "简介。", ""]
    for index, chapter in enumerate(chapters, 2):
        lines.extend(["## %d. %s" % (index, chapter), "", "正文。", ""])
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


class ControlTests(RepoTest):
    def test_auto_completion_needs_review_not_confirm_or_token(self):
        # 旧断言：完成要 --confirm + 放行令牌 +（关键停点）终端照抄
        # → 新断言：① --confirm 参数已删，CLI 与 engine 都不再接受；
        #   ② 完成由 tick 按判据自动写，缺的是对应当前产物指纹的独立审查记录。
        name = "needconfirm"
        init_sys(self.root, name)
        _doc(self.root, name, "info_input/needconfirm_info_overview.md",
             ["输入文档", "可信度", "冲突", "红线五问"])
        proc = cli(self.root, "advance", name, "--stop", "1", "--to", "完成（审核通过）",
                   "--confirm", "通过")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("unrecognized", proc.stderr)
        with self.assertRaises(TypeError):
            advance(self.root, name, 1, "完成（审核通过）", confirm="通过")
        message = advance(self.root, name, 1, "完成（审核通过）")
        self.assertIn("已由 tick 自动处理", message)
        out = tick_report(self.root, name)
        self.assertIn("spec_review", out)
        self.assertEqual(stop_row(load_state(self.root, name), 1)["state"], "进行中")
        review(self.root, name, 1)
        tick_report(self.root, name)
        row = stop_row(load_state(self.root, name), 1)
        self.assertEqual(row["state"], "完成（审核通过）")
        self.assertEqual(row["confirm_quote"], "")
        self.assertTrue(row["confirmed_at"])
        self.assertTrue(load_state(self.root, name)["position"]["rule_version"])

    def test_reopen_cascades_downstream(self):
        # 改写（按依赖级联）：
        # 旧断言：退回停点 1 后，编号更大且已启动的行（2、3）全部退回进行中，
        #         remark 标"上游 停点 1 变更待重推"；
        # 新断言：级联只到**依赖闭包（depends_on 传递下游）内、已启动**的停点——
        #         2、3 在 1 的下游且已启动，仍退回进行中并清确认痕迹；未开始的
        #         停点 4 不被级联；级联逐停点记"级联退回"事件（谁级联了谁、原因）；
        # 依据：停点退回只级联依赖闭包内已启动的停点，未开始的不动。
        # 驱动：停点 1–3 的启动与完成由 tick 自动做，退回仍用 advance。
        name = "reopen"
        init_sys(self.root, name)
        chapters = {
            1: ["输入文档", "可信度", "冲突", "红线五问"],
            2: ["输入输出", "步骤", "节点表", "运算定点化图", "边界点"],
            3: ["模块划分", "模块类型", "前后级与交互"],
        }
        for sid, rel, _chapter in (
            (1, "info_input/reopen_info_overview.md", "2. 输入文档"),
            (2, "flow_doc/reopen_flow.md", "2. 输入输出"),
            (3, "plan_doc/reopen_plan.md", "2. 模块划分"),
        ):
            _doc(self.root, name, rel, chapters[sid])
            review(self.root, name, sid)
            tick_report(self.root, name)
        advance(self.root, name, 1, "进行中")
        state = load_state(self.root, name)
        # 闭包内已启动的下游（2、3）照旧级联退回，确认痕迹清掉。
        self.assertEqual(stop_row(state, 2)["state"], "进行中")
        self.assertEqual(stop_row(state, 3)["state"], "进行中")
        self.assertIn("上游 停点 1 变更待重推", stop_row(state, 2)["remark"])
        for sid in (2, 3):
            row = stop_row(state, sid)
            self.assertEqual(row["done_at"], "", "行 %d 的确认痕迹没跟着级联清掉" % sid)
            self.assertEqual(row["cascaded_from"], 1)
        # 未开始的停点 4 不在"已启动"之列：不级联、不留级联标记。
        self.assertEqual(stop_row(state, 4)["state"], "未开始")
        self.assertEqual(stop_row(state, 4).get("cascaded_at", ""), "")
        with open(os.path.join(self.root, name, "events.jsonl"), encoding="utf-8") as fh:
            events = [line for line in fh if '"级联退回"' in line]
        self.assertEqual(len(events), 2, events)
        self.assertIn("由 1", events[0])

    def test_blocking_problem_and_decision_pick(self):
        # 旧断言：有未关闭阻断时 advance(启动) 抛错，关闭后换成依赖报错。
        # 新断言：有未关闭阻断时 tick 不自动启动该停点（仍是"未开始"），
        #         清单点名未关闭阻断；关闭后 tick 自动启动到"进行中"。
        # 尾部原用 replace_notes 断言"只报告不改写文档"，该命令已删除，
        # 改成跑两步链路的真实入库：数值裁决靠问题点选入库并自动关闭该问题。
        name = "probs"
        init_sys(self.root, name)
        state = load_state(self.root, name)
        for row in state["stops"]:
            row["state"] = "完成（审核通过）" if int(row["id"]) < 3 else "未开始"
        save(self.root, name, state)
        pid = add_problem(self.root, name, "阻断", 3, "缺时钟", "审查")
        out = tick_report(self.root, name)
        self.assertIn("未关闭阻断", out)
        self.assertEqual(stop_row(load_state(self.root, name), 3)["state"], "未开始")
        # 关闭靠证据（登记之后的一次运行记录）。
        from framework.engine import record_run
        rid = record_run(self.root, name, {
            "capability": "sim", "status": "pass", "summary": "RESULT : PASS",
            "profile_id": "p",
            "scope": {"scenario": "sys", "module": "", "tc": "", "seeds": ["1"]},
            "checks": {"result_pass": 1, "result_fail": 0, "full_regression": 1},
        })
        close_problem(self.root, name, pid, evidence=rid)
        out = tick_report(self.root, name)
        self.assertNotIn("未关闭阻断", out)
        self.assertEqual(stop_row(load_state(self.root, name), 3)["state"], "进行中")
        # 停点 3 → 阶段 2；方向/数值类不要令牌、不要 --confirm，点选即入库。
        did = decide(self.root, name, "位宽取 8", "数值", 3, options="位宽取 8|其他")
        self.assertEqual(did, "D2-001")
        state = load_state(self.root, name)
        row = [item for item in state["decisions"]["2"] if item["id"] == did][0]
        self.assertEqual(row["kind"], "数值")
        self.assertEqual(row["content"], "位宽取 8")
        self.assertEqual(row["stop"], 3, "裁决记下自己的停点（override 级联起点）")
        picked = [p for p in state["problems"]
                  if p["kind"] == "待裁决" and p.get("evidence") == did]
        self.assertEqual(len(picked), 1, "点选入库留一条已关闭的待裁决问题作来源")
        self.assertFalse(picked[0]["open"])
        self.assertNotIn("queue", state, "手工修改队列已删除")
        self.assertNotIn("T", state["seq"])
