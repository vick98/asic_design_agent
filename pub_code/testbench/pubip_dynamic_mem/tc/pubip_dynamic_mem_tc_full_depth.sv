/*========================================FILE_HEADER=====================================
# Filename: pubip_dynamic_mem_tc_full_depth.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             P0-7 验收：64 笔写满（地址 63 可用）→ 全读出；满时 wr_ready 拉低
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 full_depth（测试要点 3，P0-7 验收）：写入至 64 笔（first-fit 覆盖地址 0..63）→
        第 64 笔(地址 63)数据完整入链且可读出；满时 o_wr_ready 拉低（拒绝后续写入）；o_free_cnt
        统计与 0..63 覆盖语义逐拍核对（默认 MEM_DEPTH=64 主验证；PUBIP_DMEM_SMALL 下对应 16 笔）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_dynamic_mem_tb_pkg.sv"
`ifndef U_PUBIP_DYNAMIC_MEM_TC_FULL_DEPTH
`define U_PUBIP_DYNAMIC_MEM_TC_FULL_DEPTH
import pubip_dynamic_mem_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_dynamic_mem_tc_full_depth ------------
class pubip_dynamic_mem_tc_full_depth extends pubip_dynamic_mem_tc_base;

    function new(string name = "pubip_dynamic_mem_tc_full_depth");
        super.new(name);
    endfunction

    virtual task body();
        pubip_dynamic_mem_item seq[$];
        int i;
        int n;
        m_model = new("m_model");
        m_model.reset(mem_depth());
        reset_wait();
        `TB_CASE_BEGIN("TC3: full_depth");
        m_env.m_scb.m_enable = 1'b1;
        n = mem_depth();
        // 拍0..n-1：单 ID (ID0) 连续写满（first-fit 覆盖地址 0..n-1），o_wr_ready/o_free_cnt 逐拍核对
        for (i = 0; i < n; i = i + 1) begin
            seq.push_back(mk_cycle(m_model, 1'b1, 4'd0, 32'hB070_0000 | i, 1'b0, 4'd0, 1'b0, $sformatf("wr%0d", i)));
        end
        // 拍n：已满后置写请求（o_wr_ready 应再为 0，写被拒绝 → 不占空间）
        seq.push_back(mk_cycle(m_model, 1'b1, 4'd0, 32'hDEAD_0000, 1'b0, 4'd0, 1'b0, "wr_full_rep"));
        // 拍n+1..n+n：调度 ID0 全部读出（第 n 笔 = 地址 n-1 数据完整；队列尾 last=1）
        for (i = 0; i < n; i = i + 1) begin
            seq.push_back(mk_cycle(m_model, 1'b0, 4'd0, '0, 1'b1, 4'd0, 1'b1, $sformatf("rd%0d", i)));
        end
        // 拍2n+1..2n+2：链空后继续调度（ready=0/remain=0），恢复空闲
        seq.push_back(mk_cycle(m_model, 1'b0, 4'd0, '0, 1'b1, 4'd0, 1'b1, "rd_empty"));
        seq.push_back(mk_cycle(m_model, 1'b0, 4'd0, '0, 1'b1, 4'd0, 1'b0, "rd_idle"));
        // 收尾：链条清空、调度回 ID0
        push_tail(seq, 3);
        drive_seq(seq);
        `TB_CASE_END("TC3: full_depth", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_PUBIP_DYNAMIC_MEM_TC_FULL_DEPTH
