# 作者：vick 邮箱：ykun@yk9811.com

"""一个内容只保留一条裁决：入库按重合度拦下，修订型改走 override。

两步链路（`problem add --kind 待裁决 --options …` → `decision commit --from … --pick …`）
下，已删除的 `test_decision_queue.py` 里仍然有效的两类意图平移到这里：
- ① 重合度守卫：同一内容第二次入库被拒（`test_similar_content_blocked_on_second_commit`）、
  `--force --reason` 放行（`test_force_records_reason_and_assigns_new_id`）；
- ② withdraw 语义：只标已撤回、不再回队列（`test_withdraw_marks_history_without_requeue`）、
  撤回的裁决不再是有效证据（`test_withdrawn_decision_is_not_valid_evidence`）。
"队列上限 4 条"与 dequeue 随队列一起删除，不再平移。

停点 → 阶段号由 `--stop` 推导（行 4–6 → 阶段 3），所以原来写 `--step 3` 的用例
现在传 `--stop 4`，D 号仍是 `D3-00x`。
"""

from framework.engine import (
    EngineError, _decision_exists, add_problem, advance, commit_decision, content_overlaps,
    override_decision, tick_report, withdraw_decision,
)
from framework.state import init_sys, load_state, stop_row
from framework.tests.util import RepoTest, decide, plant_sample

# 重合度守卫按正文三元组比对；这一对（改写前/后）取自原队列用例，改后仍高度重合。
LONG = "帧样点数每帧 28456 样点约 1.42 ms"
REVISED = "帧样点数修订为每帧 28448 样点约 1.42 ms"


