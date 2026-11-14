/*========================================FILE_HEADER=====================================
# Filename: pubip_mseq_cal_sim_top.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             DUT 例化补全（默认参数：CAL_RULE=31'h9/SEQ_WIDTH=31）
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_mseq_cal 仿真顶层：时钟复位/DUT 例化（默认参数，内部 15 级转移链与 5 拍延迟固定）/
        +TC 用例选择/超时/波形
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_mseq_cal_tb_pkg.sv"
`ifndef U_PUBIP_MSEQ_CAL_SIM_TOP
`define U_PUBIP_MSEQ_CAL_SIM_TOP
import tb_pkg::*;
import pubip_mseq_cal_tb_pkg::*;

module pubip_mseq_cal_sim_top;

    //----------- 时钟复位接口（内嵌时钟生成，见 tb_clk_rst_if.sv） ------------
    tb_clk_rst_if #(.CLK_PERIOD(`TB_CLK_PERIOD))  mo_rst_if  ();//时钟复位接口（周期随 TB_CLK_PERIOD 宏联动）

    //----------- DUT 接口 ------------
    pubip_mseq_cal_if                     mo_pubip_mseq_cal_if      (mo_rst_if.clk_in);//DUT 接口

    //----------- 复位初始化（>=3 周期） ------------
    initial begin
        mo_rst_if.rst_n = 1'b0;
        #(`TB_CLK_PERIOD * 3);
        mo_rst_if.rst_n = 1'b1;
    end

    //----------- DUT 例化（默认参数：CAL_RULE=31'h9/SEQ_WIDTH=31，内部 15 级转移链与 5 拍延迟固化） ------------
    pubip_mseq_cal                 pubip_mseq_cal_inst (
        .clk_in                   ( mo_rst_if.clk_in               ),//时钟输入
        .rst_n                    ( mo_rst_if.rst_n                ),//异步复位低有效
        .i_init_seq               ( mo_pubip_mseq_cal_if.i_init_seq ),//初始M序列输入
        .i_cal_vld                ( mo_pubip_mseq_cal_if.i_cal_vld  ),//计算有效指示
        .i_trans_num              ( mo_pubip_mseq_cal_if.i_trans_num ),//转移次数控制值
        .o_seq_out                ( mo_pubip_mseq_cal_if.o_seq_out  ),//输出M序列
        .o_seq_vld                ( mo_pubip_mseq_cal_if.o_seq_vld  ) //输出M序列有效指示
    );

    //----------- 用例启动：+TC 选择（默认 tc_all），+SEED 播种 ------------
    initial begin
        string tc_name;
        int    seed;
        pubip_mseq_cal_tc_base t;
        tb_test_base tb;

        if (!$value$plusargs("TC=%s", tc_name)) tc_name = "tc_all";
        if ($value$plusargs("SEED=%d", seed)) begin
            $srandom(seed);
        end

        tb = pubip_mseq_cal_tc_factory::create(tc_name);
        if (!$cast(t, tb)) $fatal(1, "TC cast fail: %s", tc_name);
        t.m_rst_if = mo_rst_if;
        t.m_dut_if = mo_pubip_mseq_cal_if;
        t.run();
    end

    //----------- 全局超时（默认 1s，+TB_TIMEOUT_US=<us> 覆盖） ------------
    `TB_TIMEOUT_INIT

    //----------- 调试代码区（DEBUG_CODE_EN 宏隔离，编译加 +define+DEBUG_CODE_EN） ------------
    // 波形文件：由 TB_CASE_BEGIN 宏按用例自动切换 <TB_DUMP_TAG>_case<N>.vcd（默认 wave_caseN.vcd，见 rules/tb.md 6.3 节）
    // 波形标签：可选 +define+TB_DUMP_TAG="pubip_mseq_cal" 覆盖默认前缀 "wave"（ifndef 保护）
    // 随机种子：+SEED=<n>（运行参数，$srandom(seed) 播种生效，见 rules/sim.md）
endmodule
`endif //U_PUBIP_MSEQ_CAL_SIM_TOP
