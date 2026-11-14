"""wave_extract 测试：用假 fsdbq 行协议验证采样、valid 门控与文件输出。

假 fsdbq 的波形（时间单位 fsdb 原值）::

    top.clk       posedge 55000/65000/75000/85000/95000, negedge 60000/70000/80000/90000
    top.u.valid   50000=b0, 70000=b1, 88000=b0
    top.u.data    50000=b0001, 76000=b0002, 84500=b0003
    top.u.q       50000=b0101, 98000=b0110

假 fsdbq 支持 --from/--to 过滤 R/F 沿（与真 fsdbq 的窗口行为一致），并把每次
调用的参数追加到 $EDA_MCP_TEST_ARGS_LOG，用于断言 ``--max-changes 0``（不抽稀）。
"""

import json
import os
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from eda_mcp.config import Config, defaults  # noqa: E402
from eda_mcp.fsdb import FsdbError  # noqa: E402
from eda_mcp.server import wave_extract  # noqa: E402

FAKE = r"""#!/bin/sh
# 假 fsdbq：$1=mode $2=fsdb，其余为选项与信号
echo "logDir = /tmp/"
if [ -n "$EDA_MCP_TEST_ARGS_LOG" ]; then
  printf '%s\n' "$*" >> "$EDA_MCP_TEST_ARGS_LOG"
fi
mode="$1"; shift
FROM=-1; TO=-1
while [ $# -gt 0 ]; do
  case "$1" in
    --from) FROM="$2"; shift 2 ;;
    --to)   TO="$2"; shift 2 ;;
    *) shift ;;
  esac
done
edge() {  # edge TAG TIME：窗口过滤后输出 R/F 行
  if [ "$FROM" -lt 0 ] || { [ "$2" -ge "$FROM" ] && [ "$2" -le "$TO" ]; }; then
    printf '%s\t%s\n' "$1" "$2"
  fi
}
case "$mode" in
  info)
    printf 'I\tfile\t%s\n' "$FSDB_PATH"
    printf 'I\tscale_unit\t1ps\n'
    printf 'I\tmin_time\t50000\n'
    printf 'I\tmax_time\t100000\n'
    ;;
  wave)
    printf 'B\t0\ttop.clk\ttop.clk\t1\t0\t0\n'
    printf 'B\t1\ttop.u.valid\ttop.u.valid\t1\t0\t0\n'
    printf 'B\t2\ttop.u.data\ttop.u.data\t4\t3\t0\n'
    printf 'B\t3\ttop.u.q\ttop.u.q\t4\t3\t0\n'
    printf 'C\ttop.clk\t10000\t0\t9\t5\n'
    edge R 55000
    edge F 60000
    edge R 65000
    edge F 70000
    edge R 75000
    edge F 80000
    edge R 85000
    edge F 90000
    edge R 95000
    printf 'P\t1\t50000\tb0\n'
    printf 'W\t1\t70000\tb1\n'
    printf 'W\t1\t88000\tb0\n'
    printf 'P\t2\t50000\tb0001\n'
    printf 'W\t2\t76000\tb0002\n'
    printf 'W\t2\t84500\tb0003\n'
    printf 'P\t3\t50000\tb0101\n'
    printf 'W\t3\t98000\tb0110\n'
    printf 'E\t0\t5\t0\n'
    printf 'Z\tclock\ttop.clk\n'
    ;;
esac
"""


def _mk_fake(dirpath):
    path = os.path.join(dirpath, "fsdbq")
    with open(path, "w") as fh:
        fh.write(FAKE)
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


