/*========================================FILE_HEADER=====================================
# Filename: pubip_mseq_cal_if.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             按 DUT 端口补全信号（i_/o_ 一一对应，i_ 赋初值）
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_mseq_cal 接口：与 DUT 端口一一对应（默认参数 SEQ_WIDTH=31 / TRANS_NUM 固定 15 级）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_PUBIP_MSEQ_CAL_TB_IF
`define U_PUBIP_MSEQ_CAL_TB_IF

//----------- pubip_mseq_cal_if ------------
// clk 由 tb_clk_rst_if 提供；drv_skew/mon_skew 为沿后偏移(ns)
// i_ 输入信号必须赋初值：VCS 按 X 仿真，未初始化输入会经 DUT 打拍链传播至 o_ 控制信号造成 X 态误报
interface pubip_mseq_cal_if (input logic clk_in);

    real                            drv_skew    = 0.1  ;//驱动侧沿后偏移(ns)
    real                            mon_skew    = 0.1  ;//采样侧沿后偏移(ns)

    logic [30:0]                    i_init_seq  = '0    ;//初始 M 序列输入（SEQ_WIDTH=31）
    logic                           i_cal_vld   = 1'b0  ;//计算有效指示（高电平滑锁存输入启动计算）
    logic [14:0]                    i_trans_num = '0    ;//转移次数控制值（15bit，bit[k] ↔ 2^k 级）

    logic [30:0]                    o_seq_out           ;//输出 M 序列（经 i_trans_num 次转移后的结果）
    logic                           o_seq_vld           ;//输出有效指示（相对 i_cal_vld 延迟 5 拍）

endinterface
`endif //U_PUBIP_MSEQ_CAL_TB_IF
