/*========================================FILE_HEADER=====================================
# Filename: pubip_dynamic_mem_tc_wr_rd.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             单ID写8笔→FIFO读出（数据/顺序/手握手逐拍核对）
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 wr_rd（测试要点 1）：单 ID 写入 N 笔（N<空闲数）→ FIFO 读出，
        数据/顺序/o_wr_ready/o_rd_ready 手握手逐拍核对；链空后验证 ready=0/remain=0
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_dynamic_mem_tb_pkg.sv"
`ifndef U_PUBIP_DYNAMIC_MEM_TC_WR_RD
`define U_PUBIP_DYNAMIC_MEM_TC_WR_RD
import pubip_dynamic_mem_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_dynamic_mem_tc_wr_rd ------------
class pubip_dynamic_mem_tc_wr_rd extends pubip_dynamic_mem_tc_base;

    function new(string name = "pubip_dynamic_mem_tc_wr_rd");
        super.new(name);
    endfunction

    virtual task body();
        pubip_dynamic_mem_item seq[$];
        int i;
        m_model = new("m_model");
        m_model.reset(mem_depth());
        reset_wait();
        `TB_CASE_BEGIN("TC1: wr_rd");
        m_env.m_scb.m_enable = 1'b1;
        // 拍0..7：连续写 ID0 8 笔（数据高 24bit 带标志，验证 32bit 完整性）
        for (i = 0; i < 8; i = i + 1) begin
            seq.push_back(mk_cycle(m_model, 1'b1, 4'd0, 32'hA5B0_0000 | i[3:0], 1'b0, 4'd0, 1'b0, $sformatf("wr%0d", i)));
        end
        // 拍8：空闲一拍（写后空闲，ready/free_cnt 恢复核对）
        seq.push_back(mk_cycle(m_model, 1'b0, 4'd0, '0, 1'b0, 4'd0, 1'b0, "idle"));
        // 拍9..16：调度 ID0 连续读完（o_rd_ready/o_rd_data/o_rd_last 逐拍核对，FIFO 顺序）
        for (i = 0; i < 8; i = i + 1) begin
            seq.push_back(mk_cycle(m_model, 1'b0, 4'd0, '0, 1'b1, 4'd0, 1'b1, $sformatf("rd%0d", i)));
        end
        // 拍17..18：链空后继续调度（ready=0/remain=0 核对）
        seq.push_back(mk_cycle(m_model, 1'b0, 4'd0, '0, 1'b1, 4'd0, 1'b1, "rd8"));
        seq.push_back(mk_cycle(m_model, 1'b0, 4'd0, '0, 1'b1, 4'd0, 1'b0, "rd9"));
        // 收尾：链条清空、调度回 ID0（reg_schd=0，与模型复位一致）
        push_tail(seq, 3);
        drive_seq(seq);
        `TB_CASE_END("TC1: wr_rd", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_PUBIP_DYNAMIC_MEM_TC_WR_RD
