# 作者：vick 邮箱：ykun@yk9811.com

"""记录类裁决：入库与改写全自动（点选即确认），不级联的不变量保持。

T 队列与放行令牌删除，记录类走 `commit --kind 记录 --content … --stop N`
一步入库（测试经 `util.decide` 走同一路径）。
"""

import os

from framework.engine import EngineError, commit_decision, override_decision, tick_report
from framework.state import init_sys, load_state
from framework.tests.util import RepoTest, decide


def _doc(root, name, rel, chapters):
    path = os.path.join(root, name, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = ["# t", "", "简介。", ""]
    for index, chapter in enumerate(chapters, 2):
        lines.extend(["## %d. %s" % (index, chapter), "", "正文。", ""])
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


class RecordKindTests(RepoTest):
    def _push_stop(self, name, sid, rel, chapters):
        """把停点 sid 推到完成：写产物 + 补独立审查记录后由 tick 自动启动并完成
        （advance 不再承担启动/送审/完成）。"""
        _doc(self.root, name, rel, chapters)
        from framework.tests.util import review
        review(self.root, name, sid)
        tick_report(self.root, name)

    def test_record_commit_is_auto(self):
        # 旧断言：记录类入库缺 --confirm 要拒 → 新断言：点选即入库，不要确认语句
        # → 依据记录类裁决入库与改写 = 自动。
        name = "recconfirm"
        init_sys(self.root, name)
        did = decide(self.root, name, "迁移落地记录", "记录", 1)
        self.assertEqual(did, "D0-001")
        state = load_state(self.root, name)
        row = state["decisions"]["0"][0]
        self.assertEqual(row["kind"], "记录")
        self.assertNotIn("queue", state)       # 手工队列已删除
        self.assertNotIn("T", state["seq"])    # T 序号已删除

    def test_record_commit_does_not_cascade(self):
        name = "reccascade"
        init_sys(self.root, name)
        self._push_stop(name, 1, "info_input/%s_info_overview.md" % name,
                        ["输入文档", "可信度", "冲突", "红线五问"])
        self._push_stop(name, 2, "flow_doc/%s_flow.md" % name,
                        ["输入输出", "步骤", "节点表", "运算定点化图", "边界点"])
        state = load_state(self.root, name)
        fp2 = state["stops"][1]["fingerprint"]
        self.assertTrue(fp2)
        decide(self.root, name, "迁移落地记录", "记录", 1)
        state = load_state(self.root, name)
        # 记录类不级联：停点 2 仍是完成版，指纹原样保留
        row = state["stops"][1]
        self.assertEqual(row["state"], "完成（审核通过）")
        self.assertEqual(row["fingerprint"], fp2)
        self.assertNotIn("withdrawn", state["decisions"]["0"][0])

    def test_record_needs_no_token(self):
        # 旧断言：记录类入库也要令牌/确认 → 新断言：记录类自动入库，不要令牌。
        # 令牌路径本身已删除，这里验证"没有任何令牌文件也照常入库并且状态里没有令牌痕迹"。
        name = "rectoken"
        init_sys(self.root, name)
        did = decide(self.root, name, "迁移落地记录", "记录", 1)
        self.assertEqual(did, "D0-001")
        state = load_state(self.root, name)
        self.assertNotIn("token", state)
        self.assertFalse(os.path.exists(os.path.join(self.home, ".asic_design_agent", "release")),
                         "入库不应要求或产生放行令牌文件")

    def test_record_overlap_guard_needs_force_and_reason(self):
        """队列删除后没有"入队草稿 vs 入库正文"的对照；保留的是重合度守卫
        （一个内容一条裁决）：同内容再入库要拦下，`--force --reason` 才放行并记进备注。"""
        name = "recoverlap"
        init_sys(self.root, name)
        content = "迁移落地记录：接口位宽保持 16 位"
        did = decide(self.root, name, content, "记录", 1)
        with self.assertRaises(EngineError):
            commit_decision(self.root, name, content=content, kind="记录", stop=1)
        did2 = commit_decision(self.root, name, content=content, kind="记录", stop=1,
                               force=True, reason="确属新内容")
        self.assertNotEqual(did, did2)
        note = load_state(self.root, name)["decisions"]["0"][-1]["note"]
        self.assertIn("重合放行理由", note)
        self.assertIn("确属新内容", note)

    def test_record_override_is_auto(self):
        # 旧断言：记录类改写缺 --confirm 要拒 → 新断言：自动，不要确认语句 → 依据记录类裁决自动。
        name = "recoverride"
        init_sys(self.root, name)
        did = decide(self.root, name, "迁移落地记录", "记录", 1)
        override_decision(self.root, name, did, "改写后的正文")
        row = load_state(self.root, name)["decisions"]["0"][-1]
        self.assertEqual(row["content"], "改写后的正文")
        self.assertEqual(row["kind"], "记录")

    def test_decision_rows_carry_time_for_problem_close(self):
        # 关闭问题要用"证据晚于问题登记"，裁决行必须带入库时间。
        name = "rectime"
        init_sys(self.root, name)
        decide(self.root, name, "迁移落地记录", "记录", 1)
        row = load_state(self.root, name)["decisions"]["0"][0]
        self.assertRegex(row.get("time", ""), r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}")


if __name__ == "__main__":
    unittest.main()
