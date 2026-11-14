/*========================================FILE_HEADER=====================================
# Filename: sdpram_wrapper_tc_wr_rd.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 wr_rd：写读回环——写地址 0 与 63（深度上边界，P0-1 验收点：原 bug 下地址 63 丢数）读回校验；
        全深度扫描：地址 0..63 各写一值（0xA0000000+addr）再全部读回（64 点）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "sdpram_wrapper_tb_pkg.sv"
`ifndef U_SDPRAM_WRAPPER_TC_WR_RD
`define U_SDPRAM_WRAPPER_TC_WR_RD
import sdpram_wrapper_tb_pkg::*;
import tb_pkg::*;

//----------- sdpram_wrapper_tc_wr_rd ------------
class sdpram_wrapper_tc_wr_rd extends sdpram_wrapper_tc_base;

    function new(string name = "sdpram_wrapper_tc_wr_rd");
        super.new(name);
    endfunction

    virtual task body();
        sdpram_wrapper_item seq[$];
        int                  i;
        reset_wait();
        `TB_CASE_BEGIN("TC1: wr_rd");
        m_env.m_scb.m_enable = 1'b1;
        // 1) 写地址 0 与 63（深度上边界，P0-1 验收点）
        seq.push_back(mk_wr(32'hDEADBEEF, 6'd0));
        seq.push_back(mk_wr(32'hCAFEBABE, 6'd63));
        // 2) 读回校验（边界两地址）
        seq.push_back(mk_rd(6'd0));
        seq.push_back(mk_rd(6'd63));
        // 3) 全深度扫描：0..63 各写一值
        for (i = 0; i < 64; i = i + 1) begin
            seq.push_back(mk_wr(32'hA0000000 + i[31:0], i[5:0]));
        end
        // 4) 全深度扫描读回 64 点（初始写入值与读回一一对拍）
        for (i = 0; i < 64; i = i + 1) begin
            seq.push_back(mk_rd(i[5:0]));
        end
        drive_seq(seq);
        `TB_CASE_END("TC1: wr_rd", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_SDPRAM_WRAPPER_TC_WR_RD
