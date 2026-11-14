/*========================================FILE_HEADER=====================================
# Filename: pubip_mseq_cal_tc_cal_multi_call.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 cal_multi_call（对应规格书"流水线功能测试：连续多拍 i_cal_vld=1"）：
        连续 8 拍 i_cal_vld=1、每拍 i_trans_num 不同（背靠背流水满载），逐次核对
        每次输出与对应输入一一对应（流水乱序无干扰、溢出/小值/段边界值混合）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_mseq_cal_tb_pkg.sv"
`ifndef U_PUBIP_MSEQ_CAL_TC_CAL_MULTI_CALL
`define U_PUBIP_MSEQ_CAL_TC_CAL_MULTI_CALL
import pubip_mseq_cal_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_mseq_cal_tc_cal_multi_call ------------
class pubip_mseq_cal_tc_cal_multi_call extends pubip_mseq_cal_tc_base;

    function new(string name = "pubip_mseq_cal_tc_cal_multi_call");
        super.new(name);
    endfunction

    virtual task body();
        pubip_mseq_cal_item seq[$];
        pubip_mseq_cal_item it;
        logic [14:0]        tn[8];
        logic [30:0]        init[8];
        int i, pb, pf;
        // 连续 8 拍不同转移次数：小值/段内/段边界/全链路混合
        tn   = '{15'd3, 15'd5, 15'd100, 15'd1023, 15'h6000, 15'd4095, 15'd7, 15'd32767};
        init = '{31'h1234_5678, 31'h5555_5555, 31'h7654_3210, 31'h1000_0001,
                 31'h0FFF_FFFF, 31'h2AAA_AAAA, 31'h00DF_0001, 31'h3000_0003};
        reset_wait();
        `TB_CASE_BEGIN("TC8: cal_multi_call");
        m_env.m_scb.m_enable = 1'b1;
        // 背靠背连续 8 拍有效（无间隙的流水满载）
        for (i = 0; i < 8; i = i + 1) begin
            it = new($sformatf("call%0d", i));
            stim_item(it, 1'b1, init[i], tn[i]);
            seq.push_back(it);
        end
        pb = m_env.m_scb.m_pass_cnt;
        pf = m_env.m_scb.m_fail_cnt;
        drive_seq(seq);
        if (m_env.m_scb.m_pass_cnt - pb !== 8 || m_env.m_scb.m_fail_cnt !== pf) begin
            `TB_ERROR($sformatf("cal_multi_call 自检失败 pass+%0d fail=%0d（期望 pass+8/fail 不变）",
                                m_env.m_scb.m_pass_cnt - pb, m_env.m_scb.m_fail_cnt - pf));
            m_env.m_scb.m_fail_cnt = m_env.m_scb.m_fail_cnt + 1;
        end
        `TB_CASE_END("TC8: cal_multi_call", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_PUBIP_MSEQ_CAL_TC_CAL_MULTI_CALL
