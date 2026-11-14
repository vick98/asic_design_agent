/*========================================FILE_HEADER=====================================
# Filename: pubip_mseq_gen_sim_top.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_mseq_gen 仿真顶层：时钟复位/DUT 例化（参数随编译宏变体，cfg.svh 单一事实源；
        纯组合无 clk/rst 端口）/+TC 用例选择/超时/波形
        变体宏：默认 SEQ_WIDTH=4/CAL_RULE=31'h3/TRANS_NUM=1；
        PUBIP_MPG_TRANS4 -> TRANS_NUM=4（对应用例 tc_mseq_trans_n 须同宏重编译）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_mseq_gen_cfg.svh"
`include "pubip_mseq_gen_tb_pkg.sv"
`ifndef U_PUBIP_MSEQ_GEN_SIM_TOP
`define U_PUBIP_MSEQ_GEN_SIM_TOP
import tb_pkg::*;
import pubip_mseq_gen_tb_pkg::*;

module pubip_mseq_gen_sim_top;

    //----------- 时钟复位接口（内嵌时钟生成，见 tb_clk_rst_if.sv） ------------
    tb_clk_rst_if #(.CLK_PERIOD(`TB_CLK_PERIOD))  mo_rst_if  ();//时钟复位接口（周期随 TB_CLK_PERIOD 宏联动）

    //----------- DUT 接口 ------------
    pubip_mseq_gen_if                mo_pubip_mseq_gen_if (mo_rst_if.clk_in);//DUT 接口

    //----------- 复位初始化（>=3 周期） ------------
    initial begin
        mo_rst_if.rst_n = 1'b0;
        #(`TB_CLK_PERIOD * 3);
        mo_rst_if.rst_n = 1'b1;
    end

    //----------- DUT 例化（参数随编译宏变体：cfg.svh 单一事实源；纯组合无 clk/rst 端口） ------------
    pubip_mseq_gen #(
        .CAL_RULE                 ( `PUBIP_MPG_CAL_RULE   ),//LFSR反馈多项式（本原多项式）
        .SEQ_WIDTH                ( `PUBIP_MPG_SEQ_WIDTH  ),//序列位宽
        .TRANS_NUM                ( `PUBIP_MPG_TRANS_NUM  ) //单次跨越的LFSR迭代次数
    ) pubip_mseq_gen_inst (
        .i_init_seq               ( mo_pubip_mseq_gen_if.i_init_seq ),//初始序列
        .i_cal_en                 ( mo_pubip_mseq_gen_if.i_cal_en   ),//计算使能：1=输出跨越后的序列，0=旁路 i_init_seq
        .o_seq_out                ( mo_pubip_mseq_gen_if.o_seq_out  ) //输出序列
    );

    //----------- 用例启动：+TC 选择（默认 tc_all），+SEED 播种 ------------
    initial begin
        string tc_name;
        int    seed;
        pubip_mseq_gen_tc_base t;
        tb_test_base tb;

        if (!$value$plusargs("TC=%s", tc_name)) tc_name = "tc_all";
        if ($value$plusargs("SEED=%d", seed)) begin
            $srandom(seed);
        end

        tb = pubip_mseq_gen_tc_factory::create(tc_name);
        if (!$cast(t, tb)) $fatal(1, "TC cast fail: %s", tc_name);
        t.m_rst_if = mo_rst_if;
        t.m_dut_if = mo_pubip_mseq_gen_if;
        t.run();
    end

    //----------- 全局超时（默认 1s，+TB_TIMEOUT_US=<us> 覆盖） ------------
    `TB_TIMEOUT_INIT

    //----------- 调试代码区（DEBUG_CODE_EN 宏隔离，编译加 +define+DEBUG_CODE_EN） ------------
    // 波形文件：由 TB_CASE_BEGIN 宏按用例自动切换 <TB_DUMP_TAG>_case<N>.vcd（默认 wave_caseN.vcd，见 rules/tb.md 6.3 节）
    // 波形标签：可选 +define+TB_DUMP_TAG="pubip_mseq_gen" 覆盖默认前缀 "wave"（ifndef 保护）
    // 随机种子：+SEED=<n>（运行参数，$srandom(seed) 播种生效，见 rules/sim.md）
endmodule
`endif //U_PUBIP_MSEQ_GEN_SIM_TOP
