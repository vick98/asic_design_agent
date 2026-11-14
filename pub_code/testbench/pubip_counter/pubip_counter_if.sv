/*========================================FILE_HEADER=====================================
# Filename: pubip_counter_if.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             按 DUT 端口补全信号（MAX_NUM=8 参验配置）
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_counter 接口：与 DUT 端口一一对应（MAX_NUM=8，o_counter 4bit，o_cnt_shift 9bit）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_PUBIP_COUNTER_TB_IF
`define U_PUBIP_COUNTER_TB_IF

//----------- pubip_counter_if ------------
// clk/rst 由 tb_clk_rst_if 提供；drv_skew/mon_skew 为沿后偏移(ns)
interface pubip_counter_if (input logic clk_in);

    real                            drv_skew    = 0.1  ;//驱动侧沿后偏移(ns)
    real                            mon_skew    = 0.1  ;//采样侧沿后偏移(ns)

    logic                           i_cnt_start_b1  = 1'b0;//计数启动脉冲（脉冲一拍）
    logic                           i_cnt_rst       = 1'b0;//计数复位（脉冲一拍）
    logic                           i_cnt_end       = 1'b0;//计数停止（脉冲一拍）

    logic                           o_cnt_en            ;//计数使能输出
    logic [3:0]                     o_counter           ;//计数器数值输出（CNT_WIDTH=4）
    logic [8:0]                     o_cnt_shift         ;//计数脉冲输出（MAX_NUM+1=9bit，bit j ↔ 计数值 j）

endinterface
`endif //U_PUBIP_COUNTER_TB_IF
