/*========================================FILE_HEADER=====================================
# Filename: pubip_sat_tc_sat_ovf_neg.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 sat_ovf_neg：负溢出与对称负饱和（-> 8'h81 = SAT_S_NEG_SYMM）
        整数部分 < -16（-2^OUT_INT）判负溢出；-16.0（16'hF800）本身为非对称最小 -> 对称饱和
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_sat_tb_pkg.sv"
`ifndef U_PUBIP_SAT_TC_SAT_OVF_NEG
`define U_PUBIP_SAT_TC_SAT_OVF_NEG
import pubip_sat_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_sat_tc_sat_ovf_neg ------------
class pubip_sat_tc_sat_ovf_neg extends pubip_sat_tc_base;

    function new(string name = "pubip_sat_tc_sat_ovf_neg");
        super.new(name);
    endfunction

    virtual task body();
        pubip_sat_item seq[$];
        reset_wait();
        `TB_CASE_BEGIN("TC4: sat_ovf_neg");
        m_env.m_scb.m_enable = 1'b1;
        push_data(seq, 16'hFC00);  // -8.0     -> 8'hC0（不溢出，正常截位）
        push_data(seq, 16'hF800);  // -16.0    -> 8'h81（非对称最小 8'h80，对称饱和）
        push_data(seq, 16'hF7FF);  // -16.0078 -> 8'h81（负溢出，对称饱和）
        push_data(seq, 16'hF400);  // -24.0    -> 8'h81（负溢出）
        push_data(seq, 16'h8000);  // -256.0   -> 8'h81（负溢出）
        drive_seq(seq);
        `TB_CASE_END("TC4: sat_ovf_neg", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_PUBIP_SAT_TC_SAT_OVF_NEG
