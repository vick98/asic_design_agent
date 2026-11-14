/*========================================FILE_HEADER=====================================
# Filename: pubip_counter_tc_shift_width.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             实现脉冲位宽用例（bit j ↔ 计数值 j，含 bit8）
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 shift_width：o_cnt_shift 位宽 = MAX_NUM+1 = 9，bit j 与计数值 j 一一对应，
        计数值 8 的脉冲在 bit8（验证 P0-6 脉冲截断修复）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_counter_tb_pkg.sv"
`ifndef U_PUBIP_COUNTER_TC_SHIFT_WIDTH
`define U_PUBIP_COUNTER_TC_SHIFT_WIDTH
import pubip_counter_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_counter_tc_shift_width ------------
class pubip_counter_tc_shift_width extends pubip_counter_tc_base;

    function new(string name = "pubip_counter_tc_shift_width");
        super.new(name);
    endfunction

    virtual task body();
        pubip_counter_item seq[$];
        pubip_counter_item it;
        int i;
        reset_wait();
        `TB_CASE_BEGIN("TC4: shift_width");
        m_env.m_scb.m_enable = 1'b1;
        // 每次计数值 j 时仅 bit j 有效（j=1..8；bit8 = 计数值 8 的脉冲）
        for (i = 0; i < 11; i = i + 1) begin
            it = new($sformatf("seq%0d", i));
            if (i == 0) begin
                // 拍0：start 响应拍 → 清零输出（en=1、cnt=0、shift bit0 有效）
                seq_item(it, 1'b1, 1'b0, 1'b0, 1'b1, 4'd0, 9'h001);
            end
            else if (i < 9) begin
                seq_item(it, 1'b0, 1'b0, 1'b0, 1'b1, i[3:0], 9'h001 << i);
            end
            else begin
                seq_item(it, 1'b0, 1'b0, 1'b0, 1'b0, 4'd0, 9'h000);
            end
            seq.push_back(it);
        end
        drive_seq(seq);
        `TB_CASE_END("TC4: shift_width", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_PUBIP_COUNTER_TC_SHIFT_WIDTH
