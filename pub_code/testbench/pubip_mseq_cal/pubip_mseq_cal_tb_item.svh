/*========================================FILE_HEADER=====================================
# Filename: pubip_mseq_cal_tb_item.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             按 mseq_cal 语义补全激励/期望/采集字段（一拍一 item）
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_mseq_cal 事务类：一拍一 item（激励 vld/init_seq/trans_num）
        期望由 refm 独立 LFSR 模型公式回填（m_exp_seq），采集由 monitor 回填（m_out_vld/m_out_seq）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_PUBIP_MSEQ_CAL_TB_ITEM
`define U_PUBIP_MSEQ_CAL_TB_ITEM

//----------- pubip_mseq_cal_item ------------
// 一拍一 item：driver 在 negedge 驱动，DUT 在下一 posedge 采样（固定 5 拍后输出）
// 期望字段由 refm 纯函数 compute 回填（见 tb_refm.svh）；vld=0 的 item 无期望比对
class pubip_mseq_cal_item extends tb_item_base;

    //----------- 激励 ------------
    bit                             m_vld               ;//i_cal_vld 计算有效
    logic [30:0]                    m_init_seq          ;//i_init_seq 初始 M 序列（SEQ_WIDTH=31）
    logic [14:0]                    m_trans_num         ;//i_trans_num 转移次数控制值（bit[k] ↔ 2^k 级）

    //----------- 比对窗口标记（monitor 回填：0=窗口关闭拍不比对） ------------
    bit                             m_watch             ;//是否参与比对

    //----------- 期望（refm 回填：LFSR 迭代 m_trans_num 次结果） ------------
    logic [30:0]                    m_exp_seq           ;//期望：o_seq_out

    //----------- 采集（monitor 回填） ------------
    bit                             m_out_vld           ;//采集：o_seq_vld
    logic [30:0]                    m_out_seq           ;//采集：o_seq_out

    function new(string name = "pubip_mseq_cal_item");
        super.new(name);
    endfunction

    //----------- 事务描述打印 ------------
    function string do_print();
        return $sformatf("%s id=%0d vld=%0b txn=%0h init=%0h exp=%0h out_vld=%0b out=%0h",
                         m_name, m_id,
                         m_vld, m_trans_num, m_init_seq, m_exp_seq, m_out_vld, m_out_seq);
    endfunction
endclass
`endif //U_PUBIP_MSEQ_CAL_TB_ITEM
