/*========================================FILE_HEADER=====================================
# Filename: pubip_complex_mult_if.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             按 DUT 端口补全信号（DINA=10/DINB=6，输出 16bit）
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_complex_mult 接口：与 DUT 端口一一对应（DINA_WIDTH=10/DINB_WIDTH=6，
        o_dout 16bit signed；DUT 纯组合无时钟/复位，接口仍带 clk_in 供组件时序）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_PUBIP_COMPLEX_MULT_TB_IF
`define U_PUBIP_COMPLEX_MULT_TB_IF

//----------- pubip_complex_mult_if ------------
// clk/rst 由 tb_clk_rst_if 提供；drv_skew/mon_skew 为沿后偏移(ns)
interface pubip_complex_mult_if (input logic clk_in);

    real                            drv_skew    = 0.1  ;//驱动侧沿后偏移(ns)
    real                            mon_skew    = 0.1  ;//采样侧沿后偏移(ns)

    logic signed [9:0]               i_dina_re   = '0    ;//输入复数A-实部（10bit 有符号）
    logic signed [9:0]               i_dina_im   = '0    ;//输入复数A-虚部（10bit 有符号）
    logic signed [5:0]               i_dinb_re   = '0    ;//输入复数B-实部（6bit 有符号）
    logic signed [5:0]               i_dinb_im   = '0    ;//输入复数B-虚部（6bit 有符号）

    logic signed [15:0]              o_dout_re           ;//输出复数-实部（16bit 有符号）
    logic signed [15:0]              o_dout_im           ;//输出复数-虚部（16bit 有符号）

endinterface
`endif //U_PUBIP_COMPLEX_MULT_TB_IF
