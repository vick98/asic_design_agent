/*========================================FILE_HEADER=====================================
# Filename: pubip_round.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：是
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-10-06        vick          initial：按 D3-025/D3-031 的收尾舍入需求实现公共单元
#                                              （契约与参数口径见 rules/pubip.md 的 pubip_round 一节）
#   1.2     2026-10-11        vick          W_dst > 32 时界常量 32 位溢出修复：POS_MAX/NEG_SYM/
#                                              NEG_ASYM/ROUND_CONST 改 64 位有符号常量、饱和比较改
#                                              64 位有符号比较，并补 OUT_TOTAL_WIDTH <= 63 参数检查
#   1.1     2026-10-06        vick          参数检查由 generate 条件项改为 initial 过程块，
#                                              消除空生成块（nLint 22155）；中间量 32->64 位以承载
#                                              IN_TOTAL_WIDTH=33 的挂接点；负满码钳位判据由位图
#                                              改按数值比较（位图判据会误钳界内值）
#
#-----------------------------------------------------------------------------------------
# Description:
        1.通用收尾舍入公共模块：把更宽的有符号定点数右移 N 位（round-half-up）后收进
          目标容器，两侧对称饱和。对应 rules/dsp.md 收尾（finish）一步：
              y = sat_sym( (x + 2^(N-1)) >>> N )  ->  OUT 容器 <W_dst, I_dst, t>
        2.舍入：half-up，先加半个 LSB（2^(N-1)）再算术右移 N 位，0.5 LSB 边界向正方向
          取整（与 rules/dsp.md "half_up 是先加半个 LSB 再算术右移" 同口径）。N=0 时
          不加、不移，退化为纯对称饱和收位。
        3.饱和：对称饱和，输出界 [1-2^(W_dst-1), 2^(W_dst-1)-1]。I_dst 是**不含符号位**
          的整数位宽，与定点三元组 <W,I,t> 同口径。
        4.负满码钳位（对称收尾的额外判据，见需求书 §1）：输出一律不得出现补码的负最大值
          （非对称最小 -2^(W_dst-1) 的位图）——右移结果数值恰为该值时钳到对称负饱和值
          1-2^(W_dst-1)。这条是在对称界之外单列的：只按数值界判溢出时，恰等于负满码的
          结果会落在"界内"一侧被判为合法放出去。
        5.中间容器：加半个 LSB 在 IN_TOTAL_WIDTH+1 位里做（防进位溢出）；随后整体按有符号
          送入 64 位中间量再做算术右移，避免窄容器移位时的位宽/符号扩展歧义，也保证
          位宽扩张配置（W_dst 显著大于右移结果有效位宽）下输出位图仍然正确。
        6.纯组合、零延迟；无除法、无乘法；位宽全部编译期参数化（IN_TOTAL_WIDTH ≤ 63，
          中间量 64 位）；参数非法按 $error 报错，不静默（IS_SIGNED 固定有符号，不设该参数）。
#-----------------------------------------------------------------------------------------
#快速例化示例（发射成形收尾：finish <33,11,t> >> 11 half-up + sat -> <12,1,t>）
pubip_round #(
    .IN_TOTAL_WIDTH           ( 33          ),//输入数据总位宽
    .IN_INT_WIDTH             ( 11          ),//输入数据整数位宽（不含符号位）
    .OUT_TOTAL_WIDTH          ( 12          ),//输出数据总位宽
    .OUT_INT_WIDTH            ( 1           ),//输出数据整数位宽（不含符号位）
    .SHIFT_NUM                ( 11          ) //右移位数 N
) pubip_round_inst(
    .i_data                   (             ),//输入数据
    .o_data                   (             ) //输出数据（half-up 舍入 + 对称饱和后）
);
=========================================FILE_HEADER====================================*/
module pubip_round
#(
    parameter int IN_TOTAL_WIDTH  = 24    ,//输入数据总位宽（W_src）
    parameter int IN_INT_WIDTH    = 2     ,//输入数据整数位宽（I_src，不含符号位）
    parameter int OUT_TOTAL_WIDTH = 12    ,//输出数据总位宽（W_dst）
    parameter int OUT_INT_WIDTH   = 1     ,//输出数据整数位宽（I_dst，不含符号位）
    parameter int SHIFT_NUM       = 12     //右移位数 N（half-up 舍入的移位量）
)
(
    input           [IN_TOTAL_WIDTH  - 1 : 0]   i_data  ,//输入数据，补码 <W_src,I_src,t>
    output  logic   [OUT_TOTAL_WIDTH - 1 : 0]   o_data   //输出数据，补码 <W_dst,I_dst,t>
);
//======================== localparam define =================================
//v1.2：三个界常量与半个 LSB 常量一律用 64 位有符号常量算——`int` 是 32 位，
//      W_dst > 32（如宽出窄入的 z4 收尾 <48,7,t> -> <34,23,t>）时 `1 << (W_dst-1)`
//      会溢出成 0，POS_MAX 变成 -1、正饱和判据恒真，输出恒为 ±1。
localparam int TMP_WIDTH   = IN_TOTAL_WIDTH + 1                       ;//加半 LSB 中间容器位宽
localparam logic signed [63 : 0] ROUND_CONST = (SHIFT_NUM > 0) ? (64'sd1 <<< (SHIFT_NUM - 1)) : 64'sd0;//半个 LSB = 2^(N-1)，N=0 时取 0
localparam logic signed [63 : 0] POS_MAX     = (64'sd1 <<< (OUT_TOTAL_WIDTH - 1)) - 64'sd1;//对称正饱和界 2^(W_dst-1)-1
localparam logic signed [63 : 0] NEG_SYM     = 64'sd1 - (64'sd1 <<< (OUT_TOTAL_WIDTH - 1));//对称负饱和界 1-2^(W_dst-1)
localparam logic signed [63 : 0] NEG_ASYM    = -(64'sd1 <<< (OUT_TOTAL_WIDTH - 1))    ;//补码负最大值（非对称最小），禁止输出

//======================== main signal define =================================
//------ 收位中间结果 ------
logic           [TMP_WIDTH - 1 : 0]   wir_ext             ;//符号扩展后的输入（TMP_WIDTH 位）
logic           [TMP_WIDTH - 1 : 0]   wir_round_const     ;//半个 LSB 常量（随移位量编译期定值）
logic           [TMP_WIDTH - 1 : 0]   wir_adjusted        ;//加半个 LSB 后的位图（沿 TMP_WIDTH 取模）
logic   signed  [63 : 0]              wir_shifted         ;//算术右移 N 位后的有符号值（64 位承载）

//------ 饱和判据 ------
logic                                 wir_pos_overflow    ;//正溢出（超过 2^(W_dst-1)-1）
logic                                 wir_neg_overflow    ;//负溢出（小于 1-2^(W_dst-1)）
logic                                 wir_shifted_asym_min;//右移结果数值是否为补码负最大值

//======================== main process ===================================
//----------- 符号扩展到 TMP_WIDTH 位（输入按有符号） ------------
assign wir_ext = {{(TMP_WIDTH - IN_TOTAL_WIDTH){i_data[IN_TOTAL_WIDTH - 1]}}, i_data};

//----------- 加半个 LSB：SHIFT_NUM=0 时不加（半个 LSB 不存在） ------------
assign wir_round_const = (SHIFT_NUM > 0) ? TMP_WIDTH'(ROUND_CONST) : {TMP_WIDTH{1'b0}};
assign wir_adjusted    = wir_ext + wir_round_const;

