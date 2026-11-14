/*========================================FILE_HEADER=====================================
# Filename: sdpram_wrapper_if.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             按 DUT 端口补齐全部信号（默认参数 32x64 配置）
#
#-----------------------------------------------------------------------------------------
# Description:
        sdpram_wrapper 接口：与 DUT 端口一一对应（DATA_WIDTH=32/ADDR_WIDTH=6/BYTE_EN_WIDTH=4），
        i_ 输入信号赋初值（VCS 按 X 仿真，见 rules/tb.md 第 4 章步骤 2）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_SDPRAM_WRAPPER_TB_IF
`define U_SDPRAM_WRAPPER_TB_IF

//----------- sdpram_wrapper_if ------------
// clk 由 tb_clk_rst_if 提供；drv_skew/mon_skew 为沿后偏移(ns)
// 一拍一个事务：driver 在 negedge 驱动，DUT 在下一 posedge 采样（读输出下一拍可抄，实际 0 拍内部寄存器输出）
interface sdpram_wrapper_if (input logic clk_in);

    real                            drv_skew    = 0.1  ;//驱动侧沿后偏移(ns)
    real                            mon_skew    = 0.1  ;//采样侧沿后偏移(ns)

    logic                           i_wea       = 1'b0 ;//写使能，高有效
    logic [3:0]                     i_bea       = 4'h0 ;//字节使能，每bit对应一个字节
    logic [5:0]                     i_addra     = 6'h0 ;//写地址
    logic [31:0]                    i_dina      = 32'h0;//写数据
    logic                           i_reb       = 1'b0 ;//读使能，高有效
    logic [5:0]                     i_addrb     = 6'h0 ;//读地址

    logic [31:0]                    o_doutb             ;//读数据，i_reb 有效后下一拍输出

endinterface
`endif //U_SDPRAM_WRAPPER_TB_IF
