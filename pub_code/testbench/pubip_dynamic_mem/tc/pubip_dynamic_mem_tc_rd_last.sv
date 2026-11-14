/*========================================FILE_HEADER=====================================
# Filename: pubip_dynamic_mem_tc_rd_last.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             各ID链尾 o_rd_last 有效 + 单节点链展示保持（rd_vld=0 不消费）
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 rd_last（测试要点 4）：多 ID（3/2/1/1 笔）一次性读出至尾，各链尾 o_rd_last 拉高；
        穿插单节点链展示保持（rd_vld=0 → 下拍重复展示同一数据），模型逐拍核对 last/remain
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_dynamic_mem_tb_pkg.sv"
`ifndef U_PUBIP_DYNAMIC_MEM_TC_RD_LAST
`define U_PUBIP_DYNAMIC_MEM_TC_RD_LAST
import pubip_dynamic_mem_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_dynamic_mem_tc_rd_last ------------
class pubip_dynamic_mem_tc_rd_last extends pubip_dynamic_mem_tc_base;

    function new(string name = "pubip_dynamic_mem_tc_rd_last");
        super.new(name);
    endfunction

    virtual task body();
        pubip_dynamic_mem_item seq[$];
        int i;
        int wr_id;
        logic [31:0] data;
        m_model = new("m_model");
        m_model.reset(mem_depth());
        reset_wait();
        `TB_CASE_BEGIN("TC4: rd_last");
        m_env.m_scb.m_enable = 1'b1;
        // 拍0..6：写 ID0×3 / ID1×2 / ID2×1 / ID3×1（数据 {id,序号} 标志）
        for (i = 0; i < 7; i = i + 1) begin
            wr_id = (i == 3) ? 1 : ((i == 4) ? 1 : ((i == 2) ? 0 : ((i <= 1) ? 0 : ((i == 5) ? 2 : 3))));
            data  = 32'hD0D0_0000 | (wr_id << 20) | (i + 1);
            seq.push_back(mk_cycle(m_model, 1'b1, wr_id, data, 1'b0, 4'd0, 1'b0, $sformatf("wr%0d", i)));
        end
        // 拍7：空闲
        seq.push_back(mk_cycle(m_model, 1'b0, 4'd0, '0, 1'b0, 4'd0, 1'b0, "idle"));
        // 拍8..10：ID0 读到尾（第 3 笔 last=1）
        for (i = 0; i < 3; i = i + 1) begin
            seq.push_back(mk_cycle(m_model, 1'b0, 4'd0, '0, 1'b1, 4'd0, 1'b1, $sformatf("rd0_%0d", i)));
        end
        // 拍11..12：ID1 读到尾（第 2 笔 last=1）
        for (i = 0; i < 2; i = i + 1) begin
            seq.push_back(mk_cycle(m_model, 1'b0, 4'd0, '0, 1'b1, 4'd1, 1'b1, $sformatf("rd1_%0d", i)));
        end
        // 拍13..15：ID2 单节点调度 → 展示保持（拍14 rd_vld=0 不消费，拍15 同数据再次展示后才消费）
        seq.push_back(mk_cycle(m_model, 1'b0, 4'd0, '0, 1'b1, 4'd2, 1'b1, "rd2_a"));
        seq.push_back(mk_cycle(m_model, 1'b0, 4'd0, '0, 1'b1, 4'd2, 1'b0, "rd2_keep"));
        seq.push_back(mk_cycle(m_model, 1'b0, 4'd0, '0, 1'b1, 4'd2, 1'b1, "rd2_b"));
        // 拍16..18：ID3 单节点读到尾（last=1）+ 链空
        seq.push_back(mk_cycle(m_model, 1'b0, 4'd0, '0, 1'b1, 4'd3, 1'b1, "rd3_a"));
        seq.push_back(mk_cycle(m_model, 1'b0, 4'd0, '0, 1'b1, 4'd3, 1'b1, "rd3_b"));
        seq.push_back(mk_cycle(m_model, 1'b0, 4'd0, '0, 1'b1, 4'd3, 1'b1, "rd3_empty"));
        // 收尾：全部链清空、调度回 ID0
        push_tail(seq, 3);
        drive_seq(seq);
        `TB_CASE_END("TC4: rd_last", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_PUBIP_DYNAMIC_MEM_TC_RD_LAST
