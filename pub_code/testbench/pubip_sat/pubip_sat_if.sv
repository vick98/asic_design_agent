/*========================================FILE_HEADER=====================================
# Filename: pubip_sat_if.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_sat 接口：与 DUT 端口一一对应（i_data/o_data，位宽随编译宏变体）
        clk/rst 由 tb_clk_rst_if 提供；i_ 输入赋初值（VCS 按 X 仿真，防 X 态传播）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_PUBIP_SAT_TB_IF
`define U_PUBIP_SAT_TB_IF
`include "pubip_sat_cfg.svh"

//----------- pubip_sat_if ------------
// 纯组合 DUT：无有效/握手控制信号；i_data 驱动后 o_data 组合响应（零延迟）
interface pubip_sat_if (input logic clk_in);

    real                            drv_skew    = 0.1  ;//驱动侧沿后偏移(ns)
    real                            mon_skew    = 0.1  ;//采样侧沿后偏移(ns)

    logic  [`PUBIP_SAT_IN_TOTAL - 1 : 0]   i_data = '0  ;//输入数据（饱和截位前）
    logic  [`PUBIP_SAT_OUT_TOTAL - 1 : 0]  o_data      ;//输出数据（饱和截位后）

endinterface
`endif //U_PUBIP_SAT_TB_IF
