/*========================================FILE_HEADER=====================================
# Filename: pubip_counter_tc_rst_clear.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             实现异步复位用例（计数中拉低 rst_n 清零）
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 rst_clear：计数器运行中异步拉低 rst_n（经 m_rst_if），寄存器清零、计数停止，
        恢复后en=0 保持（单次模式需重新 start）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_counter_tb_pkg.sv"
`ifndef U_PUBIP_COUNTER_TC_RST_CLEAR
`define U_PUBIP_COUNTER_TC_RST_CLEAR
import pubip_counter_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_counter_tc_rst_clear ------------
class pubip_counter_tc_rst_clear extends pubip_counter_tc_base;

    function new(string name = "pubip_counter_tc_rst_clear");
        super.new(name);
    endfunction

    virtual task body();
        pubip_counter_item seq[$];
        pubip_counter_item it;
        int i;
        reset_wait();
        `TB_CASE_BEGIN("TC6: rst_clear");
        m_env.m_scb.m_enable = 1'b1;
        // 拍0 start；拍1..2 计数 1..2；拍3 期望 3（该拍后复位生效）；拍4..7 复位期/恢复期输出 0
        for (i = 0; i < 8; i = i + 1) begin
            it = new($sformatf("seq%0d", i));
            if (i == 0) begin
                // 拍0：start 响应拍 → 清零输出（en=1、cnt=0、shift bit0 有效）
                seq_item(it, 1'b1, 1'b0, 1'b0, 1'b1, 4'd0, 9'h001);
            end
            else if (i == 1) begin
                seq_item(it, 1'b0, 1'b0, 1'b0, 1'b1, 4'd1, 9'h002);
            end
            else if (i == 2) begin
                seq_item(it, 1'b0, 1'b0, 1'b0, 1'b1, 4'd2, 9'h004);
            end
            else if (i == 3) begin
                // 拍3：复位前最后计数拍（输出 3；该拍后于 negedge 拉低复位）
                seq_item(it, 1'b0, 1'b0, 1'b0, 1'b1, 4'd3, 9'h008);
            end
            else begin
                // 拍4..7：复位期/恢复期输出 0（en=0 保持，单次模式）
                seq_item(it, 1'b0, 1'b0, 1'b0, 1'b0, 4'd0, 9'h000);
            end
            seq.push_back(it);
        end
        // 越过 T0 拍采样点后置窗口；put 8 项；S_0..S_3 采样完成后
        // 在 negedge 拉低复位（monitor 仅 posedge 采样，确定性无同刻竞态），保持 2 拍后释放
        #(m_dut_if.mon_skew + 0.1);
        m_my_env.m_mon.m_cmp_start = 1'b1;
        foreach (seq[i]) m_my_env.m_drv.m_item_mb.put(seq[i]);
        // 等 start 响应拍 + 计数 1..3 共 4 拍（S_0..S_3）采样完成
        wait_cycles(4);
        // 在 negedge 拉低复位，保持 2 拍后在 negedge 释放
        @(negedge m_dut_if.clk_in); #(m_dut_if.mon_skew);
        m_rst_if.rst_n = 1'b0;
        wait_cycles(2);
        @(negedge m_dut_if.clk_in); #(m_dut_if.mon_skew);
        m_rst_if.rst_n = 1'b1;
        // 复位后 2 拍恢复观测（S_6..S_7 输出 0），随后错开采样点关窗
        wait_cycles(2);
        #(m_dut_if.mon_skew + 0.1);
        m_my_env.m_mon.m_cmp_start = 1'b0;
        wait_cycles(2);
        `TB_CASE_END("TC6: rst_clear", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_PUBIP_COUNTER_TC_RST_CLEAR
