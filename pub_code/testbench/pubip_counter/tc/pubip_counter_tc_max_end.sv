/*========================================FILE_HEADER=====================================
# Filename: pubip_counter_tc_max_end.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             实现计满用例（MAX_NUM=8 计满同步停止）
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 max_end：MAX_NUM 取 2 的幂（8）时计满（8）后 reg_cnt_en 拉低、计数器回 0
        —— 验证 $clog2(MAX_NUM+1) 位宽修复（P0-5：计数范围 0~MAX_NUM 全走通）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_counter_tb_pkg.sv"
`ifndef U_PUBIP_COUNTER_TC_MAX_END
`define U_PUBIP_COUNTER_TC_MAX_END
import pubip_counter_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_counter_tc_max_end ------------
class pubip_counter_tc_max_end extends pubip_counter_tc_base;

    function new(string name = "pubip_counter_tc_max_end");
        super.new(name);
    endfunction

    virtual task body();
        pubip_counter_item seq[$];
        pubip_counter_item it;
        int i;
        reset_wait();
        `TB_CASE_BEGIN("TC2: max_end");
        m_env.m_scb.m_enable = 1'b1;
        // 拍0 start；拍1..8 期望计数 8 前序列；拍9（计满后）en=0、cnt=0
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
        `TB_CASE_END("TC2: max_end", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_PUBIP_COUNTER_TC_MAX_END
