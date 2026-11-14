"""FFR 行协议解析测试：用假 fsdbq 脚本喂固定输出，验证解析与过滤。"""

import os
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from eda_mcp.fsdb import Fsdb, FsdbError  # noqa: E402

# 故意混入 FFR 往 stdout 打的杂项行（logDir），必须被过滤掉
FAKE = r"""#!/bin/sh
# 假 fsdbq：$1=mode $2=fsdb
echo "logDir = /tmp/"
case "$1" in
  info)
    printf 'I\tfile\t%s\n' "$2"
    printf 'I\tscale_unit\t1ps\n'
    printf 'I\tsim_version\tVCS M-2017.03\n'
    printf 'I\tmin_time\t45100\n'
    printf 'I\tmax_time\t225100\n'
    ;;
  vars)
    printf 'V\ttop.clk\t3\t0\t0\treg\t2\n'
    printf 'V\ttop.u.reg_cnt\t8\t3\t0\treg\t0\n'
    printf 'V\ttop.u.skew\t9\t63\t0\treal\t0\n'
    printf 'Z\tcount\t3\n'
    ;;
  scopes)
    printf 'S\ttop\t1\n'
    printf 'S\ttop.u\t2\n'
    ;;
  wave)
    printf 'B\t0\ttop.clk\ttop.clk\t3\t0\t0\n'
    printf 'N\t1\tnope\n'
    printf 'B\t2\ttop.u.reg_cnt\ttop.u.reg_cnt\t8\t3\t0\n'
    printf 'C\ttop.clk\t10000\t0\t37\t18\n'
    printf 'R\t55000\n'
    printf 'R\t65000\n'
    printf 'F\t60000\n'
    printf 'P\t2\t50000\tb0000\n'
    printf 'W\t2\t65000\tb0001\n'
    printf 'E\t2\t2\t0\n'
    printf 'E\t0\t20\t0\n'
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


class TestFsdbProtocol(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.fsdbq = _mk_fake(self.tmp)
        self.fsdb_path = os.path.join(self.tmp, "fake.fsdb")
        with open(self.fsdb_path, "w"):
            pass
        self.fs = Fsdb(self.fsdb_path, fsdbq=self.fsdbq)

    def test_info_filters_stray_stdout(self):
        info = self.fs.info()
        self.assertEqual(info["scale_unit"], "1ps")
        self.assertEqual(info["min_time_int"], 45100)
        self.assertEqual(info["max_time_int"], 225100)

    def test_signals(self):
        sigs = self.fs.signals()
        self.assertEqual([s.hier for s in sigs], ["top.clk", "top.u.reg_cnt", "top.u.skew"])
        self.assertEqual(sigs[0].width, 1)
        self.assertEqual(sigs[1].width, 4)
        self.assertEqual(sigs[2].width, 64)  # real -> 64
        self.assertEqual(sigs[1].name, "reg_cnt")
        self.assertEqual(sigs[1].scope, "top.u")

    def test_scopes(self):
        self.assertEqual(self.fs.scopes(), [("top", 1), ("top.u", 2)])

    def test_wave_parsing(self):
        res = self.fs.wave(["top.clk", "nope", "top.u.reg_cnt"], clock="top.clk")
        self.assertEqual(res.clock, "top.clk")
        self.assertEqual(res.period, 10000)
        self.assertEqual(res.rising, [55000, 65000])
        self.assertEqual(res.falling, [60000])
        self.assertEqual(len(res.signals), 3)
        self.assertTrue(res.signals[0].found)
        self.assertFalse(res.signals[1].found)
        self.assertEqual(res.signals[1].requested, "nope")
        cnt = res.signals[2]
        # 种子值（窗口前）必须并入 changes，否则首个采样点会退化成 x
        self.assertEqual(cnt.changes, [(50000, "b0000"), (65000, "b0001")])
        self.assertEqual(cnt.value_at(60000), "b0000")
        self.assertEqual(cnt.value_at(99999), "b0001")
        self.assertFalse(cnt.truncated)

    def test_missing_file_raises(self):
        with self.assertRaises(FsdbError):
            Fsdb(os.path.join(self.tmp, "not-there.fsdb"), fsdbq=self.fsdbq)

    def test_no_fsdbq_raises(self):
        with self.assertRaises(FsdbError):
            Fsdb(self.fs.path, fsdbq=None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
