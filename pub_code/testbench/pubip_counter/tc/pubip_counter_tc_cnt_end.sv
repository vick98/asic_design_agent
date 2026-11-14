/*========================================FILE_HEADER=====================================
# Filename: pubip_counter_tc_cnt_end.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             实现计数停止用例（i_cnt_end 停止计数）
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 cnt_end：计数运行中输入 i_cnt_end 脉冲 → reg_cnt_en 拉低、计数器清零，保持 0
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_counter_tb_pkg.sv"
`ifndef U_PUBIP_COUNTER_TC_CNT_END
`define U_PUBIP_COUNTER_TC_CNT_END
import pubip_counter_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_counter_tc_cnt_end ------------
class pubip_counter_tc_cnt_end extends pubip_counter_tc_base;

    function new(string name = "pubip_counter_tc_cnt_end");
        super.new(name);
    endfunction

    virtual task body();
        pubip_counter_item seq[$];
        pubip_counter_item it;
        int i;
        reset_wait();
        `TB_CASE_BEGIN("TC8: cnt_end");
        m_env.m_scb.m_enable = 1'b1;
        // 拍0 start；拍1..2 计数 1..2；拍3 i_cnt_end 脉冲（期望拍4 起停止为 0）
        for (i = 0; i < 9; i = i + 1) begin
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
                seq_item(it, 1'b0, 1'b0, 1'b1, 1'b0, 4'd0, 9'h000);
            end
            else begin
                seq_item(it, 1'b0, 1'b0, 1'b0, 1'b0, 4'd0, 9'h000);
            end
            seq.push_back(it);
        end
        drive_seq(seq);
        `TB_CASE_END("TC8: cnt_end", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_PUBIP_COUNTER_TC_CNT_END
