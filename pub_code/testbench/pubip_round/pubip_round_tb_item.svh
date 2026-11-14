/*========================================FILE_HEADER=====================================
# Filename: pubip_round_tb_item.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-10-06        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_round 事务类：一拍一 item（激励 m_data + 比对窗口标记 + refm 期望 + monitor 采集）
        期望由 refm.compute() 回填（用例仅填激励），与 DUT 纯组合逐拍对拍
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_PUBIP_ROUND_TB_ITEM
`define U_PUBIP_ROUND_TB_ITEM

//----------- pubip_round_item ------------
class pubip_round_item extends tb_item_base;

    //----------- 激励 ------------
    logic  [`PUBIP_ROUND_IN_TOTAL - 1 : 0]    m_data          ;//输入数据

    //----------- 比对窗口标记（monitor 回填：0=关窗拍不比对，仅保持队列配对） ------------
    bit                             m_watch         ;//是否参与比对

    //----------- 期望（refm.compute() 回填） ------------
    logic  [`PUBIP_ROUND_OUT_TOTAL - 1 : 0]   m_exp           ;//期望：输出数据

    //----------- 采集（monitor 回填） ------------
    logic  [`PUBIP_ROUND_OUT_TOTAL - 1 : 0]   m_out           ;//采集：输出数据

    function new(string name = "pubip_round_item");
        super.new(name);
    endfunction

    //----------- 事务描述打印 ------------
    function string do_print();
        return $sformatf("%s id=%0d in=%h exp=%h out=%h",
                         m_name, m_id, m_data, m_exp, m_out);
    endfunction
endclass
`endif //U_PUBIP_ROUND_TB_ITEM
