"""WaveDrom 生成器的纯函数与结构测试（不依赖服务器 / FSDB）。"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from eda_mcp.fsdb import Signal  # noqa: E402
from eda_mcp.wavedrom import (  # noqa: E402
    SignalTable,
    WaveDrom,
    align_time_window,
    bin_to_hex,
    compute_sample_times,
    cycle_rising_times,
    format_data_label,
    multi_bit_wave_char,
    parse_time_with_timescale,
    single_bit_wave_char,
)


class TestTime(unittest.TestCase):
    def test_bare_integer_is_passthrough(self):
        self.assertEqual(parse_time_with_timescale("100000", "1ps"), 100000)

    def test_unit_scaling(self):
        self.assertEqual(parse_time_with_timescale("500ns", "1ns"), 500)
        self.assertEqual(parse_time_with_timescale("500ns", "1ps"), 500000)
        self.assertEqual(parse_time_with_timescale("1us", "1ns"), 1000)
        self.assertEqual(parse_time_with_timescale("1us", "1ps"), 1000000)

    def test_no_unit_is_literal(self):
        self.assertEqual(parse_time_with_timescale("500", "1ps"), 500)

    def test_bad_input_raises(self):
        with self.assertRaises(ValueError):
            parse_time_with_timescale("abc", "1ps")
        with self.assertRaises(ValueError):
            parse_time_with_timescale("1ns", "bogus")


class TestValueChars(unittest.TestCase):
    def test_bin_to_hex(self):
        self.assertEqual(bin_to_hex("b1010"), "a")
        self.assertEqual(bin_to_hex("b0000"), "0")
        self.assertEqual(bin_to_hex("b00000001"), "1")
        self.assertEqual(bin_to_hex("b11111111"), "ff")
        # x/z 按 0 处理（与旧工具 bin_to_hex 一致）
        self.assertEqual(bin_to_hex("bxx11"), "3")

    def test_format_data_label(self):
        self.assertEqual(format_data_label("b1010"), "a")
        self.assertEqual(format_data_label("r3.14 "), "3.14 ")
        # 超过 32 bit 取低 32 bit
        long_bits = "b" + "0" * 30 + "1010"
        self.assertEqual(format_data_label(long_bits), "..0000000a")

    def test_single_bit_chars(self):
        for v in ("0", "1", "x", "z", "u", "d"):
            self.assertEqual(single_bit_wave_char(v), v)
        self.assertEqual(single_bit_wave_char("B1"), "x")

    def test_multi_bit_chars(self):
        self.assertEqual(multi_bit_wave_char("b0101"), "=")
        self.assertEqual(multi_bit_wave_char("bxxxx"), "x")
        self.assertEqual(multi_bit_wave_char("bzzzz"), "z")
        self.assertEqual(multi_bit_wave_char("x"), "x")


class TestWindow(unittest.TestCase):
    RISING = list(range(55000, 225001, 10000))
    FALLING = list(range(50000, 225001, 10000))

    def test_center_mode(self):
        # time=100000 -> 对齐到 95000；cycles=10 -> 前 5 后 4
        self.assertEqual(align_time_window(self.RISING, -1, -1, 100000, 10), (55000, 135000))

    def test_center_mode_clamps_at_case_start(self):
        # 对齐中心就是第一个上升沿时，前面无沿可取 -> 窗口被夹紧（周期数不足）
        self.assertEqual(align_time_window(self.RISING, -1, -1, 55000, 10), (55000, 95000))

    def test_range_mode(self):
        self.assertEqual(align_time_window(self.RISING, 60000, 120000, -1, 10), (55000, 125000))

    def test_default_mode(self):
        self.assertEqual(align_time_window(self.RISING, -1, -1, -1, 3), (55000, 75000))

    def test_sample_times_use_full_falling_list(self):
        window = cycle_rising_times(self.RISING, 55000, 75000)
        self.assertEqual(window, [55000, 65000, 75000])
        # 采样点 = 上升沿与其下一个下降沿的中点，下降沿取自全时间段
        self.assertEqual(compute_sample_times(window, self.FALLING), [57500, 67500, 77500])


class TestGenerate(unittest.TestCase):
    """用合成信号表验证 JSON 结构、模糊命名、未找到条目与时钟条目。"""

    def setUp(self):
        self.signals = [
            Signal("top.clk", 1, 0, 0, "reg", 2),
            Signal("top.u_dut.reg_counter", 2, 3, 0, "reg", 0),
            Signal("top.u_dut.o_cnt_en", 3, 0, 0, "reg", 0),
        ]
        self.table = SignalTable(self.signals)
        rising = list(range(55000, 225001, 10000))
        falling = list(range(50000, 225001, 10000))
        changes = {
            "top.clk": [(50000, "0"), (55000, "1"), (60000, "0"), (65000, "1")],
            "top.u_dut.reg_counter": [(55000, "b0000"), (65000, "b0001"), (75000, "b0010")],
            "top.u_dut.o_cnt_en": [(50000, "0"), (70000, "1")],
        }
        self.gen = WaveDrom(
            self.table,
            clock_path="top.clk",
            clock_id=1,
            rising=rising,
            falling=falling,
            changes_of=lambda h: changes.get(h, []),
        )

    def test_exact_fuzzy_and_notfound(self):
        text = self.gen.generate(
            ["top.clk", "top.u_dut.reg_counter", "reg_counter", "nope"], 55000, 75000
        )
        doc = json.loads(text)
        names = [e["name"] for e in doc["signal"]]
        self.assertEqual(
            names,
            ["top.clk", "top.u_dut.reg_counter", "reg_counter_match", "nope_notfind"],
        )
        clk, counter = doc["signal"][0], doc["signal"][1]
        self.assertEqual(clk["wave"], "p..")
        self.assertEqual(clk["period"], 2)
        # 采样点 60000/70000/80000：0000 -> 0001 -> 0010
        self.assertEqual(counter["wave"], "===")
        self.assertEqual(counter["data"], ["0", "1", "2"])
        self.assertEqual(doc["signal"][3]["wave"], "x..")

    def test_repeat_values_collapse_to_dot(self):
        doc = json.loads(self.gen.generate(["top.u_dut.o_cnt_en"], 55000, 85000))
        # 采样点 57500/67500/77500/87500：0 -> 0 -> 1 -> 1
        self.assertEqual(doc["signal"][0]["wave"], "0.1.")

    def test_clock_rendered_as_p(self):
        doc = json.loads(self.gen.generate(["top.clk"], 55000, 95000))
        self.assertEqual(doc["signal"][0]["wave"], "p....")

    def test_empty_window_raises(self):
        with self.assertRaises(ValueError):
            self.gen.generate(["top.clk"], 10, 20)


if __name__ == "__main__":
    unittest.main(verbosity=2)
