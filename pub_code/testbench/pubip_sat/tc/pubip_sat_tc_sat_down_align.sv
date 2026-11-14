/*========================================FILE_HEADER=====================================
# Filename: pubip_sat_tc_sat_down_align.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 sat_down_align：默认配置（<16,8,s>-><8,4,s>）正数小数位重对齐（P0-3 验收）
        IN_FRAC=7 > OUT_FRAC=3 -> 右移 4 位丢弃低位小数；期望由 refm.compute() 按定点值公式回填
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_sat_tb_pkg.sv"
`ifndef U_PUBIP_SAT_TC_SAT_DOWN_ALIGN
`define U_PUBIP_SAT_TC_SAT_DOWN_ALIGN
import pubip_sat_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_sat_tc_sat_down_align ------------
class pubip_sat_tc_sat_down_align extends pubip_sat_tc_base;

    function new(string name = "pubip_sat_tc_sat_down_align");
        super.new(name);
    endfunction

    virtual task body();
        pubip_sat_item seq[$];
        reset_wait();
        `TB_CASE_BEGIN("TC1: sat_down_align");
        m_env.m_scb.m_enable = 1'b1;
        // 正数重对齐（右移 4 位）：输入 LSB=2^-7，输出 LSB=2^-3
        push_data(seq, 16'h0100);  // 2.0        -> 8'h10
        push_data(seq, 16'h0140);  // 2.5        -> 8'h14
        push_data(seq, 16'h0180);  // 3.0        -> 8'h18
        push_data(seq, 16'h01FF);  // 3.9921875  -> 8'h1F（低位小数丢弃）
        push_data(seq, 16'h0010);  // 0.125      -> 8'h01（重对齐后保留 1 位小数）
        push_data(seq, 16'h0040);  // 0.5        -> 8'h04
        push_data(seq, 16'h0001);  // 1/128      -> 8'h00（右移 4 位完全丢弃）
        drive_seq(seq);
        `TB_CASE_END("TC1: sat_down_align", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_PUBIP_SAT_TC_SAT_DOWN_ALIGN
