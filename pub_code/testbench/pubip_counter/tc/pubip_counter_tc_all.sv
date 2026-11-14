/*========================================FILE_HEADER=====================================
# Filename: pubip_counter_tc_all.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             聚合全部用例（cycle 用例需宏单独编译，不聚合）
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_counter 聚合用例（顺序执行全部用例，共享 env）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_counter_tb_pkg.sv"
`ifndef U_PUBIP_COUNTER_TC_ALL
`define U_PUBIP_COUNTER_TC_ALL
import pubip_counter_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_counter_tc_all ------------
class pubip_counter_tc_all extends pubip_counter_tc_base;

    function new(string name = "pubip_counter_tc_all");
        super.new(name);
    endfunction

    virtual task body();
        pubip_counter_tc_basic       tc1 = new("tc1");
        pubip_counter_tc_max_end     tc2 = new("tc2");
        pubip_counter_tc_pow2_maxnum tc3 = new("tc3");
        pubip_counter_tc_shift_width tc4 = new("tc4");
        pubip_counter_tc_rst_clear   tc6 = new("tc6");
        pubip_counter_tc_cnt_rst     tc7 = new("tc7");
        pubip_counter_tc_cnt_end     tc8 = new("tc8");
        // 共享 env（不各自 build_env）
        tc1.m_rst_if = m_rst_if; tc1.m_dut_if = m_dut_if; tc1.m_env = m_env; tc1.m_my_env = m_my_env;
        tc2.m_rst_if = m_rst_if; tc2.m_dut_if = m_dut_if; tc2.m_env = m_env; tc2.m_my_env = m_my_env;
        tc3.m_rst_if = m_rst_if; tc3.m_dut_if = m_dut_if; tc3.m_env = m_env; tc3.m_my_env = m_my_env;
        tc4.m_rst_if = m_rst_if; tc4.m_dut_if = m_dut_if; tc4.m_env = m_env; tc4.m_my_env = m_my_env;
        tc6.m_rst_if = m_rst_if; tc6.m_dut_if = m_dut_if; tc6.m_env = m_env; tc6.m_my_env = m_my_env;
        tc7.m_rst_if = m_rst_if; tc7.m_dut_if = m_dut_if; tc7.m_env = m_env; tc7.m_my_env = m_my_env;
        tc8.m_rst_if = m_rst_if; tc8.m_dut_if = m_dut_if; tc8.m_env = m_env; tc8.m_my_env = m_my_env;
        tc1.body();
        tc2.body();
        tc3.body();
        tc4.body();
        tc6.body();
        tc7.body();
        tc8.body();
    endtask
endclass
`endif //U_PUBIP_COUNTER_TC_ALL
