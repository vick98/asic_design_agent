/*========================================FILE_HEADER=====================================
# Filename: pubip_dynamic_mem_tc_remain.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             32笔写入+读ID0与追加ID1并发（同拍读写）+剩余计数随动核对
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 remain（测试要点 6）：o_free_cnt/o_schd_id_remain 随写入/读出动态变化逐拍核对
        （P0-7 附带：remain 不漏计）——16 笔 ID0 + 16 笔 ID1 → 读 ID0 时长尾穿插 8 笔 ID1 追加
        （同拍读写不同 ID）→ 读 ID1 24 笔，全部计数按拍核对
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_dynamic_mem_tb_pkg.sv"
`ifndef U_PUBIP_DYNAMIC_MEM_TC_REMAIN
`define U_PUBIP_DYNAMIC_MEM_TC_REMAIN
import pubip_dynamic_mem_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_dynamic_mem_tc_remain ------------
class pubip_dynamic_mem_tc_remain extends pubip_dynamic_mem_tc_base;

    function new(string name = "pubip_dynamic_mem_tc_remain");
        super.new(name);
    endfunction

    virtual task body();
        pubip_dynamic_mem_item seq[$];
        int i;
        bit wr;
        logic [31:0] data;
        m_model = new("m_model");
        m_model.reset(mem_depth());
        reset_wait();
        `TB_CASE_BEGIN("TC6: remain");
        m_env.m_scb.m_enable = 1'b1;
        // 拍0..15：写 ID0 16 笔
        for (i = 0; i < 16; i = i + 1) begin
            seq.push_back(mk_cycle(m_model, 1'b1, 4'd0, 32'h1100_0000 | i[3:0], 1'b0, 4'd0, 1'b0, $sformatf("wr0_%0d", i)));
        end
        // 拍16..31：写 ID1 16 笔
        for (i = 0; i < 16; i = i + 1) begin
            seq.push_back(mk_cycle(m_model, 1'b1, 4'd1, 32'h2200_0000 | i[3:0], 1'b0, 4'd0, 1'b0, $sformatf("wr1_%0d", i)));
        end
        // 拍32：空闲
        seq.push_back(mk_cycle(m_model, 1'b0, 4'd0, '0, 1'b0, 4'd0, 1'b0, "idle"));
        // 拍33..48：读 ID0 16 笔，其中第 4..11 拍同拍追加 ID1 8 笔（同拍读写不同 ID，free/remain 随动）
        for (i = 0; i < 16; i = i + 1) begin
            wr   = (i >= 4) && (i < 12);
            data = wr ? 32'h22A0_0000 | (i - 4) : '0;
            seq.push_back(mk_cycle(m_model, wr, 4'd1, data, 1'b1, 4'd0, 1'b1, $sformatf("rd0_%0d", i)));
        end
        // 拍49：ID0 链空
        seq.push_back(mk_cycle(m_model, 1'b0, 4'd0, '0, 1'b1, 4'd0, 1'b0, "rd0_empty"));
        // 拍50..73：读 ID1 24 笔（16+8 追加）
        for (i = 0; i < 24; i = i + 1) begin
            seq.push_back(mk_cycle(m_model, 1'b0, 4'd0, '0, 1'b1, 4'd1, 1'b1, $sformatf("rd1_%0d", i)));
        end
        // 拍74..75：ID1 链空（remain=0/ready=0）
        seq.push_back(mk_cycle(m_model, 1'b0, 4'd0, '0, 1'b1, 4'd1, 1'b1, "rd1_empty"));
        seq.push_back(mk_cycle(m_model, 1'b0, 4'd0, '0, 1'b1, 4'd1, 1'b0, "rd1_idle"));
        // 收尾：链条清空、调度回 ID0
        push_tail(seq, 3);
        drive_seq(seq);
        `TB_CASE_END("TC6: remain", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_PUBIP_DYNAMIC_MEM_TC_REMAIN
