/*========================================FILE_HEADER=====================================
# Filename: pubip_complex_mult_sim_top.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             DUT 例化补全（DINA=10/DINB=6；PUBIP_CM_CONJ 可选 CONJ_EN=1）
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_complex_mult 仿真顶层：时钟复位/DUT 例化（DINA_WIDTH=10/DINB_WIDTH=6，CONJ_EN=0 默认；
        +define+PUBIP_CM_CONJ 编译时 CONJ_EN=1）/ +TC 用例选择/超时/波形
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_complex_mult_tb_pkg.sv"
`ifndef U_PUBIP_COMPLEX_MULT_SIM_TOP
`define U_PUBIP_COMPLEX_MULT_SIM_TOP
import tb_pkg::*;
import pubip_complex_mult_tb_pkg::*;

module pubip_complex_mult_sim_top;

    //----------- 时钟复位接口（内嵌时钟生成，见 tb_clk_rst_if.sv） ------------
    tb_clk_rst_if #(.CLK_PERIOD(`TB_CLK_PERIOD))  mo_rst_if  ();//时钟复位接口（周期随 TB_CLK_PERIOD 宏联动）

    //----------- DUT 接口 ------------
    pubip_complex_mult_if                     mo_pubip_complex_mult_if      (mo_rst_if.clk_in);//DUT 接口

    //----------- 复位初始化（>=3 周期） ------------
    initial begin
        mo_rst_if.rst_n = 1'b0;
        #(`TB_CLK_PERIOD * 3);
        mo_rst_if.rst_n = 1'b1;
    end

    //----------- DUT 例化（DINA=10/DINB=6 默认参数；CONJ_EN=1 变体编译加 +define+PUBIP_CM_CONJ） ------------
    // DUT 无时钟/复位端口（纯组合逻辑），数据信号直连 DUT 接口
`ifdef PUBIP_CM_CONJ
    pubip_complex_mult #(.DINA_WIDTH(10), .DINB_WIDTH(6), .CONJ_EN(1))  pubip_complex_mult_inst (
`else
    pubip_complex_mult #(.DINA_WIDTH(10), .DINB_WIDTH(6), .CONJ_EN(0))  pubip_complex_mult_inst (
`endif
        .i_dina_re          ( mo_pubip_complex_mult_if.i_dina_re ),//输入复数A-实部
        .i_dina_im          ( mo_pubip_complex_mult_if.i_dina_im ),//输入复数A-虚部
        .i_dinb_re          ( mo_pubip_complex_mult_if.i_dinb_re ),//输入复数B-实部
        .i_dinb_im          ( mo_pubip_complex_mult_if.i_dinb_im ),//输入复数B-虚部
        .o_dout_re          ( mo_pubip_complex_mult_if.o_dout_re ),//输出复数-实部
        .o_dout_im          ( mo_pubip_complex_mult_if.o_dout_im )  //输出复数-虚部
    );

    //----------- 用例启动：+TC 选择（默认 tc_all），+SEED 播种 ------------
    initial begin
        string tc_name;
        int    seed;
        pubip_complex_mult_tc_base t;
        tb_test_base tb;

        if (!$value$plusargs("TC=%s", tc_name)) tc_name = "tc_all";
        if ($value$plusargs("SEED=%d", seed)) begin
            $srandom(seed);
        end

        tb = pubip_complex_mult_tc_factory::create(tc_name);
        if (!$cast(t, tb)) $fatal(1, "TC cast fail: %s", tc_name);
        t.m_rst_if = mo_rst_if;
        t.m_dut_if = mo_pubip_complex_mult_if;
        t.run();
    end

    //----------- 全局超时（默认 1s，+TB_TIMEOUT_US=<us> 覆盖） ------------
    `TB_TIMEOUT_INIT

    //----------- 调试代码区（DEBUG_CODE_EN 宏隔离，编译加 +define+DEBUG_CODE_EN） ------------
    // 波形文件：由 TB_CASE_BEGIN 宏按用例自动切换 <TB_DUMP_TAG>_case<N>.vcd（默认 wave_caseN.vcd，见 rules/tb.md 6.3 节）
    // 波形标签：可选 +define+TB_DUMP_TAG="pubip_complex_mult" 覆盖默认前缀 "wave"（ifndef 保护）
    // 随机种子：+SEED=<n>（运行参数，$srandom(seed) 播种生效，见 rules/sim.md）
endmodule
`endif //U_PUBIP_COMPLEX_MULT_SIM_TOP
