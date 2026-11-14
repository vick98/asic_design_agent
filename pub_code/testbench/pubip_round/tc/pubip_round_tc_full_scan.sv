/*========================================FILE_HEADER=====================================
# Filename: pubip_round_tc_full_scan.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-10-06        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 full_scan：输入位图全值域穷举（0 ~ 2^W_src-1）
        - 覆盖每一条饱和/舍入分支组合，RTL 与参考模型逐拍零差异是强证据
        - W_src > 16 的变体（33/24 bit）不聚合本用例，由 half_bound、sat_pos/sat_neg、
          neg_asym、random 用构造边界与随机抽样覆盖
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_round_tb_pkg.sv"
`ifndef U_PUBIP_ROUND_TC_FULL_SCAN
`define U_PUBIP_ROUND_TC_FULL_SCAN
import pubip_round_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_round_tc_full_scan ------------
class pubip_round_tc_full_scan extends pubip_round_tc_base;

    function new(string name = "pubip_round_tc_full_scan");
        super.new(name);
    endfunction

    virtual task body();
`ifdef PUBIP_ROUND_HAVE_FULL_SCAN
        pubip_round_item seq[$];
        reset_wait();
        `TB_CASE_BEGIN("TC1: full_scan 全值域穷举");
        m_env.m_scb.m_enable = 1'b1;
        push_full_scan(seq);
        drive_seq(seq);
        `TB_CASE_END("TC1: full_scan 全值域穷举", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
`else
        `TB_INFO("TC1: full_scan 跳过（W_src > 16，按构造边界与随机覆盖）");
`endif
    endtask
endclass
`endif //U_PUBIP_ROUND_TC_FULL_SCAN
