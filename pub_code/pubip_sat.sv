/*========================================FILE_HEADER=====================================
# Filename: pubip_sat.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：是
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-05-05        vick           initial
#   1.1     2026-08-27        vick              修复：小数位重对齐未实现（P0-3）与位宽扩展配置反向 part-select（P0-4）
#   1.2     2026-08-27        vick              规范化：参数检查块移至 main process 后，参数判定写法统一
#   1.3     2026-08-27        vick              截位对齐块 generate 二选一化，消除不可达分支负复制量隐患（NMCM）
#
#-----------------------------------------------------------------------------------------
# Description:
        1.通用饱和截位公共模块，支持无符号/有符号数
        2.输入输出按各自小数位重对齐后截位（输入小数位多则右移丢弃低位，少则左移补零）
        3.有符号数对称饱和：负溢出或截位后为不对称最小值时，输出对称负饱和值
        4.零值保护：PROTECT_EN=1 且结果为0时，输出最小正值
#-----------------------------------------------------------------------------------------
#快速例化示例
pubip_sat #(
    .IN_TOTAL_WIDTH           ( 16          ),//输入数据总位宽
    .IN_INT_WIDTH             ( 8           ),//输入数据整数位宽
    .OUT_TOTAL_WIDTH          ( 8           ),//输出数据总位宽
    .OUT_INT_WIDTH            ( 4           ),//输出数据整数位宽
    .IS_SIGNED                ( 1           ),//1表示有符号，0表示无符号
    .PROTECT_EN               ( 0           ) //1表示开启零保护，0表示关闭
) pubip_sat_inst(
    .i_data                   (             ),//输入数据
    .o_data                   (             ) //输出数据（经过饱和截位后）
);
=========================================FILE_HEADER====================================*/
module pubip_sat
#(
    parameter int IN_TOTAL_WIDTH  = 16    ,//输入数据总位宽
    parameter int IN_INT_WIDTH    = 8     ,//输入数据整数位宽
    parameter int OUT_TOTAL_WIDTH = 8     ,//输出数据总位宽
    parameter int OUT_INT_WIDTH   = 4     ,//输出数据整数位宽
    parameter int IS_SIGNED       = 1     ,//是否为有符号数，1表示有符号，0表示无符号
    parameter int PROTECT_EN      = 0      //零值保护使能，1表示开启保护，0表示关闭保护
)
(
    input           [IN_TOTAL_WIDTH  - 1 : 0]   i_data  ,//输入数据
    output  logic   [OUT_TOTAL_WIDTH - 1 : 0]   o_data   //输出数据（经过饱和截位后）
);
//======================== localparam define =================================
localparam int IN_FRAC_WIDTH   = IN_TOTAL_WIDTH  - IN_INT_WIDTH  - (IS_SIGNED ? 1 : 0);//输入小数位宽
localparam int OUT_FRAC_WIDTH  = OUT_TOTAL_WIDTH - OUT_INT_WIDTH - (IS_SIGNED ? 1 : 0);//输出小数位宽
localparam int INT_CHECK_WIDTH = (IN_INT_WIDTH > OUT_INT_WIDTH) ? (IN_INT_WIDTH - OUT_INT_WIDTH) : 0;//整数位检查宽度
localparam int FRAC_SHIFT      = IN_FRAC_WIDTH - OUT_FRAC_WIDTH;//小数位对齐移位量（>0 右移丢弃低位小数，<0 左移补零）
localparam int EXT_WIDTH       = (OUT_TOTAL_WIDTH + FRAC_SHIFT > IN_TOTAL_WIDTH) ? (OUT_TOTAL_WIDTH + FRAC_SHIFT) : IN_TOTAL_WIDTH;//小数位对齐所需扩展位宽
localparam int TRUNC_BASE      = OUT_TOTAL_WIDTH - 1 + FRAC_SHIFT;//对齐后截取窗口的最高位
localparam int CHECK_WIDTH     = (INT_CHECK_WIDTH > 0) ? INT_CHECK_WIDTH : 1;//整数位检查宽度（钳位为1，避免位宽扩展配置产生反向 part-select）

//无符号数饱和最大值
localparam logic [OUT_TOTAL_WIDTH - 1 : 0]   SAT_US_MAX      = {OUT_TOTAL_WIDTH{1'b1}};
//无符号数零保护值
localparam logic [OUT_TOTAL_WIDTH - 1 : 0]   SAT_US_PROTECT  = {{(OUT_TOTAL_WIDTH-1){1'b0}}, 1'b1};
//有符号数正饱和最大值
localparam logic [OUT_TOTAL_WIDTH - 1 : 0]   SAT_S_POS_MAX   = {1'b0, {(OUT_TOTAL_WIDTH-1){1'b1}}};
//有符号数负饱和最小值（非对称）
localparam logic [OUT_TOTAL_WIDTH - 1 : 0]   SAT_S_NEG_MIN   = {1'b1, {(OUT_TOTAL_WIDTH-1){1'b0}}};
//有符号数对称负饱和值
localparam logic [OUT_TOTAL_WIDTH - 1 : 0]   SAT_S_NEG_SYMM  = {1'b1, {(OUT_TOTAL_WIDTH-2){1'b0}}, 1'b1};
//有符号数零保护值
localparam logic [OUT_TOTAL_WIDTH - 1 : 0]   SAT_S_PROTECT   = {1'b0, {(OUT_TOTAL_WIDTH-2){1'b0}}, 1'b1};

//======================== main signal define =================================
//------ 截位中间结果 ------
logic   [OUT_TOTAL_WIDTH - 1 : 0]   wir_truncated       ;//截位或扩展后的中间结果
logic   [EXT_WIDTH - 1 : 0]         wir_ext_data        ;//按符号/零扩展后的输入（含小数位对齐窗口）

