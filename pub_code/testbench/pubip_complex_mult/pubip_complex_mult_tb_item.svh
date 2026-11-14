/*========================================FILE_HEADER=====================================
# Filename: pubip_complex_mult_tb_item.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             按复乘语义补全激励/期望/采集字段（signed）
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_complex_mult 事务类：一拍一 item（A/B 复数输入）+ 期望（refm 公式回填）+ 采集（monitor 采样）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_PUBIP_COMPLEX_MULT_TB_ITEM
`define U_PUBIP_COMPLEX_MULT_TB_ITEM

//----------- pubip_complex_mult_item ------------
// 逐拍事务：一拍一个 item（driver 在 negedge 驱动，monitor 在 posedge 采样 DUT 组合输出）
class pubip_complex_mult_item extends tb_item_base;

    //----------- 激励 ------------
    logic signed [9:0]               m_ar                ;//输入 A 实部（10bit 有符号）
    logic signed [9:0]               m_ai                ;//输入 A 虚部（10bit 有符号）
    logic signed [5:0]               m_br                ;//输入 B 实部（6bit 有符号）
    logic signed [5:0]               m_bi                ;//输入 B 虚部（6bit 有符号）

    //----------- 比对窗口标记（monitor 回填：0=关窗拍不比对，仅保持队列配对） ------------
    bit                              m_watch             ;//是否参与比对

    //----------- 期望（refm compute 公式回填） ------------
    logic signed [15:0]              m_exp_re            ;//期望：实部（16bit 有符号补码）
    logic signed [15:0]              m_exp_im            ;//期望：虚部（16bit 有符号补码）

    //----------- 采集（monitor 回填） ------------
    logic signed [15:0]              m_out_re            ;//采集：实部
    logic signed [15:0]              m_out_im            ;//采集：虚部

    function new(string name = "pubip_complex_mult_item");
        super.new(name);
    endfunction

    //----------- 事务描述打印 ------------
    function string do_print();
        return $sformatf("%s id=%0d A=(%0d,%0d) B=(%0d,%0d) exp=(%0d,%0d) out=(%0d,%0d)",
                         m_name, m_id,
                         m_ar, m_ai, m_br, m_bi,
                         m_exp_re, m_exp_im, m_out_re, m_out_im);
    endfunction
endclass
`endif //U_PUBIP_COMPLEX_MULT_TB_ITEM
