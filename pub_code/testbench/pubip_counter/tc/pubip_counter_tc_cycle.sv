/*========================================FILE_HEADER=====================================
# Filename: pubip_counter_tc_cycle.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             实现循环计数用例（需 +define+PUBIP_CNT_CYCLE 编译）
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 cycle：CYCLE_EN=1 循环模式计数 1..8 回绕（计满回 0、下一拍 1），i_cnt_end 停止。
        注意：需要 sim_top 以 +define+PUBIP_CNT_CYCLE 编译（CYCLE_EN=1 例化），
        不在 tc_all 聚合内（默认参数例化），单独 +TC=tc_cycle 运行
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_counter_tb_pkg.sv"
`ifndef U_PUBIP_COUNTER_TC_CYCLE
`define U_PUBIP_COUNTER_TC_CYCLE
import pubip_counter_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_counter_tc_cycle ------------
class pubip_counter_tc_cycle extends pubip_counter_tc_base;

    function new(string name = "pubip_counter_tc_cycle");
        super.new(name);
    endfunction

    virtual task body();
        pubip_counter_item seq[$];
        pubip_counter_item it;
        int i;
        int cnt;
        reset_wait();
        `TB_CASE_BEGIN("TC5: cycle");
        m_env.m_scb.m_enable = 1'b1;
        // 循环两轮：1..8, 1..8 后 i_cnt_end 停止；每拍期望 cnt=上轮值回绕、shift=1<<cnt
        for (i = 0; i < 22; i = i + 1) begin
            it = new($sformatf("seq%0d", i));
            if (i == 0) begin
                // 拍0：start 响应拍 → 清零输出（en=1、cnt=0、shift bit0 有效）
                seq_item(it, 1'b1, 1'b0, 1'b0, 1'b1, 4'd0, 9'h001);
            end
            else if (i == 18) begin
                // 第 18 拍：i_cnt_end 脉冲 → 停止（en=0）
                seq_item(it, 1'b0, 1'b0, 1'b1, 1'b0, 4'd0, 9'h000);
            end
            else if (i == 9) begin
                // 第 9 拍：计满 8 回绕清零拍（en 保持，cnt=0、shift bit0 有效）
                seq_item(it, 1'b0, 1'b0, 1'b0, 1'b1, 4'd0, 9'h001);
            end
            else if (i < 18) begin
                // 两轮计数：i=1..8 第一轮 1..8；i=10..17 第二轮 1..8
                cnt = (i < 9) ? i : (i - 9);
                seq_item(it, 1'b0, 1'b0, 1'b0, 1'b1, cnt[3:0], 9'h001 << cnt);
            end
            else begin
                seq_item(it, 1'b0, 1'b0, 1'b0, 1'b0, 4'd0, 9'h000);
            end
            seq.push_back(it);
        end
        drive_seq(seq);
        `TB_CASE_END("TC5: cycle", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_PUBIP_COUNTER_TC_CYCLE
