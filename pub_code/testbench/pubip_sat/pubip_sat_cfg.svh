/*========================================FILE_HEADER=====================================
# Filename: pubip_sat_cfg.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_sat 参数配置宏中心（单一事实源）：按编译宏选择 DUT 例化参数变体，
        供 if/item/driver/monitor/refm/scoreboard/sim_top/tc 统一引用位宽与模式。
        变体宏（编译命令行 +define+ 传入，互斥，默认不定义）：
          PUBIP_SAT_EXPAND  ：位宽扩展 <8,4,s> -> <16,8,s>（P0-4）
          PUBIP_SAT_USIGNED ：无符号 <16,8,u> -> <8,4,u>
          PUBIP_SAT_PROTECT ：默认位宽 + PROTECT_EN=1
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_PUBIP_SAT_CFG
`define U_PUBIP_SAT_CFG

//----------- 参数变体（编译宏互斥选择，优先级 EXPAND > USIGNED > PROTECT > 默认） ------------
`ifdef PUBIP_SAT_EXPAND
`define PUBIP_SAT_IN_TOTAL   8    //输入数据总位宽
`define PUBIP_SAT_IN_INT     4    //输入数据整数位宽
`define PUBIP_SAT_OUT_TOTAL  16   //输出数据总位宽
`define PUBIP_SAT_OUT_INT    8    //输出数据整数位宽
`define PUBIP_SAT_SIGNED     1    //1=有符号，0=无符号
`define PUBIP_SAT_PROT       0    //1=零值保护，0=关闭
`elsif PUBIP_SAT_USIGNED
`define PUBIP_SAT_IN_TOTAL   16   //输入数据总位宽
`define PUBIP_SAT_IN_INT     8    //输入数据整数位宽
`define PUBIP_SAT_OUT_TOTAL  8    //输出数据总位宽
`define PUBIP_SAT_OUT_INT    4    //输出数据整数位宽
`define PUBIP_SAT_SIGNED     0    //1=有符号，0=无符号
`define PUBIP_SAT_PROT       0    //1=零值保护，0=关闭
`elsif PUBIP_SAT_PROTECT
`define PUBIP_SAT_IN_TOTAL   16   //输入数据总位宽
`define PUBIP_SAT_IN_INT     8    //输入数据整数位宽
`define PUBIP_SAT_OUT_TOTAL  8    //输出数据总位宽
`define PUBIP_SAT_OUT_INT    4    //输出数据整数位宽
`define PUBIP_SAT_SIGNED     1    //1=有符号，0=无符号
`define PUBIP_SAT_PROT       1    //1=零值保护，0=关闭
`else // 默认：<16,8,s> -> <8,4,s>（IN_FRAC=7 > OUT_FRAC=3，右移 4 位对齐，P0-3 验证路径）
`define PUBIP_SAT_IN_TOTAL   16   //输入数据总位宽
`define PUBIP_SAT_IN_INT     8    //输入数据整数位宽
`define PUBIP_SAT_OUT_TOTAL  8    //输出数据总位宽
`define PUBIP_SAT_OUT_INT    4    //输出数据整数位宽
`define PUBIP_SAT_SIGNED     1    //1=有符号，0=无符号
`define PUBIP_SAT_PROT       0    //1=零值保护，0=关闭
`endif

`endif //U_PUBIP_SAT_CFG
