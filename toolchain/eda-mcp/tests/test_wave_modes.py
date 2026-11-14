"""wave 模式改进的测试：路径报错信息、`-s` 通配、翻转段摘要、位宽截断显式化。

四条都来自实际使用者的反馈，这里各钉一组可观察行为：

- 路径报错要能一眼看出"解析基准"（入参原样、当前 CWD、远端主机提示）；
- `-s` **只有显式通配**（``*`` ``?`` ``[``）才模糊展开，非通配名字行为不变；
- ``summary="flip"`` 才给 ``segments``（窗口内 ``[t0, t1, 值]`` 翻转段，段内恒定、
  相邻同值合并、不产生零长末段）；默认关，且翻转次数超阈值时给 ``summary_hint``；
- 超过 32 bit 的信号在 ``width_truncated`` / ``label_truncated`` 里显式标出
  （现有 ``truncated`` 字段含义是"值变被 max_changes 截断"，两者不混）。

用假 fsdbq 走端到端；行协议与 ``test_wave_extract.py`` 同款。
"""

import json
import os
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from eda_mcp import wavegen  # noqa: E402
from eda_mcp.config import Config, defaults  # noqa: E402
from eda_mcp.fsdb import Fsdb, FsdbError  # noqa: E402
from eda_mcp.wavegen import flip_segments, wave_gen  # noqa: E402

