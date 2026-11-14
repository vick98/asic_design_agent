/*========================================FILE_HEADER=====================================
# Filename: pubip_complex_mult_tb_refm.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             复乘参考公式 compute（与 CONJ_EN 宏联动）
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_complex_mult 参考模型：核心算法为无状态纯函数 compute()（复乘参考公式），
        model() 覆写虚任务并回填期望字段（框架约定，见 rules/tb.md 9.3 节）。
        公式与 rules/pubip.md/DUT 代码核对：
          CONJ_EN=0：Re = ar*br - ai*bi；Im = ar*bi + ai*br
          CONJ_EN=1：Re = ar*br + ai*bi；Im = ai*br - ar*bi
        实现方式：先按精确算术计算（18bit 宽化），赋值 16bit 输出自动截取低 16bit，
        与 RTL 有符号补码回绕语义一致（输出位宽 DINA+DINB=16bit）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_PUBIP_COMPLEX_MULT_TB_REFM
`define U_PUBIP_COMPLEX_MULT_TB_REFM

//----------- pubip_complex_mult_refm ------------
class pubip_complex_mult_refm extends tb_refm_base;

    function new(string name = "m_refm");
        super.new(name);
    endfunction

    //----------- 核心算法纯函数（复乘参考公式，无状态；i_conj=1 时按 A*conj(B) 计算） ------------
    static function void compute(
        input  logic signed [9:0]   i_ar                    ,//输入 A 实部
        input  logic signed [9:0]   i_ai                    ,//输入 A 虚部
        input  logic signed [5:0]   i_br                    ,//输入 B 实部
        input  logic signed [5:0]   i_bi                    ,//输入 B 虚部
        input  bit                  i_conj                  ,//共轭选择：1=A*conj(B)，0=A*B
        output logic signed [15:0]  o_exp_re                ,//期望实部
        output logic signed [15:0]  o_exp_im                 //期望虚部
    );
        //------ 宽化到 18bit（乘积 10*6=16bit 精确、和差 17bit 覆盖，确保精确算术后截位） ------
        logic signed [17:0]          w_ar                    ;//宽化 A 实部
        logic signed [17:0]          w_ai                    ;//宽化 A 虚部
        logic signed [17:0]          w_br                    ;//宽化 B 实部
        logic signed [17:0]          w_bi                    ;//宽化 B 虚部

        w_ar = i_ar;
        w_ai = i_ai;
        w_br = i_br;
        w_bi = i_bi;
        if (i_conj) begin
            o_exp_re = w_ar * w_br + w_ai * w_bi;   // A*conj(B) 实部
            o_exp_im = w_ai * w_br - w_ar * w_bi;   // A*conj(B) 虚部
        end
        else begin
            o_exp_re = w_ar * w_br - w_ai * w_bi;   // A*B 实部
            o_exp_im = w_ar * w_bi + w_ai * w_br;   // A*B 虚部
        end
    endfunction

    //----------- 模型计算：调用 compute 回填期望字段（CONJ 变体经编译宏联动） ------------
    virtual task model(tb_item_base it);
        pubip_complex_mult_item dut_it;
        $cast(dut_it, it);
`ifdef PUBIP_CM_CONJ
        compute(dut_it.m_ar, dut_it.m_ai, dut_it.m_br, dut_it.m_bi, 1'b1 ,
                dut_it.m_exp_re, dut_it.m_exp_im);
`else
        compute(dut_it.m_ar, dut_it.m_ai, dut_it.m_br, dut_it.m_bi, 1'b0 ,
                dut_it.m_exp_re, dut_it.m_exp_im);
`endif
    endtask
endclass
`endif //U_PUBIP_COMPLEX_MULT_TB_REFM
