/*========================================FILE_HEADER=====================================
# Filename: pubip_round_cfg.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.1     2026-10-11        vick          加 PUBIP_ROUND_Z4 宽输出变体；界常量宏改 64 位有符号算
#   1.0     2026-10-06        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_round 参数配置宏中心（单一事实源）：按编译宏选择 DUT 例化参数变体，
        供 if/item/driver/monitor/refm/scoreboard/sim_top/tc 统一引用位宽与移位量，
        并按闭合式 N = (W_src-I_src) - (W_dst-I_dst) 编译期复算 N。
        变体宏（编译命令行 +define+ 传入，互斥，默认不定义）：
          （默认）                ：<33,11,t> -> <12,1,t>，D3-025 挂接点 tx_fir
          PUBIP_ROUND_RXMF        ：<33,13,t> -> <12,1,t>
          PUBIP_ROUND_CORR        ：<24,2,t>  -> <12,1,t>
          PUBIP_ROUND_NZERO       ：<12,11,t> -> <12,1,t>，N=0 纯对称饱和收位
          PUBIP_ROUND_DELTAI      ：<16,8,t>  -> <12,4,t>，N=0 且 I_dst < I_src（缩径饱和）
          PUBIP_ROUND_EXPAND      ：<16,8,t>  -> <20,12,t>，N=0 位宽扩张
          PUBIP_ROUND_SMALL       ：<8,3,t>   -> <4,1,t>
          PUBIP_ROUND_Z4          ：<48,7,t>  -> <34,23,t>，W_dst > 32 的宽输出变体
                                    （宽出窄入 z4 收尾挂接点；界常量必须 64 位算，见 v1.1）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_PUBIP_ROUND_CFG
`define U_PUBIP_ROUND_CFG

//----------- 参数变体（编译宏互斥选择，优先级 RXMF > CORR > NZERO > DELTAI > EXPAND > SMALL > 默认） ------------
`ifdef PUBIP_ROUND_RXMF
`define PUBIP_ROUND_IN_TOTAL   33   //输入数据总位宽
`define PUBIP_ROUND_IN_INT     13   //输入数据整数位宽（不含符号位）
`define PUBIP_ROUND_OUT_TOTAL  12   //输出数据总位宽
`define PUBIP_ROUND_OUT_INT    1    //输出数据整数位宽（不含符号位）
`elsif PUBIP_ROUND_CORR
`define PUBIP_ROUND_IN_TOTAL   24   //输入数据总位宽
`define PUBIP_ROUND_IN_INT     2    //输入数据整数位宽（不含符号位）
`define PUBIP_ROUND_OUT_TOTAL  12   //输出数据总位宽
`define PUBIP_ROUND_OUT_INT    1    //输出数据整数位宽（不含符号位）
`elsif PUBIP_ROUND_NZERO
`define PUBIP_ROUND_IN_TOTAL   12   //输入数据总位宽
`define PUBIP_ROUND_IN_INT     1    //输入数据整数位宽（不含符号位）；与输出同格式 -> N=0
`define PUBIP_ROUND_OUT_TOTAL  12   //输出数据总位宽
`define PUBIP_ROUND_OUT_INT    1    //输出数据整数位宽（不含符号位）
`elsif PUBIP_ROUND_DELTAI
`define PUBIP_ROUND_IN_TOTAL   16   //输入数据总位宽
`define PUBIP_ROUND_IN_INT     8    //输入数据整数位宽（不含符号位）
`define PUBIP_ROUND_OUT_TOTAL  12   //输出数据总位宽
`define PUBIP_ROUND_OUT_INT    4    //输出数据整数位宽（不含符号位）
`elsif PUBIP_ROUND_EXPAND
`define PUBIP_ROUND_IN_TOTAL   16   //输入数据总位宽
`define PUBIP_ROUND_IN_INT     8    //输入数据整数位宽（不含符号位）
`define PUBIP_ROUND_OUT_TOTAL  20   //输出数据总位宽
`define PUBIP_ROUND_OUT_INT    12   //输出数据整数位宽（不含符号位）
`elsif PUBIP_ROUND_Z4
`define PUBIP_ROUND_IN_TOTAL   48   //输入数据总位宽
`define PUBIP_ROUND_IN_INT     7    //输入数据整数位宽（不含符号位）
`define PUBIP_ROUND_OUT_TOTAL  34   //输出数据总位宽（> 32，覆盖 32 位界常量溢出场景）
`define PUBIP_ROUND_OUT_INT    23   //输出数据整数位宽（不含符号位）
`elsif PUBIP_ROUND_SMALL
`define PUBIP_ROUND_IN_TOTAL   8    //输入数据总位宽
`define PUBIP_ROUND_IN_INT     3    //输入数据整数位宽（不含符号位）
`define PUBIP_ROUND_OUT_TOTAL  4    //输出数据总位宽
`define PUBIP_ROUND_OUT_INT    1    //输出数据整数位宽（不含符号位）
`else // 默认：D3-025 挂接点 tx_fir，finish <33,11,t> >> 11 half-up + sat -> <12,1,t>
`define PUBIP_ROUND_IN_TOTAL   33   //输入数据总位宽
`define PUBIP_ROUND_IN_INT     11   //输入数据整数位宽（不含符号位）
`define PUBIP_ROUND_OUT_TOTAL  12   //输出数据总位宽
`define PUBIP_ROUND_OUT_INT    1    //输出数据整数位宽（不含符号位）
`endif

//----------- 移位量按闭合式编译期复算（I 不含符号位，有符号：f = W-I-1） ------------
`define PUBIP_ROUND_F_SRC      (`PUBIP_ROUND_IN_TOTAL  - `PUBIP_ROUND_IN_INT  - 1)
`define PUBIP_ROUND_F_DST      (`PUBIP_ROUND_OUT_TOTAL - `PUBIP_ROUND_OUT_INT - 1)
`define PUBIP_ROUND_SHIFT      (`PUBIP_ROUND_F_SRC - `PUBIP_ROUND_F_DST)

//----------- 输出对称界与负满码（补码负最大值）位图 ------------
//v1.1：一律用 64 位有符号常量算——`1 << (W_dst-1)` 在 32 位 int 里对 W_dst > 32 溢出，
//      POS_MAX 会变成 -1，参考模型跟着判错（PUBIP_ROUND_Z4 变体就是为这条加的）。
`define PUBIP_ROUND_POS_MAX    ((64'sd1 <<< (`PUBIP_ROUND_OUT_TOTAL - 1)) - 64'sd1)  //对称正饱和界
`define PUBIP_ROUND_NEG_SYM    (64'sd1 - (64'sd1 <<< (`PUBIP_ROUND_OUT_TOTAL - 1)))  //对称负饱和界
`define PUBIP_ROUND_NEG_ASYM   (-(64'sd1 <<< (`PUBIP_ROUND_OUT_TOTAL - 1)))          //负满码（禁止输出）

//----------- 全值域穷举可行性（W_src <= 16 时开，见 tc_full_scan） ------------
// 预处理器不认参数表达式，这里按位宽逐个列举（本项目实际用到的 W_src）
`ifdef PUBIP_ROUND_SMALL
`define PUBIP_ROUND_HAVE_FULL_SCAN
`endif
`ifdef PUBIP_ROUND_DELTAI
`define PUBIP_ROUND_HAVE_FULL_SCAN
`endif
`ifdef PUBIP_ROUND_EXPAND
`define PUBIP_ROUND_HAVE_FULL_SCAN
`endif
`ifdef PUBIP_ROUND_NZERO
`define PUBIP_ROUND_HAVE_FULL_SCAN
`endif

`endif //U_PUBIP_ROUND_CFG
