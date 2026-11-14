/*========================================FILE_HEADER=====================================
# Filename: pubip_round_tc_sat_neg.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-10-06        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 sat_neg：负侧对称饱和专项
        输出对称负界 = 1-2^(W_dst-1)，负满码 = -2^(W_dst-1)（禁止输出）。
        在 -2^(W_dst-1) 个输出整数单位附近铺 ±3 个单位，覆盖：
          刚好落在对称负界、刚好越过（钳到 1-2^(W_dst-1)）、远离的整片负饱和区
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_round_tb_pkg.sv"
`ifndef U_PUBIP_ROUND_TC_SAT_NEG
`define U_PUBIP_ROUND_TC_SAT_NEG
import pubip_round_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_round_tc_sat_neg ------------
class pubip_round_tc_sat_neg extends pubip_round_tc_base;

    function new(string name = "pubip_round_tc_sat_neg");
        super.new(name);
    endfunction

    virtual task body();
        pubip_round_item seq[$];
        longint out_unit;
        longint neg_edge;
        int     k;
        reset_wait();
        `TB_CASE_BEGIN("TC4: sat_neg 负饱和");
        m_env.m_scb.m_enable = 1'b1;
        out_unit = 64'sd1 <<< `PUBIP_ROUND_SHIFT                        ;//1 个输出整数单位（源 LSB 计）
        neg_edge = -(64'sd1 <<< (`PUBIP_ROUND_OUT_TOTAL - 1)) * out_unit;//负满码 -2^(W_dst-1) 处
        for (k = -3; k <= 3; k = k + 1)
            push_value(seq, neg_edge + k * out_unit);
        push_value(seq, neg_edge + out_unit);       //对称负界 1-2^(W_dst-1)
        push_value(seq, neg_edge + out_unit + 1);
        push_value(seq, neg_edge + out_unit - 1);
        // 源负最小值
        push_value(seq, -(64'sd1 <<< (`PUBIP_ROUND_IN_TOTAL - 1)));
        drive_seq(seq);
        `TB_CASE_END("TC4: sat_neg 负饱和", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_PUBIP_ROUND_TC_SAT_NEG
