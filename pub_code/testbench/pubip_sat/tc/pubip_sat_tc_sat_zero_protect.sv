/*========================================FILE_HEADER=====================================
# Filename: pubip_sat_tc_sat_zero_protect.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 sat_zero_protect：零值保护（PROTECT_EN=1，需 +define+PUBIP_SAT_PROTECT 编译，单独 +TC 运行）
        截位结果为 0 -> 输出 SAT_S_PROTECT（8'h01 最小正值）；非零正常截位不受影响；
        对称饱和优先于零保护（-16.0 -> 8'h81 而非 8'h01）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_sat_tb_pkg.sv"
`ifndef U_PUBIP_SAT_TC_SAT_ZERO_PROTECT
`define U_PUBIP_SAT_TC_SAT_ZERO_PROTECT
import pubip_sat_tb_pkg::*;
import tb_pkg::*;

`ifdef PUBIP_SAT_PROTECT
//----------- pubip_sat_tc_sat_zero_protect ------------
class pubip_sat_tc_sat_zero_protect extends pubip_sat_tc_base;

    function new(string name = "pubip_sat_tc_sat_zero_protect");
        super.new(name);
    endfunction

    virtual task body();
        pubip_sat_item seq[$];
        reset_wait();
        `TB_CASE_BEGIN("TC5: sat_zero_protect");
        m_env.m_scb.m_enable = 1'b1;
        push_data(seq, 16'h0000);  // 0      -> 8'h01（截位 0，零值保护）
        push_data(seq, 16'h0001);  // 1/128  -> 8'h01（右移 4 位后截位 0，零值保护）
        push_data(seq, 16'h000F);  // 15/128 -> 8'h01（右移 4 位后截位 0，零值保护）
        push_data(seq, 16'h0010);  // 0.125  -> 8'h01（截位非 0，正常输出）
        push_data(seq, 16'h0100);  // 2.0    -> 8'h10（正常）
        push_data(seq, 16'hFF00);  // -2.0   -> 8'hF0（负值正常，保护仅作用于 0）
        push_data(seq, 16'hF800);  // -16.0  -> 8'h81（对称饱和优先于零保护）
        drive_seq(seq);
        `TB_CASE_END("TC5: sat_zero_protect", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //PUBIP_SAT_PROTECT
`endif //U_PUBIP_SAT_TC_SAT_ZERO_PROTECT
