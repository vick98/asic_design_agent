/*========================================FILE_HEADER=====================================
# Filename: pubip_dynamic_mem_tb_item.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             按模块语义补全激励/期望/采集字段（一拍一 item）
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_dynamic_mem 事务类：一拍一 item（逐拍激励 6 输入 + 用例侧行为模型预置的逐拍期望 7 输出）
        + monitor 采集。期望由用例侧 dmem 行为模型（数组+链表）按拍计算预置，refm 纯函数透传
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_PUBIP_DYNAMIC_MEM_TB_ITEM
`define U_PUBIP_DYNAMIC_MEM_TB_ITEM

//----------- pubip_dynamic_mem_item ------------
class pubip_dynamic_mem_item extends tb_item_base;

    //----------- 激励（一拍：driver 在 negedge 驱动，DUT 在下一 posedge 采样） ------------
    bit                             m_wr_vld            ;//写入有效指示
    logic [3:0]                     m_wr_id             ;//写入数据对应ID
    logic [31:0]                    m_wr_data           ;//写入数据
    bit                             m_rd_id_vld         ;//读取调度ID有效指示
    logic [3:0]                     m_rd_id             ;//读取调度ID
    bit                             m_rd_vld            ;//后级读取有效指示

    //----------- 比对窗口标记（monitor 回填：0=复位/关窗拍不比对） ------------
    bit                             m_watch             ;//是否参与比对

    //----------- 期望（用例按行为模型预置） ------------
    bit                             m_exp_wr_ready      ;//期望：写就绪
    bit                             m_exp_rd_ready      ;//期望：读就绪
    logic [31:0]                    m_exp_rd_data       ;//期望：读数据
    bit                             m_exp_rd_last       ;//期望：尾指示
    logic [3:0]                     m_exp_schd_id       ;//期望：调度输出ID
    logic [6:0]                     m_exp_remain        ;//期望：调度ID剩余个数
    logic [6:0]                     m_exp_free_cnt      ;//期望：剩余空间个数

    //----------- 采集（monitor 回填） ------------
    bit                             m_out_wr_ready      ;//采集：写就绪
    bit                             m_out_rd_ready      ;//采集：读就绪
    logic [31:0]                    m_out_rd_data       ;//采集：读数据
    bit                             m_out_rd_last       ;//采集：尾指示
    logic [3:0]                     m_out_schd_id       ;//采集：调度输出ID
    logic [6:0]                     m_out_remain        ;//采集：调度ID剩余个数
    logic [6:0]                     m_out_free_cnt      ;//采集：剩余空间个数

    function new(string name = "pubip_dynamic_mem_item");
        super.new(name);
    endfunction

    //----------- 事务描述打印 ------------
    function string do_print();
        return $sformatf("%s wr=%0b/%0d/%0h rd=%0b/%0d/%0b | exp=rw%0b/rd%0b/%0h/l%0b/id%0d/rm%0d/fc%0d | out=rw%0b/rd%0b/%0h/l%0b/id%0d/rm%0d/fc%0d",
                         m_name,
                         m_wr_vld, m_wr_id, m_wr_data, m_rd_id_vld, m_rd_id, m_rd_vld,
                         m_exp_wr_ready, m_exp_rd_ready, m_exp_rd_data, m_exp_rd_last,
                         m_exp_schd_id, m_exp_remain, m_exp_free_cnt,
                         m_out_wr_ready, m_out_rd_ready, m_out_rd_data, m_out_rd_last,
                         m_out_schd_id, m_out_remain, m_out_free_cnt);
    endfunction
endclass
`endif //U_PUBIP_DYNAMIC_MEM_TB_ITEM
