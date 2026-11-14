/*========================================FILE_HEADER=====================================
# Filename: pubip_complex_mult_tc_all.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             聚合 CONJ_EN=0 用例（cm_conj 需宏编译，不聚合）
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_complex_mult 聚合用例（顺序执行 CONJ_EN=0 全部用例，共享 env）；
        cm_conj 需 +define+PUBIP_CM_CONJ 重编译，单独 +TC=tc_cm_conj 运行，不聚合
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_complex_mult_tb_pkg.sv"
`ifndef U_PUBIP_COMPLEX_MULT_TC_ALL
`define U_PUBIP_COMPLEX_MULT_TC_ALL
import pubip_complex_mult_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_complex_mult_tc_all ------------
class pubip_complex_mult_tc_all extends pubip_complex_mult_tc_base;

    function new(string name = "pubip_complex_mult_tc_all");
        super.new(name);
    endfunction

    virtual task body();
        pubip_complex_mult_tc_cm_re_basic       tc1 = new("tc1");
        pubip_complex_mult_tc_cm_im_basic       tc2 = new("tc2");
        pubip_complex_mult_tc_cm_neg            tc3 = new("tc3");
        pubip_complex_mult_tc_cm_overflow_range tc4 = new("tc4");
        // 共享 env（不各自 build_env）
        tc1.m_rst_if = m_rst_if; tc1.m_dut_if = m_dut_if; tc1.m_env = m_env; tc1.m_my_env = m_my_env;
        tc2.m_rst_if = m_rst_if; tc2.m_dut_if = m_dut_if; tc2.m_env = m_env; tc2.m_my_env = m_my_env;
        tc3.m_rst_if = m_rst_if; tc3.m_dut_if = m_dut_if; tc3.m_env = m_env; tc3.m_my_env = m_my_env;
        tc4.m_rst_if = m_rst_if; tc4.m_dut_if = m_dut_if; tc4.m_env = m_env; tc4.m_my_env = m_my_env;
        tc1.body();
        tc2.body();
        tc3.body();
        tc4.body();
    endtask
endclass
`endif //U_PUBIP_COMPLEX_MULT_TC_ALL
