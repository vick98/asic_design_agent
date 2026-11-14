/*========================================FILE_HEADER=====================================
# Filename: pubip_counter_tb_driver.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             按 counter 语义：negedge 驱动一拍一个 item
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_counter 驱动器：negedge 驱动（先广播后驱动），DUT 在下一 posedge 采样
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_PUBIP_COUNTER_TB_DRIVER
`define U_PUBIP_COUNTER_TB_DRIVER

//----------- pubip_counter_driver ------------
// 一拍一个 item：negedge 驱动接口脉冲（DUT 下一 posedge 采样），先广播给 refm
class pubip_counter_driver extends tb_driver_base;

    virtual pubip_counter_if             m_dut_if            ;//DUT 接口（env 下发）

    function new(string name = "m_drv");
        super.new(name);
    endfunction

    //----------- 驱动单事务（逐拍：negedge 驱动，每 item 一拍） ------------
    virtual task drive(tb_item_base it);
        pubip_counter_item dut_it;
        $cast(dut_it, it);
        // 先广播给 refm（refm 同步计算期望入队，model 为无延迟纯函数），再驱动接口
        m_drv_mb.put(it);
        @(negedge m_dut_if.clk_in);
        m_dut_if.i_cnt_start_b1 = dut_it.m_start;
        m_dut_if.i_cnt_rst      = dut_it.m_rst;
        m_dut_if.i_cnt_end      = dut_it.m_end;
    endtask
endclass
`endif //U_PUBIP_COUNTER_TB_DRIVER
