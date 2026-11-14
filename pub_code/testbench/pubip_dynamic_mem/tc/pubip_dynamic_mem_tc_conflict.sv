/*========================================FILE_HEADER=====================================
# Filename: pubip_dynamic_mem_tc_conflict.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             同拍读写冲突（同ID单节点/不同ID双节点+提升；展示保持）
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 conflict（测试要点 5）：同拍读写冲突场景——(a) 单节点链展示同拍写同 ID（冲突覆盖：
        新节点成为新头、读展示仍为旧头数据、随后隔一拍展示新数据）；(b) 双节点链展示同拍写不同
        ID（消费+后继提升+新链并行）；(c) 单节点链展示保持（rd_vld=0 重复展示）。语义以 RTL
        握手约定为准：写/读各自握手独立，读展示数据为 T0 匹配的旧头，新写数据随后续调度读出。
        期望由用例侧行为模型逐拍预置（含冲突覆盖时序）。
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_dynamic_mem_tb_pkg.sv"
`ifndef U_PUBIP_DYNAMIC_MEM_TC_CONFLICT
`define U_PUBIP_DYNAMIC_MEM_TC_CONFLICT
import pubip_dynamic_mem_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_dynamic_mem_tc_conflict ------------
class pubip_dynamic_mem_tc_conflict extends pubip_dynamic_mem_tc_base;

    function new(string name = "pubip_dynamic_mem_tc_conflict");
        super.new(name);
    endfunction

    virtual task body();
        pubip_dynamic_mem_item seq[$];
        m_model = new("m_model");
        m_model.reset(mem_depth());
        reset_wait();
        `TB_CASE_BEGIN("TC5: conflict");
        m_env.m_scb.m_enable = 1'b1;
        //----------- (a) 单节点链同拍写扩展（冲突覆盖） ------------
        seq.push_back(mk_cycle(m_model, 1'b1, 4'd0, 32'hCF00_0001, 1'b0, 4'd0, 1'b0, "c0"));//写 ID0:A
        seq.push_back(mk_cycle(m_model, 1'b0, 4'd0, '0, 1'b1, 4'd0, 1'b0, "c1"));              //调度0：A 将展示
        seq.push_back(mk_cycle(m_model, 1'b1, 4'd0, 32'hCF00_0002, 1'b1, 4'd0, 1'b1, "c2"));//消费 A + 写 ID0:B（冲突覆盖）
        seq.push_back(mk_cycle(m_model, 1'b0, 4'd0, '0, 1'b1, 4'd0, 1'b1, "c3"));            //隔拍：B 展示（新头）
        seq.push_back(mk_cycle(m_model, 1'b0, 4'd0, '0, 1'b1, 4'd0, 1'b1, "c4"));            //消费 B（链空）
        //----------- (b) 写不同 ID 同拍展开 / 双节点消费+提升 ------------
        seq.push_back(mk_cycle(m_model, 1'b1, 4'd1, 32'hCF00_0013, 1'b1, 4'd1, 1'b1, "c5"));//写 ID1:C + 调度1
        seq.push_back(mk_cycle(m_model, 1'b0, 4'd0, '0, 1'b1, 4'd1, 1'b1, "c6"));            //C 展示（last）
        seq.push_back(mk_cycle(m_model, 1'b0, 4'd0, '0, 1'b1, 4'd1, 1'b1, "c7"));            //C 已消费（链空）
        seq.push_back(mk_cycle(m_model, 1'b1, 4'd0, 32'hCF00_0004, 1'b1, 4'd0, 1'b1, "c8"));//写 ID0:D + 调度0
        seq.push_back(mk_cycle(m_model, 1'b1, 4'd0, 32'hCF00_0005, 1'b1, 4'd0, 1'b1, "c9"));//写 ID0:E（追加）+ 调度0
        seq.push_back(mk_cycle(m_model, 1'b1, 4'd3, 32'hCF00_0036, 1'b1, 4'd0, 1'b1, "c10"));//消费 D + 写 ID3:F（不同ID）+ 后继 E 提升
        seq.push_back(mk_cycle(m_model, 1'b0, 4'd0, '0, 1'b1, 4'd3, 1'b1, "c11"));           //E 展示（ID0 尾）
        seq.push_back(mk_cycle(m_model, 1'b0, 4'd0, '0, 1'b1, 4'd3, 1'b1, "c12"));           //F 展示（ID3 尾）
        seq.push_back(mk_cycle(m_model, 1'b0, 4'd0, '0, 1'b1, 4'd3, 1'b1, "c13"));           //全部链空
        // 收尾：链条清空、调度回 ID0
        push_tail(seq, 3);
        drive_seq(seq);
        `TB_CASE_END("TC5: conflict", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_PUBIP_DYNAMIC_MEM_TC_CONFLICT
