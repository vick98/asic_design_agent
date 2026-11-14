/*========================================FILE_HEADER=====================================
# Filename: pubip_mseq_cal_tc_base.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             reset_wait / stim_item / drive_seq（5 拍对齐窗口）/ 保持检查 helper
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_mseq_cal 用例基类：等待复位、激励构造、批量驱动序列（含比对窗口管理与
        固定 5 拍延迟的采样对齐）、无效间隙输出保持检查、有效输入计数自检辅助
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_mseq_cal_tb_pkg.sv"
`ifndef U_PUBIP_MSEQ_CAL_TC_BASE
`define U_PUBIP_MSEQ_CAL_TC_BASE
import pubip_mseq_cal_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_mseq_cal_tc_base ------------
class pubip_mseq_cal_tc_base extends tb_test_base;

    pubip_mseq_cal_env                    m_my_env            ;//模块环境（具体类型）
    virtual pubip_mseq_cal_if             m_dut_if            ;//DUT 接口（sim_top 赋值）

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

    //----------- 构造一个激励 item（vld/init_seq/trans_num 三字段） ------------
    function void stim_item(pubip_mseq_cal_item it,
                            bit vld, logic [30:0] init_seq, logic [14:0] trans_num);
        it.m_vld       = vld;
        it.m_init_seq  = init_seq;
        it.m_trans_num = trans_num;
    endfunction

    //----------- 批量驱动序列：一拍一 item（driver 在 negedge 驱动）+ 比对窗口管理 ------------
    // 窗口时序说明（避开 monitor 采样同刻竞态，DUT 固定 5 拍延迟）：
    //   monitor 每 posedge+#mon_skew 采样一拍；用例置位/清位 m_cmp_start 的时刻须错开该采样点。
    //   T0 拍（put 前最后一拍）采样读旧值 watch=0 → 置位推迟 ~0.2ns 后：从下一拍（item0 响应
    //   拍）起 watch=1；期望由 refm 同步入队（vld=1 项），DUT 输出固定延迟 5 拍，vld=0 的采样拍
    //   不消耗期望（scoreboard 按 o_seq_vld 配对），5 拍错位自然吸收。
    //   序列末尾追加 vld=0 静默 item：归还 i_cal_vld=0，防止接口残留有效电平污染后续用例。
    task drive_seq(pubip_mseq_cal_item seq[$]);
        pubip_mseq_cal_item it;
        // 1) 越过 T0 拍 monitor 采样点后置窗口
        #(m_dut_if.mon_skew + 0.1);
        m_my_env.m_mon.m_cmp_start = 1'b1;
        // 2) 逐拍入队激励（driver 在下一 negedge 驱动 item0，DUT 在 posedge 采样）
        foreach (seq[i]) begin
            it = new($sformatf("stim%0d", i));
            it.m_vld       = seq[i].m_vld;
            it.m_init_seq  = seq[i].m_init_seq;
            it.m_trans_num = seq[i].m_trans_num;
            m_my_env.m_drv.m_item_mb.put(it);
        end
        // 3) 追加 vld=0 静默 item：下一拍驱动归还 i_cal_vld=0（DUT 5 拍后 o_seq_vld 回落）
        it = new("stim_idle");
        stim_item(it, 1'b0, '0, '0);
        m_my_env.m_drv.m_item_mb.put(it);
        // 4) 等待 item0..itemN-1 响应拍（S_{N-1} = T0 后 N+4 拍）全部采样完毕
        wait_cycles(seq.size() + 5);
        // 5) 越过最后一个响应拍采样点后关窗（下一拍采样读 watch=0，不产生多余比对）
        #(m_dut_if.mon_skew + 0.1);
        m_my_env.m_mon.m_cmp_start = 1'b0;
        wait_cycles(2);
    endtask

    //----------- 有效输入计数（用例自检辅助） ------------
    function int count_vld(pubip_mseq_cal_item seq[$]);
        foreach (seq[i]) begin
            if (seq[i].m_vld) count_vld = count_vld + 1;
        end
    endfunction

    //----------- 无效间隙输出保持检查：连续 n 拍采样 o_seq_out 相等且 o_seq_vld=0 ------------
    // 验证规格书"en=0 时各段寄存器保持原值不翻转"语义；失败借用 scoreboard 计数器计 fail
    task check_out_hold(int n);
        logic [30:0] held;
        held = m_dut_if.o_seq_out;
        repeat (n) begin
            @(posedge m_dut_if.clk_in);
            #(m_dut_if.mon_skew);
            if (m_dut_if.o_seq_out !== held || m_dut_if.o_seq_vld !== 1'b0) begin
                `TB_ERROR($sformatf("无效间隙输出未保持 held=%0h got=%0h vld=%0b",
                                    held, m_dut_if.o_seq_out, m_dut_if.o_seq_vld));
                m_env.m_scb.m_fail_cnt = m_env.m_scb.m_fail_cnt + 1;
            end
        end
    endtask
endclass
`endif //U_PUBIP_MSEQ_CAL_TC_BASE
