/*========================================FILE_HEADER=====================================
# Filename: pubip_sat_tb_refm.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_sat 参考模型：无状态纯函数 compute() 按"定点值语义"独立实现参考公式
        （值域判断 + 算术移位对齐 + 输出位图截取），与 RTL 位图实现不同路径；
        覆写 model() 回填期望字段（框架硬约定，只实现 compute 不覆写 model 会漏回填）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_PUBIP_SAT_TB_REFM
`define U_PUBIP_SAT_TB_REFM

//----------- pubip_sat_refm ------------
class pubip_sat_refm extends tb_refm_base;

    //----------- 定点参数（由 cfg 编译宏展开，保证与 DUT 参数一致） ------------
    localparam int L_IN_FRAC   = `PUBIP_SAT_IN_TOTAL - `PUBIP_SAT_IN_INT - (`PUBIP_SAT_SIGNED ? 1 : 0);//输入小数位宽
    localparam int L_OUT_FRAC  = `PUBIP_SAT_OUT_TOTAL - `PUBIP_SAT_OUT_INT - (`PUBIP_SAT_SIGNED ? 1 : 0);//输出小数位宽
    localparam int L_SHIFT     = L_IN_FRAC - L_OUT_FRAC;//小数位对齐移位量（>0 右移丢弃，<0 左移补零）
    localparam int L_INT_MAX   = (1 << `PUBIP_SAT_OUT_INT) - 1;//输出整数部分最大值（2^OUT_INT - 1）
    localparam int L_INT_MIN   = -(1 << `PUBIP_SAT_OUT_INT);//输出整数部分最小值（-2^OUT_INT）

    //----------- 饱和/保护常量（输出位图，与 DUT 定义一致） ------------
    localparam logic [`PUBIP_SAT_OUT_TOTAL - 1 : 0] L_US_MAX   = {`PUBIP_SAT_OUT_TOTAL{1'b1}};                 //无符号饱和最大值
    localparam logic [`PUBIP_SAT_OUT_TOTAL - 1 : 0] L_US_PROT  = {{(`PUBIP_SAT_OUT_TOTAL - 1){1'b0}}, 1'b1};  //无符号零保护值
    localparam logic [`PUBIP_SAT_OUT_TOTAL - 1 : 0] L_S_POSMAX = {1'b0, {(`PUBIP_SAT_OUT_TOTAL - 1){1'b1}}};  //有符号正饱和
    localparam logic [`PUBIP_SAT_OUT_TOTAL - 1 : 0] L_S_NEGMIN = {1'b1, {(`PUBIP_SAT_OUT_TOTAL - 1){1'b0}}};  //有符号非对称最小
    localparam logic [`PUBIP_SAT_OUT_TOTAL - 1 : 0] L_S_NEGSYM = {1'b1, {(`PUBIP_SAT_OUT_TOTAL - 2){1'b0}}, 1'b1};//有符号对称负饱和
    localparam logic [`PUBIP_SAT_OUT_TOTAL - 1 : 0] L_S_PROT   = {1'b0, {(`PUBIP_SAT_OUT_TOTAL - 2){1'b0}}, 1'b1};//有符号零保护值

    function new(string name = "m_refm");
        super.new(name);
    endfunction

    //----------- 核心算法纯函数（无状态：相同输入必得相同输出，不读写类成员/时间） ------------
    // 参考公式（值语义，独立于 RTL 位图实现）：
    //   1) 整数部分（输入 LSB 尺度 2^-IN_FRAC 的 floor）是否超出输出可表达 [-2^OUT_INT, 2^OUT_INT-1]
    //   2) 小数位对齐：FRAC_SHIFT>=0 算术右移（向负无穷截断），<0 左移低位补零；再截取输出位宽位图
    //   3) 对称饱和：负溢出或截位值为非对称最小（SAT_S_NEG_MIN）-> 输出对称饱和值
    //   4) 零值保护：PROTECT_EN=1 且截位为 0 -> 输出最小正值
    static function logic [`PUBIP_SAT_OUT_TOTAL - 1 : 0] compute(input logic [`PUBIP_SAT_IN_TOTAL - 1 : 0] in_data);
        logic signed [`PUBIP_SAT_IN_TOTAL - 1 : 0]   sv_in;      //有符号输入位图
        logic signed [31 : 0]                       sv_ext;     //32 位扩展（位宽充裕）
        logic signed [31 : 0]                       sv_align;   //对齐后值
        logic [`PUBIP_SAT_IN_TOTAL - 1 : 0]         uv_in;      //无符号输入位图
        logic [31 : 0]                              uv_ext;     //32 位零扩展
        logic [31 : 0]                              uv_align;   //对齐后位图
        logic [`PUBIP_SAT_OUT_TOTAL - 1 : 0]        trunc;      //截位位图
        int                                         i_in;       //输入整数部分（floor 语义）
        bit                                         pos_ovf;    //正溢出
        bit                                         neg_ovf;    //负溢出
        bit                                         us_ovf;     //无符号溢出
        bit                                         is_zero;    //截位为 0
        bit                                         is_asym_min;//截位为非对称最小

        if (`PUBIP_SAT_SIGNED) begin
            //------------ 有符号模式 ------------
            sv_in   = $signed(in_data);
            i_in    = sv_in >>> L_IN_FRAC;                          //整数部分（floor，向负无穷）
            pos_ovf = (i_in > L_INT_MAX);                           //正溢出：超出 2^OUT_INT-1
            neg_ovf = (i_in < L_INT_MIN);                           //负溢出：小于 -2^OUT_INT
            sv_ext  = sv_in;                                        //32 位符号扩展
            if (L_SHIFT >= 0)
                sv_align = sv_ext >>> L_SHIFT;                      //右移丢弃低位（向负无穷截断）
            else
                sv_align = sv_ext << (-L_SHIFT);                    //左移低位补零
            trunc      = sv_align[`PUBIP_SAT_OUT_TOTAL - 1 : 0];    //截取输出位宽
            is_asym_min = (trunc == L_S_NEGMIN);
            is_zero     = (trunc == '0);
            if (pos_ovf)
                compute = L_S_POSMAX;                               //正饱和
            else if (neg_ovf | is_asym_min)
                compute = L_S_NEGSYM;                               //对称负饱和
            else if (`PUBIP_SAT_PROT && is_zero)
                compute = L_S_PROT;                                 //零值保护
            else
                compute = trunc;
        end
        else begin
            //------------ 无符号模式 ------------
            uv_in   = in_data;
            i_in    = uv_in >> L_IN_FRAC;                           //整数部分（逻辑右移）
            us_ovf  = (i_in > L_INT_MAX);                           //溢出：超出 2^OUT_INT-1
            uv_ext  = 32'(uv_in);                                   //32 位零扩展
            if (L_SHIFT >= 0)
                uv_align = uv_ext >> L_SHIFT;                       //右移丢弃低位
            else
                uv_align = uv_ext << (-L_SHIFT);                    //左移低位补零
            trunc      = uv_align[`PUBIP_SAT_OUT_TOTAL - 1 : 0];    //截取输出位宽
            is_zero    = (trunc == '0);
            if (us_ovf)
                compute = L_US_MAX;                                 //无符号饱和
            else if (`PUBIP_SAT_PROT && is_zero)
                compute = L_US_PROT;                                //零值保护
            else
                compute = trunc;
        end
    endfunction

    //----------- 模型计算：调用 compute 回填期望字段（基类 run() 随后统一广播） ------------
    virtual task model(tb_item_base it);
        pubip_sat_item dut_it;
        $cast(dut_it, it);
        dut_it.m_exp = compute(dut_it.m_data);
    endtask
endclass
`endif //U_PUBIP_SAT_TB_REFM