//----------- 算术右移 N 位：整体按有符号进 64 位域再做 >>>，N=0 直通 ------------
//64 位域覆盖 TMP_WIDTH <= 64 的全部合法参数（SHIFT_NUM <= IN_TOTAL_WIDTH），
//符号扩展在这里显式给出，不依赖窄有符号容器赋值时的隐式行为。
generate
    if (SHIFT_NUM == 0) begin : g_shift_none
        always_comb
            wir_shifted = $signed(wir_adjusted);
    end
    else begin : g_shift_arith
        always_comb
            wir_shifted = $signed(wir_adjusted) >>> SHIFT_NUM;
    end
endgenerate

//----------- 饱和判据：与对称界比较 ------------
always_comb begin
    wir_pos_overflow     = (wir_shifted > POS_MAX)      ;//超过 2^(W_dst-1)-1（两侧同为 64 位有符号比较）
    wir_neg_overflow     = (wir_shifted < NEG_SYM)      ;//小于对称负界 1-2^(W_dst-1)
    //负满码钳位：右移结果数值恰为补码负最大值 -2^(W_dst-1) 时钳到对称负界。
    //不能按"符号位 1 且高位全 0"的位图判据下判：右移结果有效位宽大于 W_dst 时，
    //该位图还覆盖 (NEG_SYM, 0) 一段正常值，会把它们误钳。
    wir_shifted_asym_min = (wir_shifted == NEG_ASYM)    ;
