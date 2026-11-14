# 作者：vick 邮箱：ykun@yk9811.com

"""tick/status 的机器可读结构：两张清单先建结构、再由结构渲染文本。

- `tick_data` 返回 actions / todo / human；每一项带建议命令，结构字段齐全；
- `status_data` 只读，另带当前位置（当前停点、所处、下一步等）与小结；
- 文本渲染与结构同源：结构里每一项的 text 就是文本里那一行（去掉 "- " 前缀）。
"""

import os

from framework.engine import (
    add_problem, item_open, item_set, status_data, status_report, tick_data,
    tick_report,
)
from framework.flow import DONE, PENDING
from framework.state import init_sys, load_state, save, stop_row
from framework.tests.util import (
    RepoTest, cli, confirm_milestone, force_done, plant_sample, review,
)

TODO_KINDS = {"start", "finish", "fix", "milestone"}
HUMAN_KINDS = {"decision", "milestone", "escalation", "deferred"}
COMMAND_PREFIX = "python3 script/framework.py "
TODO_TITLE = "可推进的工作："
HUMAN_TITLE = "需要开发者："


def _section_lines(text, title, stop_title):
    """取某张清单的条目行（以 "- " 开头、排除空清单提示行）。"""
    body = text.split(title, 1)[1]
    if stop_title:
        body = body.split(stop_title, 1)[0]
    return [line for line in body.splitlines()
            if line.startswith("- ") and not line.startswith("- （")]


def _snapshot(base):
    rows = {}
    for dirpath, dirnames, files in os.walk(base):
        dirnames.sort()
        for fn in sorted(files):
            path = os.path.join(dirpath, fn)
            rows[os.path.relpath(path, base)] = (
                os.path.getsize(path), os.path.getmtime(path))
    return rows


class StatusDataTests(RepoTest):
    def test_position_fields_and_shape(self):
        name = "jsonshape"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        data = status_data(self.root, name)
        self.assertEqual(data["sys"], name)
        self.assertFalse(data["done"])
        self.assertTrue(data["where"])
        self.assertTrue(data["next"])
        current = data["current"]
        self.assertEqual(current["stop"], 1)
        self.assertEqual(current["name"], "信息输入")
        self.assertTrue(current["command"].startswith(COMMAND_PREFIX))
        self.assertIsInstance(data["summaries"], list)
        self.assertIsInstance(data["todo"], list)
        self.assertIsInstance(data["human"], list)

    def test_status_data_is_read_only(self):
        name = "jsonreadonly"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        add_problem(self.root, name, "待裁决", 2, "帧窗口取行 2 还是行 3 口径",
                    options="行 2|行 3", blocks="3")
        base = os.path.join(self.root, name)
        before = _snapshot(base)
        status_data(self.root, name)
        self.assertEqual(before, _snapshot(base))

    def test_status_text_is_rendered_from_structure(self):
        name = "jsonrender"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        add_problem(self.root, name, "待裁决", 2, "帧窗口取行 2 还是行 3 口径",
                    options="行 2|行 3", blocks="3")
        data = status_data(self.root, name)
        text = status_report(self.root, name)
        self.assertEqual(_section_lines(text, TODO_TITLE, HUMAN_TITLE),
                         ["- %s" % item["text"] for item in data["todo"]])
        self.assertEqual(_section_lines(text, HUMAN_TITLE, None),
                         ["- %s" % item["text"] for item in data["human"]])

    def test_every_item_has_a_command_and_known_kind(self):
        name = "jsonitems"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        for sid in (1, 2, 3):
            review(self.root, name, sid)
            tick_report(self.root, name)
        add_problem(self.root, name, "待裁决", 4, "仲裁轮询还是固定优先级",
                    options="轮询|固定优先级", blocks="4")
        mid = item_open(self.root, name, "调试", "行 7 建立时间违例", side="rtl")
        for _ in range(5):
            item_set(self.root, name, mid, "换约束重跑")
        data = status_data(self.root, name)
        for item in data["todo"]:
            self.assertIn(item["kind"], TODO_KINDS)
            self.assertIn("stop", item)
            self.assertIsInstance(item["reasons"], list)
            self.assertTrue(item["command"].startswith(COMMAND_PREFIX), item)
            self.assertTrue(item["text"])
        for item in data["human"]:
            self.assertIn(item["kind"], HUMAN_KINDS)
            for key in ("id", "stop", "text", "command"):
                self.assertIn(key, item)
            self.assertTrue(item["command"].startswith(COMMAND_PREFIX), item)
            self.assertTrue(item["text"])
        kinds = {item["kind"] for item in data["human"]}
        self.assertIn("decision", kinds)
        self.assertIn("escalation", kinds)
        # M1 就绪但缺结论摘要：里程碑行在 todo（智能体先补摘要），不在 human。
        milestone_kinds = {item["kind"] for item in data["todo"] + data["human"]}
        self.assertIn("milestone", milestone_kinds)

    def test_decision_item_fields_and_command(self):
        name = "jsondecision"
        init_sys(self.root, name)
        add_problem(self.root, name, "待裁决", 2, "帧窗口取行 2 还是行 3 口径",
                    options="行 2|行 3")
        data = status_data(self.root, name)
        item = next(row for row in data["human"] if row["id"] == "I001")
        self.assertEqual(item["kind"], "decision")
        self.assertEqual(item["stop"], 2)
        self.assertIn("待裁决问题 I001", item["text"])
        self.assertIn("decision %s commit --from I001" % name, item["command"])

    def test_milestone_item_command_lists_review_pack(self):
        name = "jsonmilestone"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        for sid in (1, 2, 3):
            review(self.root, name, sid)
            tick_report(self.root, name)
        data = status_data(self.root, name)
        items = [row for row in data["todo"] + data["human"] if row["kind"] == "milestone"]
        self.assertTrue(items, data)
        self.assertTrue(any("milestone %s show --id M1" % name in row["command"]
                            for row in items))


