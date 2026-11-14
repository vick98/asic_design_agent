/*========================================FILE_HEADER=====================================
# Filename: sdpram_wrapper_tc_write_first.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        用例 write_first：同拍同地址读写写优先——i_wea+i_reb 同拍且 addra==addrb 时，
        读输出返回新写入值（全字节使能与部分字节使能两种形态）；另覆盖同拍异地址读写与 bea=0000 边界
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`timescale 1ns/1ps
`include "tb_define.svh"
`include "sdpram_wrapper_tb_pkg.sv"
`ifndef U_SDPRAM_WRAPPER_TC_WRITE_FIRST
`define U_SDPRAM_WRAPPER_TC_WRITE_FIRST
import sdpram_wrapper_tb_pkg::*;
import tb_pkg::*;

//----------- sdpram_wrapper_tc_write_first ------------
class sdpram_wrapper_tc_write_first extends sdpram_wrapper_tc_base;

    function new(string name = "sdpram_wrapper_tc_write_first");
        super.new(name);
    endfunction

    virtual task body();
        sdpram_wrapper_item seq[$];
        reset_wait();
        `TB_CASE_BEGIN("TC3: write_first");
        m_env.m_scb.m_enable = 1'b1;
        // 1) 预写地址 2 = ABCDEF01（旧值铺垫）
        seq.push_back(mk_wr(32'hABCDEF01, 6'd2));
        // 2) 同拍同地址读写 + 全字节使能：读输出 = 新写入 11223344（写优先）
        seq.push_back(mk_wr_rd(32'h11223344, 6'd2, 4'b1111));
        // 3) 后续读地址 2 应为新值
        seq.push_back(mk_rd(6'd2));          // 期望 11223344
        // 4) 同拍同地址读写 + bea=4'b0011：低两字节取新值 77/88，高两字节取写前旧值 11/22（写优先逐字节）
        seq.push_back(mk_wr_rd(32'h55667788, 6'd2, 4'b0011));
        // 5) 后续读地址 2 = 11227788
        seq.push_back(mk_rd(6'd2));          // 期望 11227788
        // 6) 同拍异地址读写：写地址 3 的同时读地址 2 → 读输出应为旧值 11227788（非写优先分支）
        seq.push_back(mk_stim(1'b1, 4'hf, 6'd3, 32'hDEADBEEF, 1'b1, 6'd2));
        // 7) 后续读地址 3 = DEADBEEF（说明旁路写与读互不干扰）
        seq.push_back(mk_rd(6'd3));          // 期望 DEADBEEF
        // 8) 同拍同地址读写 + bea=0000：字节使能全 0 → 读输出保持写前旧值 11227788
        seq.push_back(mk_wr_rd(32'hFFFFFFFF, 6'd2, 4'b0000));
        drive_seq(seq);
        `TB_CASE_END("TC3: write_first", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);
    endtask
endclass
`endif //U_SDPRAM_WRAPPER_TC_WRITE_FIRST
