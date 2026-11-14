/*========================================FILE_HEADER=====================================
# Filename: sdpram_wrapper_tb_driver.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             按 sdpram 语义：negedge 驱动一拍一个 item
#
#-----------------------------------------------------------------------------------------
# Description:
        sdpram_wrapper 驱动器：negedge 驱动（先广播后驱动），DUT 在下一 posedge 采样
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_SDPRAM_WRAPPER_TB_DRIVER
`define U_SDPRAM_WRAPPER_TB_DRIVER

//----------- sdpram_wrapper_driver ------------
// 一拍一个 item：negedge 驱动接口信号（DUT 下一 posedge 采样），先广播给 refm
class sdpram_wrapper_driver extends tb_driver_base;

    virtual sdpram_wrapper_if             m_dut_if            ;//DUT 接口（env 下发）

    function new(string name = "m_drv");
        super.new(name);
    endfunction

    //----------- 驱动单事务（逐拍：negedge 驱动，每 item 一拍） ------------
    virtual task drive(tb_item_base it);
        sdpram_wrapper_item dut_it;
        $cast(dut_it, it);
        // 先广播给 refm（refm 同步算期望入队，见框架 7.2 节竞态约定），再驱动接口
        m_drv_mb.put(it);
        @(negedge m_dut_if.clk_in);
        m_dut_if.i_wea   = dut_it.m_wea;
        m_dut_if.i_bea   = dut_it.m_bea;
        m_dut_if.i_addra = dut_it.m_addra;
        m_dut_if.i_dina  = dut_it.m_dina;
        m_dut_if.i_reb   = dut_it.m_reb;
        m_dut_if.i_addrb = dut_it.m_addrb;
    endtask
endclass
`endif //U_SDPRAM_WRAPPER_TB_DRIVER