class DecisionContentTests(RepoTest):
    """`decide` 记录的是"开发者点选的那一项"，所以正文敏感的用例把候选项写成正文本身。"""

    def _decide(self, name, content, kind="方向", stop=4):
        return decide(self.root, name, content, kind, stop, options="%s|其他" % content)

    def test_similar_content_blocked_on_second_commit(self):
        # 原 test_decision_queue.py 的重合守卫意图：第二次入库在守卫处被拦，
        # 报错点名已有 D 号并指向 override / --force，且不占新 D 号。
        name = "onecontent"
        init_sys(self.root, name)
        first = self._decide(name, LONG)
        self.assertEqual(first, "D3-001")
        with self.assertRaises(EngineError) as ctx:
            self._decide(name, REVISED)
        message = str(ctx.exception)
        self.assertIn("D3-001", message)
        self.assertIn("override", message)
        self.assertIn("--force", message)
        # 拦下不占 D 号、不留多余裁决；手工修改队列已删除，不得再出现。
        state = load_state(self.root, name)
        self.assertEqual(len(state["decisions"]["3"]), 1)
        self.assertEqual(state["seq"]["D"]["3"], 1)
        self.assertNotIn("queue", state)
        self.assertNotIn("dequeued", state)
        self.assertNotIn("T", state["seq"])

    def test_force_records_reason_and_assigns_new_id(self):
        name = "onecontentforce"
        init_sys(self.root, name)
        self._decide(name, LONG)
        # 重合放行仍走 "--force --reason"，且理由落进该裁决的 note。
        pid = add_problem(self.root, name, "待裁决", 4, REVISED, "测试夹具",
                          options="%s|其他" % REVISED)
        did = commit_decision(self.root, name, kind="方向", from_problem=pid, pick=REVISED,
                              force=True, reason="确为新内容：分辨率链重定")
        self.assertEqual(did, "D3-002")
        state = load_state(self.root, name)
        row = [item for item in state["decisions"]["3"] if item["id"] == did][0]
        self.assertIn("重合放行理由", row["note"])
        self.assertIn("分辨率链重定", row["note"])
        self.assertFalse(next(p for p in state["problems"] if p["id"] == pid)["open"],
                         "放行入库同样自动关闭问题")

    def test_force_without_reason_still_blocked(self):
        # 加强：--force 必须配 --reason，单给 --force 不放行。
        name = "onecontentforceless"
        init_sys(self.root, name)
        self._decide(name, LONG)
        pid = add_problem(self.root, name, "待裁决", 4, REVISED, "测试夹具",
                          options="%s|其他" % REVISED)
        with self.assertRaises(EngineError) as ctx:
            commit_decision(self.root, name, kind="方向", from_problem=pid, pick=REVISED,
                            force=True)
        self.assertIn("D3-001", str(ctx.exception))
        state = load_state(self.root, name)
        self.assertEqual(len(state["decisions"]["3"]), 1)
        self.assertEqual(state["seq"]["D"]["3"], 1)

    def test_override_rewrites_same_number_and_keeps_history(self):
        name = "onecontentoverride"
        init_sys(self.root, name)
        did = self._decide(name, "帧样点数每帧 28456 样点")
        self.assertEqual(did, "D3-001")
        self.assertEqual(override_decision(self.root, name, did,
                                           "帧样点数每帧 28448 样点"),
                         did)
        state = load_state(self.root, name)
        self.assertEqual(len(state["decisions"]["3"]), 1)
        row = state["decisions"]["3"][0]
        self.assertEqual(row["content"], "帧样点数每帧 28448 样点")
        self.assertEqual(row["history"][-1]["content"], "帧样点数每帧 28456 样点")

    def test_withdraw_marks_history_without_requeue(self):
        # 原 test_withdraw_returns_entry_to_queue：撤回不再把条目放回队列——
        # 只标 withdrawn/withdrawn_at 保留历史，库里仍有这条（带撤回标记）。
        name = "onecontentwithdraw"
        init_sys(self.root, name)
        first = self._decide(name, "观测口只有一路 40 位数据")
        second = self._decide(name, "接收定标缺省移位为零")
        self.assertEqual((first, second), ("D3-001", "D3-002"))
        self.assertEqual(withdraw_decision(self.root, name, second), second)
        state = load_state(self.root, name)
        self.assertEqual([row["id"] for row in state["decisions"]["3"]], [first, second],
                         "撤回保留历史，不从库里删除")
        row = [item for item in state["decisions"]["3"] if item["id"] == second][0]
        self.assertTrue(row["withdrawn"])
        self.assertTrue(row["withdrawn_at"])
        # 不再有队列，撤回也就不可能"回流"；D 号不回收。
        self.assertNotIn("queue", state)
        self.assertNotIn("dequeued", state)
        self.assertNotIn("T", state["seq"])
        self.assertEqual(state["seq"]["D"]["3"], 2)
        self.assertEqual(self._decide(name, "第三条不同内容"), "D3-003")

    def test_withdrawn_decision_is_not_valid_evidence(self):
        # 原 test_committed_decision_not_dequeueable 的替代：撤回的裁决不再是
        # 有效证据——带违例送审（红线）拒收它，且拒的是"已撤回"而不是"没有"。
        name = "onecontentevidence"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        tick_report(self.root, name)
        self.assertEqual(stop_row(load_state(self.root, name), 1)["state"], "进行中")
        did = self._decide(name, "观测口只有一路 40 位数据", stop=1)
        self.assertEqual(did, "D0-001")
        withdraw_decision(self.root, name, did)
        self.assertFalse(_decision_exists(load_state(self.root, name), did))
        with self.assertRaises(EngineError) as ctx:
            advance(self.root, name, 1, "已送审", allow_violation=True, decision=did)
        self.assertIn("已撤回", str(ctx.exception))

    def test_similar_content_blocked_for_record_kind_too(self):
        # 原 test_enqueue_blocks_same_content_before_queue_grows：守卫在两步链路
        # 的入库口上，不因"记录类不经问题"而漏掉；报错同样点名已有 D 号。
        name = "onecontentenq"
        init_sys(self.root, name)
        decide(self.root, name, "残差相位由环路积分支路吸收", "记录", 4)
        with self.assertRaises(EngineError) as ctx:
            decide(self.root, name, "残差相位由环路积分支路完全吸收", "记录", 4)
        self.assertIn("D3-001", str(ctx.exception))
        self.assertEqual(load_state(self.root, name)["seq"]["D"]["3"], 1)

    def test_empty_content_is_rejected(self):
        # 原队列用例"空草稿 + 空正文被拒"的替代：草稿机制已删除，空正文仍然入不了库。
        name = "onecontentempty"
        init_sys(self.root, name)
        with self.assertRaises(EngineError) as ctx:
            commit_decision(self.root, name, content="", kind="记录", stop=4)
        self.assertIn("正文为空", str(ctx.exception))
        state = load_state(self.root, name)
        self.assertEqual(state["decisions"]["3"], [])
        self.assertEqual(state["seq"]["D"]["3"], 0)

    def test_problem_can_only_be_picked_once(self):
        # 原 test_committed_decision_not_dequeueable 的配套：一条待裁决问题只对应
        # 一次点选入库；重复点选被拒，不领第二个 D 号。
        name = "onecontentonce"
        init_sys(self.root, name)
        content = "帧样点数每帧 28456 样点"
        pid = add_problem(self.root, name, "待裁决", 4, content, "测试夹具",
                          options="%s|其他" % content)
        did = commit_decision(self.root, name, kind="方向", from_problem=pid, pick=content)
        self.assertEqual(did, "D3-001")
        with self.assertRaises(EngineError) as ctx:
            commit_decision(self.root, name, kind="方向", from_problem=pid, pick=content)
        self.assertIn("已关闭", str(ctx.exception))
        state = load_state(self.root, name)
        self.assertEqual([row["id"] for row in state["decisions"]["3"]], [did])
        self.assertEqual(state["seq"]["D"]["3"], 1)

    def test_explicit_content_wins_and_source_records_pick(self):
        # 原 test_commit_explicit_other_content_keeps_mismatch_note：草稿不一致的
        # note 机制随队列删除，但"显式正文优先 + 点选来源留痕"这层语义仍在——
        # 问题原文与所选项都写进 events.jsonl 的"裁决入库"一行。
        import json
        import os
        from framework.state import sys_dir

        name = "onecontentmismatch"
        init_sys(self.root, name)
        draft = "草稿：帧样点数每帧 28456 样点"
        final = "定稿：帧样点数每帧 28448 样点"
        pid = add_problem(self.root, name, "待裁决", 4, draft, "测试夹具", options="取甲|取乙")
        did = commit_decision(self.root, name, kind="方向", from_problem=pid, pick="取甲",
                              content=final, stop=4)
        state = load_state(self.root, name)
        row = [item for item in state["decisions"]["3"] if item["id"] == did][0]
        self.assertEqual(row["content"], final, "显式 --content 优先于点选项")
        self.assertEqual(row["source"], "%s/取甲" % pid)
        with open(os.path.join(sys_dir(self.root, name), "events.jsonl"),
                  encoding="utf-8") as fh:
            events = [json.loads(line) for line in fh if line.strip()]
        entry = [e for e in events if e["action"] == "裁决入库"][-1]
        self.assertEqual(entry["object"], did)
        self.assertIn(draft, entry["evidence"], "问题原文进事件证据")
        self.assertIn("取甲", entry["evidence"], "所选项进事件证据")

    def test_short_content_is_not_compared(self):
        name = "onecontentshort"
        init_sys(self.root, name)
        state = load_state(self.root, name)
        self.assertEqual(content_overlaps(state, "同意"), [])
