/*========================================FILE_HEADER=====================================
# Filename: pubip_sat_tc_sat_random.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 sat_random：随机输入 500 拍（$urandom_range 全值域），期望由 refm.compute() 参考公式
        自算（右移/左移/饱和/对称/保护判定），与 DUT 纯组合逐拍对拍；
        播种由 sim_top 按 +SEED=<n> 统一处理，用例内不调用 $srandom
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_sat_tb_pkg.sv"
`ifndef U_PUBIP_SAT_TC_SAT_RANDOM
`define U_PUBIP_SAT_TC_SAT_RANDOM
import pubip_sat_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_sat_tc_sat_random ------------
class pubip_sat_tc_sat_random extends pubip_sat_tc_base;

    function new(string name = "pubip_sat_tc_sat_random");
        super.new(name);
    endfunction

    virtual task body();
        pubip_sat_item seq[$];
        int i;
        logic [`PUBIP_SAT_IN_TOTAL - 1 : 0] rnd;
        reset_wait();
        `TB_CASE_BEGIN("TC6: sat_random");
        m_env.m_scb.m_enable = 1'b1;
        // 500 拍全值域随机（含正/负/溢出/边界自然覆盖），一拍一 item
        for (i = 0; i < 500; i = i + 1) begin
            rnd = $urandom_range(0, (1 << `PUBIP_SAT_IN_TOTAL) - 1);
            push_data(seq, rnd);
        end
        drive_seq(seq);
        `TB_CASE_END("TC6: sat_random", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_PUBIP_SAT_TC_SAT_RANDOM
