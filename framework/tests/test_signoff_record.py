# 作者：vick 邮箱：ykun@yk9811.com

"""签核记录补全：签核文件逐项断言（只引用记录号，不抄日志）。

覆盖：模块 lint 记录号与摘要、全量回归、覆盖率与阈值来源、综合与时序明细、
剖面与工具版本、豁免与带违例送审留痕、三个里程碑的确认时间/语句与 M1/M2 当前
有效性、在途事项 0、未关闭阻断 0、RTL 目录指纹与 SDC 摘要、放行语句。
"""

import os
import unittest

from framework.engine import (
    add_waiver, advance, module_digest, record_run, render_signoff, tick_report,
)
from framework.state import init_sys, load_state, sys_dir
from framework.tests.util import RepoTest, confirm_milestone, decide, force_done, plant_sample


def _lint(root, name, modules):
    base = sys_dir(root, name)
    record_run(root, name, {
        "capability": "lint", "status": "pass", "summary": "lint pass",
        "profile_id": "example",
        "scope": {"modules": list(modules),
                  "module_digests": {mod: module_digest(base, mod) for mod in modules}},
        "checks": {"errors": 0, "tool_versions": {"rtl_sim": "V-2023.03"}},
    })


def _sim(root, name):
    record_run(root, name, {
        "capability": "sim", "status": "pass", "summary": "RESULT : PASS",
        "profile_id": "example",
        "scope": {"scenario": "sys", "module": "", "tc": "", "seeds": ["1", "2"]},
        "checks": {"result_pass": 1, "result_fail": 0, "full_regression": 1,
                   "tool_versions": {"rtl_sim": "V-2023.03"}},
    })


def _coverage(root, name):
    record_run(root, name, {
        "capability": "coverage", "status": "pass", "summary": "coverage pass",
        "profile_id": "example",
        "checks": {"line": 100.0, "cond": 98.0, "fsm": 100.0, "tgl": 95.0},
    })


def _midend(root, name):
    record_run(root, name, {
        "capability": "synth", "status": "pass", "summary": "synth pass",
        "profile_id": "example",
        "checks": {"errors": 0, "latches": 2, "area": 1234.5,
                   "tool_versions": {"logic_synth": "T-2022.03"}},
    })
    record_run(root, name, {
        "capability": "sta", "status": "pass", "summary": "sta pass",
        "profile_id": "example",
        "checks": {"corners": [{"name": "slow", "setup_wns": 0.12, "hold_wns": 0.05,
                                "setup_violations": 0, "hold_violations": 1}],
                   "unconstrained_endpoints": 3,
                   "tool_versions": {"timing_check": "T-2022.03"}},
    })


def _read_signoff(root, name):
    path = os.path.join(sys_dir(root, name), "signoff", "%s_signoff.md" % name)
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class SignoffRecordTests(RepoTest):
    def test_signoff_covers_every_item(self):
        name = "sgfull"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        for sid in range(1, 7):
            force_done(self.root, name, sid)
        confirm_milestone(self.root, name, "M1")
        confirm_milestone(self.root, name, "M2")
        for sid in range(7, 12):
            force_done(self.root, name, sid)
        _lint(self.root, name, ["alu"])
        _sim(self.root, name)
        _coverage(self.root, name)
        _midend(self.root, name)
        # 一条方向裁决：既是 S1 豁免的引用，也是带违例送审的裁决号。
        did = decide(self.root, name, "带违例送审的口径", "方向", 11)
        add_waiver(self.root, name, "S1", "info_input/%s_info_overview.md" % name, did)
        add_waiver(self.root, name, "sta-unconstrained", "sta", did)
        # 行 11 先主动退回进行中，再带违例送审（advance 的两种真用法）。
        advance(self.root, name, 11, "进行中")
        advance(self.root, name, 11, "已送审", allow_violation=True, decision=did)
        tick_report(self.root, name)
        render_signoff(self.root, name, load_state(self.root, name))
        text = _read_signoff(self.root, name)

        for phrase in ("## 1. 剖面与工具", "## 2. 模块、回归与覆盖率", "## 3. 综合与时序",
                       "## 4. 红线留痕", "## 5. 收尾核对"):
            self.assertIn(phrase, text)
        # 模块：最后一次 lint 记录号 + 模块摘要 + 派生态。
        self.assertIn("行 7 模块 alu：lint R", text)
        self.assertIn("模块摘要", text)
        self.assertIn("lint 通过", text)
        # 全量回归（用例数 × seed 数）与覆盖率四项 + 阈值来源。
        self.assertIn("全量回归：R", text)
        self.assertIn("用例 1 × seed 2", text)
        self.assertIn("line 100.0 / cond 98.0 / fsm 100.0 / tgl 95.0", text)
        self.assertIn("阈值来源：剖面缺省", text)
        # 综合与时序明细。
        self.assertIn("面积 1234.5", text)
        self.assertIn("latch 2", text)
        self.assertIn("slow：setup WNS 0.12", text)
        self.assertIn("hold WNS 0.05", text)
        self.assertIn("违例 0/1", text)
        self.assertIn("未约束端点 3", text)
        # 剖面与工具版本。
        self.assertIn("logic_synth T-2022.03", text)
        self.assertIn("timing_check T-2022.03", text)
        self.assertIn("rtl_sim V-2023.03", text)
        # 豁免清单（规则、位置、裁决号）与带违例送审的裁决号。
        self.assertIn("豁免：S1 info_input/sgfull_info_overview.md ← %s" % did, text)
        self.assertIn("带违例送审：停点 11 ← 裁决 %s" % did, text)
        # 里程碑：确认时间/语句 + M1/M2 当前有效性。
        self.assertIn("- 里程碑 M1：", text)
        self.assertIn("当前有效", text)
        self.assertIn("- 里程碑 M2：", text)
        self.assertIn("- 里程碑 M3：未确认", text)
        # 收尾核对。
        self.assertIn("在途调试事项：0（必须为 0）", text)
        self.assertIn("未关闭阻断：0（必须为 0）", text)
        self.assertIn("RTL 目录指纹：", text)
        self.assertIn("SDC 摘要：", text)
        # 没有确认语句时不得出现"待开发者"这类未确认先签核的措辞。
        self.assertNotIn("待开发者", text)

    def test_m3_confirm_quote_lands_in_signoff(self):
        name = "sgm3"
        init_sys(self.root, name)
        plant_sample(self.root, name)
        for sid in range(1, 11):
            force_done(self.root, name, sid)
        _midend(self.root, name)
        tick_report(self.root, name)
        render_signoff(self.root, name, load_state(self.root, name), confirm="sgm3 签核放行")
        self.assertIn("- 放行：sgm3 签核放行", _read_signoff(self.root, name))


if __name__ == "__main__":
    unittest.main()
