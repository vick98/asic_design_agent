/*========================================FILE_HEADER=====================================
# Filename: sdpram_wrapper_tb_refm.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             行为 RAM 参考模型（写优先/字节使能，compute 为无状态纯函数）
#   1.2     2026-08-31        vick             删除 INIT_FILE 镜像加载（该功能随 DUT 删除），仅保留零初始化
#
#-----------------------------------------------------------------------------------------
# Description:
        sdpram_wrapper 参考模型：行为 RAM 镜像（m_mem 经参数传入 compute 纯函数），
        compute 按 DUT 语义计算读期望（写优先/字节使能）并更新内存状态
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_SDPRAM_WRAPPER_TB_REFM
`define U_SDPRAM_WRAPPER_TB_REFM

//----------- sdpram_wrapper_refm ------------
// 参考模型：m_in_mb 取驱动事务 -> model 调 compute 计算期望 -> 回填 item -> m_out_mb 广播
class sdpram_wrapper_refm extends tb_refm_base;

    logic [31:0]                m_mem [64]          ;//行为 RAM 镜像（ADDR_WIDTH=6 深度 64）
    bit                         m_mem_loaded = 1'b0 ;//镜像初始化标志

    function new(string name = "m_refm");
        super.new(name);
    endfunction

    //----------- 核心算法纯函数（无状态：内存状态经 ref 参数传入/传出，不读类成员） ------------
    // DUT 语义（与 sdpram_wrapper.sv 对齐）：
    //   1) 写：i_wea 时逐字节按 i_bea 更新内存；i_bea=0 的字节保持旧值
    //   2) 读（写前状态）：本拍 i_reb 时输出 mem[i_addrb]（写前值——内存写与读同拍时，
    //      DUT 读块经非阻塞赋值读到的是写前旧值，另走写优先分支处理同地址）
    //   3) 写优先：i_wea && i_addra==i_addrb 时，读输出 = bea?新数据:旧内存 逐字节拼合
    static function void compute(ref logic [31:0] mem [64], sdpram_wrapper_item in);
        logic [31:0]        exp;
        int                 i;
        //----------- 先算读期望（使用写前状态） ------------
        if (in.m_reb) begin
            if (in.m_wea && (in.m_addra === in.m_addrb)) begin
                // 写优先：字节使能字节取新写数据，其余字节取写前旧值
                exp = mem[in.m_addrb];
                for (i = 0; i < 4; i = i + 1) begin
                    if (in.m_bea[i])
                        exp[8*i +: 8] = in.m_dina[8*i +: 8];
                end
            end else begin
                exp = mem[in.m_addrb];
            end
        end
        //----------- 再执行写（更新内存状态为写后） ------------
        if (in.m_wea) begin
            for (i = 0; i < 4; i = i + 1) begin
                if (in.m_bea[i])
                    mem[in.m_addra][8*i +: 8] = in.m_dina[8*i +: 8];
            end
        end
        //----------- 回填期望 ------------
        in.m_exp_vld  = in.m_reb;
        in.m_exp_dout = exp;
    endfunction

    //----------- 模型计算：初始化镜像后调用 compute 回填期望字段 ------------
    virtual task model(tb_item_base it);
        sdpram_wrapper_item dut_it;
        int                 k;
        $cast(dut_it, it);
        if (!m_mem_loaded) begin
            // 镜像初始 0（DUT 无复位初始为 X；用例设计保证读地址均已被写/预写，不比对未定义值）
            for (k = 0; k < 64; k = k + 1) begin
                m_mem[k] = 32'h0;
            end
            m_mem_loaded = 1'b1;
        end
        compute(m_mem, dut_it);
    endtask
endclass
`endif //U_SDPRAM_WRAPPER_TB_REFM