//------ 无符号数溢出判断 ------
logic                               wir_unsigned_overflow;//无符号数溢出标志

//------ 有符号数溢出判断 ------
logic                               wir_sign            ;//输入数据符号位
logic                               wir_all_zero        ;//检查位是否全0
logic                               wir_all_one         ;//检查位是否全1
logic                               wir_pos_overflow    ;//有符号数正溢出标志
logic                               wir_neg_overflow    ;//有符号数负溢出标志

//------ 对称饱和与零保护判断 ------
logic                               wir_is_asym_min     ;//是否为不对称最小值
logic                               wir_is_zero         ;//截位结果是否为零
logic                               wir_need_symm       ;//是否需要对称饱和
logic                               wir_need_protect    ;//是否需要零值保护

//======================== main process ===================================
//----------- 截位中间结果 ------------
always_comb begin
    if (EXT_WIDTH == IN_TOTAL_WIDTH)
        wir_ext_data = i_data;
    else if (IS_SIGNED)
        wir_ext_data = {{(EXT_WIDTH - IN_TOTAL_WIDTH){i_data[IN_TOTAL_WIDTH - 1]}}, i_data};
    else
        wir_ext_data = {{(EXT_WIDTH - IN_TOTAL_WIDTH){1'b0}}, i_data};
end

//----------- 小数位对齐截位（generate 二选一：仅选中分支展开，避免不可达分支负复制量） ------------
generate
    if (IN_FRAC_WIDTH < OUT_FRAC_WIDTH) begin : g_align_left
        //输入小数位 < 输出小数位：左移对齐，低位补零
        always_comb
            wir_truncated = {wir_ext_data[TRUNC_BASE : 0], {(-FRAC_SHIFT){1'b0}}};
    end
    else begin : g_align_right
        //输入小数位 >= 输出小数位：右移对齐，丢弃低位小数
        always_comb
            wir_truncated = wir_ext_data[TRUNC_BASE -: OUT_TOTAL_WIDTH];
    end
endgenerate

//----------- 无符号数溢出判断 ------------
always_comb begin
    if (IS_SIGNED == 0 && IN_INT_WIDTH > OUT_INT_WIDTH)
        wir_unsigned_overflow = |i_data[IN_TOTAL_WIDTH - 1 -: CHECK_WIDTH];
    else
        wir_unsigned_overflow = 1'b0;
end

//----------- 有符号数溢出判断 ------------
always_comb begin
    if (IS_SIGNED == 1 && IN_INT_WIDTH > OUT_INT_WIDTH) begin
        wir_sign          = i_data[IN_TOTAL_WIDTH - 1];
        wir_all_zero      = ~(|i_data[IN_TOTAL_WIDTH - 2 -: CHECK_WIDTH]);
        wir_all_one       =  &(i_data[IN_TOTAL_WIDTH - 2 -: CHECK_WIDTH]);
        wir_pos_overflow  = ~wir_sign & ~wir_all_zero;
        wir_neg_overflow  =  wir_sign & ~wir_all_one;
    end
    else begin
        wir_sign          = 1'b0;
        wir_all_zero      = 1'b0;
        wir_all_one       = 1'b0;
        wir_pos_overflow  = 1'b0;
        wir_neg_overflow  = 1'b0;
    end
end

//----------- 对称饱和与零保护判断 ------------
always_comb begin
    wir_is_asym_min  = (IS_SIGNED == 1) & (wir_truncated == SAT_S_NEG_MIN);
    wir_is_zero      = ~(|wir_truncated);
    wir_need_symm    = (IS_SIGNED == 1) & (wir_neg_overflow | wir_is_asym_min);
    wir_need_protect = (PROTECT_EN == 1) & wir_is_zero;
end

//----------- 输出选择与饱和值生成 ------------
always_comb begin
    if (IS_SIGNED == 0) begin
        //无符号模式
        if (wir_unsigned_overflow)
            o_data = SAT_US_MAX;
        else if (wir_need_protect)
            o_data = SAT_US_PROTECT;
        else
            o_data = wir_truncated;
    end
    else begin
        //有符号模式
        if (wir_pos_overflow)
            o_data = SAT_S_POS_MAX;
        else if (wir_need_symm)
            o_data = SAT_S_NEG_SYMM;
        else if (wir_need_protect)
            o_data = SAT_S_PROTECT;
        else
            o_data = wir_truncated;
    end
end

//----------- 参数合法性检查 ------------
generate
    if (IN_INT_WIDTH > IN_TOTAL_WIDTH)
        $error("IN_INT_WIDTH(%0d) must be <= IN_TOTAL_WIDTH(%0d)", IN_INT_WIDTH, IN_TOTAL_WIDTH);
    if (OUT_INT_WIDTH > OUT_TOTAL_WIDTH)
        $error("OUT_INT_WIDTH(%0d) must be <= OUT_TOTAL_WIDTH(%0d)", OUT_INT_WIDTH, OUT_TOTAL_WIDTH);
    if (IN_TOTAL_WIDTH == 0 || OUT_TOTAL_WIDTH == 0)
        $error("IN_TOTAL_WIDTH and OUT_TOTAL_WIDTH must be > 0");
    if (OUT_INT_WIDTH + IN_FRAC_WIDTH < 1)
        $error("OUT_INT_WIDTH(%0d) + IN_FRAC_WIDTH(%0d) must be >= 1 (output width insufficient for fractional alignment)", OUT_INT_WIDTH, IN_FRAC_WIDTH);
endgenerate

endmodule
