/*========================================FILE_HEADER=====================================
# Filename: sdpram_wrapper_tc_byte_en.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 byte_en：字节使能逐字节写——32bit 数据分 4 字节，bea 逐个 bit 置位后
        读回验证：使能字节为新值、其余字节保持原值（旧值）；另覆盖双字节使能与非相邻字节组合
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "sdpram_wrapper_tb_pkg.sv"
`ifndef U_SDPRAM_WRAPPER_TC_BYTE_EN
`define U_SDPRAM_WRAPPER_TC_BYTE_EN
import sdpram_wrapper_tb_pkg::*;
import tb_pkg::*;

//----------- sdpram_wrapper_tc_byte_en ------------
class sdpram_wrapper_tc_byte_en extends sdpram_wrapper_tc_base;

    function new(string name = "sdpram_wrapper_tc_byte_en");
        super.new(name);
    endfunction

    virtual task body();
        sdpram_wrapper_item seq[$];
        reset_wait();
        `TB_CASE_BEGIN("TC2: byte_en");
        m_env.m_scb.m_enable = 1'b1;
        // 1) 地址 0 全字节写 AABBCCDD（各字节值 = [AA][BB][CC][DD]，便于逐字节区分）
        seq.push_back(mk_wr(32'hAABBCCDD, 6'd0));
        // 2) bea=4'b0001：低字节（byte0）写 0x44，byte1..3 保持 CC/BB/AA
        seq.push_back(mk_wr_be(32'h11223344, 6'd0, 4'b0001));
        seq.push_back(mk_rd(6'd0));          // 期望 AABBCC44
        // 3) bea=4'b0010：byte1 写 0x88，其余保持 CC44
        seq.push_back(mk_wr_be(32'h55667788, 6'd0, 4'b0010));
        seq.push_back(mk_rd(6'd0));          // 期望 AABB8844
        // 4) bea=4'b0100：byte2 写 0x22，其余保持 88 44
        seq.push_back(mk_wr_be(32'h99001122, 6'd0, 4'b0100));
        seq.push_back(mk_rd(6'd0));          // 期望 AA228844
        // 5) bea=4'b1000：byte3 写 0x88，其余保持 22 88 44
        seq.push_back(mk_wr_be(32'h55667788, 6'd0, 4'b1000));
        seq.push_back(mk_rd(6'd0));          // 期望 88228844
        // 6) bea=4'b0101：非相邻双字节（byte0/byte2）写 EF/DE，byte1/byte3 保持
        seq.push_back(mk_wr_be(32'hDEADBEEF, 6'd0, 4'b0101));
        seq.push_back(mk_rd(6'd0));          // 期望 88DE88EF
        // 7) 另一地址独立性：地址 5 全写 11111111 后 bea=4'b0011 写低两字节 3333
        seq.push_back(mk_wr(32'h11111111, 6'd5));
        seq.push_back(mk_wr_be(32'h22223333, 6'd5, 4'b0011));
        seq.push_back(mk_rd(6'd5));          // 期望 11113333
        drive_seq(seq);
        `TB_CASE_END("TC2: byte_en", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_SDPRAM_WRAPPER_TC_BYTE_EN