end

//----------- 输出选择：正饱和 > 负饱和/负满码钳位 > 收位直通 ------------
always_comb begin
    if (wir_pos_overflow)
        o_data = OUT_TOTAL_WIDTH'(POS_MAX)  ;//正饱和：2^(W_dst-1)-1
    else if (wir_neg_overflow || wir_shifted_asym_min)
        o_data = OUT_TOTAL_WIDTH'(NEG_SYM)  ;//对称负饱和：1-2^(W_dst-1)，负满码一律钳到此处
    else
        o_data = wir_shifted[OUT_TOTAL_WIDTH - 1 : 0];//界内：取低 W_dst 位（补码一致，扩张时高位补 0）
end

//----------- 参数合法性检查 ------------
// 放在 initial 里（$error/$warning 是 elaboration system task，任何过程上下文都可用）：
// generate 条件项在条件不成立时会留下空生成块，触发 nLint Warning 22155（详见 v1.1 说明）。
initial begin
    if (IN_INT_WIDTH < 0)
        $error("IN_INT_WIDTH(%0d) must be >= 0", IN_INT_WIDTH);
    else if (OUT_INT_WIDTH < 0)
        $error("OUT_INT_WIDTH(%0d) must be >= 0", OUT_INT_WIDTH);
    else if (IN_INT_WIDTH >= IN_TOTAL_WIDTH)
        $error("IN_INT_WIDTH(%0d) must be <= IN_TOTAL_WIDTH-1(%0d) (I 不含符号位)",
               IN_INT_WIDTH, IN_TOTAL_WIDTH - 1);
    else if (OUT_INT_WIDTH >= OUT_TOTAL_WIDTH)
        $error("OUT_INT_WIDTH(%0d) must be <= OUT_TOTAL_WIDTH-1(%0d) (I 不含符号位)",
               OUT_INT_WIDTH, OUT_TOTAL_WIDTH - 1);
    else if (IN_TOTAL_WIDTH < 2 || OUT_TOTAL_WIDTH < 2)
        $error("IN_TOTAL_WIDTH(%0d) and OUT_TOTAL_WIDTH(%0d) must be >= 2 (signed)",
               IN_TOTAL_WIDTH, OUT_TOTAL_WIDTH);
    else if (IN_TOTAL_WIDTH > 63)
        $error("IN_TOTAL_WIDTH(%0d) must be <= 63 (TMP_WIDTH=%0d must fit the 64-bit signed stage)",
               IN_TOTAL_WIDTH, IN_TOTAL_WIDTH + 1);
    else if (OUT_TOTAL_WIDTH > 63)
        $error("OUT_TOTAL_WIDTH(%0d) must be <= 63 (bounds are computed in a 64-bit signed container)",
               OUT_TOTAL_WIDTH);
    else if (SHIFT_NUM < 0)
        $error("SHIFT_NUM(%0d) must be >= 0", SHIFT_NUM);
    else if (SHIFT_NUM > IN_TOTAL_WIDTH)
        $error("SHIFT_NUM(%0d) must be <= IN_TOTAL_WIDTH(%0d)", SHIFT_NUM, IN_TOTAL_WIDTH);
    //闭合条件：f_dst = f_src - N，其中 f = W - I - 1（I 不含符号位）
    else if ((IN_TOTAL_WIDTH - IN_INT_WIDTH) - (OUT_TOTAL_WIDTH - OUT_INT_WIDTH) != SHIFT_NUM)
        $error("fractional widths not closed: (W_src-I_src)=(%0d), (W_dst-I_dst)=(%0d), but SHIFT_NUM=%0d",
               IN_TOTAL_WIDTH - IN_INT_WIDTH, OUT_TOTAL_WIDTH - OUT_INT_WIDTH, SHIFT_NUM);
end

endmodule
