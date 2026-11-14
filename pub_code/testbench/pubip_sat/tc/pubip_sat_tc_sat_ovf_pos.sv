/*========================================FILE_HEADER=====================================
# Filename: pubip_sat_tc_sat_ovf_pos.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 sat_ovf_pos：正溢出饱和（-> 8'h7F = SAT_S_POS_MAX）
        整数部分 > 15（2^OUT_INT-1）判溢出：16.0=16'h0800 起判；15.992=16'h07FF 为不溢出边界
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_sat_tb_pkg.sv"
`ifndef U_PUBIP_SAT_TC_SAT_OVF_POS
`define U_PUBIP_SAT_TC_SAT_OVF_POS
import pubip_sat_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_sat_tc_sat_ovf_pos ------------
class pubip_sat_tc_sat_ovf_pos extends pubip_sat_tc_base;

    function new(string name = "pubip_sat_tc_sat_ovf_pos");
        super.new(name);
    endfunction

    virtual task body();
        pubip_sat_item seq[$];
        reset_wait();
        `TB_CASE_BEGIN("TC3: sat_ovf_pos");
        m_env.m_scb.m_enable = 1'b1;
        push_data(seq, 16'h07C0);  // 15.5      -> 8'h7C（不溢出，正常截位）
        push_data(seq, 16'h07FF);  // 15.992    -> 8'h7F（不溢出边界，最大合法 15.875）
        push_data(seq, 16'h0800);  // 16.0      -> 8'h7F（整数 16 > 15，正溢出）
        push_data(seq, 16'h1000);  // 32.0      -> 8'h7F（正溢出）
        push_data(seq, 16'h2000);  // 64.0      -> 8'h7F（正溢出）
        push_data(seq, 16'h7FFF);  // 255.992   -> 8'h7F（正溢出）
        drive_seq(seq);
        `TB_CASE_END("TC3: sat_ovf_pos", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_PUBIP_SAT_TC_SAT_OVF_POS
