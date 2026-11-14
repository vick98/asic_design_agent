/*========================================FILE_HEADER=====================================
# Filename: pubip_counter_tb_item.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             按 counter 语义补全激励/期望/采集字段
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_counter 事务类：逐拍激励（start/rst/end 脉冲）+ 用例预置期望 + monitor 采集
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_PUBIP_COUNTER_TB_ITEM
`define U_PUBIP_COUNTER_TB_ITEM

//----------- pubip_counter_item ------------
// 逐拍事务：一拍一个 item（激励经 driver 在 negedge 驱动，DUT 在下一个 posedge 采样）
// 期望字段由用例按 DUT 语义预置（refm 经纯函数 compute 透传，见 tb_refm.svh）
class pubip_counter_item extends tb_item_base;

    //----------- 激励 ------------
    bit                             m_start             ;//计数启动脉冲
    bit                             m_rst               ;//计数复位脉冲
    bit                             m_end               ;//计数停止脉冲

    //----------- 比对窗口标记（monitor 回填：0=复位/关窗拍不比对，仅保持队列配对） ------------
    bit                             m_watch             ;//是否参与比对

    //----------- 期望（用例预置） ------------
    bit                             m_exp_en            ;//期望：计数使能
    logic [3:0]                     m_exp_cnt           ;//期望：计数值（MAX_NUM=8 → CNT_WIDTH=4）
    logic [8:0]                     m_exp_shift         ;//期望：脉冲（bit j ↔ 计数值 j）

    //----------- 采集（monitor 回填） ------------
    bit                             m_out_en            ;//采集：计数使能
    logic [3:0]                     m_out_cnt           ;//采集：计数值
    logic [8:0]                     m_out_shift         ;//采集：脉冲

    function new(string name = "pubip_counter_item");
        super.new(name);
    endfunction

    //----------- 事务描述打印 ------------
    function string do_print();
        return $sformatf("%s id=%0d exp=%0b/%0h/%0h out=%0b/%0h/%0h",
                         m_name, m_id,
                         m_exp_en, m_exp_cnt, m_exp_shift,
                         m_out_en, m_out_cnt, m_out_shift);
    endfunction
endclass
`endif //U_PUBIP_COUNTER_TB_ITEM
