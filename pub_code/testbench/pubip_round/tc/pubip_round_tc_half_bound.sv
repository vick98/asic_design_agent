/*========================================FILE_HEADER=====================================
# Filename: pubip_round_tc_half_bound.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-10-06        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 half_bound：0.5 LSB 半值边界专项（正负各一组，取 delta ∈ {-1,0,+1}）
        激励 x = k*2^N + 2^(N-1) + delta，正负 k 都取：
          - delta = 0 时恰在 0.5 LSB 边界，half-up 向正方向取整（-2.5 -> -2）
          - delta = -1 向下不进位，delta = +1 向上进位
        额外铺 ±2^(W_dst-1) 邻域（对称饱和界所在的整数级）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_round_tb_pkg.sv"
`ifndef U_PUBIP_ROUND_TC_HALF_BOUND
`define U_PUBIP_ROUND_TC_HALF_BOUND
import pubip_round_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_round_tc_half_bound ------------
class pubip_round_tc_half_bound extends pubip_round_tc_base;

    function new(string name = "pubip_round_tc_half_bound");
        super.new(name);
    endfunction

    virtual task body();
        pubip_round_item seq[$];
        reset_wait();
        `TB_CASE_BEGIN("TC2: half_bound 0.5 LSB 边界");
        m_env.m_scb.m_enable = 1'b1;
        push_half_boundary(seq);
        push_sat_boundary(seq);
        // 零与 ±1 LSB 邻域（N=0 变体下 push_half_boundary 为空，这里保证仍有激励）
        push_value(seq, 0);
        push_value(seq, 1);
        push_value(seq, -1);
        drive_seq(seq);
        `TB_CASE_END("TC2: half_bound 0.5 LSB 边界", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_PUBIP_ROUND_TC_HALF_BOUND
