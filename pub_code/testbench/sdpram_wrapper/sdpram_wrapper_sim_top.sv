/*========================================FILE_HEADER=====================================
# Filename: sdpram_wrapper_sim_top.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-31        vick             INIT_FILE 删除（DUT 不再支持初始化），例化去宏分支
#
#-----------------------------------------------------------------------------------------
# Description:
        sdpram_wrapper 仿真顶层：时钟复位/DUT 例化/+TC 用例选择/超时/波形
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "sdpram_wrapper_tb_pkg.sv"
`ifndef U_SDPRAM_WRAPPER_SIM_TOP
`define U_SDPRAM_WRAPPER_SIM_TOP
import tb_pkg::*;
import sdpram_wrapper_tb_pkg::*;

module sdpram_wrapper_sim_top;

    //----------- 时钟复位接口（内嵌时钟生成，见 tb_clk_rst_if.sv） ------------
    tb_clk_rst_if #(.CLK_PERIOD(`TB_CLK_PERIOD))  mo_rst_if  ();//时钟复位接口（周期随 TB_CLK_PERIOD 宏联动）

    //----------- DUT 接口 ------------
    sdpram_wrapper_if                     mo_sdpram_wrapper_if      (mo_rst_if.clk_in);//DUT 接口

    //----------- 复位初始化（>=3 周期；DUT 无复位端口，仅用于接口/框架时序） ------------
    initial begin
        mo_rst_if.rst_n = 1'b0;
        #(`TB_CLK_PERIOD * 3);
        mo_rst_if.rst_n = 1'b1;
    end

    //----------- DUT 例化（默认参数 32x64） ------------
    sdpram_wrapper #(
        .DATA_WIDTH               ( 32         ),//数据位宽
        .ADDR_WIDTH               ( 6          ),//地址位宽，对应深度 64
        .BYTE_EN_WIDTH            ( 4          ) //字节使能位宽
    ) sdpram_wrapper_inst (
        .clk_in                   ( mo_rst_if.clk_in               ),//时钟输入
        .i_wea                    ( mo_sdpram_wrapper_if.i_wea    ),//写使能，高有效
        .i_bea                    ( mo_sdpram_wrapper_if.i_bea    ),//字节使能，每bit对应一个字节
        .i_addra                  ( mo_sdpram_wrapper_if.i_addra  ),//写地址
        .i_dina                   ( mo_sdpram_wrapper_if.i_dina   ),//写数据
        .i_reb                    ( mo_sdpram_wrapper_if.i_reb    ),//读使能，高有效
        .i_addrb                  ( mo_sdpram_wrapper_if.i_addrb  ),//读地址
        .o_doutb                  ( mo_sdpram_wrapper_if.o_doutb   ) //读数据，i_reb有效后下一拍输出
    );

    //----------- 用例启动：+TC 选择（默认 tc_all），+SEED 播种 ------------
    initial begin
        string tc_name;
        int    seed;
        sdpram_wrapper_tc_base t;
        tb_test_base tb;

        if (!$value$plusargs("TC=%s", tc_name)) tc_name = "tc_all";
        if ($value$plusargs("SEED=%d", seed)) begin
            $srandom(seed);
        end

        tb = sdpram_wrapper_tc_factory::create(tc_name);
        if (!$cast(t, tb)) $fatal(1, "TC cast fail: %s", tc_name);
        t.m_rst_if = mo_rst_if;
        t.m_dut_if = mo_sdpram_wrapper_if;
        t.run();
    end

    //----------- 全局超时（默认 1s，+TB_TIMEOUT_US=<us> 覆盖） ------------
    `TB_TIMEOUT_INIT

    //----------- 调试代码区（DEBUG_CODE_EN 宏隔离，编译加 +define+DEBUG_CODE_EN） ------------
    // 波形文件：由 TB_CASE_BEGIN 宏按用例自动切换 <TB_DUMP_TAG>_case<N>.vcd（默认 wave_caseN.vcd，见 rules/tb.md 6.3 节）
    // 波形标签：可选 +define+TB_DUMP_TAG="sdpram_wrapper" 覆盖默认前缀 "wave"（ifndef 保护）
    // 随机种子：+SEED=<n>（运行参数，$srandom(seed) 播种生效，见 rules/sim.md）
endmodule
`endif //U_SDPRAM_WRAPPER_SIM_TOP
