"""join 层测试：FSDB×NPI 联立（假 fsdbq + 假 NpiClient）。

假设计：``demo_sys_top.gen_w08.op_blk_w08``（op_blk 的 a_r/y_c/y_r 链），
FSDB 里挂在 ``demo_sys_sim_top.u_dut.`` 前缀下。时间线（1ps）::

    clk_in 上升沿  60000/70000/80000/90000
    a_in           50000=b00000011, 70000=b00000100
    a_r            50000=b00000011, 71000=b00000100（70000 沿采集）
    b_r/c_r/d_r    恒 3/0/0
    y_c            50000=b...1001(9), 71000=b...1100(12)
    y_r            50000=b...1001(9), 81000=b...1100(12)（80000 沿采集）

X 场景单独一条 c_in/c_r 恒 x 的支路。
"""

import os
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from eda_mcp.fsdb import Fsdb  # noqa: E402
from eda_mcp.join import (  # noqa: E402
    JoinError,
    Mapping,
    active_drivers,
    map_target,
    state_transitions,
    trace_value,
)
from eda_mcp.npi import HierNode, NpiError, ObjInfo, TraceHit  # noqa: E402

P = "demo_sys_top.gen_w08.op_blk_w08."
F = "demo_sys_sim_top.u_dut." + P

FAKE = r"""#!/bin/sh
echo "logDir = /tmp/"
mode="$1"; shift 2
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
inwin() {
  { [ "$FROM" -lt 0 ] || [ "$1" -ge "$FROM" ]; } && \
  { [ "$TO" -lt 0 ] || [ "$1" -le "$TO" ]; }
}
seed() {
  case "$1" in
    *a_in)  echo "b00000011" ;;
    *a_r)   echo "b00000011" ;;
    *b_r)   echo "b00000011" ;;
    *c_r)   case "$FSDB_PATH" in *wave_x*) echo "bx" ;; *) echo "b00000000" ;; esac ;;
    *d_r)   echo "b00000000" ;;
    *c_in)  case "$FSDB_PATH" in *wave_x*) echo "bx" ;; *) echo "b00000000" ;; esac ;;
    *y_c)   echo "b0000000000001001" ;;
    *y_r)   echo "b0000000000001001" ;;
    *clk_in) echo "b0" ;;
    *) echo "" ;;
  esac
}
W() {
  case "$1" in
    *a_in)  echo "70000	b00000100" ;;
    *a_r)   echo "71000	b00000100" ;;
    *y_c)   case "$FSDB_PATH" in *wave_x*) echo "71000	bxxxxxxxxxxxxxxxx" ;; *) echo "71000	b0000000000001100" ;; esac ;;
    *y_r)   case "$FSDB_PATH" in *wave_x*) echo "81000	bxxxxxxxxxxxxxxxx" ;; *) echo "81000	b0000000000001100" ;; esac ;;
    *)      echo "" ;;
  esac
}
case "$mode" in
  info)
    printf 'I\tfile\t%s\n' "$FSDB_PATH"
    printf 'I\tscale_unit\t1ps\n'
    printf 'I\tmin_time\t50000\n'
    printf 'I\tmax_time\t200000\n'
    ;;
  vars)
    printf 'V\t%sclk_in\t1\t0\t0\treg\t0\n' "$FSDB_SCOPE_PREFIX"
    ;;
  wave)
    i=0
    for sig in "$@"; do
      case "$sig" in
        *clk_in)
          printf 'B\t%d\t%s\t%s\t1\t0\t0\n' "$i" "$sig" "$sig"
          printf 'P\t%d\t50000\tb0\n' "$i"
          printf 'C\t%s\t10000\t0\t15\t15\n' "$sig"
          k=0
          while [ $k -lt 15 ]; do
            t=$((60000 + k*10000))
            if inwin "$t"; then printf 'R\t%d\n' "$t"; fi
            k=$((k+1))
          done
          printf 'E\t%d\t0\t0\n' "$i"
          i=$((i+1)); continue ;;
      esac
      w=$(W "$sig")
      if [ -z "$w" ] && [ -z "$(seed "$sig")" ]; then
        printf 'N\t%d\t%s\n' "$i" "$sig"; i=$((i+1)); continue
      fi
      case "$sig" in
        *clk_in) WID=1; MSB=0 ;;
        *y_c|*y_r|*y_out) WID=16; MSB=15 ;;
        *) WID=8; MSB=7 ;;
      esac
      printf 'B\t%d\t%s\t%s\t%d\t%d\t0\n' "$i" "$sig" "$sig" "$WID" "$MSB"
      s=$(seed "$sig"); printf 'P\t%d\t50000\t%s\n' "$i" "$s"
      printf '%s\n' "$w" | while IFS= read -r line; do
        [ -z "$line" ] && continue
        t=${line%%"	"*}; v=${line#*"	"}
        if inwin "$t"; then printf 'W\t%d\t%s\t%s\n' "$i" "$t" "$v"; fi
      done
      printf 'E\t%d\t1\t0\n' "$i"
      i=$((i+1))
    done
    ;;
esac
"""


