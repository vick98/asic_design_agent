/*========================================FILE_HEADER=====================================
# Filename: pubip_sat_tc_all.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_sat 聚合用例（默认配置：顺序执行全部默认用例，共享 env）；
        变体用例（protect/expand/unsigned）需对应编译宏，按宏取值加入本聚合
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_sat_tb_pkg.sv"
`ifndef U_PUBIP_SAT_TC_ALL
`define U_PUBIP_SAT_TC_ALL
import pubip_sat_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_sat_tc_all ------------
class pubip_sat_tc_all extends pubip_sat_tc_base;

    function new(string name = "pubip_sat_tc_all");
        super.new(name);
    endfunction

    virtual task body();
        // 默认配置用例（共享 env，pass/fail 累计）
        pubip_sat_tc_sat_down_align tc1 = new("tc1");
        pubip_sat_tc_sat_neg       tc2 = new("tc2");
        pubip_sat_tc_sat_ovf_pos   tc3 = new("tc3");
        pubip_sat_tc_sat_ovf_neg   tc4 = new("tc4");
        pubip_sat_tc_sat_random    tc6 = new("tc6");
        tc1.m_rst_if = m_rst_if; tc1.m_dut_if = m_dut_if; tc1.m_env = m_env; tc1.m_my_env = m_my_env;
        tc2.m_rst_if = m_rst_if; tc2.m_dut_if = m_dut_if; tc2.m_env = m_env; tc2.m_my_env = m_my_env;
        tc3.m_rst_if = m_rst_if; tc3.m_dut_if = m_dut_if; tc3.m_env = m_env; tc3.m_my_env = m_my_env;
        tc4.m_rst_if = m_rst_if; tc4.m_dut_if = m_dut_if; tc4.m_env = m_env; tc4.m_my_env = m_my_env;
        tc6.m_rst_if = m_rst_if; tc6.m_dut_if = m_dut_if; tc6.m_env = m_env; tc6.m_my_env = m_my_env;
        tc1.body();
        tc2.body();
        tc3.body();
        tc4.body();
        tc6.body();
        // 变体用例（zero_protect/expand/unsigned）不进 tc_all 聚合：
        //   需对应编译宏重编译，经 factory 以 +TC=tc_sat_<name> 单独运行（见 tb_handoff_sat.md）
        //   （VCS 2017.03 对条件编译块内类类型变量声明存在解析异常，聚合引用会报 SE 语法错误；
        //     删除聚合段后对应宏编译下 tc_all 亦可正常编译，变体覆盖不受影响）
    endtask
endclass
`endif //U_PUBIP_SAT_TC_ALL
