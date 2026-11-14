/*========================================FILE_HEADER=====================================
# Filename: pubip_mseq_cal_tc_cal_random.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 cal_random（对应规格书"与参考模型对比测试：随机 i_trans_num 对拍"）：
        连续 300 拍 i_cal_vld=1 满载随机对拍——i_trans_num 随机（≤1023 域为主，
        25% 概率混合段边界/极值点），i_init_seq 随机非零；与设计独立 LFSR 参考模型
        逐拍比对（随机值限定 ≤1023 域避免 32767×300 迭代拖慢仿真，+SEED= 控种子）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_mseq_cal_tb_pkg.sv"
`ifndef U_PUBIP_MSEQ_CAL_TC_CAL_RANDOM
`define U_PUBIP_MSEQ_CAL_TC_CAL_RANDOM
import pubip_mseq_cal_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_mseq_cal_tc_cal_random ------------
class pubip_mseq_cal_tc_cal_random extends pubip_mseq_cal_tc_base;

    function new(string name = "pubip_mseq_cal_tc_cal_random");
        super.new(name);
    endfunction

    virtual task body();
        pubip_mseq_cal_item seq[$];
        pubip_mseq_cal_item it;
        logic [14:0]        edge_tn[9];        // 边界/极值混合集
        logic [30:0]        init_seq;
        int i, pb, pf;
        // 边界集：0/1/2、段 2 边界、段 4 边界、段 3 边界、段 1 边界、全链路极值
        edge_tn = '{15'd0, 15'd1, 15'd2, 15'd32767, 15'd127, 15'd128, 15'd384, 15'd7680, 15'd24576};
        reset_wait();
        `TB_CASE_BEGIN("TC9: cal_random");
        m_env.m_scb.m_enable = 1'b1;
        // 连续 300 拍有效（满载流水 + 独立参考模型逐拍对拍）
        for (i = 0; i < 300; i = i + 1) begin
            it = new($sformatf("rand%0d", i));
            init_seq = $urandom_range(30'h2000_0000) | 31'h0000_0001;   // 随机非零初始序列
            if ($urandom_range(0, 99) < 25) begin
                // 25% 概率取边界/极值集（覆盖段边界与全链路）
                stim_item(it, 1'b1, init_seq, edge_tn[$urandom_range(0, 8)]);
            end
            else begin
                // 75% 概率取 ≤1023 域随机（仿真成本可控，2^0~2^9 级覆盖）
                stim_item(it, 1'b1, init_seq, $urandom_range(0, 1023));
            end
            seq.push_back(it);
        end
        pb = m_env.m_scb.m_pass_cnt;
        pf = m_env.m_scb.m_fail_cnt;
        drive_seq(seq);
        if (m_env.m_scb.m_pass_cnt - pb !== 300 || m_env.m_scb.m_fail_cnt !== pf) begin
            `TB_ERROR($sformatf("cal_random 自检失败 pass+%0d fail=%0d（期望 pass+300/fail 不变）",
                                m_env.m_scb.m_pass_cnt - pb, m_env.m_scb.m_fail_cnt - pf));
            m_env.m_scb.m_fail_cnt = m_env.m_scb.m_fail_cnt + 1;
        end
        `TB_CASE_END("TC9: cal_random", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_PUBIP_MSEQ_CAL_TC_CAL_RANDOM