class FakeNpi:
    """假 NpiClient：只认识 NPI 命名空间（demo_sys_top.*）的对象。"""

    def __init__(self, x_scenario=False):
        self.x = x_scenario

    def hierarchy(self, root=None, max_depth=None, pattern=None):
        return [HierNode(depth=0, full="demo_sys_top", def_name="demo_sys_top")]

    def object(self, path):
        parts = path.split(".")
        # 只认识真实子树：demo_sys_top[.gen_wXX.op_YY_wZZ.<leaf>]
        if parts[0] != "demo_sys_top" or (len(parts) > 1 and parts[1] != "gen_w08"):
            raise NpiError("对象不存在: %s" % path)
        width = 1 if path.endswith("clk_in") or path.endswith("wir_rst_n_sync") else 8
        if path.endswith("y_c") or path.endswith("y_r") or path.endswith("y_out"):
            width = 16
        return ObjInfo(full=path, type="npiReg", name=path.rsplit(".", 1)[-1],
                       width=width, file="op_blk.sv", line=40)

    def trace(self, path, direction="both", limit=200):
        if not path.startswith("demo_sys_top."):
            raise NpiError("对象不存在: %s" % path)
        leaf = path.rsplit(".", 1)[-1]
        out = []
        if leaf in ("a_r", "b_r", "c_r", "d_r"):
            base = path.rsplit(".", 1)[0]
            out.append(TraceHit("driver", "npiNet", base + "." + leaf[0] + "_in"))
            out.append(TraceHit("driver", "npiConstant", "[unnamed:npiConstant]"))
        elif leaf == "y_c":
            if self.x:
                out.append(TraceHit("driver", "npiNet", P + "c_r"))
            else:
                out.append(TraceHit("driver", "npiNet", P + "a_r"))
                out.append(TraceHit("driver", "npiNet", P + "b_r"))
                out.append(TraceHit("driver", "npiNet", P + "c_r"))
                out.append(TraceHit("driver", "npiNet", P + "d_r"))
        elif leaf == "y_r":
            out.append(TraceHit("driver", "npiNet", P + "y_c"))
        return out

    def stmtmap(self, root="", max_depth=8, limit=5000):
        return [
            {"lhs": P + "y_c", "lhs_text": "y_c", "file": "op_blk.sv", "line": 63,
             "rhs": "((a_r * b_r) + (c_r * d_r))"},
            {"lhs": P + "y_out", "lhs_text": "y_out", "file": "op_blk.sv", "line": 74,
             "rhs": "y_r"},
        ]


