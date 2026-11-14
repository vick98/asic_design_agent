/*========================================FILE_HEADER=====================================
# Filename: pubip_sat_tc_sat_expand.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 sat_expand：位宽扩展（<8,4,s>-><16,8,s>，IN_FRAC=3 < OUT_FRAC=7 左移 4 位补零；
        P0-4 验收）。需 +define+PUBIP_SAT_EXPAND 编译，单独 +TC=tc_sat_expand 运行（不在默认 tc_all）
        2.0 = 8'h10（2*2^3）-> 16'h100（2*2^7）；另有定点边界 + 随机 100 拍（左移路径对拍）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_sat_tb_pkg.sv"
`ifndef U_PUBIP_SAT_TC_SAT_EXPAND
`define U_PUBIP_SAT_TC_SAT_EXPAND
import pubip_sat_tb_pkg::*;
import tb_pkg::*;

`ifdef PUBIP_SAT_EXPAND
//----------- pubip_sat_tc_sat_expand ------------
class pubip_sat_tc_sat_expand extends pubip_sat_tc_base;

    function new(string name = "pubip_sat_tc_sat_expand");
        super.new(name);
    endfunction

    virtual task body();
        pubip_sat_item seq[$];
        int i;
        logic [`PUBIP_SAT_IN_TOTAL - 1 : 0] rnd;
        reset_wait();
        `TB_CASE_BEGIN("TC7: sat_expand");
        m_env.m_scb.m_enable = 1'b1;
        // 左移 4 位补零：输入 LSB=2^-3，输出 LSB=2^-7
        push_data(seq, 8'h10);  // 2.0    -> 16'h100
        push_data(seq, 8'h14);  // 2.5    -> 16'h140
        push_data(seq, 8'hF0);  // -2.0   -> 16'hFF00
        push_data(seq, 8'h7F);  // 15.875 -> 16'h7F0
        push_data(seq, 8'h80);  // -16.0  -> 16'hF800
        push_data(seq, 8'hFF);  // -0.125 -> 16'hFFF0
        // 左移路径随机 100 拍（扩展场景无溢出条件：IN_INT=4 <= OUT_INT=8）
        for (i = 0; i < 100; i = i + 1) begin
            rnd = $urandom_range(0, (1 << `PUBIP_SAT_IN_TOTAL) - 1);
            push_data(seq, rnd);
        end
        drive_seq(seq);
        `TB_CASE_END("TC7: sat_expand", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //PUBIP_SAT_EXPAND
`endif //U_PUBIP_SAT_TC_SAT_EXPAND
