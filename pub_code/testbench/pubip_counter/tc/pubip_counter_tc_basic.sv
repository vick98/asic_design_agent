/*========================================FILE_HEADER=====================================
# Filename: pubip_counter_tc_basic.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             实现基本计数用例（start→1..8→自动停止并保持）
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 basic：一个启动脉冲后计数 1..8，计满（wir_cnt_end）自动停止，输出保持 0
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_counter_tb_pkg.sv"
`ifndef U_PUBIP_COUNTER_TC_BASIC
`define U_PUBIP_COUNTER_TC_BASIC
import pubip_counter_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_counter_tc_basic ------------
class pubip_counter_tc_basic extends pubip_counter_tc_base;

    function new(string name = "pubip_counter_tc_basic");
        super.new(name);
    endfunction

    virtual task body();
        pubip_counter_item seq[$];
        pubip_counter_item it;
        int i;
        reset_wait();
        `TB_CASE_BEGIN("TC1: basic");
        m_env.m_scb.m_enable = 1'b1;
        // 拍0：start 脉冲；后续各拍期望依次为计数 1..8（shift=1<<cnt）、停止后为 0
        for (i = 0; i < 14; i = i + 1) begin
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
        `TB_CASE_END("TC1: basic", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_PUBIP_COUNTER_TC_BASIC
