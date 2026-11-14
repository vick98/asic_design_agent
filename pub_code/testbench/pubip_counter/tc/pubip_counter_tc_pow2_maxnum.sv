/*========================================FILE_HEADER=====================================
# Filename: pubip_counter_tc_pow2_maxnum.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             实现 2 的幂 MAX_NUM 全量计数用例
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 pow2_maxnum：MAX_NUM=8 时 0~8 共 9 个值全走通（CNT_WIDTH 自动 = $clog2(9) = 4，
        无截断/溢出），专门验证 P0-5 位宽修复
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_counter_tb_pkg.sv"
`ifndef U_PUBIP_COUNTER_TC_POW2_MAXNUM
`define U_PUBIP_COUNTER_TC_POW2_MAXNUM
import pubip_counter_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_counter_tc_pow2_maxnum ------------
class pubip_counter_tc_pow2_maxnum extends pubip_counter_tc_base;

    function new(string name = "pubip_counter_tc_pow2_maxnum");
        super.new(name);
    endfunction

    virtual task body();
        pubip_counter_item seq[$];
        pubip_counter_item it;
        int i;
        reset_wait();
        `TB_CASE_BEGIN("TC3: pow2_maxnum");
        m_env.m_scb.m_enable = 1'b1;
        // 全值扫描：计数 1..8（o_counter 4bit 无溢出），随后停止
        for (i = 0; i < 12; i = i + 1) begin
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
        `TB_CASE_END("TC3: pow2_maxnum", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_PUBIP_COUNTER_TC_POW2_MAXNUM
