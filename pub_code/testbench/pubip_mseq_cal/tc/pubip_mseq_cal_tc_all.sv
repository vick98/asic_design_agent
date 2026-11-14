/*========================================FILE_HEADER=====================================
# Filename: pubip_mseq_cal_tc_all.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             聚合全部用例（9 条测试要点一一对应，顺序执行）
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_mseq_cal 聚合用例（顺序执行全部用例，共享 env；pass/fail 累计，
        随机用例经 +SEED= 播种可复现）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_mseq_cal_tb_pkg.sv"
`ifndef U_PUBIP_MSEQ_CAL_TC_ALL
`define U_PUBIP_MSEQ_CAL_TC_ALL
import pubip_mseq_cal_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_mseq_cal_tc_all ------------
class pubip_mseq_cal_tc_all extends pubip_mseq_cal_tc_base;

    function new(string name = "pubip_mseq_cal_tc_all");
        super.new(name);
    endfunction

    virtual task body();
        pubip_mseq_cal_tc_cal_trans0      tc1 = new("tc1");
        pubip_mseq_cal_tc_cal_trans1      tc2 = new("tc2");
        pubip_mseq_cal_tc_cal_pow2        tc3 = new("tc3");
        pubip_mseq_cal_tc_cal_full32767   tc4 = new("tc4");
        pubip_mseq_cal_tc_cal_seg1_bound  tc5 = new("tc5");
        pubip_mseq_cal_tc_cal_seg2_bound  tc6 = new("tc6");
        pubip_mseq_cal_tc_cal_vld_align   tc7 = new("tc7");
        pubip_mseq_cal_tc_cal_multi_call  tc8 = new("tc8");
        pubip_mseq_cal_tc_cal_random      tc9 = new("tc9");
        // 共享 env（不各自 build_env）
        tc1.m_rst_if = m_rst_if; tc1.m_dut_if = m_dut_if; tc1.m_env = m_env; tc1.m_my_env = m_my_env;
        tc2.m_rst_if = m_rst_if; tc2.m_dut_if = m_dut_if; tc2.m_env = m_env; tc2.m_my_env = m_my_env;
        tc3.m_rst_if = m_rst_if; tc3.m_dut_if = m_dut_if; tc3.m_env = m_env; tc3.m_my_env = m_my_env;
        tc4.m_rst_if = m_rst_if; tc4.m_dut_if = m_dut_if; tc4.m_env = m_env; tc4.m_my_env = m_my_env;
        tc5.m_rst_if = m_rst_if; tc5.m_dut_if = m_dut_if; tc5.m_env = m_env; tc5.m_my_env = m_my_env;
        tc6.m_rst_if = m_rst_if; tc6.m_dut_if = m_dut_if; tc6.m_env = m_env; tc6.m_my_env = m_my_env;
        tc7.m_rst_if = m_rst_if; tc7.m_dut_if = m_dut_if; tc7.m_env = m_env; tc7.m_my_env = m_my_env;
        tc8.m_rst_if = m_rst_if; tc8.m_dut_if = m_dut_if; tc8.m_env = m_env; tc8.m_my_env = m_my_env;
        tc9.m_rst_if = m_rst_if; tc9.m_dut_if = m_dut_if; tc9.m_env = m_env; tc9.m_my_env = m_my_env;
        tc1.body();
        tc2.body();
        tc3.body();
        tc4.body();
        tc5.body();
        tc6.body();
        tc7.body();
        tc8.body();
        tc9.body();
    endtask
endclass
`endif //U_PUBIP_MSEQ_CAL_TC_ALL
