/*========================================FILE_HEADER=====================================
# Filename: pubip_round_tc_all.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-10-06        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_round 聚合用例：按当前编译宏变体的位宽，顺序执行适用于该变体的全部用例
        （共享 env，pass/fail 累计）；W_src <= 16 的变体额外聚合全值域穷举
        变体宏见 pubip_round_cfg.svh；聚合内容随位宽自适应，不用另改文件
        全值域穷举用 t0.body() 的 ifdef 守卫（与 pubip_sat 的变体用例同处理方式，
        避免 VCS 2017.03 对条件编译块内类类型变量声明的解析异常）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_round_tb_pkg.sv"
`ifndef U_PUBIP_ROUND_TC_ALL
`define U_PUBIP_ROUND_TC_ALL
import pubip_round_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_round_tc_all ------------
class pubip_round_tc_all extends pubip_round_tc_base;

    function new(string name = "pubip_round_tc_all");
        super.new(name);
    endfunction

    virtual task body();
        // 默认配置用例（共享 env，pass/fail 累计）
        pubip_round_tc_full_scan   t0 = new("tc0");
        pubip_round_tc_half_bound  t1 = new("tc1");
        pubip_round_tc_sat_pos     t2 = new("tc2");
        pubip_round_tc_sat_neg     t3 = new("tc3");
        pubip_round_tc_neg_asym    t4 = new("tc4");
        pubip_round_tc_nzero       t5 = new("tc5");
        pubip_round_tc_random      t6 = new("tc6");
        pubip_round_tc_clamp_check t7 = new("tc7");
        t0.m_rst_if = m_rst_if; t0.m_dut_if = m_dut_if; t0.m_env = m_env; t0.m_my_env = m_my_env;
        t1.m_rst_if = m_rst_if; t1.m_dut_if = m_dut_if; t1.m_env = m_env; t1.m_my_env = m_my_env;
        t2.m_rst_if = m_rst_if; t2.m_dut_if = m_dut_if; t2.m_env = m_env; t2.m_my_env = m_my_env;
        t3.m_rst_if = m_rst_if; t3.m_dut_if = m_dut_if; t3.m_env = m_env; t3.m_my_env = m_my_env;
        t4.m_rst_if = m_rst_if; t4.m_dut_if = m_dut_if; t4.m_env = m_env; t4.m_my_env = m_my_env;
        t5.m_rst_if = m_rst_if; t5.m_dut_if = m_dut_if; t5.m_env = m_env; t5.m_my_env = m_my_env;
        t6.m_rst_if = m_rst_if; t6.m_dut_if = m_dut_if; t6.m_env = m_env; t6.m_my_env = m_my_env;
        t7.m_rst_if = m_rst_if; t7.m_dut_if = m_dut_if; t7.m_env = m_env; t7.m_my_env = m_my_env;
`ifdef PUBIP_ROUND_HAVE_FULL_SCAN
        t0.body();
`endif
        t1.body();
        t2.body();
        t3.body();
        t4.body();
        t5.body();
        t6.body();
        t7.body();
    endtask
endclass
`endif //U_PUBIP_ROUND_TC_ALL
