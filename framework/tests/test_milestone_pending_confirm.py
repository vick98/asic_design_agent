# 作者：vick 邮箱：ykun@yk9811.com

"""里程碑确认的"待确认"标注检查：覆盖范围内的产品文档还留着标注就拒绝确认。

U1 闸门只要求标注行带一个仍打开的问题号；里程碑确认更严——标注一律清掉才能冻结/签核，
不论问题是否已关闭。原因要指名文件与标注行文本。
"""

import os

from framework.engine import (
    EngineError, add_problem, commit_decision, milestone_confirm, tick_report,
)
from framework.gates.run import run_gates
from framework.state import init_sys, load_state, sys_dir
from framework.tests.util import RepoTest, plant_sample, review, write_milestone_notes


class MilestonePendingConfirmTests(RepoTest):
    LINE = "采样位宽：<16,8,u>（推断-待确认）"

    def _ready_m1(self, name):
        """行 1–3 完成、M1 就绪，但覆盖范围内留一处带打开问题号的待确认标注。"""
        init_sys(self.root, name)
        plant_sample(self.root, name)
        pid = add_problem(self.root, name, "待裁决", 1, "输入精度待确认", "测试夹具")
        path = os.path.join(sys_dir(self.root, name), "info_input",
                            "%s_info_overview.md" % name)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("\n%s〔%s〕\n" % (self.LINE, pid))
        for sid in (1, 2, 3):
            review(self.root, name, sid)
        tick_report(self.root, name)
        write_milestone_notes(self.root, name, "M1")
        return pid, path

    def test_open_reference_passes_u1_but_blocks_confirm(self):
        name = "m6open"
        self._ready_m1(name)
        state = load_state(self.root, name)
        u1 = [item for item in run_gates(self.root, name, 1, state)
              if item["rule"] == "U1"]
        self.assertEqual(u1, [], "带仍打开的问题号，U1 闸门不报")
        with self.assertRaises(EngineError) as ctx:
            milestone_confirm(self.root, name, "M1", pick="通过")
        message = str(ctx.exception)
        self.assertIn("待确认", message)
        self.assertIn("info_input/%s_info_overview.md" % name, message)
        self.assertIn("采样位宽", message)

    def test_annotation_after_problem_closed_blocks_confirm(self):
        name = "m6closed"
        pid, _path = self._ready_m1(name)
        # 问题类型只剩阻断/待裁决：待裁决问题以点选入库的方向类裁决关闭。
        # 停在签核行（--stop 12），级联不波及已启动的覆盖停点。
        commit_decision(self.root, name, kind="方向", from_problem=pid,
                        pick="按标注取整", stop=12)
        with self.assertRaises(EngineError) as ctx:
            milestone_confirm(self.root, name, "M1", pick="通过")
        message = str(ctx.exception)
        self.assertIn("待确认", message)
        self.assertIn("info_input/%s_info_overview.md" % name, message)
        self.assertIn("采样位宽", message)
