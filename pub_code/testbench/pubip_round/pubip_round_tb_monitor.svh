/*========================================FILE_HEADER=====================================
# Filename: pubip_round_tb_monitor.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-10-06        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_round 监视器：每拍采样 o_data（posedge+#mon_skew），m_cmp_start 控制比对窗口
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_PUBIP_ROUND_TB_MONITOR
`define U_PUBIP_ROUND_TB_MONITOR

//----------- pubip_round_monitor ------------
// 每 posedge+#mon_skew 采样一拍；m_cmp_start 之前采样的 item.m_watch=0（比对跳过，复位窗口）
class pubip_round_monitor extends tb_monitor_base;

    virtual pubip_round_if           m_dut_if            ;//DUT 接口（env 下发）
    bit                             m_cmp_start = 1'b0  ;//比对窗口开关（用例在复位释放后开启、扫拍结束关闭）

    function new(string name = "m_mon");
        super.new(name);
    endfunction

    //----------- 采集单事务（每周期一次，m_watch 标记参与比对） ------------
    virtual task collect(ref tb_item_base it);
        pubip_round_item dut_it;
        @(posedge m_dut_if.clk_in);
        #(m_dut_if.mon_skew);
        dut_it            = new("mon_item");
        dut_it.m_watch    = m_cmp_start;
        dut_it.m_out      = m_dut_if.o_data;
        it                = dut_it;
    endtask
endclass
`endif //U_PUBIP_ROUND_TB_MONITOR
