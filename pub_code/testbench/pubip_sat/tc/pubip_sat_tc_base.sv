/*========================================FILE_HEADER=====================================
# Filename: pubip_sat_tc_base.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_sat 用例基类：等待复位释放、逐拍序列驱动（一拍一 item，期望由 refm 计算回填）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_sat_tb_pkg.sv"
`ifndef U_PUBIP_SAT_TC_BASE
`define U_PUBIP_SAT_TC_BASE
import pubip_sat_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_sat_tc_base ------------
class pubip_sat_tc_base extends tb_test_base;

    pubip_sat_env                    m_my_env            ;//模块环境（具体类型）
    virtual pubip_sat_if             m_dut_if            ;//DUT 接口（sim_top 赋值）

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

    //----------- 构造单拍激励并压入序列（期望由 refm.compute() 回填，不预置） ------------
    // 注意：queue 形参必须显式 ref（默认 input 为值拷贝，push_back 仅作用于副本，序列会丢失数据）
    function void push_data(ref pubip_sat_item seq[$], input logic [`PUBIP_SAT_IN_TOTAL - 1 : 0] data);
        pubip_sat_item it;
        it          = new("stim");
        it.m_data   = data;
        seq.push_back(it);
    endfunction

    //----------- 逐拍驱动序列：一拍一个 item（driver 在 negedge 驱动），比对窗口随之开关 ------------
    // 窗口时序说明（避开 monitor 采样同刻竞态）：
    //   monitor 每个 posedge+#mon_skew 采样一拍；用例置位/清位 m_cmp_start 的时刻须错开该采样点。
    //   put 前最后一拍采样读旧值 watch=0 → 置位推迟 ~0.1ns 后：从下一拍（item0 响应拍）起
    //   watch=1，共 seq.size() 拍与期望项 1:1 配对；清位同样错开 S_{N-1} 拍采样点，下一拍采样读 watch=0
    task drive_seq(pubip_sat_item seq[$]);
        pubip_sat_item it;
        // 1) 越过 T0 拍 monitor 采样点后置窗口
        #(m_dut_if.mon_skew + 0.1);
        m_my_env.m_mon.m_cmp_start = 1'b1;
        // 2) 逐拍入队激励（driver 在下一 negedge 驱动 item0，纯组合输出于 posedge 采样时稳定）
        foreach (seq[i]) begin
            it = new($sformatf("stim%0d", i));
            it.m_data = seq[i].m_data;
            m_my_env.m_drv.m_item_mb.put(it);
        end
        // 3) 等待 item0..itemN-1 响应拍（S_0..S_{N-1}）全部采样完毕（组合模块驱动后至少一拍等待）
        wait_cycles(seq.size());
        // 4) 越过 S_{N-1} 拍采样点后关窗（下一拍采样读 watch=0，不产生多余比对）
        #(m_dut_if.mon_skew + 0.1);
        m_my_env.m_mon.m_cmp_start = 1'b0;
        wait_cycles(2);
    endtask
endclass
`endif //U_PUBIP_SAT_TC_BASE
