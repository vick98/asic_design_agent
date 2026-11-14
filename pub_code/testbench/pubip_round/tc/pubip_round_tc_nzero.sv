/*========================================FILE_HEADER=====================================
# Filename: pubip_round_tc_nzero.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-10-06        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 nzero：N = 0 退化路径专项（纯对称饱和收位，不加半、不移位）
        覆盖：0、±1、±(对称界)、±(对称界±1)、负满码、源最大/最小值；
        期望：负满码一律钳到 1-2^(W_dst-1)，界内直通，越界钳到对应界
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_round_tb_pkg.sv"
`ifndef U_PUBIP_ROUND_TC_NZERO
`define U_PUBIP_ROUND_TC_NZERO
import pubip_round_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_round_tc_nzero ------------
class pubip_round_tc_nzero extends pubip_round_tc_base;

    function new(string name = "pubip_round_tc_nzero");
        super.new(name);
    endfunction

    virtual task body();
        pubip_round_item seq[$];
        longint pos_sym;
        longint neg_sym;
        longint neg_asym;
        int     delta;
        reset_wait();
        `TB_CASE_BEGIN("TC6: nzero N=0 纯饱和收位");
        m_env.m_scb.m_enable = 1'b1;
        pos_sym  = (64'sd1 <<< (`PUBIP_ROUND_OUT_TOTAL - 1)) - 1 ;//正界
        neg_sym  = 1 - (64'sd1 <<< (`PUBIP_ROUND_OUT_TOTAL - 1)) ;//对称负界
        neg_asym = -(64'sd1 <<< (`PUBIP_ROUND_OUT_TOTAL - 1))    ;//负满码
        push_value(seq, 0);
        push_value(seq, 1);
        push_value(seq, -1);
        for (delta = -1; delta <= 1; delta = delta + 1) begin
            push_value(seq, pos_sym + delta);
            push_value(seq, neg_sym + delta);
            push_value(seq, neg_asym + delta);
        end
        push_value(seq, (64'sd1 <<< (`PUBIP_ROUND_IN_TOTAL - 1)) - 1);//源正最大
        push_value(seq, -(64'sd1 <<< (`PUBIP_ROUND_IN_TOTAL - 1)));   //源负最小
        drive_seq(seq);
        `TB_CASE_END("TC6: nzero N=0 纯饱和收位", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_PUBIP_ROUND_TC_NZERO