# 假 fsdbq：vars（带 --pattern）/ info / wave 三个模式。
# 信号表：一个时钟、三个同族 reg_*（给通配用）、一个 40 bit（给位宽截断用）。
FAKE = r"""#!/bin/sh
echo "logDir = /tmp/"
mode="$1"; shift
PAT=""
for arg in "$@"; do
  case "$arg" in
    --pattern=*) PAT="${arg#--pattern=}" ;;
  esac
done
prev=""
for arg in "$@"; do
  if [ "$prev" = "--pattern" ]; then PAT="$arg"; fi
  prev="$arg"
done
emit_var() {  # emit_var HIER ID L R
  leaf="${1##*.}"
  if [ -n "$PAT" ]; then
    case "$PAT" in
      *.*) case "$1" in $PAT) ;; *) return 0 ;; esac ;;      # 含点：按整体层次匹配
      *)   case "$leaf" in $PAT) ;; *) return 0 ;; esac ;;   # 不含点：按叶子名匹配
    esac
  fi
  printf 'V\t%s\t%s\t%s\t%s\twire\t0\n' "$1" "$2" "$3" "$4"
}
case "$mode" in
  info)
    printf 'I\tfile\t%s\n' "$FSDB_PATH"
    printf 'I\tscale_unit\t1ps\n'
    printf 'I\tmin_time\t0\n'
    printf 'I\tmax_time\t100000\n'
    ;;
  vars)
    emit_var top.clk 0 0 0
    emit_var top.u.wir_req_set_id 1 7 0
    emit_var top.u.reg_set_id 2 7 0
    emit_var top.u.reg_row_base 3 7 0
    emit_var top.u.wide 4 39 0
    ;;
  wave)
    printf 'C\ttop.clk\t10000\t0\t5\t5\n'
    printf 'B\t0\ttop.clk\ttop.clk\t0\t0\t0\n'
    printf 'B\t1\ttop.u.wir_req_set_id\ttop.u.wir_req_set_id\t1\t7\t0\n'
    printf 'B\t2\ttop.u.reg_set_id\ttop.u.reg_set_id\t2\t7\t0\n'
    printf 'B\t3\ttop.u.reg_row_base\ttop.u.reg_row_base\t3\t7\t0\n'
    printf 'B\t4\ttop.u.wide\ttop.u.wide\t4\t39\t0\n'
    printf 'R\t10000\n'; printf 'F\t15000\n'
    printf 'R\t20000\n'; printf 'F\t25000\n'
    printf 'R\t30000\n'; printf 'F\t35000\n'
    printf 'R\t40000\n'; printf 'F\t45000\n'
    printf 'P\t1\t0\tb00000001\n'
    printf 'W\t1\t25000\tb00000010\n'
    printf 'P\t2\t0\tb00000011\n'
    printf 'W\t2\t25000\tb00000100\n'
    printf 'P\t3\t0\tb00000101\n'
    printf 'P\t4\t0\tb1111111111111111111111111111111111110001\n'
    printf 'W\t4\t25000\tb1111111111111111111111111111111111110010\n'
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


class TestFlipSegments(unittest.TestCase):
    """纯函数：窗口裁剪、相邻同值合并、不产生零长末段、值格式与 wave 标签同款。"""

    def test_clips_window_and_formats_value(self):
        changes = [(0, "b0001"), (100, "b0001"), (150, "b0010"), (400, "b0010")]
        self.assertEqual(flip_segments(changes, 100, 400), [[100, 150, "1"], [150, 400, "2"]])

    def test_same_value_changes_merge_into_one_segment(self):
        changes = [(0, "b0001"), (100, "b0001"), (150, "b0010"), (400, "b0010")]
        # 0..500：100 处值没变，应与前一段合并成 [0,150]
        self.assertEqual(flip_segments(changes, 0, 500), [[0, 150, "1"], [150, 500, "2"]])

    def test_single_point_window_still_gives_one_segment(self):
        self.assertEqual(flip_segments([(0, "b0010")], 400, 400), [[400, 400, "2"]])

    def test_unknown_value_is_passed_through(self):
        self.assertEqual(flip_segments([(0, "x"), (10, "x")], 0, 20), [[0, 20, "x"]])

    def test_raw_mode_keeps_the_wire_string(self):
        segs = flip_segments([(0, "b0001")], 0, 10, label=False)
        self.assertEqual(segs, [[0, 10, "b0001"]])


class TestFsdbPathError(unittest.TestCase):
    """路径报错要带解析基准：入参原样 + 当前 CWD + 远端提示。"""

    def test_message_shows_given_path_and_cwd(self):
        with self.assertRaises(FsdbError) as ctx:
            Fsdb("/definitely/not/here/x.fsdb", fsdbq="/bin/true")
        message = str(ctx.exception)
        self.assertIn("/definitely/not/here/x.fsdb", message)      # 解析后的绝对路径
        self.assertIn("入参原样", message)
        self.assertIn(os.getcwd(), message)                        # 当前 CWD
        self.assertIn("远端主机", message)                          # 解析发生在远端

    def test_relative_path_is_resolved_against_cwd_and_reported(self):
        with self.assertRaises(FsdbError) as ctx:
            Fsdb("no_such_dir/x.fsdb", fsdbq="/bin/true")
        message = str(ctx.exception)
        self.assertIn(os.path.join(os.getcwd(), "no_such_dir", "x.fsdb"), message)
        self.assertIn("no_such_dir/x.fsdb", message)

    def test_ensure_fsdb_is_the_site_wave_actually_hits(self):
        """`wave` 走的是 ensure_fsdb（报"波形文件不存在"），这条也要带解析基准。"""
        from eda_mcp.wavegen import ensure_fsdb

        with self.assertRaises(FsdbError) as ctx:
            ensure_fsdb("/definitely/not/here/x.fsdb")
        message = str(ctx.exception)
        self.assertIn("波形文件不存在", message)
        self.assertIn("/definitely/not/here/x.fsdb", message)
        self.assertIn("入参原样", message)
        self.assertIn(os.getcwd(), message)
        self.assertIn("远端主机", message)


class TestWaveModes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.fsdbq = _mk_fake(self.tmp)
        self.fsdb_path = os.path.join(self.tmp, "fake.fsdb")
        with open(self.fsdb_path, "w"):
            pass
        data = defaults()
        data["fsdb"]["fsdbq_bin"] = self.fsdbq
        self.cfg = Config(data)
        self._hint = wavegen.SUMMARY_HINT_FLIPS
        self.addCleanup(setattr, wavegen, "SUMMARY_HINT_FLIPS", self._hint)

    def _gen(self, **kw):
        kw.setdefault("cycles", 4)
        kw.setdefault("clock", "top.clk")
        kw.setdefault("cfg", self.cfg)
        return wave_gen(self.fsdb_path, **kw)

    # ---- S2：`-s` 只有显式通配才模糊 ----------------------------------
    def test_explicit_wildcard_expands_to_matching_signals(self):
        res = self._gen(signals=["top.u.reg_*"])
        expanded = sorted(item["resolved"] for item in res["glob_expanded"])
        self.assertEqual(expanded, ["top.u.reg_row_base", "top.u.reg_set_id"])
        requested = [item["requested"] for item in res["signals"]]
        self.assertIn("top.u.reg_row_base", requested)
        self.assertIn("top.u.reg_set_id", requested)

    def test_leaf_name_wildcard_grabs_a_family_in_one_step(self):
        """实际场景：一次抓 wir_req_set_id + reg_set_id 等同族叶子名。"""
        res = self._gen(signals=["*_set_id"])
        expanded = sorted(item["resolved"] for item in res["glob_expanded"])
        self.assertEqual(expanded, ["top.u.reg_set_id", "top.u.wir_req_set_id"])
        self.assertEqual(len([item for item in res["signals"] if item["match"] != "not-found"]), 3)

    def test_plain_name_is_not_treated_as_a_pattern(self):
        res = self._gen(signals=["top.u.reg_set_id"])
        self.assertEqual(res["glob_expanded"], [])
        self.assertEqual([item["requested"] for item in res["signals"]],
                         ["top.clk", "top.u.reg_set_id"])

    def test_unmatched_wildcard_is_kept_and_reported_not_found(self):
        res = self._gen(signals=["top.u.nope_*"])
        self.assertEqual(res["glob_expanded"], [])
        self.assertEqual(res["signals"][-1]["match"], "not-found")

    # ---- S3：翻转段摘要 ----------------------------------------------
    def test_summary_off_by_default(self):
        res = self._gen(signals=["top.u.reg_set_id"])
        self.assertEqual(res["segments"], {})
        self.assertEqual(res["summary"], "")
        self.assertNotIn("summary_hint", res)

    def test_summary_flip_returns_windowed_segments(self):
        res = self._gen(signals=["top.u.reg_set_id"], summary="flip")
        segs = res["segments"]["top.u.reg_set_id"]
        self.assertEqual(res["summary"], "flip")
        self.assertEqual(segs[0][0], res["window"]["start"])
        self.assertEqual(segs[-1][1], res["window"]["end"])
        self.assertEqual(len(segs), 2)                    # 窗口内只有一次翻转
        self.assertNotEqual(segs[0][2], segs[1][2])
        self.assertNotIn("top.clk", res["segments"])      # 时钟不进摘要

    def test_summary_hint_appears_only_when_flips_are_many(self):
        wavegen.SUMMARY_HINT_FLIPS = 1
        res = self._gen(signals=["top.u.reg_set_id"])
        self.assertIn("summary_hint", res)
        self.assertIn("--summary flip", res["summary_hint"])
        again = self._gen(signals=["top.u.reg_set_id"], summary="flip")
        self.assertNotIn("summary_hint", again)

    def test_unknown_summary_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            self._gen(signals=["top.u.reg_set_id"], summary="fancy")

    # ---- S4：位宽截断显式化 ------------------------------------------
    def test_wide_signal_is_flagged_explicitly(self):
        res = self._gen(signals=["top.u.wide"])
        self.assertEqual(res["width_truncated"], ["top.u.wide"])
        detail = [item for item in res["signals"] if item["resolved"] == "top.u.wide"][0]
        self.assertEqual(detail["width"], 40)
        self.assertEqual(detail["label_bits"], 32)
        self.assertTrue(detail["label_truncated"])

    def test_narrow_signal_is_not_flagged(self):
        res = self._gen(signals=["top.u.reg_set_id"])
        self.assertEqual(res["width_truncated"], [])
        detail = [item for item in res["signals"] if item["resolved"] == "top.u.reg_set_id"][0]
        self.assertEqual(detail["label_bits"], 8)
        self.assertFalse(detail["label_truncated"])

    def test_changes_truncation_field_keeps_its_own_meaning(self):
        """现成的 truncated 仍表示"值变被 max_changes 截断"，不被位宽占用。"""
        res = self._gen(signals=["top.u.wide"])
        self.assertEqual(res["truncated"], [])
        self.assertEqual(res["width_truncated"], ["top.u.wide"])


class TestSignalsAsArgs(unittest.TestCase):
    """`signals --as-args`：一次列匹配、一次粘走，不用手抄全名。"""

    def test_joins_full_hier_names_as_wave_args(self):
        from eda_mcp.fsdb import Signal
        from eda_mcp.wavedrom import signals_as_args

        sigs = [Signal(hier="top.u.a", idcode=1, l=0, r=0, vtype="wire", direction=0),
                Signal(hier="top.u.b", idcode=2, l=7, r=0, vtype="wire", direction=0)]
        self.assertEqual(signals_as_args(sigs), "-s top.u.a -s top.u.b")

    def test_empty_list_gives_empty_string(self):
        from eda_mcp.wavedrom import signals_as_args

        self.assertEqual(signals_as_args([]), "")

    def test_cli_exposes_the_flag(self):
        from eda_mcp.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["signals", "x.fsdb", "--pattern", "*_id", "--as-args"])
        self.assertTrue(args.as_args)
        self.assertFalse(parser.parse_args(["signals", "x.fsdb"]).as_args)


class TestCliSurface(unittest.TestCase):
    """CLI 面：--summary 可选值、帮助里能看到它。"""

    def test_wave_parser_accepts_flip_and_rejects_other(self):
        from eda_mcp.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["wave", "x.fsdb", "-s", "a", "--summary", "flip"])
        self.assertEqual(args.summary, "flip")
        args = parser.parse_args(["wave", "x.fsdb", "-s", "a"])
        self.assertIsNone(args.summary)
        with self.assertRaises(SystemExit):
            parser.parse_args(["wave", "x.fsdb", "-s", "a", "--summary", "fancy"])

    def test_mcp_tool_passes_summary_through(self):
        import inspect

        from eda_mcp import server

        self.assertIn("summary", inspect.signature(server.wave_gen).parameters)
        self.assertIn("summary='flip'", server.wave_gen.__doc__ or "")


if __name__ == "__main__":
    unittest.main()
