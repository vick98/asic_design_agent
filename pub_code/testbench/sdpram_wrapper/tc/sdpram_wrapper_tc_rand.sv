/*========================================FILE_HEADER=====================================
# Filename: sdpram_wrapper_tc_rand.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 rand：300 拍随机对拍——随机写使能/字节使能/地址/数据/读使能随机化，
        读回数据与 refm 行为 RAM 模型逐一比对；先全地址预写（保证任意读地址数据已定义）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "sdpram_wrapper_tb_pkg.sv"
`ifndef U_SDPRAM_WRAPPER_TC_RAND
`define U_SDPRAM_WRAPPER_TC_RAND
import sdpram_wrapper_tb_pkg::*;
import tb_pkg::*;

//----------- sdpram_wrapper_tc_rand ------------
class sdpram_wrapper_tc_rand extends sdpram_wrapper_tc_base;

    function new(string name = "sdpram_wrapper_tc_rand");
        super.new(name);
    endfunction

    virtual task body();
        sdpram_wrapper_item seq[$];
        sdpram_wrapper_item it                ;//激励构造暂存
        bit                 rnd_wea             ;//随机写使能
        bit                 rnd_reb             ;//随机读使能
        logic [3:0]         rnd_bea             ;//随机字节使能
        logic [5:0]         rnd_addra           ;//随机写地址
        logic [5:0]         rnd_addrb           ;//随机读地址
        logic [31:0]        rnd_data            ;//随机写数据
        int                 i;
        reset_wait();
        `TB_CASE_BEGIN("TC4: rand");
        m_env.m_scb.m_enable = 1'b1;
        // 1) 全地址预写（0xA0000000+addr，全字节使能）：保证随后任意读地址数据已定义（非 X）
        for (i = 0; i < 64; i = i + 1) begin
            seq.push_back(mk_wr(32'hA0000000 + i[31:0], i[5:0]));
        end
        // 2) 300 拍随机对拍（写使能/字节使能/地址/数据/读使能全随机，可复现由 +SEED 控制）
        for (i = 0; i < 300; i = i + 1) begin
            // 每拍独立随机化（遵守用例随机化仅用 $urandom_range；数据由 4 个 8bit 随机拼装）
            rnd_wea   = $urandom_range(0, 1);
            rnd_reb   = $urandom_range(0, 1);
            rnd_bea   = $urandom_range(0, 15);
            rnd_addra = $urandom_range(0, 63);
            rnd_addrb = $urandom_range(0, 63);
            rnd_data  = ($urandom_range(0, 255) << 24) |
                        ($urandom_range(0, 255) << 16) |
                        ($urandom_range(0, 255) << 8)  |
                        $urandom_range(0, 255);
            it = mk_stim(rnd_wea, rnd_bea, rnd_addra, rnd_data, rnd_reb, rnd_addrb);
            seq.push_back(it);
        end
        drive_seq(seq);
        `TB_CASE_END("TC4: rand", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_SDPRAM_WRAPPER_TC_RAND
