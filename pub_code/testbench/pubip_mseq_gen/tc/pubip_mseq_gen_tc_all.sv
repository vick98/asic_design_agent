/*========================================FILE_HEADER=====================================
# Filename: pubip_mseq_gen_tc_all.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_mseq_gen 聚合用例（默认配置：顺序执行全部默认用例，共享 env）；
        变体用例（trans_n）需对应编译宏 PUBIP_MPG_TRANS4，按宏取值加入本聚合
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_mseq_gen_tb_pkg.sv"
`ifndef U_PUBIP_MSEQ_GEN_TC_ALL
`define U_PUBIP_MSEQ_GEN_TC_ALL
import pubip_mseq_gen_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_mseq_gen_tc_all ------------
class pubip_mseq_gen_tc_all extends pubip_mseq_gen_tc_base;

    function new(string name = "pubip_mseq_gen_tc_all");
        super.new(name);
    endfunction

    virtual task body();
        // 默认配置用例（共享 env，pass/fail 累计；声明集中块开头，VCS 2017 不支持块中部声明）
        pubip_mseq_gen_tc_mseq_trans1  tc1 = new("tc1");
        pubip_mseq_gen_tc_mseq_border  tc3 = new("tc3");
        pubip_mseq_gen_tc_mseq_random  tc4 = new("tc4");
`ifdef PUBIP_MPG_TRANS4
        pubip_mseq_gen_tc_mseq_trans_n tc2;
`endif
        tc1.m_rst_if = m_rst_if; tc1.m_dut_if = m_dut_if; tc1.m_env = m_env; tc1.m_my_env = m_my_env;
        tc3.m_rst_if = m_rst_if; tc3.m_dut_if = m_dut_if; tc3.m_env = m_env; tc3.m_my_env = m_my_env;
        tc4.m_rst_if = m_rst_if; tc4.m_dut_if = m_dut_if; tc4.m_env = m_env; tc4.m_my_env = m_my_env;
        tc1.body();
        tc3.body();
        tc4.body();
`ifdef PUBIP_MPG_TRANS4
        tc2 = new("tc2");
        tc2.m_rst_if = m_rst_if; tc2.m_dut_if = m_dut_if; tc2.m_env = m_env; tc2.m_my_env = m_my_env;
        tc2.body();
`endif
    endtask
endclass
`endif //U_PUBIP_MSEQ_GEN_TC_ALL
