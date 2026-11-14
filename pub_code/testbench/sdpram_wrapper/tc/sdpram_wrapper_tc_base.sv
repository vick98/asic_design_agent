/*========================================FILE_HEADER=====================================
# Filename: sdpram_wrapper_tc_base.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             reset_wait / 激励构造 / drive_seq 逐拍序列驱动 helper
#
#-----------------------------------------------------------------------------------------
# Description:
        sdpram_wrapper 用例基类：等待复位释放、激励 item 构造（写/读/读写同拍）、
        逐拍序列驱动（一拍一 item，比对窗口随序列开关）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "sdpram_wrapper_tb_pkg.sv"
`ifndef U_SDPRAM_WRAPPER_TC_BASE
`define U_SDPRAM_WRAPPER_TC_BASE
import sdpram_wrapper_tb_pkg::*;
import tb_pkg::*;

//----------- sdpram_wrapper_tc_base ------------
// 用例基类：build_env 创建 env 并下发接口；子类仅实现 body()
class sdpram_wrapper_tc_base extends tb_test_base;

    sdpram_wrapper_env                    m_my_env            ;//模块环境（具体类型）
    virtual sdpram_wrapper_if             m_dut_if            ;//DUT 接口（sim_top 赋值）

    function new(string name = "tc");
        super.new(name);
    endfunction

    //----------- 构建环境：创建 env 并下发接口 ------------
    virtual function void build_env();
        m_my_env = new("m_env");
        m_my_env.m_rst_if = m_rst_if;
        m_my_env.m_dut_if = m_dut_if;
        m_env     = m_my_env;
    endfunction

    //----------- 等待 n 个时钟周期（沿后采样轮询，统一采样时刻） ------------
    task wait_cycles(int n);
        repeat (n) begin
            @(posedge m_dut_if.clk_in);
            #(m_dut_if.mon_skew);
        end
    endtask

    //----------- 等待复位释放 ------------
    task reset_wait();
        do begin
            @(posedge m_rst_if.clk_in);
        end while (m_rst_if.rst_n !== 1'b1);
        wait_cycles(1);
    endtask

    //----------- 构造一个完整激励 item（全字段） ------------
    function sdpram_wrapper_item mk_stim(bit wea, logic [3:0] bea, logic [5:0] addra,
                                         logic [31:0] dina, bit reb, logic [5:0] addrb);
        sdpram_wrapper_item it;
        it       = new("stim");
        it.m_wea   = wea;
        it.m_bea   = bea;
        it.m_addra = addra;
        it.m_dina  = dina;
        it.m_reb   = reb;
        it.m_addrb = addrb;
        return it;
    endfunction

    //----------- 写一拍（全字节使能） ------------
    function sdpram_wrapper_item mk_wr(logic [31:0] dina, logic [5:0] addr);
        return mk_stim(1'b1, 4'hf, addr, dina, 1'b0, 6'h0);
    endfunction

    //----------- 写一拍（按字节使能） ------------
    function sdpram_wrapper_item mk_wr_be(logic [31:0] dina, logic [5:0] addr, logic [3:0] bea);
        return mk_stim(1'b1, bea, addr, dina, 1'b0, 6'h0);
    endfunction

    //----------- 读一拍 ------------
    function sdpram_wrapper_item mk_rd(logic [5:0] addr);
        return mk_stim(1'b0, 4'h0, 6'h0, 32'h0, 1'b1, addr);
    endfunction

    //----------- 同拍同地址读写（写优先验证） ------------
    function sdpram_wrapper_item mk_wr_rd(logic [31:0] dina, logic [5:0] addr, logic [3:0] bea = 4'hf);
        return mk_stim(1'b1, bea, addr, dina, 1'b1, addr);
    endfunction

    //----------- 逐拍驱动序列：一拍一个 item（driver 在 negedge 驱动），比对窗口随之开关 ------------
    // 窗口时序说明（避开 monitor 采样同刻竞态）：
    //   monitor 每个 posedge+#mon_skew 采样一拍；用例置位/清位 m_cmp_start 的时刻须错开该采样点。
    //   T0 拍（put 前最后一拍）采样读旧值 watch=0 → 置位推迟 ~0.2ns 后：从下一拍（item0 响应拍）起
    //   watch 按 本拍 i_reb 标记，共 seq.size() 拍与期望项 1:1 配对；清位同样错开 S_{N-1} 拍采样点
    task drive_seq(sdpram_wrapper_item seq[$]);
        sdpram_wrapper_item it;
        // 1) 越过 T0 拍 monitor 采样点后置窗口
        #(m_dut_if.mon_skew + 0.1);
        m_my_env.m_mon.m_cmp_start = 1'b1;
        // 2) 逐拍入队激励（driver 在下一 negedge 驱动 item0，DUT 在 posedge 响应）
        foreach (seq[i]) begin
            it = new($sformatf("stim%0d", i));
            it.m_wea     = seq[i].m_wea;
            it.m_bea     = seq[i].m_bea;
            it.m_addra   = seq[i].m_addra;
            it.m_dina    = seq[i].m_dina;
            it.m_reb     = seq[i].m_reb;
            it.m_addrb   = seq[i].m_addrb;
            m_my_env.m_drv.m_item_mb.put(it);
        end
        // 3) 等待 item0..itemN-1 响应拍（S_0..S_{N-1}）全部采样完毕
        wait_cycles(seq.size());
        // 4) 越过 S_{N-1} 拍采样点后关窗（下一拍采样读 watch=0，不产生多余比对）
        #(m_dut_if.mon_skew + 0.1);
        m_my_env.m_mon.m_cmp_start = 1'b0;
        wait_cycles(2);
    endtask
endclass
`endif //U_SDPRAM_WRAPPER_TC_BASE
