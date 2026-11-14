/*========================================FILE_HEADER=====================================
# Filename: pubip_mseq_gen_if.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_mseq_gen 接口：与 DUT 端口一一对应（位宽随 cfg 编译宏变体）
        clk/rst 由 tb_clk_rst_if 提供；i_ 输入赋初值（VCS 按 X 仿真，防 X 态传播）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_PUBIP_MSEQ_GEN_TB_IF
`define U_PUBIP_MSEQ_GEN_TB_IF
`include "pubip_mseq_gen_cfg.svh"

//----------- pubip_mseq_gen_if ------------
// 纯组合 DUT：i_init_seq/i_cal_en 驱动后 o_seq_out 组合响应（零延迟）
interface pubip_mseq_gen_if (input logic clk_in);

    real                            drv_skew    = 0.1  ;//驱动侧沿后偏移(ns)
    real                            mon_skew    = 0.1  ;//采样侧沿后偏移(ns)

    logic [`PUBIP_MPG_SEQ_WIDTH - 1 : 0]  i_init_seq = '0   ;//初始序列
    logic                                i_cal_en   = 1'b0 ;//计算使能：1=转移 TRANS_NUM 步，0=旁路
    logic [`PUBIP_MPG_SEQ_WIDTH - 1 : 0]  o_seq_out        ;//输出序列

endinterface
`endif //U_PUBIP_MSEQ_GEN_TB_IF
