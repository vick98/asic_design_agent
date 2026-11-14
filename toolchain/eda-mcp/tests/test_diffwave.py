"""diffwave 测试：假 fsdbq 双/三文件的首分歧定位、时钟对齐与分歧簇。

三份假波形（时间 1ps）::

    top.u.err   A: 90000 变 1    B: 70000 变 1（最早分歧者）   C: 80000 变 1
    top.u.a     A/B 一致（70000 变 0010）
    top.u.b     A: 130000 变 0   B: 110000 变 0（110000 起分歧）
    top.clk     R 55000.. 步进 10000；F 60000.. 步进 10000

预期：事件口径首分歧 70000（err）；时钟沿口径首分歧 75000；三文件时 err 分
两簇（{A,C} vs {B}）。
"""

import os
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from eda_mcp.diffwave import first_divergence  # noqa: E402

FAKE = r"""#!/bin/sh
echo "logDir = /tmp/"
mode="$1"; FSDB="$2"; shift 2
FROM=-1; TO=-1
while [ $# -gt 0 ]; do
  case "$1" in
    --from) FROM="$2"; shift 2 ;;
    --to)   TO="$2"; shift 2 ;;
    --clock|--pattern|--max-changes) shift 2 ;;
    --*) shift 2 ;;
    *) break ;;
  esac
done
case "$FSDB" in
  *fail_b*) VARIANT=b ;;
  *run_c*)  VARIANT=c ;;
  *)        VARIANT=a ;;
esac
inwin() {  # inwin <t>：FROM/TO 为负表示该侧无界
  { [ "$FROM" -lt 0 ] || [ "$1" -ge "$FROM" ]; } && \
  { [ "$TO" -lt 0 ] || [ "$1" -le "$TO" ]; }
}
err_a() { printf '90000\tb1\n'; }
err_b() { printf '70000\tb1\n'; }
err_c() { printf '80000\tb1\n'; }
a_a()   { printf '70000\tb0010\n'; }
b_a()   { printf '130000\tb0\n'; }
b_b()   { printf '110000\tb0\n'; }
case "$mode" in
  info)
    printf 'I\tfile\t%s\n' "$FSDB"
    printf 'I\tscale_unit\t1ps\n'
    printf 'I\tmin_time\t50000\n'
    printf 'I\tmax_time\t200000\n'
    ;;
  vars)
    printf 'V\ttop.u.err\t11\t0\t0\treg\t0\n'
    printf 'V\ttop.u.a\t12\t3\t0\treg\t0\n'
    printf 'V\ttop.u.b\t13\t0\t0\treg\t0\n'
    printf 'V\ttop.clk\t14\t0\t0\treg\t0\n'
    ;;
  wave)
    i=0
    for sig in "$@"; do
      printf 'B\t%d\t%s\t%s\t4\t3\t0\n' "$i" "$sig" "$sig"
      printf 'P\t%d\t50000\t%s\n' "$i" "$1"  # 占位（下行覆盖真实种子）
      case "$sig" in
        top.u.err)
          case "$VARIANT" in a) C=$(err_a);; b) C=$(err_b);; c) C=$(err_c);; esac ;;
        top.u.a)
          case "$VARIANT" in b) C=$(a_a);; *) C=$(a_a);; esac ;;
        top.u.b)
          case "$VARIANT" in b) C=$(b_b);; *) C=$(b_a);; esac ;;
        top.clk) C="" ;;
      esac
      # 种子（P）
      case "$sig" in
        top.u.err)         printf 'P\t%d\t50000\tb0\n' "$i" ;;
        top.u.b)           printf 'P\t%d\t50000\tb1\n' "$i" ;;
        top.u.a)           printf 'P\t%d\t50000\tb0001\n' "$i" ;;
        top.clk)           printf 'P\t%d\t50000\tb0\n' "$i" ;;
      esac
      # 值变（W）
      printf '%s\n' "$C" | while IFS= read -r line; do
        [ -z "$line" ] && continue
        t=${line%%$'\t'*}
        v=${line#*$'\t'}
        if inwin "$t"; then
          printf 'W\t%d\t%s\t%s\n' "$i" "$t" "$v"
        fi
      done
      if [ "$sig" = "top.clk" ]; then
        printf 'C\ttop.clk\t10000\t0\t15\t15\n'
        k=0
        while [ $k -le 14 ]; do
          t=$((55000 + k*10000))
          if inwin "$t"; then
            printf 'R\t%d\n' "$t"
          fi
          k=$((k+1))
        done
      fi
      printf 'E\t%d\t3\t0\n' "$i"
      i=$((i+1))
    done
    ;;
esac
"""


class DiffWaveTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="eda_mcp_test_diff_")
        self.fsdbq = os.path.join(self.dir, "fsdbq")
        with open(self.fsdbq, "w") as fh:
            fh.write(FAKE)
        os.chmod(self.fsdbq, os.stat(self.fsdbq).st_mode | stat.S_IEXEC)
        self.pa = os.path.join(self.dir, "pass_a.fsdb")
        self.pb = os.path.join(self.dir, "fail_b.fsdb")
        self.pc = os.path.join(self.dir, "run_c.fsdb")
        for p in (self.pa, self.pb, self.pc):
            open(p, "w").close()

    def test_first_divergence_two_files(self):
        res = first_divergence([self.pa, self.pb], fsdbq=self.fsdbq)
        self.assertEqual(res["status"], "ok")
        # 相对时间轴：各文件 min_time=50000，err 在 B 于 rel 20000 变 1（abs 70000）
        self.assertEqual(res["first_divergence"], 20000)
        self.assertEqual([r["hier"] for r in res["signals"]], ["top.u.err", "top.u.b"])
        self.assertEqual(res["signals"][0]["values"], ["b0", "b1"])
        self.assertIsNone(res["groups"])

    def test_clock_aligned_sampling(self):
        # 只在上升沿比较（相对轴）：rel 25000 沿上 err 分歧（B 已变 1、A 还没）
        res = first_divergence([self.pa, self.pb], clock="top.clk", fsdbq=self.fsdbq)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["first_divergence"], 25000)
        self.assertEqual(res["signals"][0]["hier"], "top.u.err")

    def test_three_files_groups(self):
        res = first_divergence([self.pa, self.pb, self.pc], fsdbq=self.fsdbq)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["first_divergence"], 20000)
        self.assertIsNotNone(res["groups"])
        self.assertEqual(res["groups"]["signal"], "top.u.err")
        clusters = {tuple(c["files"]) for c in res["groups"]["clusters"]}
        self.assertEqual(clusters, {(0, 2), (1,)})

    def test_explicit_signals_and_window(self):
        res = first_divergence([self.pa, self.pb], signals=["top.u.b"], fsdbq=self.fsdbq)
        self.assertEqual(res["compared"], 1)
        self.assertEqual(res["first_divergence"], 60000)  # B 在 rel 60000 变 0
        # after=70000（相对量）：B 的变化在窗外，窗口内首分歧是 A 变 0 的 rel 80000
        res2 = first_divergence([self.pa, self.pb], signals=["top.u.b"],
                                after=70000, fsdbq=self.fsdbq)
        self.assertEqual(res2["first_divergence"], 80000)
        # after=90000：两份都已是 0 → 无分歧
        res3 = first_divergence([self.pa, self.pb], signals=["top.u.b"],
                                after=90000, fsdbq=self.fsdbq)
        self.assertIsNone(res3["first_divergence"])

    def test_need_two_files(self):
        res = first_divergence([self.pa], fsdbq=self.fsdbq)
        self.assertEqual(res["status"], "error")
        self.assertEqual(res["error_type"], "need_two_files")


if __name__ == "__main__":
    unittest.main()
