/*========================================FILE_HEADER=====================================
# Filename: pubip_mseq_gen_tb_item.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_mseq_gen 事务类：一拍一 item（激励 m_init_seq/m_cal_en + 比对窗口标记 +
        refm 期望 m_exp_seq + monitor 采集 m_out_seq）；期望由 refm.compute() 回填
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_PUBIP_MSEQ_GEN_TB_ITEM
`define U_PUBIP_MSEQ_GEN_TB_ITEM

//----------- pubip_mseq_gen_item ------------
class pubip_mseq_gen_item extends tb_item_base;

    //----------- 激励 ------------
    logic [`PUBIP_MPG_SEQ_WIDTH - 1 : 0]  m_init_seq      ;//初始序列
    bit                                  m_cal_en        ;//计算使能：1=转移 TRANS_NUM 步，0=旁路

    //----------- 比对窗口标记（monitor 回填：0=关窗拍不比对，仅保持队列配对） ------------
    bit                                  m_watch         ;//是否参与比对

    //----------- 期望（refm.compute() 回填） ------------
    logic [`PUBIP_MPG_SEQ_WIDTH - 1 : 0]  m_exp_seq       ;//期望：输出序列

    //----------- 采集（monitor 回填） ------------
    logic [`PUBIP_MPG_SEQ_WIDTH - 1 : 0]  m_out_seq       ;//采集：输出序列

    function new(string name = "pubip_mseq_gen_item");
        super.new(name);
    endfunction

    //----------- 事务描述打印 ------------
    function string do_print();
        return $sformatf("%s id=%0d init=%h cal=%0b exp=%h out=%h",
                         m_name, m_id, m_init_seq, m_cal_en, m_exp_seq, m_out_seq);
    endfunction
endclass
`endif //U_PUBIP_MSEQ_GEN_TB_ITEM
