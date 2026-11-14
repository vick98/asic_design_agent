/*========================================FILE_HEADER=====================================
# Filename: pubip_dynamic_mem_tb_driver.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             按模块语义：negedge 驱动一拍一 item（6 个 i_ 输入）
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_dynamic_mem 驱动器：negedge 驱动（先广播后驱动），DUT 在下一 posedge 采样
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_PUBIP_DYNAMIC_MEM_TB_DRIVER
`define U_PUBIP_DYNAMIC_MEM_TB_DRIVER

//----------- pubip_dynamic_mem_driver ------------
// 一拍一个 item：negedge 驱动接口 6 个输入（DUT 下一 posedge 采样），先广播给 refm
class pubip_dynamic_mem_driver extends tb_driver_base;

    virtual pubip_dynamic_mem_if             m_dut_if            ;//DUT 接口（env 下发）

    function new(string name = "m_drv");
        super.new(name);
    endfunction

    //----------- 驱动单事务（逐拍：negedge 驱动，每 item 一拍） ------------
    virtual task drive(tb_item_base it);
        pubip_dynamic_mem_item dut_it;
        $cast(dut_it, it);
        // 先广播给 refm（refm 同步计算期望入队），再驱动接口
        m_drv_mb.put(it);
        @(negedge m_dut_if.clk_in);
        m_dut_if.i_wr_data   = dut_it.m_wr_data ;
        m_dut_if.i_wr_id     = dut_it.m_wr_id   ;
        m_dut_if.i_wr_vld    = dut_it.m_wr_vld  ;
        m_dut_if.i_rd_id     = dut_it.m_rd_id   ;
        m_dut_if.i_rd_id_vld = dut_it.m_rd_id_vld;
        m_dut_if.i_rd_vld    = dut_it.m_rd_vld  ;
    endtask
endclass
`endif //U_PUBIP_DYNAMIC_MEM_TB_DRIVER
