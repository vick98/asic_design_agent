/*========================================FILE_HEADER=====================================
# Filename: pubip_sat_tb_driver.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_sat 驱动器：negedge 驱动一拍一 item（先广播后驱动，纯组合 DUT 下一采样拍有效）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_PUBIP_SAT_TB_DRIVER
`define U_PUBIP_SAT_TB_DRIVER

//----------- pubip_sat_driver ------------
// 一拍一个 item：negedge 驱动 i_data（monitor 在下一 posedge+#mon_skew 采样组合输出）
class pubip_sat_driver extends tb_driver_base;

    virtual pubip_sat_if             m_dut_if            ;//DUT 接口（env 下发）

    function new(string name = "m_drv");
        super.new(name);
    endfunction

    //----------- 驱动单事务（逐拍：negedge 驱动，每 item 一拍） ------------
    virtual task drive(tb_item_base it);
        pubip_sat_item dut_it;
        $cast(dut_it, it);
        // 先广播给 refm（refm 同步计算期望入队，model 为无延迟纯函数），再驱动接口；
        // 避免组合输出先于期望到达 scoreboard 的竞态
        m_drv_mb.put(it);
        @(negedge m_dut_if.clk_in);
        #(m_dut_if.drv_skew);
        m_dut_if.i_data = dut_it.m_data;
    endtask
endclass
`endif //U_PUBIP_SAT_TB_DRIVER
