/*========================================FILE_HEADER=====================================
# Filename: tb_clk_rst_if.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-01        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        轻量级 UVM 风格自测平台框架 - 时钟复位虚拟接口
        内嵌时钟生成（initial 复位初值 + always 周期翻转），
        drv_skew/mon_skew 为驱动/采样侧沿后偏移(ns)，
        等效 clocking 块 cb_drv/cb_mon 的 input skew（本框架禁用 clocking 块）
#-----------------------------------------------------------------------------------------
#快速例化示例
tb_clk_rst_if #(
    .CLK_PERIOD               ( 10          ) //时钟周期(ns)
) rst_if(
    .clk_in                   ( clk_in      ),//时钟输出
    .rst_n                    ( rst_n       ) //复位输出，低有效
);
=========================================FILE_HEADER====================================*/
`ifndef U_TB_CLK_RST_IF
`define U_TB_CLK_RST_IF
`timescale 1ns/1ps

interface tb_clk_rst_if #(
    parameter real CLK_PERIOD = 10//时钟周期(ns)
) (
    output logic                clk_in      ,//时钟输出
    output logic                rst_n        //复位输出，低有效
);
//======================== main signal define =================================
    //------ 时序控制参数 ------
    real                        drv_skew    = 0.1    ;//驱动侧沿后偏移(ns)，等效 clocking cb_drv input skew
    real                        mon_skew    = 0.1    ;//采样侧沿后偏移(ns)，等效 clocking cb_mon input skew

//======================== main process ===================================
//----------- 时钟生成 ------------
// 内嵌时钟生成：0 时刻赋初值，此后每 CLK_PERIOD/2 翻转一次
    initial begin
        clk_in = 1'b0;
    end
    always #(CLK_PERIOD/2) clk_in = ~clk_in;

endinterface

`endif
