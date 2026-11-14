/*========================================FILE_HEADER=====================================
# Filename: pubip_sat_sim_top.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_sat 仿真顶层：时钟复位/DUT 例化（参数随编译宏变体）/+TC 用例选择/超时/波形
        变体宏：默认 <16,8,s>-><8,4,s>；PUBIP_SAT_EXPAND/PUBIP_SAT_USIGNED/PUBIP_SAT_PROTECT
        对应用例运行时须同宏重编译（如 +define+PUBIP_SAT_EXPAND 后 +TC=tc_sat_expand）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_sat_cfg.svh"
`include "pubip_sat_tb_pkg.sv"
`ifndef U_PUBIP_SAT_SIM_TOP
`define U_PUBIP_SAT_SIM_TOP
import tb_pkg::*;
import pubip_sat_tb_pkg::*;

module pubip_sat_sim_top;

    //----------- 时钟复位接口（内嵌时钟生成，见 tb_clk_rst_if.sv） ------------
    tb_clk_rst_if #(.CLK_PERIOD(`TB_CLK_PERIOD))  mo_rst_if  ();//时钟复位接口（周期随 TB_CLK_PERIOD 宏联动）

    //----------- DUT 接口 ------------
    pubip_sat_if                     mo_pubip_sat_if      (mo_rst_if.clk_in);//DUT 接口

    //----------- 复位初始化（>=3 周期） ------------
    initial begin
        mo_rst_if.rst_n = 1'b0;
        #(`TB_CLK_PERIOD * 3);
        mo_rst_if.rst_n = 1'b1;
    end

    //----------- DUT 例化（参数随编译宏变体：cfg.svh 单一事实源；纯组合无 clk/rst 端口） ------------
    pubip_sat #(
        .IN_TOTAL_WIDTH           ( `PUBIP_SAT_IN_TOTAL    ),//输入数据总位宽
        .IN_INT_WIDTH             ( `PUBIP_SAT_IN_INT      ),//输入数据整数位宽
        .OUT_TOTAL_WIDTH          ( `PUBIP_SAT_OUT_TOTAL   ),//输出数据总位宽
        .OUT_INT_WIDTH            ( `PUBIP_SAT_OUT_INT     ),//输出数据整数位宽
        .IS_SIGNED                ( `PUBIP_SAT_SIGNED      ),//1=有符号，0=无符号
        .PROTECT_EN               ( `PUBIP_SAT_PROT        ) //1=零值保护，0=关闭
    ) pubip_sat_inst (
        .i_data                   ( mo_pubip_sat_if.i_data ),//输入数据
        .o_data                   ( mo_pubip_sat_if.o_data ) //输出数据（经过饱和截位后）
    );

    //----------- 用例启动：+TC 选择（默认 tc_all），+SEED 播种 ------------
    initial begin
        string tc_name;
        int    seed;
        pubip_sat_tc_base t;
        tb_test_base tb;

        if (!$value$plusargs("TC=%s", tc_name)) tc_name = "tc_all";
        if ($value$plusargs("SEED=%d", seed)) begin
            $srandom(seed);
        end

        tb = pubip_sat_tc_factory::create(tc_name);
        if (!$cast(t, tb)) $fatal(1, "TC cast fail: %s", tc_name);
        t.m_rst_if = mo_rst_if;
        t.m_dut_if = mo_pubip_sat_if;
        t.run();
    end

    //----------- 全局超时（默认 1s，+TB_TIMEOUT_US=<us> 覆盖） ------------
    `TB_TIMEOUT_INIT

    //----------- 调试代码区（DEBUG_CODE_EN 宏隔离，编译加 +define+DEBUG_CODE_EN） ------------
    // 波形文件：由 TB_CASE_BEGIN 宏按用例自动切换 <TB_DUMP_TAG>_case<N>.vcd（默认 wave_caseN.vcd，见 rules/tb.md 6.3 节）
    // 波形标签：可选 +define+TB_DUMP_TAG="pubip_sat" 覆盖默认前缀 "wave"（ifndef 保护）
    // 随机种子：+SEED=<n>（运行参数，$srandom(seed) 播种生效，见 rules/sim.md）
endmodule
`endif //U_PUBIP_SAT_SIM_TOP
