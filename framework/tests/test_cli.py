# 作者：vick 邮箱：ykun@yk9811.com

import json
import os
import subprocess
import sys
import unittest

from framework.engine import EngineError, _send_stop
from framework.flow import load
from framework.gates.docs import check_bloat
from framework.gates.rtl import compare_ports
from framework.state import init_sys, load_state, save, state_txn
from framework.tests.util import RepoTest, checkout_root


def _script():
    return os.path.join(checkout_root(), "script", "framework.py")


def _run(args, root):
    env = os.environ.copy()
    env["ADF_ROOT"] = root
    return subprocess.run(
        [sys.executable, _script()] + args,
        env=env, capture_output=True, text=True,
    )


class CliTests(unittest.TestCase):
    def test_readme_commands_are_in_help(self):
        with open(os.path.join(checkout_root(), "README.md"), encoding="utf-8") as fh:
            readme = fh.read()
        block = readme.split("## 命令", 1)[1].split("```", 2)[1]
        help_out = subprocess.check_output([sys.executable, _script(), "--help"], text=True)
        found = []
        for line in block.splitlines():
            line = line.strip()
            if not line.startswith("python3 script/framework.py"):
                continue
            cmd = line.split()[2]
            found.append(cmd)
            self.assertIn(cmd, help_out)
        self.assertGreaterEqual(len(found), 8)
        # 删掉的命令不得复活（README 已同步，这里只做反向守卫）。
        for gone in ("next-number", "enqueue", "dequeue", "replace-notes"):
            self.assertNotIn(gone, help_out, "已删除的命令 %s 不得再出现在 --help" % gone)

    def test_run_help_drops_unused_flags(self):
        help_out = subprocess.check_output(
            [sys.executable, _script(), "run", "--help"], text=True)
        self.assertNotIn("--record", help_out)
        self.assertNotIn("--lsb", help_out)


class CellTests(unittest.TestCase):
    def test_cell_escapes_pipe_and_newline_and_summary_first_line(self):
        from framework.state import _cell
        self.assertEqual(_cell("a|b"), "a\\|b")
        self.assertEqual(_cell("a\nb"), "a<br>b")
        self.assertEqual(_cell("第一行\n第二行", summary=True), "第一行")


class RuleIdTests(unittest.TestCase):
    def test_walk_mark_is_k1_and_param_mismatch_stays_m1(self):
        marks = check_bloat("## 2. 正文\n\nmark: todo\n", "doc.md")
        self.assertTrue(any(item["rule"] == "K1" for item in marks))
        self.assertFalse(any(item["rule"] == "M1" for item in marks))
        spec = (
            "## 3. 端口表\n\n| 名字 | 方向 | 位宽 |\n|---|---|---|\n"
            "| i_a | input | 8 |\n\n## 4. 参数\n\n| 参数名 |\n|---|\n| W |\n"
        )
        rtl = "module alu #(parameter X = 1) (input [7:0] i_a);\nendmodule\n"
        params = [item for item in compare_ports(spec, rtl, "alu") if item["rule"] == "M1"]
        self.assertTrue(params)


