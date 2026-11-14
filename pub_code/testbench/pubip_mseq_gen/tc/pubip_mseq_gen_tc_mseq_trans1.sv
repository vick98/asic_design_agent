/*========================================FILE_HEADER=====================================
# Filename: pubip_mseq_gen_tc_mseq_trans1.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 mseq_trans1（测试要点 1，默认小参验配置 TRANS_NUM=1）：单步转移对拍 + 旁路验证。
        i_cal_en=1：输出 = LFSR 一步值（refm 独立 LFSR 参考模型逐拍迭代对拍）；
        i_cal_en=0：输出 = i_init_seq（旁路原序列）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_mseq_gen_tb_pkg.sv"
`ifndef U_PUBIP_MSEQ_GEN_TC_MSEQ_TRANS1
`define U_PUBIP_MSEQ_GEN_TC_MSEQ_TRANS1
import pubip_mseq_gen_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_mseq_gen_tc_mseq_trans1 ------------
class pubip_mseq_gen_tc_mseq_trans1 extends pubip_mseq_gen_tc_base;

    function new(string name = "pubip_mseq_gen_tc_mseq_trans1");
        super.new(name);
    endfunction

    virtual task body();
        pubip_mseq_gen_item seq[$];
        logic [`PUBIP_MPG_SEQ_WIDTH - 1 : 0] rnd;
        int i;
        reset_wait();
        `TB_CASE_BEGIN("TC1: mseq_trans1");
        m_env.m_scb.m_enable = 1'b1;
        // 定向校验（单步转移 + 旁路）：
        push_stim(seq, 4'h1, 1'b1);   // 0001 -> 1000（反馈 1^0=1 填 MSB）
        push_stim(seq, 4'h2, 1'b1);   // 0010 -> 1001（反馈 0^1=1）
        push_stim(seq, 4'h8, 1'b1);   // 1000 -> 0100（反馈 0^0=0）
        push_stim(seq, 4'h5, 1'b0);   // 旁路：输出 = 0101
        push_stim(seq, 4'hF, 1'b1);   // 1111 -> 0111（反馈 1^1=0）
        push_stim(seq, 4'h0, 1'b1);   // 全零态保持 0（非法态检查）
        // 随机初始值单步转移（i%3==0 拍旁路，其余 cal_en=1）
        for (i = 0; i < 18; i = i + 1) begin
            rnd = $urandom_range(0, (1 << `PUBIP_MPG_SEQ_WIDTH) - 1);
            push_stim(seq, rnd, (i % 3 == 0) ? 1'b0 : 1'b1);
        end
        drive_seq(seq);
        `TB_CASE_END("TC1: mseq_trans1", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_PUBIP_MSEQ_GEN_TC_MSEQ_TRANS1
