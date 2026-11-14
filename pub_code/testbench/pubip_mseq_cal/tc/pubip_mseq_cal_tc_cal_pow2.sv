/*========================================FILE_HEADER=====================================
# Filename: pubip_mseq_cal_tc_cal_pow2.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 cal_pow2（对应规格书"基础功能测试：i_trans_num 单 bit 场景"）：
        单 bit 代表值 1/2/32/1024/16384（2^0/2^1/2^5/2^10/2^14），逐一验证对应级
        mseq_gen 独立正确（各级 TRANS_NUM 与 i_cal_en 命中链路）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_mseq_cal_tb_pkg.sv"
`ifndef U_PUBIP_MSEQ_CAL_TC_CAL_POW2
`define U_PUBIP_MSEQ_CAL_TC_CAL_POW2
import pubip_mseq_cal_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_mseq_cal_tc_cal_pow2 ------------
class pubip_mseq_cal_tc_cal_pow2 extends pubip_mseq_cal_tc_base;

    function new(string name = "pubip_mseq_cal_tc_cal_pow2");
        super.new(name);
    endfunction

    virtual task body();
        pubip_mseq_cal_item seq[$];
        pubip_mseq_cal_item it;
        logic [14:0]        tn[5];        // 单 bit 代表：2^0/2^1/2^5/2^10/2^14
        logic [30:0]        init[5];
        int i, pb, pf;
        tn   = '{15'd1, 15'd2, 15'd32, 15'd1024, 15'd16384};
        init = '{31'h1234_5678, 31'h7654_3210, 31'h0FFF_FFFF, 31'h1555_5555, 31'h3AAA_AAAA};
        reset_wait();
        `TB_CASE_BEGIN("TC3: cal_pow2");
        m_env.m_scb.m_enable = 1'b1;
        // 5 个单 bit 代表逐个调用（调用间 2 拍无效间隙）
        for (i = 0; i < 5; i = i + 1) begin
            it = new($sformatf("s%0d", i));
            stim_item(it, 1'b1, init[i], tn[i]);
            seq.push_back(it);
            it = new($sformatf("g%0d", i));
            stim_item(it, 1'b0, '0, '0);
            seq.push_back(it);
            it = new($sformatf("h%0d", i));
            stim_item(it, 1'b0, '0, '0);
            seq.push_back(it);
        end
        pb = m_env.m_scb.m_pass_cnt;
        pf = m_env.m_scb.m_fail_cnt;
        drive_seq(seq);
        if (m_env.m_scb.m_pass_cnt - pb !== 5 || m_env.m_scb.m_fail_cnt !== pf) begin
            `TB_ERROR($sformatf("cal_pow2 自检失败 pass+%0d fail=%0d（期望 pass+5/fail 不变）",
                                m_env.m_scb.m_pass_cnt - pb, m_env.m_scb.m_fail_cnt - pf));
            m_env.m_scb.m_fail_cnt = m_env.m_scb.m_fail_cnt + 1;
        end
        `TB_CASE_END("TC3: cal_pow2", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_PUBIP_MSEQ_CAL_TC_CAL_POW2
