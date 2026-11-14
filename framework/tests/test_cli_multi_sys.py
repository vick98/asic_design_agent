# 作者：vick 邮箱：ykun@yk9811.com

"""`status` 不带子系统名时列出仓库内全部子系统。

- 每个含 `state.json` 的子系统一行：名字、当前停点名字、是否有等待开发者的事项；
- 纯只读：不写 `state.json`、不记事件；
- 没有子系统时给出提示而不是报错；
- `--json` 同样支持不带子系统名（输出行结构数组）。
"""

import json
import os

from framework.engine import add_problem
from framework.state import init_sys
from framework.tests.util import RepoTest, cli, plant_sample


def _snapshot(base):
    rows = {}
    for dirpath, _dirnames, files in os.walk(base):
        for fn in sorted(files):
            path = os.path.join(dirpath, fn)
            stat = os.stat(path)
            with open(path, "rb") as fh:
                rows[os.path.relpath(path, base)] = (stat.st_mtime_ns, fh.read())
    return rows


class MultiSystemStatusTests(RepoTest):
    def setUp(self):
        super().setUp()
        self.names = ("alphamssys", "betamssys")
        for name in self.names:
            init_sys(self.root, name)
            plant_sample(self.root, name)
        # 让 beta 有一个等开发者点选的待裁决问题：它的"等待开发者"一栏要为"有"。
        add_problem(self.root, "betamssys", "待裁决", 2, "帧窗口取行 2 还是行 3 口径",
                    options="行 2|行 3")

    def _line_of(self, text, name):
        lines = [line for line in text.splitlines() if name in line]
        self.assertEqual(len(lines), 1, "子系统 %s 应正好一行：%r" % (name, text))
        return lines[0]

    def test_lists_every_subsystem_with_current_stop(self):
        proc = cli(self.root, "status")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        alpha = self._line_of(proc.stdout, "alphamssys")
        beta = self._line_of(proc.stdout, "betamssys")
        for line in (alpha, beta):
            self.assertIn("信息输入", line, line)
        self.assertIn("等待开发者 无", alpha)
        self.assertIn("等待开发者 有", beta)
        self.assertNotIn("Traceback", proc.stderr)

    def test_overview_is_read_only(self):
        before = {name: _snapshot(os.path.join(self.root, name)) for name in self.names}
        proc = cli(self.root, "status")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        after = {name: _snapshot(os.path.join(self.root, name)) for name in self.names}
        self.assertEqual(before, after, "status 多子系统清单不得写状态或事件")

    def test_json_overview_lists_rows(self):
        proc = cli(self.root, "status", "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        rows = json.loads(proc.stdout)
        self.assertEqual(sorted(row["sys"] for row in rows), sorted(self.names))
        for row in rows:
            self.assertEqual(row["current"], "信息输入")
            self.assertEqual(row["current_stop"], 1)
            self.assertIsInstance(row["human"], int)
        by_name = {row["sys"]: row for row in rows}
        self.assertEqual(by_name["alphamssys"]["human"], 0)
        self.assertGreaterEqual(by_name["betamssys"]["human"], 1)


class NoSystemStatusTests(RepoTest):
    def test_no_subsystem_prints_a_hint(self):
        proc = cli(self.root, "status")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("没有含 state.json 的子系统", proc.stdout)

    def test_no_subsystem_json_is_an_empty_list(self):
        proc = cli(self.root, "status", "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout), [])
