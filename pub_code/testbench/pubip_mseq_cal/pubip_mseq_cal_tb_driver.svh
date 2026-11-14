/*========================================FILE_HEADER=====================================
# Filename: pubip_mseq_cal_tb_driver.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             按 mseq_cal 语义：negedge 驱动一拍一 item（先广播后驱动）
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_mseq_cal 驱动器：negedge 驱动（先广播给 refm 再驱动接口），DUT 在下一 posedge 采样
        一拍一 item：i_cal_vld=0 的 item 也覆盖驱动（接口复位 i_cal_vld=0，防止残留有效）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_PUBIP_MSEQ_CAL_TB_DRIVER
`define U_PUBIP_MSEQ_CAL_TB_DRIVER

//----------- pubip_mseq_cal_driver ------------
// 一拍一 item：negedge 驱动接口（DUT 下一 posedge 采样），先广播给 refm（期望同步计算入队）
class pubip_mseq_cal_driver extends tb_driver_base;

    virtual pubip_mseq_cal_if             m_dut_if            ;//DUT 接口（env 下发）

    function new(string name = "m_drv");
        super.new(name);
    endfunction

    //----------- 驱动单事务（逐拍：negedge 驱动，每 item 一拍） ------------
    virtual task drive(tb_item_base it);
        pubip_mseq_cal_item dut_it;
        $cast(dut_it, it);
        // 先广播给 refm（refm 同步计算期望入队，compute 为无延迟纯函数），再驱动接口
        m_drv_mb.put(it);
        @(negedge m_dut_if.clk_in);
        m_dut_if.i_init_seq  = dut_it.m_init_seq;
        m_dut_if.i_cal_vld   = dut_it.m_vld;
        m_dut_if.i_trans_num = dut_it.m_trans_num;
    endtask
endclass
`endif //U_PUBIP_MSEQ_CAL_TB_DRIVER
