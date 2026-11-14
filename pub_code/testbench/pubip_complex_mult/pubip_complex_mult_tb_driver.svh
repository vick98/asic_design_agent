/*========================================FILE_HEADER=====================================
# Filename: pubip_complex_mult_tb_driver.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             按复乘语义：negedge 驱动一拍一个 item
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_complex_mult 驱动器：negedge 驱动（先广播后驱动），DUT 组合输出在此后立即稳定、
        monitor 在下一 posedge 采样
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_PUBIP_COMPLEX_MULT_TB_DRIVER
`define U_PUBIP_COMPLEX_MULT_TB_DRIVER

//----------- pubip_complex_mult_driver ------------
// 一拍一个 item：negedge 驱动接口（DUT 为纯组合，输出在驱动后组合稳定），先广播给 refm
class pubip_complex_mult_driver extends tb_driver_base;

    virtual pubip_complex_mult_if     m_dut_if            ;//DUT 接口（env 下发）

    function new(string name = "m_drv");
        super.new(name);
    endfunction

    //----------- 驱动单事务（逐拍：negedge 驱动，每 item 一拍） ------------
    virtual task drive(tb_item_base it);
        pubip_complex_mult_item dut_it;
        $cast(dut_it, it);
        // 先广播给 refm（refm 同步计算期望入队，model 为无延迟纯函数），再驱动接口；
        // 避免 DUT 组合输出先于期望到达 scoreboard 的竞态
        m_drv_mb.put(it);
        @(negedge m_dut_if.clk_in);
        m_dut_if.i_dina_re = dut_it.m_ar;
        m_dut_if.i_dina_im = dut_it.m_ai;
        m_dut_if.i_dinb_re = dut_it.m_br;
        m_dut_if.i_dinb_im = dut_it.m_bi;
    endtask
endclass
`endif //U_PUBIP_COMPLEX_MULT_TB_DRIVER
