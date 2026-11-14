/*========================================FILE_HEADER=====================================
# Filename: pubip_dynamic_mem_tc_random.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             500 拍随机写/读/调度对拍（+SEED= 播种，行为模型逐拍校对）
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 random（测试要点 7）：随机写/读/调度 500 拍（$urandom_range，播种 +SEED= 由 sim_top
        统一处理），用例侧行为模型逐拍对拍；尾随 3 拍空闲清零管道
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_dynamic_mem_tb_pkg.sv"
`ifndef U_PUBIP_DYNAMIC_MEM_TC_RANDOM
`define U_PUBIP_DYNAMIC_MEM_TC_RANDOM
import pubip_dynamic_mem_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_dynamic_mem_tc_random ------------
class pubip_dynamic_mem_tc_random extends pubip_dynamic_mem_tc_base;

    function new(string name = "pubip_dynamic_mem_tc_random");
        super.new(name);
    endfunction

    virtual task body();
        pubip_dynamic_mem_item seq[$];
        int c;
        bit wv;
        bit rv;
        bit dv;
        int wid;
        int rid;
        m_model = new("m_model");
        m_model.reset(mem_depth());
        reset_wait();
        `TB_CASE_BEGIN("TC7: random");
        m_env.m_scb.m_enable = 1'b1;
        // 500 拍随机激励：写 60% / 调度 40% / 后级读 40%（可命中满链/空链/冲突场景）
        for (c = 0; c < 500; c = c + 1) begin
            wv  = ($urandom_range(0, 99) < 60);
            rv  = ($urandom_range(0, 99) < 40);
            dv  = ($urandom_range(0, 99) < 40);
            wid = $urandom_range(0, 15);
            rid = $urandom_range(0, 15);
            seq.push_back(mk_cycle(m_model, wv, wid, $urandom, rv, rid, dv, $sformatf("rnd%0d", c)));
        end
        // 收尾：管道清空、调度回 ID0
        push_tail(seq, 3);
        drive_seq(seq);
        `TB_CASE_END("TC7: random", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_PUBIP_DYNAMIC_MEM_TC_RANDOM