class DecisionCliTests(RepoTest):
    """两步链路的命令行面：阶段号只由 `--stop` 推导，来源只有
    `--from/--pick`（或 mark 收割）一条路，入库不需要任何放行令牌。

    原 DecisionStepCliTests 测的是 `--temp/--step/--confirm` 三件套与草稿回落，
    这三样随队列一起删除，用例改为在真实两步链路上断言同一批不变量。
    """

    def _commit(self, name, *args):
        return _run(["decision", name, "commit"] + list(args), self.root)

    def test_stage_is_derived_from_stop(self):
        # 原"step 与 stop 可以不一致"：不再有 --step，阶段号一律由 --stop 推导
        #（行 2→阶段 1、行 3→阶段 2、行 4→阶段 3）。
        name = "clistage"
        init_sys(self.root, name)
        for stop, stage, want, content in (
            ("2", "1", "D1-001", "帧窗口按行 2 口径"),
            ("3", "2", "D2-001", "缓存采用乒乓双缓冲结构"),
            ("4", "3", "D3-001", "接收定标缺省移位为零"),
        ):
            proc = self._commit(name, "--kind", "记录", "--stop", stop,
                                "--content", content)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn(want, proc.stdout)
            state = load_state(self.root, name)
            self.assertEqual(state["decisions"][stage][-1]["stop"], int(stop))
            self.assertEqual(state["decisions"][stage][-1]["content"], content)

    def test_record_commit_without_content_is_rejected(self):
        # 原 test_commit_empty_draft_is_rejected：草稿机制删除后，空正文仍不得入库。
        name = "clicontentempty"
        init_sys(self.root, name)
        proc = self._commit(name, "--kind", "记录", "--stop", "4")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("--content", proc.stderr)
        self.assertEqual(load_state(self.root, name)["seq"]["D"]["3"], 0)

    def test_direction_commit_needs_a_pick_source_not_a_token(self):
        # 旧断言：方向类入库缺放行令牌被拒（"令牌"）。令牌已删除，人的按点落在
        # --from/--pick 上：无来源被拒的是"点选来源"，补上后不要任何令牌即入库。
        name = "clidir"
        init_sys(self.root, name)
        without = self._commit(name, "--kind", "方向", "--content", "接口归属取甲",
                               "--stop", "2")
        self.assertEqual(without.returncode, 1)
        self.assertIn("必须有点选来源", without.stderr)
        self.assertNotIn("令牌", without.stderr)
        self.assertEqual(load_state(self.root, name)["decisions"]["1"], [])
        added = _run(["problem", name, "add", "--kind", "待裁决", "--stop", "2",
                      "--text", "接口归属取甲还是取乙", "--options", "取甲|取乙"], self.root)
        self.assertEqual(added.returncode, 0, added.stderr)
        pid = added.stdout.strip().splitlines()[-1]
        self.assertRegex(pid, r"^I\d{3}$")
        proc = self._commit(name, "--kind", "方向", "--from", pid, "--pick", "取乙")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("D1-001", proc.stdout)
        state = load_state(self.root, name)
        row = state["decisions"]["1"][0]
        self.assertEqual(row["kind"], "方向")
        self.assertEqual(row["content"], "接口归属取甲还是取乙：取乙",
                         "缺省正文带问题原文与所选项")
        self.assertEqual(row["source"], "%s/取乙" % pid)
        self.assertEqual(next(p for p in state["problems"] if p["id"] == pid)["evidence"],
                         "D1-001", "点选入库自动关闭问题并以裁决为证据")
        self.assertNotIn("queue", state)

    def test_deleted_decision_actions_and_flags_are_gone(self):
        # enqueue/dequeue/replace-notes 与 --temp/--step/--confirm 不留兼容壳：
        # --help 里不得出现，调用直接报参数错（退出码 2）。
        decision_help = subprocess.check_output(
            [sys.executable, _script(), "decision", "--help"], text=True)
        for flag in ("--temp", "--step", "--confirm", "--enqueue", "--dequeue"):
            self.assertNotIn(flag, decision_help)
        self.assertIn("{commit,list,similar,withdraw,override}", decision_help)
        top_help = subprocess.check_output([sys.executable, _script(), "--help"], text=True)
        self.assertNotIn("next-number", top_help)
        name = "cligone"
        init_sys(self.root, name)
        for args in (["decision", name, "enqueue", "--content", "x"],
                     ["decision", name, "dequeue", "--id", "T001"],
                     ["decision", name, "replace-notes"],
                     ["next-number", name, "T"]):
            proc = _run(args, self.root)
            self.assertEqual(proc.returncode, 2, "%s 应报参数错误：%s" % (args, proc.stderr))


class GateParityTests(RepoTest):
    def test_gate_json_matches_engine_send_path_for_every_stop(self):
        # 送审闸门现在是 tick（里程碑归属停点）与带违例送审共用的 `_send_stop`：
        # advance 的普通送审已收窄为 no-op，引擎侧的对照入口随之换成它。
        # 断言的仍是"gate --json 与引擎送审闸门报的 findings 逐条一致"。
        name = "gateparity"
        init_sys(self.root, name)
        for sid in range(1, 13):
            state = load_state(self.root, name)
            for row in state["stops"]:
                cur = int(row["id"])
                if cur < sid:
                    row["state"] = "完成（审核通过）"
                elif cur == sid:
                    row["state"] = "进行中"
                else:
                    row["state"] = "未开始"
            # enter_structure 字段已随 schema 迁移删除；进入行 5 只看上一停点完成。
            save(self.root, name, state)
            proc = _run(["gate", name, "--stop", str(sid), "--json"], self.root)
            payload = json.loads(proc.stdout)
            try:
                with state_txn(self.root, name, cmd="gateparity") as st:
                    _send_stop(self.root, name, st, load()["by_id"][sid], False)
                advanced = []
            except EngineError as exc:
                advanced = list(exc.findings)
            self.assertEqual(payload["findings"], advanced, "stop %d" % sid)


class RunUnavailableExitCodeTests(RepoTest):
    """剖面把能力声明为 unavailable 时，`run` 用独立退出码 3：它不是"通过"。"""

    def setUp(self):
        super().setUp()
        self.name = "unavail"
        init_sys(self.root, self.name)
        # _template 剖面把全部能力声明为 available: false，run 走 unavailable 分支。
        with open(os.path.join(self.root, "toolchain", "active"), "w",
                  encoding="utf-8") as fh:
            fh.write("_template\n")

    def test_unavailable_exits_three_with_exempt_path_hint(self):
        proc = _run(["run", "lint", "--sys", self.name], self.root)
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
        out = proc.stdout + proc.stderr
        self.assertIn("status: unavailable", proc.stdout)
        self.assertIn("当前剖面未提供 lint", out)
        self.assertIn("走规则与裁决豁免路径", out)


if __name__ == "__main__":
    unittest.main()
