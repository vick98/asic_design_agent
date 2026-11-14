/*========================================FILE_HEADER=====================================
# Filename: pubip_mseq_gen_tc_mseq_border.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 mseq_border（测试要点 3）：边界与非法态验证。
        i_init_seq 全 0（LFSR 全零态为非法态——反馈与移位均为 0 而保持 0）与全 1 边界；
        i_cal_en 随机翻转（旁路输出 = i_init_seq，使能输出 = 逐步转移）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_mseq_gen_tb_pkg.sv"
`ifndef U_PUBIP_MSEQ_GEN_TC_MSEQ_BORDER
`define U_PUBIP_MSEQ_GEN_TC_MSEQ_BORDER
import pubip_mseq_gen_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_mseq_gen_tc_mseq_border ------------
class pubip_mseq_gen_tc_mseq_border extends pubip_mseq_gen_tc_base;

    function new(string name = "pubip_mseq_gen_tc_mseq_border");
        super.new(name);
    endfunction

    virtual task body();
        pubip_mseq_gen_item seq[$];
        int i;
        reset_wait();
        `TB_CASE_BEGIN("TC3: mseq_border");
        m_env.m_scb.m_enable = 1'b1;
        // 全 0 边界：非法态保持 0（cal_en=0 旁路 / =1 转移均输出 0）
        push_stim(seq, 4'h0, 1'b0);
        push_stim(seq, 4'h0, 1'b1);
        push_stim(seq, 4'h0, 1'b1);
        push_stim(seq, 4'h0, 1'b0);
        // 全 1 边界：旁路输出全 1；转移后进入 0111->0011->0001->1000 链（逐步转移）
        push_stim(seq, 4'hF, 1'b0);
        push_stim(seq, 4'hF, 1'b1);
        push_stim(seq, 4'hF, 1'b1);
        push_stim(seq, 4'hF, 1'b1);
        push_stim(seq, 4'hF, 1'b1);
        push_stim(seq, 4'hF, 1'b1);
        // 全 1 状态上随机翻转 i_cal_en（旁路/转移交替，检查旁路输出回路正确）
        for (i = 0; i < 10; i = i + 1) begin
            push_stim(seq, 4'hF, $urandom_range(0, 1));
        end
        // 单 bit 初始值定向边界（0x1/0x8 转移一步）
        push_stim(seq, 4'h1, 1'b1);
        push_stim(seq, 4'h8, 1'b1);
        drive_seq(seq);
        `TB_CASE_END("TC3: mseq_border", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_PUBIP_MSEQ_GEN_TC_MSEQ_BORDER
