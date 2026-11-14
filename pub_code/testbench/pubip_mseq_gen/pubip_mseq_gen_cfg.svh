/*========================================FILE_HEADER=====================================
# Filename: pubip_mseq_gen_cfg.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_mseq_gen 参数配置宏中心（单一事实源）：按编译宏选择 DUT 例化参数变体，
        供 if/item/driver/monitor/refm/scoreboard/sim_top/tc 统一引用位宽与参数。
        变体宏（编译命令行 +define+ 传入，默认不定义）：
          PUBIP_MPG_TRANS4 ：TRANS_NUM 4 跨步配置（与默认 TRANS_NUM=1 共用的 SEQ_WIDTH=4）
        参数说明（LFSR 语义，已与 RTL {^(CAL_RULE & state), state>>1} 核对）：
          CAL_RULE 为 LFSR 反馈抽头位掩码：bit k = 1 表示多项式 x^k 项；
          x^N 项由序列位宽隐含（TRANS_NUM 个转移步内不回环）。本原多项式约定：
          x^4+x+1  -> 抽头 bits {1,0} -> 4'b0011（周期 15，已用枚举校验）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_PUBIP_MSEQ_GEN_CFG
`define U_PUBIP_MSEQ_GEN_CFG

//----------- 参数变体（编译宏选择：TRANS4 为多步跨步配置，默认单步） ------------
`ifdef PUBIP_MPG_TRANS4
`define PUBIP_MPG_SEQ_WIDTH   4      //序列位宽（LFSR 级数）
`define PUBIP_MPG_CAL_RULE    31'h3  //LFSR 反馈多项式（x^4+x+1，抽头 bits {1,0}=4'b0011，位宽固定 31 与 RTL 默认一致）
`define PUBIP_MPG_TRANS_NUM   4      //单次跨越的 LFSR 迭代次数
`else // 默认：小参验配置（缩短矩阵展开编译时间）
`define PUBIP_MPG_SEQ_WIDTH   4      //序列位宽（LFSR 级数）
`define PUBIP_MPG_CAL_RULE    31'h3  //LFSR 反馈多项式（x^4+x+1，抽头 bits {1,0}=4'b0011，位宽固定 31 与 RTL 默认一致）
`define PUBIP_MPG_TRANS_NUM   1      //单次跨越的 LFSR 迭代次数
`endif

`endif //U_PUBIP_MSEQ_GEN_CFG
