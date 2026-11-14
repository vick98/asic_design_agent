/*========================================FILE_HEADER=====================================
# Filename: pubip_mseq_gen_tc_mseq_trans_n.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 mseq_trans_n（测试要点 2，变体宏 PUBIP_MPG_TRANS4）：TRANS_NUM=4 多步跨步对拍。
        refm 独立 LFSR 参考模型迭代 4 次计算期望；旁路（i_cal_en=0）仍输出 i_init_seq。
        使用方式：编译加 +define+PUBIP_MPG_TRANS4 后 +TC=tc_mseq_trans_n（工厂注册宏隔离）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_mseq_gen_tb_pkg.sv"
`ifndef U_PUBIP_MSEQ_GEN_TC_MSEQ_TRANS_N
`define U_PUBIP_MSEQ_GEN_TC_MSEQ_TRANS_N
import pubip_mseq_gen_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_mseq_gen_tc_mseq_trans_n ------------
class pubip_mseq_gen_tc_mseq_trans_n extends pubip_mseq_gen_tc_base;

    function new(string name = "pubip_mseq_gen_tc_mseq_trans_n");
        super.new(name);
    endfunction

    virtual task body();
        pubip_mseq_gen_item seq[$];
        logic [`PUBIP_MPG_SEQ_WIDTH - 1 : 0] rnd;
        int i;
        reset_wait();
        `TB_CASE_BEGIN("TC2: mseq_trans_n");
        m_env.m_scb.m_enable = 1'b1;
        // 定向校验（4 步转移链 + 旁路）：
        push_stim(seq, 4'h1, 1'b1);   // 0001 ->(4步) 0001->1000->0100->0010->1001
        push_stim(seq, 4'h7, 1'b1);   // 0111 ->(4步) 0011->0001->1000->0100
        push_stim(seq, 4'hF, 1'b1);   // 1111 ->(4步) 0111->0011->0001->1000
        push_stim(seq, 4'hA, 1'b0);   // 旁路：输出 = 1010
        push_stim(seq, 4'h0, 1'b1);   // 全零态保持 0（非法态检查）
        // 随机初始值 4 步跨步（i%5==0 拍旁路，其余 cal_en=1）
        for (i = 0; i < 20; i = i + 1) begin
            rnd = $urandom_range(0, (1 << `PUBIP_MPG_SEQ_WIDTH) - 1);
            push_stim(seq, rnd, (i % 5 == 0) ? 1'b0 : 1'b1);
        end
        drive_seq(seq);
        `TB_CASE_END("TC2: mseq_trans_n", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_PUBIP_MSEQ_GEN_TC_MSEQ_TRANS_N
