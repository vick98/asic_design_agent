"""timequery 测试：用假 fsdbq 行协议验证谓词时间窗的事件扫描。

假波形（时间单位 fsdb 原值，1ps）::

    top.u.valid   50000=b0, 70000=b1, 120000=b0, 150000=b1
    top.u.cnt     50000=b0000, 60000=b0001, 80000=b0010, 100000=b0001, 140000=b0010
    top.u.bad     恒 x（验证 undecidable 单列，绝不计入命中）

预期（``valid == 1 && cnt > 1``）：[80000,100000) 与 [150000,200000)（open_ended）。
"""

import json
import os
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from eda_mcp.fsdb import Fsdb  # noqa: E402
from eda_mcp.timequery import eval_at_time, find_time_windows  # noqa: E402

FAKE = r"""#!/bin/sh
echo "logDir = /tmp/"
mode="$1"; shift 2
FROM=-1; TO=-1
while [ $# -gt 0 ]; do
  case "$1" in
    --from) FROM="$2"; shift 2 ;;
    --to)   TO="$2"; shift 2 ;;
    --clock|--pattern) shift 2 ;;
    --max-changes) shift 2 ;;
    *) break ;;
  esac
done
inwin() {  # FROM/TO 为负表示该侧无界
  { [ "$FROM" -lt 0 ] || [ "$1" -ge "$FROM" ]; } && \
  { [ "$TO" -lt 0 ] || [ "$1" -le "$TO" ]; }
}
seed_val() {
  case "$1" in
    top.u.valid) echo "b0" ;;
    top.u.cnt)   echo "b0000" ;;
    top.u.bad)   echo "bx" ;;
  esac
}
changes() {
  case "$1" in
    top.u.valid) printf '70000\tb1\n120000\tb0\n150000\tb1\n' ;;
    top.u.cnt)   printf '60000\tb0001\n80000\tb0010\n100000\tb0001\n140000\tb0010\n' ;;
    top.u.bad)   printf '' ;;
  esac
}
case "$mode" in
  info)
    printf 'I\tfile\t%s\n' "$FSDB_PATH"
    printf 'I\tscale_unit\t1ps\n'
    printf 'I\tmin_time\t50000\n'
    printf 'I\tmax_time\t200000\n'
    ;;
  wave)
    i=0
    for sig in "$@"; do
      case "$sig" in
        *nosuch*) printf 'N\t%d\t%s\n' "$i" "$sig"; i=$((i+1)); continue ;;
      esac
      printf 'B\t%d\t%s\t%s\t4\t3\t0\n' "$i" "$sig" "$sig"
      seed=$(seed_val "$sig")
      printf 'P\t%d\t50000\t%s\n' "$i" "$seed"
      changes "$sig" | while IFS="$(printf '\t')" read -r t v; do
        if inwin "$t"; then
          printf 'W\t%d\t%s\t%s\n' "$i" "$t" "$v"
        fi
      done
      printf 'E\t%d\t3\t0\n' "$i"
      i=$((i+1))
    done
    ;;
esac
"""


class TimeQueryTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="eda_mcp_test_tq_")
        self.fsdbq = os.path.join(self.dir, "fsdbq")
        with open(self.fsdbq, "w") as fh:
            fh.write(FAKE)
        os.chmod(self.fsdbq, os.stat(self.fsdbq).st_mode | stat.S_IEXEC)
        self.fsdb = os.path.join(self.dir, "wave_case1.fsdb")
        open(self.fsdb, "w").close()
        os.environ["FSDB_PATH"] = self.fsdb
        self.fs = Fsdb(self.fsdb, fsdbq=self.fsdbq)

    def tearDown(self):
        os.environ.pop("FSDB_PATH", None)

    def test_windows_expected_intervals(self):
        res = find_time_windows(self.fs, "top.u.valid == 1 && top.u.cnt > 1", 50000, 200000)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["total_hits"], 2)
        self.assertEqual(res["hits"], [
            {"start": 80000, "end": 100000, "duration": 20000, "open_ended": False},
            {"start": 150000, "end": 200000, "duration": 50000, "open_ended": True},
        ])
        self.assertEqual(res["undecidable_time"], 0)
        self.assertFalse(res["truncated"])

    def test_min_duration_filter(self):
        res = find_time_windows(self.fs, "top.u.valid == 1 && top.u.cnt > 1",
                                50000, 200000, min_duration=30000)
        self.assertEqual(res["total_hits"], 1)
        self.assertEqual([h["start"] for h in res["hits"]], [150000])

    def test_window_subrange(self):
        # 只看 [60000, 120000]：命中 [80000,100000)，末端 120000 处已变 false
        res = find_time_windows(self.fs, "top.u.valid == 1 && top.u.cnt > 1", 60000, 120000)
        self.assertEqual(res["hits"], [
            {"start": 80000, "end": 100000, "duration": 20000, "open_ended": False},
        ])
        # 窗口里没有事件变化（比如 [51000,59000] 恒 false）→ 空结果
        res2 = find_time_windows(self.fs, "top.u.valid == 1", 51000, 59000)
        self.assertEqual(res2["hits"], [])
        self.assertEqual(res2["total_hits"], 0)

    def test_undecidable_never_counts_as_hit(self):
        res = find_time_windows(self.fs, "top.u.bad == 1", 50000, 200000)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["hits"], [])
        self.assertEqual(res["total_hits"], 0)
        self.assertEqual(res["undecidable_time"], 150000)

    def test_missing_signal(self):
        res = find_time_windows(self.fs, "top.u.nosuch == 1", 50000, 200000)
        self.assertEqual(res["status"], "error")
        self.assertEqual(res["error_type"], "signal_not_found")
        self.assertIn("top.u.nosuch", res["missing"])

    def test_invalid_expr_and_window(self):
        res = find_time_windows(self.fs, "top.u.valid ==", 50000, 200000)
        self.assertEqual(res["status"], "error")
        self.assertEqual(res["error_type"], "invalid_expression")
        res2 = find_time_windows(self.fs, "top.u.valid == 1", 200000, 50000)
        self.assertEqual(res2["status"], "error")
        self.assertEqual(res2["error_type"], "invalid_window")

    def test_max_hits_truncation(self):
        # max_hits=1 时第二条只计数不列出
        res = find_time_windows(self.fs, "top.u.valid == 1 && top.u.cnt > 1",
                                50000, 200000, max_hits=1)
        self.assertEqual(len(res["hits"]), 1)
        self.assertEqual(res["total_hits"], 2)
        self.assertTrue(res["truncated"])

    def test_eval_at_time(self):
        res = eval_at_time(self.fs, "top.u.valid == 1 && top.u.cnt > 1", 80000)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["truth"], "true")
        self.assertEqual(res["values"]["top.u.valid"], "b1")
        self.assertEqual(res["values"]["top.u.cnt"], "b0010")
        res2 = eval_at_time(self.fs, "top.u.valid == 1 && top.u.cnt > 1", 60000)
        self.assertEqual(res2["truth"], "false")

    def test_json_serializable(self):
        res = find_time_windows(self.fs, "top.u.valid == 1 && top.u.cnt > 1", 50000, 200000)
        # 结果必须是纯 JSON 类型（dbg/CLI 落盘用）
        json.dumps(res)


if __name__ == "__main__":
    unittest.main()
