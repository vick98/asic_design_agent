/*========================================FILE_HEADER=====================================
# Filename: pubip_dynamic_mem_tc_all.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             类实例声明集中块首（VCs 2017 不支持块中部声明）
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_dynamic_mem 聚合用例（顺序执行全部用例，共享 env）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_dynamic_mem_tb_pkg.sv"
`ifndef U_PUBIP_DYNAMIC_MEM_TC_ALL
`define U_PUBIP_DYNAMIC_MEM_TC_ALL
import pubip_dynamic_mem_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_dynamic_mem_tc_all ------------
// 聚合用例：顺序执行全部已注册用例（共享本 env，不各自 build_env；
//   tb_test_base.run() 以 $finish 结尾，故不能对各用例调 run()）
class pubip_dynamic_mem_tc_all extends pubip_dynamic_mem_tc_base;

    function new(string name = "pubip_dynamic_mem_tc_all");
        super.new(name);
    endfunction

    virtual task body();
        // 按 --tcs 顺序依次执行（共享 env，pass/fail 累计）
        // 声明集中块开头（VCS 2017.03 不支持块中部声明，实测跨类声明报 token 语法错），
        // 先全部声明 → 分发接口 → 顺序调用 body()
        pubip_dynamic_mem_tc_wr_rd      tc1 = new("tc1");
        pubip_dynamic_mem_tc_multi_id   tc2 = new("tc2");
        pubip_dynamic_mem_tc_full_depth tc3 = new("tc3");
        pubip_dynamic_mem_tc_rd_last    tc4 = new("tc4");
        pubip_dynamic_mem_tc_conflict   tc5 = new("tc5");
        pubip_dynamic_mem_tc_remain     tc6 = new("tc6");
        pubip_dynamic_mem_tc_random     tc7 = new("tc7");
        tc1.m_rst_if = m_rst_if;
        tc1.m_dut_if = m_dut_if;
        tc1.m_env    = m_env;
        tc1.m_my_env = m_my_env;
        tc1.body();
        tc2.m_rst_if = m_rst_if;
        tc2.m_dut_if = m_dut_if;
        tc2.m_env    = m_env;
        tc2.m_my_env = m_my_env;
        tc2.body();
        tc3.m_rst_if = m_rst_if;
        tc3.m_dut_if = m_dut_if;
        tc3.m_env    = m_env;
        tc3.m_my_env = m_my_env;
        tc3.body();
        tc4.m_rst_if = m_rst_if;
        tc4.m_dut_if = m_dut_if;
        tc4.m_env    = m_env;
        tc4.m_my_env = m_my_env;
        tc4.body();
        tc5.m_rst_if = m_rst_if;
        tc5.m_dut_if = m_dut_if;
        tc5.m_env    = m_env;
        tc5.m_my_env = m_my_env;
        tc5.body();
        tc6.m_rst_if = m_rst_if;
        tc6.m_dut_if = m_dut_if;
        tc6.m_env    = m_env;
        tc6.m_my_env = m_my_env;
        tc6.body();
        tc7.m_rst_if = m_rst_if;
        tc7.m_dut_if = m_dut_if;
        tc7.m_env    = m_env;
        tc7.m_my_env = m_my_env;
        tc7.body();
    endtask
endclass
`endif //U_PUBIP_DYNAMIC_MEM_TC_ALL
