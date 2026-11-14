/*========================================FILE_HEADER=====================================
# Filename: pubip_round_tc_random.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-10-06        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 random：随机扫描（+SEED=<n> 播种，见 sim_top）
        激励分两档，各占一半：
          a) 全位宽随机（覆盖大范围值域与随机饱和）
          b) 饱和/半值邻域随机（低 log2(2^N) 位随机 + 高位取 ±2^(W_dst-1) 附近），
             把采样重心压在舍入边界与饱和界上——33/24 bit 变体靠这一档补覆盖
        期望全部由 refm.compute() 按值语义公式回填
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "pubip_round_tb_pkg.sv"
`ifndef U_PUBIP_ROUND_TC_RANDOM
`define U_PUBIP_ROUND_TC_RANDOM
import pubip_round_tb_pkg::*;
import tb_pkg::*;

//----------- pubip_round_tc_random ------------
class pubip_round_tc_random extends pubip_round_tc_base;

    localparam int RAND_NUM = 2000;//随机拍数

    function new(string name = "pubip_round_tc_random");
        super.new(name);
    endfunction

    virtual task body();
        pubip_round_item seq[$];
        longint rnd;
        longint out_unit;
        longint base;
        int     i;
        reset_wait();
        `TB_CASE_BEGIN("TC7: random 随机扫描");
        m_env.m_scb.m_enable = 1'b1;
        out_unit = 64'sd1 <<< `PUBIP_ROUND_SHIFT;//1 个输出整数单位（源 LSB 计）
        for (i = 0; i < RAND_NUM; i = i + 1) begin
            rnd = {$urandom(), $urandom()};//64 位随机
            if (i % 2 == 0) begin
                //a) 全位宽随机
                push_value(seq, rnd);
            end
            else begin
                //b) 饱和/半值邻域：以 ±2^(W_dst-1) 个输出整数单位为中心，加随机小偏移
                base = (rnd % (2 * (64'sd1 <<< (`PUBIP_ROUND_OUT_TOTAL - 1)) + 1)
                        - (64'sd1 <<< (`PUBIP_ROUND_OUT_TOTAL - 1))) * out_unit;
                push_value(seq, base + ($urandom_range(0, 2 * (1 << `PUBIP_ROUND_SHIFT) + 1) - (1 << `PUBIP_ROUND_SHIFT)));
            end
        end
        drive_seq(seq);
        `TB_CASE_END("TC7: random 随机扫描", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_PUBIP_ROUND_TC_RANDOM
