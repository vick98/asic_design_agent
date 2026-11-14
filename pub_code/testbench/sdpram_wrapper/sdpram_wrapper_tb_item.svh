/*========================================FILE_HEADER=====================================
# Filename: sdpram_wrapper_tb_item.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             按 sdpram 语义补全激励/期望/采集字段（一拍一个 item）
#
#-----------------------------------------------------------------------------------------
# Description:
        sdpram_wrapper 事务类：一拍一个事务（写/读/读写同拍的激励描述），
        期望值由 refm 按行为 RAM 模型回填（m_exp_vld/m_exp_dout），采集值由 monitor 回填
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_SDPRAM_WRAPPER_TB_ITEM
`define U_SDPRAM_WRAPPER_TB_ITEM

//----------- sdpram_wrapper_item ------------
// 一拍一个 item：激励（wea/bea/addra/dina/reb/addrb）+ 期望（refm 回填）+ 采集（monitor 回填）
class sdpram_wrapper_item extends tb_item_base;

    //----------- 激励 ------------
    bit                             m_wea               ;//写使能
    logic [3:0]                     m_bea               ;//字节使能（bit i 控制第 i 字节）
    logic [5:0]                     m_addra             ;//写地址
    logic [31:0]                    m_dina              ;//写数据
    bit                             m_reb               ;//读使能
    logic [5:0]                     m_addrb             ;//读地址

    //----------- 期望（refm 回填；m_exp_vld=1 表示本拍有读比对） ------------
    bit                             m_exp_vld           ;//期望有效（本拍履行了读）
    logic [31:0]                    m_exp_dout          ;//期望读数据

    //----------- 采集（monitor 回填） ------------
    bit                             m_watch             ;//参与比对（比对窗口内且本拍读使能有效）
    logic [31:0]                    m_out_dout          ;//采样读数据

    function new(string name = "sdpram_wrapper_item");
        super.new(name);
    endfunction

    //----------- 事务描述打印 ------------
    function string do_print();
        return $sformatf("%s id=%0d w=%0b/%0b/%0h/%0h r=%0b/%0h exp=%0b/%0h out=%0b/%0h",
                         m_name, m_id,
                         m_wea, m_bea, m_addra, m_dina,
                         m_reb, m_addrb,
                         m_exp_vld, m_exp_dout,
                         m_watch, m_out_dout);
    endfunction
endclass
`endif //U_SDPRAM_WRAPPER_TB_ITEM
