/*========================================FILE_HEADER=====================================
# Filename: pubip_mseq_cal_tc_cal_trans1.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 cal_trans1（对应规格书"基础功能测试：i_trans_num=1"）：
        i_trans_num=1 时仅段 4 末级（TRANS_NUM=1）i_cal_en=1，输出 = mseq_gen 单步转移结果；
        refm 用独立 LFSR 参考实现按 1 次迭代对拍
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_mseq_cal_tb_pkg.sv"
`ifndef U_PUBIP_MSEQ_CAL_TC_CAL_TRANS1
`define U_PUBIP_MSEQ_CAL_TC_CAL_TRANS1
import pubip_mseq_cal_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_mseq_cal_tc_cal_trans1 ------------
class pubip_mseq_cal_tc_cal_trans1 extends pubip_mseq_cal_tc_base;

    function new(string name = "pubip_mseq_cal_tc_cal_trans1");
        super.new(name);
    endfunction

    virtual task body();
        pubip_mseq_cal_item seq[$];
        pubip_mseq_cal_item it;
        int pb, pf;
        reset_wait();
        `TB_CASE_BEGIN("TC2: cal_trans1");
        m_env.m_scb.m_enable = 1'b1;
        // trans_num=1 调用 ×3（不同初始序列，调用间 3 拍无效间隙）
        it = new("s1"); stim_item(it, 1'b1, 31'h1234_5678, 15'd1);   seq.push_back(it);
        it = new("g0"); stim_item(it, 1'b0, '0, '0);                 seq.push_back(it);
        it = new("g1"); stim_item(it, 1'b0, '0, '0);                 seq.push_back(it);
        it = new("g2"); stim_item(it, 1'b0, '0, '0);                 seq.push_back(it);
        it = new("s2"); stim_item(it, 1'b1, 31'h00DF_0001, 15'd1);   seq.push_back(it);
        it = new("g3"); stim_item(it, 1'b0, '0, '0);                 seq.push_back(it);
        it = new("g4"); stim_item(it, 1'b0, '0, '0);                 seq.push_back(it);
        it = new("g5"); stim_item(it, 1'b0, '0, '0);                 seq.push_back(it);
        it = new("s3"); stim_item(it, 1'b1, 31'h1000_0001, 15'd1);   seq.push_back(it);
        pb = m_env.m_scb.m_pass_cnt;
        pf = m_env.m_scb.m_fail_cnt;
        drive_seq(seq);
        if (m_env.m_scb.m_pass_cnt - pb !== 3 || m_env.m_scb.m_fail_cnt !== pf) begin
            `TB_ERROR($sformatf("cal_trans1 自检失败 pass+%0d fail=%0d（期望 pass+3/fail 不变）",
                                m_env.m_scb.m_pass_cnt - pb, m_env.m_scb.m_fail_cnt - pf));
            m_env.m_scb.m_fail_cnt = m_env.m_scb.m_fail_cnt + 1;
        end
        `TB_CASE_END("TC2: cal_trans1", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_PUBIP_MSEQ_CAL_TC_CAL_TRANS1
