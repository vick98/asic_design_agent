/*========================================FILE_HEADER=====================================
# Filename: pubip_dynamic_mem_tc_base.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             reset_wait/wait_cycles/mk_cycle（行为模型逐拍期望）/drive_seq
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_dynamic_mem 用例基类：等待复位释放、逐拍序列驱动（一拍一 item，期望由用例侧
        行为模型 pubip_dynamic_mem_model 逐拍预置，refm 纯函数透传）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_dynamic_mem_tb_pkg.sv"
`ifndef U_PUBIP_DYNAMIC_MEM_TC_BASE
`define U_PUBIP_DYNAMIC_MEM_TC_BASE
import pubip_dynamic_mem_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_dynamic_mem_tc_base ------------
class pubip_dynamic_mem_tc_base extends tb_test_base;

    pubip_dynamic_mem_env                    m_my_env            ;//模块环境（具体类型）
    virtual pubip_dynamic_mem_if             m_dut_if            ;//DUT 接口（sim_top 赋值）
    pubip_dynamic_mem_model                  m_model             ;//行为参考模型（用例侧，逐拍期望预置）

    function new(string name = "tc");
        super.new(name);
    endfunction

    //----------- 构建环境：创建 env 并下发接口 ------------
    virtual function void build_env();
        m_my_env = new("m_env");
        m_my_env.m_rst_if = m_rst_if;
        m_my_env.m_dut_if = m_dut_if;
        m_env     = m_my_env;
    endfunction

    //----------- 当前 DUT 深度（与 sim_top 例化参数保持一致） ------------
    function int mem_depth();
`ifdef PUBIP_DMEM_SMALL
        mem_depth = 16;
`else
        mem_depth = 64;
`endif
    endfunction

    //----------- 等待 n 个时钟周期（沿后采样轮询，统一采样时刻） ------------
    task wait_cycles(int n);
        repeat (n) begin
            @(posedge m_dut_if.clk_in);
            #(m_dut_if.mon_skew);
        end
    endtask

    //----------- 等待复位释放 ------------
    task reset_wait();
        do begin
            @(posedge m_rst_if.clk_in);
        end while (m_rst_if.rst_n !== 1'b1);
        wait_cycles(1);
    endtask

    //----------- 生成一拍 item：行为模型 step 计算该拍激励对应的下一采样拍期望值 ------------
    // 输入 = 本拍将要驱动的 6 项激励（首参为行为模型实例，与全部调用点 mk_cycle(m_model, ...) 对齐）；
    // 模型依据内部链表/展示流水状态推进并回填 7 项期望
    function pubip_dynamic_mem_item mk_cycle(pubip_dynamic_mem_model mdl, bit wr_vld, int wr_id,
                                             logic [31:0] wr_data,
                                             bit rd_id_vld, int rd_id, bit rd_vld, string tag);
        pubip_dynamic_mem_item it;
        it = new(tag);
        it.m_wr_vld    = wr_vld     ;
        it.m_wr_id     = wr_id[3:0] ;
        it.m_wr_data   = wr_data    ;
        it.m_rd_id_vld = rd_id_vld  ;
        it.m_rd_id     = rd_id[3:0] ;
        it.m_rd_vld    = rd_vld     ;
        mdl.step(it.m_wr_vld, it.m_wr_id, it.m_wr_data,
                 it.m_rd_id_vld, it.m_rd_id, it.m_rd_vld,
                 it.m_exp_wr_ready, it.m_exp_rd_ready, it.m_exp_rd_data, it.m_exp_rd_last,
                 it.m_exp_schd_id, it.m_exp_remain, it.m_exp_free_cnt);
        return it;
    endfunction

    //----------- 逐拍驱动序列：一拍一个 item（driver 在 negedge 驱动），比对窗口随之开关 ------------
    // 窗口时序说明（避开 monitor 采样同刻竞态）：
    //   monitor 每个 posedge+#mon_skew 采样一拍；用例置位/清位 m_cmp_start 的时刻须错开该采样点。
    //   T0 拍（put 前最后一拍）采样读旧值 watch=0 → 置位推迟 ~0.2ns 后：从下一拍（item0 响应拍）起
    //   watch=1，共 seq.size() 拍与期望项 1:1 配对；清位同样错开 S_{N-1} 拍采样点，下一拍采样读 watch=0
    task drive_seq(pubip_dynamic_mem_item seq[$]);
        pubip_dynamic_mem_item it;
        // 1) 越过 T0 拍 monitor 采样点后置窗口
        #(m_dut_if.mon_skew + 0.1);
        m_my_env.m_mon.m_cmp_start = 1'b1;
        // 2) 逐拍入队激励（driver 在下一 negedge 驱动 item0，DUT 在 posedge 响应）
        foreach (seq[i]) begin
            it = new($sformatf("stim%0d", i));
            it.m_wr_vld     = seq[i].m_wr_vld    ;
            it.m_wr_id      = seq[i].m_wr_id     ;
            it.m_wr_data    = seq[i].m_wr_data   ;
            it.m_rd_id_vld  = seq[i].m_rd_id_vld ;
            it.m_rd_id      = seq[i].m_rd_id     ;
            it.m_rd_vld     = seq[i].m_rd_vld    ;
            it.m_exp_wr_ready = seq[i].m_exp_wr_ready ;
            it.m_exp_rd_ready = seq[i].m_exp_rd_ready ;
            it.m_exp_rd_data  = seq[i].m_exp_rd_data  ;
            it.m_exp_rd_last  = seq[i].m_exp_rd_last  ;
            it.m_exp_schd_id  = seq[i].m_exp_schd_id  ;
            it.m_exp_remain   = seq[i].m_exp_remain   ;
            it.m_exp_free_cnt = seq[i].m_exp_free_cnt ;
            m_my_env.m_drv.m_item_mb.put(it);
        end
        // 3) 等待 item0..itemN-1 响应拍（S_0..S_{N-1}）全部采样完毕
        wait_cycles(seq.size());
        // 4) 越过 S_{N-1} 拍采样点后关窗（下一拍采样读 watch=0，不产生多余比对）
        #(m_dut_if.mon_skew + 0.1);
        m_my_env.m_mon.m_cmp_start = 1'b0;
        wait_cycles(2);
    endtask

    //----------- 通用零收尾序列：链清空后继续空闲若干拍（DUT 回到"全空闲"基准态，供 tc_all 串联） ------------
    // 首拍显式调度回 ID0：锁存 DUT reg_schd_id=0（模型 m_last_schd_id 同步）——用例最后一拍可能
    // 调度到非 0 ID（如 tc_rd_last 尾段调度 ID3、tc_conflict 尾段调度 ID3、tc_remain 尾段调度 ID1），
    // 不锁回则下一用例模型复位态（reg_schd=0）与 DUT 残留值错位，o_schd_id/remain 逐拍错位（tc_all 实测）。
    function void push_tail(ref pubip_dynamic_mem_item seq[$], input int n);
        int i;
        // ref 序列：SV 中 $ 队列作子程序参数默认按值拷贝，无 ref 时 push_back 只改局部拷贝、
        // 调用者队列不变（实测 drive_seq seq.size 少 3，收尾拍从未驱动——tc_all 串联残留 reg_schd 根因）
        seq.push_back(mk_cycle(m_model, 1'b0, 4'd0, '0, 1'b1, 4'd0, 1'b0, "tail_lock"));
        for (i = 1; i < n; i = i + 1) begin
            seq.push_back(mk_cycle(m_model, 1'b0, 4'd0, '0, 1'b0, 4'd0, 1'b0, $sformatf("tail%0d", i)));
        end
    endfunction
endclass
`endif //U_PUBIP_DYNAMIC_MEM_TC_BASE
