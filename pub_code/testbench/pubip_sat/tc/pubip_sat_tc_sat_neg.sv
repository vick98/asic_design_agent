/*========================================FILE_HEADER=====================================
# Filename: pubip_sat_tc_sat_neg.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 sat_neg：有符号负数重对齐与对称负饱和边界
        -2.0 = 16'hFF00（-2*128）、-4.0 = 16'hFE00、-8.0 = 16'hFC00；
        -16.0 = 16'hF800 是非对称最小（截位 8'h80）-> 对称饱和 8'h81；
        -16.0078 = 16'hF7FF 负溢出 -> 8'h81；-1 LSB 截断向负无穷（16'hFFFF -> 8'hFF）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_sat_tb_pkg.sv"
`ifndef U_PUBIP_SAT_TC_SAT_NEG
`define U_PUBIP_SAT_TC_SAT_NEG
import pubip_sat_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_sat_tc_sat_neg ------------
class pubip_sat_tc_sat_neg extends pubip_sat_tc_base;

    function new(string name = "pubip_sat_tc_sat_neg");
        super.new(name);
    endfunction

    virtual task body();
        pubip_sat_item seq[$];
        reset_wait();
        `TB_CASE_BEGIN("TC2: sat_neg");
        m_env.m_scb.m_enable = 1'b1;
        push_data(seq, 16'hFF00);  // -2.0   -> 8'hF0（-2.0*128 补码）
        push_data(seq, 16'hFE00);  // -4.0   -> 8'hE0
        push_data(seq, 16'hFC00);  // -8.0   -> 8'hC0（在输出范围内，正常截位）
        push_data(seq, 16'hFFC0);  // -0.5   -> 8'hFC
        push_data(seq, 16'hFFFF);  // -1/128 -> 8'hFF（右移 4 位向负无穷截断，典型补码语义）
        push_data(seq, 16'hF800);  // -16.0  -> 8'h81（截位为非对称最小 8'h80，对称饱和）
        push_data(seq, 16'hF7FF);  // -16.0078 -> 8'h81（负溢出，对称饱和）
        drive_seq(seq);
        `TB_CASE_END("TC2: sat_neg", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_PUBIP_SAT_TC_SAT_NEG
