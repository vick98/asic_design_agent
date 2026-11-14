/*========================================FILE_HEADER=====================================
# Filename: sdpram_wrapper_tc_all.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             聚合 5 个用例（init_file 需宏单独编译，不聚合）
#   1.2     2026-08-31        vick             移除 init_file 聚合（INIT_FILE 功能随 DUT 删除），聚合 4 个用例
#
#-----------------------------------------------------------------------------------------
# Description:
        sdpram_wrapper 聚合用例（顺序执行全部用例，共享 env）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "sdpram_wrapper_tb_pkg.sv"
`ifndef U_SDPRAM_WRAPPER_TC_ALL
`define U_SDPRAM_WRAPPER_TC_ALL
import sdpram_wrapper_tb_pkg::*;
import tb_pkg::*;

//----------- sdpram_wrapper_tc_all ------------
class sdpram_wrapper_tc_all extends sdpram_wrapper_tc_base;

    function new(string name = "sdpram_wrapper_tc_all");
        super.new(name);
    endfunction

    virtual task body();
        sdpram_wrapper_tc_wr_rd        tc1 = new("tc1");
        sdpram_wrapper_tc_byte_en      tc2 = new("tc2");
        sdpram_wrapper_tc_write_first  tc3 = new("tc3");
        sdpram_wrapper_tc_rand         tc4 = new("tc4");
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
`endif //U_SDPRAM_WRAPPER_TC_ALL
