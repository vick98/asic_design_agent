/*========================================FILE_HEADER=====================================
# Filename: pubip_counter_tb_monitor.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             按 counter 语义采样 o_ 信号，m_cmp_start 控制比对窗口
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_counter 监视器：每拍采样 o_cnt_en/o_counter/o_cnt_shift，m_cmp_start 开启后采样才参与比对
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_PUBIP_COUNTER_TB_MONITOR
`define U_PUBIP_COUNTER_TB_MONITOR

//----------- pubip_counter_monitor ------------
// 每 posedge+#mon_skew 采样一拍；m_cmp_start 之前采样的 item.m_watch=0（比对跳过，复位窗口）
class pubip_counter_monitor extends tb_monitor_base;

    virtual pubip_counter_if             m_dut_if            ;//DUT 接口（env 下发）
    bit                                 m_cmp_start = 1'b0  ;//比对窗口开关（用例在复位释放后开启、扫拍结束关闭）

    function new(string name = "m_mon");
        super.new(name);
    endfunction

    //----------- 采集单事务（每周期一次，m_watch 标记参与比对） ------------
    virtual task collect(ref tb_item_base it);
        pubip_counter_item dut_it;
        @(posedge m_dut_if.clk_in);
        #(m_dut_if.mon_skew);
        dut_it       = new("mon_item");
        dut_it.m_watch    = m_cmp_start;
        dut_it.m_out_en   = m_dut_if.o_cnt_en;
        dut_it.m_out_cnt  = m_dut_if.o_counter;
        dut_it.m_out_shift= m_dut_if.o_cnt_shift;
        it           = dut_it;
    endtask
endclass
`endif //U_PUBIP_COUNTER_TB_MONITOR
