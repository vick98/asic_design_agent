/*========================================FILE_HEADER=====================================
# Filename: pubip_counter_sim_top.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             DUT 例化补全（MAX_NUM=8 统一参验；PUBIP_CNT_CYCLE 可选 CYCLE_EN=1）
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_counter 仿真顶层：时钟复位/DUT 例化（MAX_NUM=8，验证 CNT_WIDTH 位宽修复与 9bit 脉冲输出）/
        +TC 用例选择/超时/波形
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_counter_tb_pkg.sv"
`ifndef U_PUBIP_COUNTER_SIM_TOP
`define U_PUBIP_COUNTER_SIM_TOP
import tb_pkg::*;
import pubip_counter_tb_pkg::*;

module pubip_counter_sim_top;

    //----------- 时钟复位接口（内嵌时钟生成，见 tb_clk_rst_if.sv） ------------
    tb_clk_rst_if                   mo_rst_if           ();//时钟复位接口

    //----------- DUT 接口 ------------
    pubip_counter_if                mo_pubip_counter_if (mo_rst_if.clk_in);//DUT 接口

    //----------- 复位初始化（>=3 周期） ------------
    initial begin
        mo_rst_if.rst_n = 1'b0;
        #(`TB_CLK_PERIOD * 3);
        mo_rst_if.rst_n = 1'b1;
    end

    //----------- DUT 例化（MAX_NUM=8：CNT_WIDTH=4、o_cnt_shift 9bit；循环模式用例编译加 +define+PUBIP_CNT_CYCLE） ------------
`ifdef PUBIP_CNT_CYCLE
    pubip_counter #(.MAX_NUM(8), .CYCLE_EN(1))  pubip_counter_inst (
`else
    pubip_counter #(.MAX_NUM(8))                pubip_counter_inst (
`endif
        .clk_in               ( mo_rst_if.clk_in               ),//时钟输入
        .rst_n                ( mo_rst_if.rst_n                ),//异步复位低有效
        .i_cnt_start_b1       ( mo_pubip_counter_if.i_cnt_start_b1 ),//计数启动脉冲
        .i_cnt_rst            ( mo_pubip_counter_if.i_cnt_rst  ),//计数复位
        .i_cnt_end            ( mo_pubip_counter_if.i_cnt_end  ),//计数停止
        .o_cnt_en             ( mo_pubip_counter_if.o_cnt_en   ),//计数使能输出
        .o_counter            ( mo_pubip_counter_if.o_counter  ),//计数器数值输出
        .o_cnt_shift          ( mo_pubip_counter_if.o_cnt_shift ) //计数器脉冲输出
    );

    //----------- 用例启动：+TC 选择（默认 tc_all），+SEED 播种 ------------
    initial begin
        string tc_name;
        int    seed;
        pubip_counter_tc_base t;
        tb_test_base tb;

        if (!$value$plusargs("TC=%s", tc_name)) tc_name = "tc_all";
        if ($value$plusargs("SEED=%d", seed)) begin
            $srandom(seed);
        end

        tb = pubip_counter_tc_factory::create(tc_name);
        if (!$cast(t, tb)) $fatal(1, "TC cast fail: %s", tc_name);
        t.m_rst_if = mo_rst_if;
        t.m_dut_if = mo_pubip_counter_if;
        t.run();
    end

    //----------- 全局超时（默认 1s，+TB_TIMEOUT_US=<us> 覆盖） ------------
    `TB_TIMEOUT_INIT

    //----------- 调试代码区（DEBUG_CODE_EN 宏隔离，编译加 +define+DEBUG_CODE_EN） ------------
    // 波形文件：由 TB_CASE_BEGIN 宏按用例自动切换 <TB_DUMP_TAG>_case<N>.vcd（默认 wave_caseN.vcd，见 rules/tb.md 6.3 节）
    // 随机种子：+SEED=<n>（运行参数，$srandom(seed) 播种生效，见 rules/sim.md）
endmodule
`endif //U_PUBIP_COUNTER_SIM_TOP
