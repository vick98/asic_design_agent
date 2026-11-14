/*========================================FILE_HEADER=====================================
# Filename: pubip_sat_tc_sat_unsigned.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 sat_unsigned：无符号路径（<16,8,u>-><8,4,u>，IS_SIGNED=0，IN_FRAC=8 > OUT_FRAC=4
        右移 4 位）。需 +define+PUBIP_SAT_USIGNED 编译，单独 +TC=tc_sat_unsigned 运行（不在默认 tc_all）。
        边界：16.0（16'h1000）整数部分 16 > 15 -> 无符号饱和 8'hFF；饱和值 = 2^OUT_TOTAL - 1
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_sat_tb_pkg.sv"
`ifndef U_PUBIP_SAT_TC_SAT_UNSIGNED
`define U_PUBIP_SAT_TC_SAT_UNSIGNED
import pubip_sat_tb_pkg::*;
import tb_pkg::*;

`ifdef PUBIP_SAT_USIGNED
//----------- pubip_sat_tc_sat_unsigned ------------
class pubip_sat_tc_sat_unsigned extends pubip_sat_tc_base;

    function new(string name = "pubip_sat_tc_sat_unsigned");
        super.new(name);
    endfunction

    virtual task body();
        pubip_sat_item seq[$];
        int i;
        logic [`PUBIP_SAT_IN_TOTAL - 1 : 0] rnd;
        reset_wait();
        `TB_CASE_BEGIN("TC8: sat_unsigned");
        m_env.m_scb.m_enable = 1'b1;
        push_data(seq, 16'h0100);  // 1.0    -> 8'h10
        push_data(seq, 16'h0140);  // 1.25   -> 8'h14
        push_data(seq, 16'h0FFF);  // 15.996 -> 8'hFF（不溢出，截位最大 15.9375）
        push_data(seq, 16'h1000);  // 16.0   -> 8'hFF（整数 16 > 15，无符号饱和）
        push_data(seq, 16'hFFFF);  // 255.996-> 8'hFF（无符号饱和）
        push_data(seq, 16'h0020);  // 0.125  -> 8'h02
        push_data(seq, 16'h0001);  // 1/256  -> 8'h00（右移 4 位低位丢弃）
        // 随机 100 拍（覆盖无符号全值域）
        for (i = 0; i < 100; i = i + 1) begin
            rnd = $urandom_range(0, (1 << `PUBIP_SAT_IN_TOTAL) - 1);
            push_data(seq, rnd);
        end
        drive_seq(seq);
        `TB_CASE_END("TC8: sat_unsigned", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //PUBIP_SAT_USIGNED
`endif //U_PUBIP_SAT_TC_SAT_UNSIGNED
