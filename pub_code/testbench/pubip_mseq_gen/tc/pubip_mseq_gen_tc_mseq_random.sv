/*========================================FILE_HEADER=====================================
# Filename: pubip_mseq_gen_tc_mseq_random.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 mseq_random（测试要点 4）：随机初始化种子/使能 300 拍对拍
        （$urandom_range 全值域种子 + 随机 i_cal_en），期望由 refm.compute() 参考模型自算；
        播种由 sim_top 按 +SEED=<n> 统一处理，用例内不调用 $srandom
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_mseq_gen_tb_pkg.sv"
`ifndef U_PUBIP_MSEQ_GEN_TC_MSEQ_RANDOM
`define U_PUBIP_MSEQ_GEN_TC_MSEQ_RANDOM
import pubip_mseq_gen_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_mseq_gen_tc_mseq_random ------------
class pubip_mseq_gen_tc_mseq_random extends pubip_mseq_gen_tc_base;

    function new(string name = "pubip_mseq_gen_tc_mseq_random");
        super.new(name);
    endfunction

    virtual task body();
        pubip_mseq_gen_item seq[$];
        int i;
        logic [`PUBIP_MPG_SEQ_WIDTH - 1 : 0] rnd;
        reset_wait();
        `TB_CASE_BEGIN("TC4: mseq_random");
        m_env.m_scb.m_enable = 1'b1;
        // 300 拍随机种子/使能（一拍一 item，随机化用 $urandom_range）
        for (i = 0; i < 300; i = i + 1) begin
            rnd = $urandom_range(0, (1 << `PUBIP_MPG_SEQ_WIDTH) - 1);
            push_stim(seq, rnd, $urandom_range(0, 1));
        end
        drive_seq(seq);
        `TB_CASE_END("TC4: mseq_random", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_PUBIP_MSEQ_GEN_TC_MSEQ_RANDOM
