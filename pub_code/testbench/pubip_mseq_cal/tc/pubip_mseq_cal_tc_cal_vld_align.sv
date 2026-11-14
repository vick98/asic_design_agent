/*========================================FILE_HEADER=====================================
# Filename: pubip_mseq_cal_tc_cal_vld_align.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 cal_vld_align（对应规格书"流水线功能测试：i_cal_vld 间隔拉高/断续脉冲"）：
        i_cal_vld 断续脉冲（长短间隙混合 + 局部连续拍），验证 o_seq_vld 相对 i_cal_vld
        恒 5 拍对齐（scoreboard 按 vld 消耗期望逐拍核对输拍），并检查间隙拍 o_seq_out
        保持不翻转、o_seq_vld=0
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_mseq_cal_tb_pkg.sv"
`ifndef U_PUBIP_MSEQ_CAL_TC_CAL_VLD_ALIGN
`define U_PUBIP_MSEQ_CAL_TC_CAL_VLD_ALIGN
import pubip_mseq_cal_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_mseq_cal_tc_cal_vld_align ------------
class pubip_mseq_cal_tc_cal_vld_align extends pubip_mseq_cal_tc_base;

    function new(string name = "pubip_mseq_cal_tc_cal_vld_align");
        super.new(name);
    endfunction

    virtual task body();
        pubip_mseq_cal_item seq[$];
        pubip_mseq_cal_item it;
        int pb, pf, exp_vld;
        int i;
        int valid_at[6];                        // 有效拍位置（其余为间隙）
        logic [30:0] init_seq[6];               // 每有效拍初始序列
        logic [14:0] trans_num[6];              // 每有效拍转移次数
        // 断续 vld 模式：单拍脉冲 + 短间隙 + 长间隙 + 局部连续 3 拍 + 尾隙
        valid_at  = '{0, 3, 8, 9, 10, 13};
        init_seq  = '{31'h1000_0001, 31'h07FF_1235, 31'h2000_0003,
                      31'h1555_5555, 31'h2AAA_AAAA, 31'h00DF_0001};
        trans_num = '{15'd7, 15'd15, 15'd16, 15'd1023, 15'd1, 15'd0};
        reset_wait();
        `TB_CASE_BEGIN("TC7: cal_vld_align");
        m_env.m_scb.m_enable = 1'b1;
        // 17 拍：0/3/8-10/13 有效，其余为间隙（14-16 尾隙用于输出保持检查）
        for (i = 0; i < 17; i = i + 1) begin
            it = new($sformatf("st%0d", i));
            stim_item(it, 1'b0, '0, '0);
            foreach (valid_at[j]) begin
                if (i == valid_at[j]) begin
                    stim_item(it, 1'b1, init_seq[j], trans_num[j]);
                end
            end
            seq.push_back(it);
        end
        exp_vld = count_vld(seq);   // 期望有效输出个数（= 有效输入拍数）
        pb = m_env.m_scb.m_pass_cnt;
        pf = m_env.m_scb.m_fail_cnt;
        drive_seq(seq);
        // 自检：有效输出比对个数 == 有效输入个数（5 拍对齐 + 每拍一一对应）
        if (m_env.m_scb.m_pass_cnt - pb !== exp_vld || m_env.m_scb.m_fail_cnt !== pf) begin
            `TB_ERROR($sformatf("cal_vld_align 自检失败 pass+%0d fail=%0d（期望 pass+%0d/fail 不变）",
                                m_env.m_scb.m_pass_cnt - pb, m_env.m_scb.m_fail_cnt - pf, exp_vld));
            m_env.m_scb.m_fail_cnt = m_env.m_scb.m_fail_cnt + 1;
        end
        // 尾隙输出保持检查：排空后 o_seq_out 保持最后一次响应值且 o_seq_vld=0
        check_out_hold(2);
        `TB_CASE_END("TC7: cal_vld_align", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_PUBIP_MSEQ_CAL_TC_CAL_VLD_ALIGN