class TestWaveExtract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.fsdbq = _mk_fake(self.tmp)
        self.fsdb_path = os.path.join(self.tmp, "fake.fsdb")
        with open(self.fsdb_path, "w"):
            pass
        self.out_dir = os.path.join(self.tmp, "out")
        self.args_log = os.path.join(self.tmp, "args.log")
        self._saved_env = os.environ.get("EDA_MCP_TEST_ARGS_LOG")
        os.environ["EDA_MCP_TEST_ARGS_LOG"] = self.args_log
        data = defaults()
        data["fsdb"]["fsdbq_bin"] = self.fsdbq
        self.cfg = Config(data)

    def tearDown(self):
        if self._saved_env is None:
            os.environ.pop("EDA_MCP_TEST_ARGS_LOG", None)
        else:
            os.environ["EDA_MCP_TEST_ARGS_LOG"] = self._saved_env

    def _extract(self, **kw):
        kw.setdefault("cfg", self.cfg)
        kw.setdefault("path", self.fsdb_path)
        kw.setdefault("clock", "top.clk")
        kw.setdefault("nodes", ["data=top.u.data", "q=top.u.q"])
        kw.setdefault("out_dir", self.out_dir)
        return json.loads(wave_extract(**kw))

    # ---- valid 门控与拍号 ----
    def test_valid_gating_and_beat_numbering(self):
        res = self._extract(valid="top.u.valid")
        # posedge 5 个；valid 在 75000/85000 为 1（88000 起回 0，95000 排除）
        self.assertEqual(res["clock_edges"], 5)
        self.assertEqual(res["beats"], 2)
        self.assertEqual(res["edge"], "posedge")
        # 拍号按放行的拍从 0 编号；值取 <= 沿时刻的最近值变
        self.assertEqual(
            _read(res["nodes"][0]["file"]).splitlines(),
            ["0 75000 b0001", "1 85000 b0003"],
        )

    def test_no_valid_records_every_edge(self):
        res = self._extract()
        self.assertEqual(res["beats"], res["clock_edges"])
        self.assertEqual(res["beats"], 5)
        for node in res["nodes"]:
            self.assertEqual(node["lines"], 5)
        self.assertEqual(_read(res["nodes"][0]["file"]).splitlines()[-1], "4 95000 b0003")

    def test_negedge_sampling(self):
        res = self._extract(edge="negedge", valid="top.u.valid")
        # negedge 60000/70000/80000/90000：valid 为 1 的是 70000/80000
        self.assertEqual(res["edge"], "negedge")
        self.assertEqual(res["beats"], 2)
        self.assertEqual(
            _read(res["nodes"][0]["file"]).splitlines(),
            ["0 70000 b0001", "1 80000 b0002"],
        )

    def test_time_window(self):
        res = self._extract(start=56000, end=86000)
        # 窗口内 posedge 只剩 65000/75000/85000（假 fsdbq 过滤 R 行）
        self.assertEqual(res["beats"], 3)
        self.assertEqual(_read(res["nodes"][1]["file"]).splitlines(),
                         ["0 65000 b0101", "1 75000 b0101", "2 85000 b0101"])

    # ---- 多节点各写一个文件 ----
    def test_one_file_per_node(self):
        res = self._extract(valid="top.u.valid")
        files = [n["file"] for n in res["nodes"]]
        self.assertEqual(len(files), 2)
        self.assertEqual(len(set(files)), 2)
        for f in files:
            self.assertTrue(os.path.isfile(f))
        self.assertEqual([n["name"] for n in res["nodes"]], ["data", "q"])
        self.assertEqual([n["resolved"] for n in res["nodes"]], ["top.u.data", "top.u.q"])
        self.assertEqual([n["lines"] for n in res["nodes"]], [2, 2])

    # ---- 不抽稀 ----
    def test_no_thinning_max_changes_zero(self):
        res = self._extract()
        with open(self.args_log, "r", encoding="utf-8") as fh:
            calls = fh.read().splitlines()
        self.assertEqual(len(calls), 1)
        tokens = calls[0].split("\t") if "\t" in calls[0] else calls[0].split()
        self.assertIn("--max-changes", tokens)
        self.assertEqual(tokens[tokens.index("--max-changes") + 1], "0")
        # 密集值变下 5 个沿逐拍全在
        self.assertEqual(len(_read(res["nodes"][0]["file"]).splitlines()), 5)

    # ---- 输出契约 ----
    def test_json_contract(self):
        res = self._extract(valid="top.u.valid", start=50000, end=95000)
        for key in ("fsdb", "out_dir", "clock", "edge", "valid", "start", "end",
                    "clock_edges", "beats", "nodes"):
            self.assertIn(key, res)
        self.assertEqual(res["clock"], "top.clk")
        self.assertEqual(res["valid"], "top.u.valid")
        self.assertEqual(res["start"], 50000)
        self.assertEqual(res["end"], 95000)
        node = res["nodes"][0]
        for key in ("name", "path", "resolved", "width", "file", "lines"):
            self.assertIn(key, node)
        self.assertEqual(node["width"], 4)
        self.assertTrue(os.path.isabs(node["file"]))

    # ---- 错误处理 ----
    def test_unknown_node_raises(self):
        with self.assertRaises(FsdbError):
            self._extract(nodes=["x=top.u.nope"])

    def test_unknown_valid_raises(self):
        with self.assertRaises(FsdbError):
            self._extract(valid="top.u.nope")

    def test_bad_edge_raises(self):
        with self.assertRaises(FsdbError):
            self._extract(edge="both")

    def test_bad_node_form_raises(self):
        with self.assertRaises(FsdbError):
            self._extract(nodes=["no_equal_sign"])

    def test_missing_out_dir_raises(self):
        with self.assertRaises(FsdbError):
            self._extract(out_dir=None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
