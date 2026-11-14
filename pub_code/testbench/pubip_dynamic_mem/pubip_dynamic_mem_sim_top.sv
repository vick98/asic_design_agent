/*========================================FILE_HEADER=====================================
# Filename: pubip_dynamic_mem_sim_top.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             DUT 例化补全（默认 MEM_DEPTH=64；PUBIP_DMEM_SMALL 可选 16 缩短边界扫描）
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_dynamic_mem 仿真顶层：时钟复位/DUT 例化（默认参数 64/32/4；主验证 P0-7 满深度用默认 64）/
        +TC 用例选择/+SEED 播种/全局超时
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_dynamic_mem_tb_pkg.sv"
`ifndef U_PUBIP_DYNAMIC_MEM_SIM_TOP
`define U_PUBIP_DYNAMIC_MEM_SIM_TOP
import tb_pkg::*;
import pubip_dynamic_mem_tb_pkg::*;

module pubip_dynamic_mem_sim_top;

    //----------- 时钟复位接口（内嵌时钟生成，见 tb_clk_rst_if.sv） ------------
    tb_clk_rst_if #(.CLK_PERIOD(`TB_CLK_PERIOD))  mo_rst_if  ();//时钟复位接口（周期随 TB_CLK_PERIOD 宏联动）

    //----------- DUT 接口 ------------
    pubip_dynamic_mem_if                     mo_pubip_dynamic_mem_if      (mo_rst_if.clk_in);//DUT 接口

    //----------- 复位初始化（>=3 周期） ------------
    initial begin
        mo_rst_if.rst_n = 1'b0;
        #(`TB_CLK_PERIOD * 3);
        mo_rst_if.rst_n = 1'b1;
    end

    //----------- DUT 例化（默认 MEM_DEPTH=64/DATA_WIDTH=32/ID_WIDTH=4；+define+PUBIP_DMEM_SMALL 时深度 16） ------------
`ifdef PUBIP_DMEM_SMALL
    pubip_dynamic_mem #(.MEM_DEPTH(16), .DATA_WIDTH(32), .ID_WIDTH(4)) pubip_dynamic_mem_inst (
`else
    pubip_dynamic_mem #(.MEM_DEPTH(64), .DATA_WIDTH(32), .ID_WIDTH(4)) pubip_dynamic_mem_inst (
`endif
        .clk_in               ( mo_rst_if.clk_in                  ),//时钟输入
        .rst_n                ( mo_rst_if.rst_n                   ),//异步复位低有效
        .o_wr_ready           ( mo_pubip_dynamic_mem_if.o_wr_ready   ),//模块写入就绪指示
        .i_wr_vld             ( mo_pubip_dynamic_mem_if.i_wr_vld     ),//写入有效指示
        .i_wr_id              ( mo_pubip_dynamic_mem_if.i_wr_id      ),//写入数据对应ID
        .i_wr_data            ( mo_pubip_dynamic_mem_if.i_wr_data    ),//写入数据
        .i_rd_id_vld          ( mo_pubip_dynamic_mem_if.i_rd_id_vld  ),//读取调度ID有效指示
        .i_rd_id              ( mo_pubip_dynamic_mem_if.i_rd_id      ),//读取调度ID
        .o_rd_ready           ( mo_pubip_dynamic_mem_if.o_rd_ready   ),//模块读取就绪指示
        .i_rd_vld             ( mo_pubip_dynamic_mem_if.i_rd_vld     ),//后级读取有效指示
        .o_rd_data            ( mo_pubip_dynamic_mem_if.o_rd_data    ),//读取数据输出
        .o_rd_last            ( mo_pubip_dynamic_mem_if.o_rd_last    ),//当前输出为对应ID最后一笔指示
        .o_free_cnt           ( mo_pubip_dynamic_mem_if.o_free_cnt   ),//当前剩余空间个数
        .o_schd_id            ( mo_pubip_dynamic_mem_if.o_schd_id    ),//当前调度输出ID指示
        .o_schd_id_remain     ( mo_pubip_dynamic_mem_if.o_schd_id_remain )//当前调度ID剩余数据个数
    );

    //----------- 用例启动：+TC 选择（默认 tc_all），+SEED 播种 ------------
    initial begin
        string tc_name;
        int    seed;
        pubip_dynamic_mem_tc_base t;
        tb_test_base tb;

        if (!$value$plusargs("TC=%s", tc_name)) tc_name = "tc_all";
        if ($value$plusargs("SEED=%d", seed)) begin
            $srandom(seed);
        end

        tb = pubip_dynamic_mem_tc_factory::create(tc_name);
        if (!$cast(t, tb)) $fatal(1, "TC cast fail: %s", tc_name);
        t.m_rst_if = mo_rst_if;
        t.m_dut_if = mo_pubip_dynamic_mem_if;
        t.run();
    end

    //----------- 全局超时（默认 1s，+TB_TIMEOUT_US=<us> 覆盖） ------------
    `TB_TIMEOUT_INIT

    //----------- 调试代码区（DEBUG_CODE_EN 宏隔离，编译加 +define+DEBUG_CODE_EN） ------------
    // 波形文件：由 TB_CASE_BEGIN 宏按用例自动切换 <TB_DUMP_TAG>_case<N>.vcd（默认 wave_caseN.vcd，见 rules/tb.md 6.3 节）
    // 波形标签：可选 +define+TB_DUMP_TAG="pubip_dynamic_mem" 覆盖默认前缀 "wave"（ifndef 保护）
    // 随机种子：+SEED=<n>（运行参数，$srandom(seed) 播种生效，见 rules/sim.md）
endmodule
`endif //U_PUBIP_DYNAMIC_MEM_SIM_TOP