class TickDataTests(RepoTest):
    def test_actions_shape_and_rounds(self):
        name = "tickjson"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        review(self.root, name, 1)
        data = tick_data(self.root, name)
        self.assertEqual(set(data["actions"]),
                         {"done", "started", "sent", "recovered", "retreated"})
        for value in data["actions"].values():
            self.assertIsInstance(value, list)
        self.assertEqual(data["actions"]["done"], [1])
        self.assertGreaterEqual(data["rounds"], 1)
        self.assertIsInstance(data["todo"], list)
        self.assertIsInstance(data["human"], list)

    def test_tick_text_renders_the_same_lists(self):
        name = "tickjsontext"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        review(self.root, name, 1)
        data = tick_data(self.root, name)
        text = tick_report(self.root, name)
        self.assertEqual(_section_lines(text, TODO_TITLE, HUMAN_TITLE),
                         ["- %s" % item["text"] for item in data["todo"]])
        self.assertEqual(_section_lines(text, HUMAN_TITLE, None),
                         ["- %s" % item["text"] for item in data["human"]])

    def test_refused_stop_is_reported_once(self):
        # 已送审停点送审后产物被改：tick 不收口，只把"先退回重做"报一次
        #（多轮循环里不重复累积），并带上建议命令。
        name = "tickrefused"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        review(self.root, name, 1)
        review(self.root, name, 2)
        state = load_state(self.root, name)
        row = next(item for item in state["stops"] if int(item["id"]) == 2)
        row["state"] = PENDING
        row["pending_digest"] = "与当前产物对不上的旧基线"
        save(self.root, name, state)
        data = tick_data(self.root, name)
        self.assertEqual([item["stop"] for item in data["refused"]], [2])
        refusals = [item for item in data["todo"] if "送审后产物已改动" in item["text"]]
        self.assertEqual(len(refusals), 1, refusals)
        self.assertEqual(refusals[0]["stop"], 2)
        self.assertTrue(refusals[0]["command"].startswith(COMMAND_PREFIX))