class JoinTests(unittest.TestCase):
    def setUp(self, x_scenario=False):
        self.dir = tempfile.mkdtemp(prefix="eda_mcp_test_join_")
        self.fsdbq = os.path.join(self.dir, "fsdbq")
        with open(self.fsdbq, "w") as fh:
            fh.write(FAKE)
        os.chmod(self.fsdbq, os.stat(self.fsdbq).st_mode | stat.S_IEXEC)
        # X 场景用独立文件名：fake 按文件名切到 x 时间线（c_r/c_in/y_c 恒 x）
        name = "wave_x.fsdb" if x_scenario else "wave_case1.fsdb"
        self.fsdb = os.path.join(self.dir, name)
        open(self.fsdb, "w").close()
        os.environ["FSDB_PATH"] = self.fsdb
        self.fs = Fsdb(self.fsdb, fsdbq=self.fsdbq)
        self.npi = FakeNpi(x_scenario=x_scenario)

    def tearDown(self):
        os.environ.pop("FSDB_PATH", None)

    def _map(self):
        target = F + "a_r"
        m = map_target(self.fs, self.npi, target)
        self.assertEqual(m.fsdb_prefix, "demo_sys_sim_top.u_dut.")
        self.assertEqual(m.npi_target, P + "a_r")
        return m

    def test_map_target(self):
        self._map()

    def test_map_target_rejects_unknown(self):
        with self.assertRaises(JoinError):
            map_target(self.fs, self.npi, "demo_sys_sim_top.nothere.sig")

    def test_trace_value_chain(self):
        m = self._map()
        res = trace_value(self.fs, self.npi, m, F + "y_r", 90000, depth=4)
        self.assertEqual(res["status"], "ok")
        paths = [n["path"] for n in res["nodes"]]
        self.assertIn(F + "y_r", paths)
        self.assertIn(F + "y_c", paths)
        self.assertIn(F + "a_r", paths)
        self.assertIn(F + "a_in", paths)
        by_path = {n["path"]: n for n in res["nodes"]}
        # 90000 时刻：y_r 已在 81000 变 12
        self.assertEqual(by_path[F + "y_r"]["value"], "b0000000000001100")
        # y_c 节点挂了连续赋值语句语境（file:line=63）
        self.assertEqual(by_path[F + "y_c"]["stmt"]["line"], 63)
        self.assertIn("a_r", by_path[F + "y_c"]["stmt"]["rhs"])
        # 驱动链：y_c 的 driver 里含 a_r/b_r/c_r/d_r
        drv = [d["path"] for d in by_path[F + "y_c"]["drivers"]]
        self.assertIn(F + "c_r", drv)
        # 常量驱动标注为 constant
        a_r_drv = by_path[F + "a_r"]["drivers"]
        self.assertTrue(any(d["kind"] == "constant" for d in a_r_drv))

    def test_trace_value_missing_signal(self):
        m = self._map()
        res = trace_value(self.fs, self.npi, m, "demo_sys_sim_top.u_dut.nosuch", 90000)
        self.assertEqual(res["status"], "error")
        self.assertEqual(res["error_type"], "signal_not_found")

    def test_trace_x_finds_root(self):
        # X 场景：y_c 只挂 c_r，c_r/c_in 恒 x
        self.setUp(x_scenario=True)
        m = map_target(self.fs, self.npi, F + "y_c")
        res = trace_value(self.fs, self.npi, m, F + "y_c", 90000, depth=4, x_only=True)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["mode"], "trace_x")
        roots = [r["path"] for r in res["x_roots"]]
        # c_in 是恒 x 且不再有信号驱动的叶子（X 根因候选）
        self.assertIn(F + "c_in", roots)
        # a_r 干净支路不被展开
        paths = [n["path"] for n in res["nodes"]]
        self.assertNotIn(F + "a_r", paths)

    def test_active_drivers_with_clock(self):
        m = self._map()
        res = active_drivers(self.fs, self.npi, m, F + "y_r", 81500,
                             clock=F + "clk_in")
        self.assertEqual(res["status"], "ok")
        # 90000 之前最后一个上升沿是 80000；驱动值取沿前一时刻（同时间戳上
        # 组合更新与 NBA 采集并存，value_at(te) 会取到沿后的新值）
        self.assertEqual(res["value_time"], 79999)
        self.assertEqual(res["target"]["value"], "b0000000000001100")
        y_c = [d for d in res["drivers"] if d.get("path") == F + "y_c"][0]
        self.assertEqual(y_c["classification"], "match")
        self.assertIn("t=80000", res["capture_note"])

    def test_active_drivers_const_and_missing(self):
        m = self._map()
        res = active_drivers(self.fs, self.npi, m, F + "a_r", 90000)
        self.assertEqual(res["status"], "ok")
        kinds = {d["classification"] for d in res["drivers"]}
        self.assertIn("constant", kinds)
        self.assertIn("match", kinds)   # a_in@90000 = b00000100 == a_r
        self.assertTrue(res["capture_note"])  # 未给 clock 的过程寄存器提示

    def test_state_transitions(self):
        m = self._map()
        res = state_transitions(self.fs, self.npi, m, F + "y_r",
                                clock=F + "clk_in", start=50000, end=200000)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["count"], 1)
        tr = res["transitions"][0]
        self.assertEqual(tr["from"], "b0000000000001001")
        self.assertEqual(tr["to"], "b0000000000001100")
        self.assertEqual(tr["first_time"], 81000)
        self.assertEqual(tr["capture_edge"], 80000)
        vals = {d["path"]: d["value"] for d in tr["drivers_at_capture"]}
        self.assertEqual(vals[F + "y_c"], "b0000000000001100")

    def test_mapping_helper_roundtrip(self):
        m = Mapping("demo_sys_sim_top.u_dut.", F + "a_r", P + "a_r")
        self.assertEqual(m.fsdb(P + "y_c"), F + "y_c")
        self.assertEqual(m.npi(F + "y_c"), P + "y_c")


if __name__ == "__main__":
    unittest.main()
