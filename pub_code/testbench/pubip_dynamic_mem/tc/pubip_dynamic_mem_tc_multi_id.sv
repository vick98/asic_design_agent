/*========================================FILE_HEADER=====================================
# Filename: pubip_dynamic_mem_tc_multi_id.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             多ID交叉写入→乱序调度读出（o_schd_id/remain 逐笔核对）
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 multi_id（测试要点 2）：ID0/ID1/ID2 交叉写入各 4/3/3 笔 → 按 2→1→0 乱序调度读出
        各自 FIFO 序列，o_schd_id/o_schd_id_remain 逐笔核对
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_dynamic_mem_tb_pkg.sv"
`ifndef U_PUBIP_DYNAMIC_MEM_TC_MULTI_ID
`define U_PUBIP_DYNAMIC_MEM_TC_MULTI_ID
import pubip_dynamic_mem_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_dynamic_mem_tc_multi_id ------------
class pubip_dynamic_mem_tc_multi_id extends pubip_dynamic_mem_tc_base;

    function new(string name = "pubip_dynamic_mem_tc_multi_id");
        super.new(name);
    endfunction

    //----------- 交叉写入序列：ID0×4 / ID1×3 / ID2×3（先灌后读） ------------
    virtual task body();
        pubip_dynamic_mem_item seq[$];
        int i;
        int wid;
        logic [31:0] data;
        m_model = new("m_model");
        m_model.reset(mem_depth());
        reset_wait();
        `TB_CASE_BEGIN("TC2: multi_id");
        m_env.m_scb.m_enable = 1'b1;
        // 拍0..9：交叉写（0,1,2,0,1,2,0,1,2,0）—— 数据 = {id,4bit序列号} 标志
        for (i = 0; i < 10; i = i + 1) begin
            wid = (i % 3 == 0) ? 0 : ((i % 3 == 1) ? 1 : 2);
            data = 32'hCA0_0000 | (wid << 20) | (i / 3 + 1);
            seq.push_back(mk_cycle(m_model, 1'b1, wid, data, 1'b0, 4'd0, 1'b0, $sformatf("wr%0d", i)));
        end
        // 拍10：空闲
        seq.push_back(mk_cycle(m_model, 1'b0, 4'd0, '0, 1'b0, 4'd0, 1'b0, "idle"));
        // 拍11..14：乱序调度读出 ID2（3 笔数据 + 1 拍空），o_schd_id/remain 逐拍核对
        for (i = 0; i < 4; i = i + 1) begin
            seq.push_back(mk_cycle(m_model, 1'b0, 4'd0, '0, 1'b1, 4'd2, 1'b1, $sformatf("rd2_%0d", i)));
        end
        // 拍15..17：调度 ID1（3 笔数据）
        for (i = 0; i < 3; i = i + 1) begin
            seq.push_back(mk_cycle(m_model, 1'b0, 4'd0, '0, 1'b1, 4'd1, 1'b1, $sformatf("rd1_%0d", i)));
        end
        // 拍18..22：调度 ID0（4 笔数据 + 1 拍空）
        for (i = 0; i < 5; i = i + 1) begin
            seq.push_back(mk_cycle(m_model, 1'b0, 4'd0, '0, 1'b1, 4'd0, 1'b1, $sformatf("rd0_%0d", i)));
        end
        // 收尾：全部链清空、调度回 ID0
        push_tail(seq, 3);
        drive_seq(seq);
        `TB_CASE_END("TC2: multi_id", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_PUBIP_DYNAMIC_MEM_TC_MULTI_ID
