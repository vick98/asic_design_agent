/*========================================FILE_HEADER=====================================
# Filename: pubip_complex_mult_tb_monitor.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             按复乘语义采样 o_dout，m_cmp_start 控制比对窗口
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_complex_mult 监视器：每拍采样 o_dout_re/o_dout_im，m_cmp_start 开启后采样才参与比对
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_PUBIP_COMPLEX_MULT_TB_MONITOR
`define U_PUBIP_COMPLEX_MULT_TB_MONITOR

//----------- pubip_complex_mult_monitor ------------
// 每 posedge+#mon_skew 采样一拍；m_cmp_start 之前采样的 item.m_watch=0（比对跳过，复位窗口）
class pubip_complex_mult_monitor extends tb_monitor_base;

    virtual pubip_complex_mult_if     m_dut_if            ;//DUT 接口（env 下发）
    bit                              m_cmp_start = 1'b0  ;//比对窗口开关（用例在复位释放后开启、扫拍结束关闭）

    function new(string name = "m_mon");
        super.new(name);
    endfunction

    //----------- 采集单事务（每周期一次，m_watch 标记参与比对） ------------
    virtual task collect(ref tb_item_base it);
        pubip_complex_mult_item dut_it;
        @(posedge m_dut_if.clk_in);
        #(m_dut_if.mon_skew);
        dut_it         = new("mon_item");
        dut_it.m_watch = m_cmp_start;
        dut_it.m_out_re = m_dut_if.o_dout_re;
        dut_it.m_out_im = m_dut_if.o_dout_im;
        it             = dut_it;
    endtask
endclass
`endif //U_PUBIP_COMPLEX_MULT_TB_MONITOR