class CommandExecutabilityTests(RepoTest):
    """清单里的建议命令必须是可照抄执行的：子命令顺序、<sys> 与参数都要对。

    回归守卫：曾出现 `milestone show --id M1`（缺 sys）、`decision commit ...`
    （缺 sys）与 `item list <sys>`（顺序错）这类"看起来像命令、复制即失败"的文案。
    """

    def _run(self, command):
        self.assertTrue(command.startswith(COMMAND_PREFIX), command)
        return cli(self.root, *command[len(COMMAND_PREFIX):].split())

    def test_decision_command_runs(self):
        name = "cmddecision"
        init_sys(self.root, name)
        add_problem(self.root, name, "待裁决", 2, "帧窗口取行 2 还是行 3 口径",
                    options="取甲|取乙")
        item = next(row for row in status_data(self.root, name)["human"]
                    if row["kind"] == "decision")
        cmd = (item["command"].replace("<选项>", "取甲")
               .replace("<方向|数值>", "方向"))
        proc = self._run(cmd)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("D", proc.stdout)

    def test_milestone_command_runs(self):
        name = "cmdmilestone"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        for sid in (1, 2, 3):
            review(self.root, name, sid)
            tick_report(self.root, name)
        data = status_data(self.root, name)
        item = next(row for row in data["todo"] + data["human"]
                    if row["kind"] == "milestone")
        proc = self._run(item["command"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("里程碑 M1", proc.stdout)

    def test_escalation_item_list_command_runs(self):
        name = "cmdesc"
        init_sys(self.root, name)
        mid = item_open(self.root, name, "调试", "整帧比对不过", side="rtl")
        for _ in range(5):
            item_set(self.root, name, mid, "继续定位")
        item = next(row for row in status_data(self.root, name)["human"]
                    if row["kind"] == "escalation" and row.get("id") == mid)
        proc = self._run(item["command"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(mid, proc.stdout)


class StatusCurrentTests(RepoTest):
    """status 的当前位置必须与首个未完成停点一致，且命令可执行。"""

    def _done_until(self, name, last):
        for sid in range(1, last + 1):
            force_done(self.root, name, sid)

    def test_pending_milestone_returns_upstream_show_first(self):
        name = "cmdpending"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        self._done_until(name, 5)
        state = load_state(self.root, name)
        stop_row(state, 6)["state"] = PENDING
        save(self.root, name, state)
        current = status_data(self.root, name)["current"]
        self.assertEqual(current["stop"], 6)
        self.assertTrue(current["command"].startswith(COMMAND_PREFIX), current["command"])
        # M1 未确认：先出 M1 审阅包，不能直接确认 M2。
        self.assertIn("milestone %s show --id M1" % name, current["command"])

    def test_pending_milestone_after_upstream_confirmed(self):
        name = "cmdready"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        self._done_until(name, 3)
        confirm_milestone(self.root, name, "M1")
        self._done_until(name, 5)
        state = load_state(self.root, name)
        stop_row(state, 6)["state"] = PENDING
        save(self.root, name, state)
        current = status_data(self.root, name)["current"]
        self.assertEqual(current["stop"], 6)
        self.assertIn("milestone %s show --id M2" % name, current["command"])

    def test_m3_confirm_command_uses_quoted_fixed_sentence(self):
        from framework.engine import _milestone_command
        cmd = _milestone_command("s11demo", "M3", "confirm")
        self.assertIn('--confirm "确认 s11demo 签核放行（M3）通过"', cmd)
        self.assertNotIn("<", cmd)

    def test_tick_refreshes_position_to_first_unfinished_stop(self):
        name = "cmdposition"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        self._done_until(name, 10)
        state = load_state(self.root, name)
        stop_row(state, 11)["state"] = PENDING
        stop_row(state, 12)["state"] = "进行中"
        save(self.root, name, state)
        tick_report(self.root, name)
        data = status_data(self.root, name)
        self.assertEqual(data["current"]["stop"], 11)
        self.assertIn("停点 11", data["where"])
        self.assertIn("已送审", data["where"])

    def test_blocking_problem_takes_priority_over_milestone_hint(self):
        name = "cmdblocked"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        self._done_until(name, 3)
        from framework.engine import add_problem
        add_problem(self.root, name, "阻断", 4, "行 4 的阻断", "测试")
        data = status_data(self.root, name)
        self.assertEqual(data["current"]["stop"], 4)
        self.assertIn("problem %s list" % name, data["current"]["command"])
        notes = " ".join(data["current"]["notes"])
        self.assertIn("未关闭阻断", notes)
        self.assertIn("problem %s close" % name, notes)
