/*========================================FILE_HEADER=====================================
# Filename: pubip_mseq_cal_tc_cal_trans0.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 cal_trans0（对应规格书"基础功能测试：i_trans_num=0"）：
        i_trans_num=0 时全部 i_cal_en=0，o_seq_out 应等于 i_init_seq 延迟 5 拍
        （15 级 mseq_gen 全旁路），验证 3 个不同初始序列
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_mseq_cal_tb_pkg.sv"
`ifndef U_PUBIP_MSEQ_CAL_TC_CAL_TRANS0
`define U_PUBIP_MSEQ_CAL_TC_CAL_TRANS0
import pubip_mseq_cal_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_mseq_cal_tc_cal_trans0 ------------
class pubip_mseq_cal_tc_cal_trans0 extends pubip_mseq_cal_tc_base;

    function new(string name = "pubip_mseq_cal_tc_cal_trans0");
        super.new(name);
    endfunction

    virtual task body();
        pubip_mseq_cal_item seq[$];
        pubip_mseq_cal_item it;
        int pb, pf;
        reset_wait();
        `TB_CASE_BEGIN("TC1: cal_trans0");
        m_env.m_scb.m_enable = 1'b1;
        // thans_num=0 调用 ×3（不同初始序列，调用间 3 拍无效间隙）
        it = new("s1"); stim_item(it, 1'b1, 31'h1234_5678, 15'd0);   seq.push_back(it);
        it = new("g0"); stim_item(it, 1'b0, '0, '0);                 seq.push_back(it);
        it = new("g1"); stim_item(it, 1'b0, '0, '0);                 seq.push_back(it);
        it = new("g2"); stim_item(it, 1'b0, '0, '0);                 seq.push_back(it);
        it = new("s2"); stim_item(it, 1'b1, 31'h5555_5555, 15'd0);   seq.push_back(it);
        it = new("g3"); stim_item(it, 1'b0, '0, '0);                 seq.push_back(it);
        it = new("g4"); stim_item(it, 1'b0, '0, '0);                 seq.push_back(it);
        it = new("g5"); stim_item(it, 1'b0, '0, '0);                 seq.push_back(it);
        it = new("s3"); stim_item(it, 1'b1, 31'h2AAA_AAAA, 15'd0);   seq.push_back(it);
        pb = m_env.m_scb.m_pass_cnt;
        pf = m_env.m_scb.m_fail_cnt;
        drive_seq(seq);
        // 自检：3 次有效调用应有 3 次有效输出比对，无失败
        if (m_env.m_scb.m_pass_cnt - pb !== 3 || m_env.m_scb.m_fail_cnt !== pf) begin
            `TB_ERROR($sformatf("cal_trans0 自检失败 pass+%0d fail=%0d（期望 pass+3/fail 不变）",
                                m_env.m_scb.m_pass_cnt - pb, m_env.m_scb.m_fail_cnt - pf));
            m_env.m_scb.m_fail_cnt = m_env.m_scb.m_fail_cnt + 1;
        end
        `TB_CASE_END("TC1: cal_trans0", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_PUBIP_MSEQ_CAL_TC_CAL_TRANS0
