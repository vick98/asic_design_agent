/*========================================FILE_HEADER=====================================
# Filename: pubip_round_tc_sat_pos.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-10-06        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 sat_pos：正侧对称饱和专项
        源尺度上"1 个输出整数单位"= 2^N 个输入 LSB；输出正界 = 2^(W_dst-1)-1。
        在 +2^(W_dst-1) 个输出整数单位附近铺 ±3 个输出整数单位，覆盖：
          刚好等于正界、刚好越过正界（越界钳到 2^(W_dst-1)-1）、远离正界的整片饱和区
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_round_tb_pkg.sv"
`ifndef U_PUBIP_ROUND_TC_SAT_POS
`define U_PUBIP_ROUND_TC_SAT_POS
import pubip_round_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_round_tc_sat_pos ------------
class pubip_round_tc_sat_pos extends pubip_round_tc_base;

    function new(string name = "pubip_round_tc_sat_pos");
        super.new(name);
    endfunction

    virtual task body();
        pubip_round_item seq[$];
        longint out_unit;
        longint pos_edge;
        int     k;
        reset_wait();
        `TB_CASE_BEGIN("TC3: sat_pos 正饱和");
        m_env.m_scb.m_enable = 1'b1;
        out_unit = 64'sd1 <<< `PUBIP_ROUND_SHIFT                        ;//1 个输出整数单位（源 LSB 计）
        pos_edge = (64'sd1 <<< (`PUBIP_ROUND_OUT_TOTAL - 1)) * out_unit ;//正界 +2^(W_dst-1) 处
        for (k = -3; k <= 3; k = k + 1)
            push_value(seq, pos_edge + k * out_unit);
        // 正界下方一点（2^(W_dst-1)-1 个输出整数单位）的两个邻域点
        push_value(seq, pos_edge - out_unit);
        push_value(seq, pos_edge - out_unit - 1);
        push_value(seq, pos_edge - out_unit + 1);
        // 源正最大值
        push_value(seq, (64'sd1 <<< (`PUBIP_ROUND_IN_TOTAL - 1)) - 1);
        drive_seq(seq);
        `TB_CASE_END("TC3: sat_pos 正饱和", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_PUBIP_ROUND_TC_SAT_POS
