/*========================================FILE_HEADER=====================================
# Filename: sdpram_wrapper_tb_monitor.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             按 sdpram 语义采样 o_doutb，m_cmp_start+i_reb 控制比对窗口
#
#-----------------------------------------------------------------------------------------
# Description:
        sdpram_wrapper 监视器：每拍采样 o_doutb，m_cmp_start 开启且本拍 i_reb=1 的采样才参与比对
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_SDPRAM_WRAPPER_TB_MONITOR
`define U_SDPRAM_WRAPPER_TB_MONITOR

//----------- sdpram_wrapper_monitor ------------
// 每 posedge+#mon_skew 采样一拍；m_watch = m_cmp_start && i_reb（比对窗口内且读使能为 1 才比对）
class sdpram_wrapper_monitor extends tb_monitor_base;

    virtual sdpram_wrapper_if             m_dut_if            ;//DUT 接口（env 下发）
    bit                                 m_cmp_start = 1'b0  ;//比对窗口开关（用例在驱动序列开始时开启、结束时关闭）

    function new(string name = "m_mon");
        super.new(name);
    endfunction

    //----------- 采集单事务（每周期一次，m_watch 标记参与比对） ------------
    virtual task collect(ref tb_item_base it);
        sdpram_wrapper_item dut_it;
        @(posedge m_dut_if.clk_in);
        #(m_dut_if.mon_skew);
        dut_it         = new("mon_item");
        dut_it.m_watch = (m_cmp_start === 1'b1) && (m_dut_if.i_reb === 1'b1);
        dut_it.m_out_dout = m_dut_if.o_doutb;
        it             = dut_it;
    endtask
endclass
`endif //U_SDPRAM_WRAPPER_TB_MONITOR
