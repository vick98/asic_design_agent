/*========================================FILE_HEADER=====================================
# Filename: pubip_dynamic_mem.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：是
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-05-13        vick          initial
#   1.1     2026-08-27        vick             修复链表寄存器组深度少一格（[MEM_DEPTH-1]）
#   1.2     2026-08-27        vick             分组注释统一为标准分隔线格式，文件头 email 冒号统一
#   1.3     2026-08-27        vick             sdpram 例化端口名同步（.i_clk→.clk_in）与实例名规范化（_inst）
#
#-----------------------------------------------------------------------------------------
# Description:
        1.动态存储空间调度模块，基于链表结构管理多ID的数据存储
        2.支持多个ID交叉写入，first-fit空闲地址分配，FIFO顺序读出
        3.T0-T1全流水读取：T0调度ID → T1输出数据+ID指示（利用SDPRAM 1周期读延迟）
        4.支持连续乱序调度：每拍可调度不同ID，每拍输出对应ID的数据
        5.链表不变式：head/tail单向链表，bitmap标记占用，同拍读写冲突检测与处理
        6.ID个数与存储深度独立参数化
#-----------------------------------------------------------------------------------------
#快速例化示例
pubip_dynamic_mem #(
    .MEM_DEPTH               ( 64            ),//存储深度
    .DATA_WIDTH              ( 32            ),//数据位宽
    .ID_WIDTH                ( 4             ) //ID位宽
) pubip_dynamic_mem_inst(
    .clk_in                  (               ),//时钟输入
    .rst_n                   (               ),//异步复位低有效
    .o_wr_ready              (               ),//模块写入就绪指示
    .i_wr_vld                (               ),//写入有效指示
    .i_wr_id                 (               ),//写入数据对应ID
    .i_wr_data               (               ),//写入数据
    .i_rd_id_vld             (               ),//读取调度ID有效指示
    .i_rd_id                 (               ),//读取调度ID
    .o_rd_ready              (               ),//模块读取就绪指示
    .i_rd_vld                (               ),//后级读取有效指示
    .o_rd_data               (               ),//读取数据输出
    .o_rd_last               (               ),//当前输出为对应ID最后一笔指示
    .o_free_cnt              (               ),//当前剩余空间个数
    .o_schd_id               (               ),//当前调度输出ID指示
    .o_schd_id_remain        (               ) //当前调度ID剩余数据个数
);
=========================================FILE_HEADER====================================*/
module pubip_dynamic_mem
#(
    parameter  MEM_DEPTH   = 64 ,//存储深度
    parameter  DATA_WIDTH  = 32 ,//数据位宽
    parameter  ID_WIDTH    = 4   //ID位宽     
)
(
    input                                   clk_in              ,
    input                                   rst_n               ,

    output                                  o_wr_ready          ,//模块写入就绪指示
    input                                   i_wr_vld            ,//写入有效指示
    input       [ID_WIDTH-1:0]              i_wr_id             ,//写入数据对应ID
    input       [DATA_WIDTH-1:0]            i_wr_data           ,//写入数据

    input                                   i_rd_id_vld         ,//读取调度ID有效指示
    input       [ID_WIDTH-1:0]              i_rd_id             ,//读取调度ID
    output                                  o_rd_ready          ,//模块读取就绪指示
    input                                   i_rd_vld            ,//后级读取有效指示
    output      [DATA_WIDTH-1:0]            o_rd_data           ,//读取数据输出
    output                                  o_rd_last           ,//当前输出为对应ID最后一笔指示
    output      [$clog2(MEM_DEPTH+1)-1:0]   o_free_cnt          ,//当前剩余空间个数
    output      [ID_WIDTH-1:0]              o_schd_id           ,//当前调度输出ID指示
    output      [$clog2(MEM_DEPTH+1)-1:0]   o_schd_id_remain     //当前调度ID剩余数据个数
);
//======================== localparam define =================================
localparam  ADDR_WIDTH      = $clog2(MEM_DEPTH);
localparam  FREE_CNT_WIDTH  = $clog2(MEM_DEPTH+1);
localparam  BYTE_EN_NUM     = DATA_WIDTH/8;       //整字读写字节使能位宽（要求 DATA_WIDTH 为8的倍数）
//======================== main signal define =================================
//------ FreeAddrAlloc ------
logic       [ADDR_WIDTH-1:0]                wir_wr_alloc_addr       ;//first-fit空闲地址编码结果
logic                                       wir_has_free            ;//是否存在空闲空间
//------ WrTailMatch ------
logic       [ADDR_WIDTH-1:0]                wir_wr_tail_addr        ;//匹配到的尾节点地址
logic                                       wir_wr_tail_found       ;//是否匹配到尾节点
//------ RdHeadMatch ------
logic       [MEM_DEPTH-1:0]                 wir_head_flag_eff       ;//有效head_flag（计入当前拍读握手影响）
logic                                       wir_rd_handshake        ;//T1读握手成功指示
logic       [ADDR_WIDTH-1:0]                wir_rd_head_addr        ;//匹配到的头节点地址
logic                                       wir_rd_head_found       ;//是否匹配成功
logic       [ADDR_WIDTH-1:0]                wir_rd_next_addr        ;//头节点的link_addr
logic                                       wir_rd_head_is_tail     ;//头节点是否同时为尾节点
logic       [ID_WIDTH-1:0]                  wir_rd_head_id          ;//头节点的link_id
//------ RwConflictDetect + 共享握手信号 ------
logic                                       wir_wr_handshake        ;//写握手成功指示
logic                                       wir_rw_conflict_override;//冲突覆盖：强制新节点head_flag=1
logic                                       wir_wr_extends_single   ;//调度同拍写扩展检测：同拍写延长了正在调度的单节点ID链
//------ LinkRegFile：链表结构寄存器组（所有链表寄存器只在此块更新） ------
logic       [MEM_DEPTH-1:0]                 reg_bitmap                      ;//位图，1=占用，0=空闲
logic       [MEM_DEPTH-1:0]                 reg_head_flag                   ;//头节点标志
logic       [MEM_DEPTH-1:0]                 reg_tail_flag                   ;//尾节点标志
logic       [ID_WIDTH-1:0]                  reg_link_id     [MEM_DEPTH]     ;//各位置存储的ID
logic       [ADDR_WIDTH-1:0]                reg_link_addr   [MEM_DEPTH]     ;//链表指针(下一跳地址)
//------ RdPathReg：读通路锁存寄存器组（T0匹配结果→T1拍使用） ------
logic       [ADDR_WIDTH-1:0]                reg_rd_head_addr        ;//T0匹配到的头节点地址
logic                                       reg_rd_head_found       ;//T0匹配是否成功
logic       [ADDR_WIDTH-1:0]                reg_rd_next_addr        ;//头节点的link_addr
logic                                       reg_tail_flag_d1        ;//头节点是否同时为tail
logic       [ID_WIDTH-1:0]                  reg_rd_head_id          ;//头节点的link_id
logic       [ID_WIDTH-1:0]                  reg_rd_id               ;//T0拍有效调度ID锁存(T1拍指示当前输出数据归属ID)
//------ StatusReg：状态信号 ------
logic       [FREE_CNT_WIDTH-1:0]            reg_free_cnt            ;//剩余空闲空间计数器
logic       [ID_WIDTH-1:0]                  reg_schd_id             ;//当前调度ID锁存器
logic       [ID_WIDTH-1:0]                  wir_active_id           ;//有效调度ID
logic       [FREE_CNT_WIDTH-1:0]            wir_schd_id_remain      ;//当前调度ID剩余数据个数(组合逻辑)
//------ SdpramMem：SDPRAM数据存储体 ------
logic       [DATA_WIDTH-1:0]                wir_sdpram_rd_data      ;//SDPRAM读数据输出
//======================== main process ===================================
//----------- 1. 空闲地址分配器 (FreeAddrAlloc) ------------
// first-fit优先级编码：对~bitmap从LSB向MSB查找第一个空闲地址
always_comb begin
    wir_wr_alloc_addr = '0;
    wir_has_free = 1'b0;
    for (int i = MEM_DEPTH-1; i >= 0; i--) begin
        if (~reg_bitmap[i]) begin
            wir_wr_alloc_addr = ADDR_WIDTH'(i);
            wir_has_free = 1'b1;
        end
    end
end
// 写入就绪 = 存在空闲空间（由FreeAddrAlloc产生）
assign o_wr_ready = wir_has_free;
//----------- 2. 写尾节点匹配器 (WrTailMatch) ------------
// 匹配tail_flag=1且link_id==i_wr_id的位置，每个ID最多一个tail
always_comb begin
    wir_wr_tail_addr = '0;
    wir_wr_tail_found = 1'b0;
    for (int i = 0; i < MEM_DEPTH; i++) begin
        if (reg_tail_flag[i] && (reg_link_id[i] == i_wr_id)) begin
            wir_wr_tail_addr = ADDR_WIDTH'(i);
            wir_wr_tail_found = 1'b1;
        end
    end
end
//----------- 3. 读头节点匹配器 (RdHeadMatch) ------------
// 计算有效head_flag并匹配调度ID的链表头节点
assign wir_rd_handshake = reg_rd_head_found && i_rd_vld;
// 有效head_flag逐位计算：基础值=reg_head_flag，读握手时扣除旧head、提升新head
generate
    for (genvar gi = 0; gi < MEM_DEPTH; gi++) begin : gen_head_flag_eff
        always_comb begin
            wir_head_flag_eff[gi] = reg_head_flag[gi];
            if (wir_rd_handshake) begin
                if (gi == reg_rd_head_addr)
                    wir_head_flag_eff[gi] = 1'b0;
                else if (!reg_tail_flag_d1 && (gi == reg_rd_next_addr))
                    wir_head_flag_eff[gi] = 1'b1;
            end
        end
    end
endgenerate
always_comb begin
    // 头节点匹配：始终使用有效调度ID匹配head_flag_eff=1且link_id==wir_active_id
    wir_rd_head_addr = '0;
    wir_rd_head_found = 1'b0;
    wir_rd_next_addr = '0;
    wir_rd_head_is_tail = 1'b0;
    wir_rd_head_id = '0;
    for (int i = 0; i < MEM_DEPTH; i++) begin
        if (wir_head_flag_eff[i] && (reg_link_id[i] == wir_active_id)) begin
            wir_rd_head_addr = ADDR_WIDTH'(i);
            wir_rd_head_found = 1'b1;
            wir_rd_next_addr = reg_link_addr[i];
            wir_rd_head_is_tail = reg_tail_flag[i];
            wir_rd_head_id = reg_link_id[i];
        end
    end
end
//----------- 4. 读写冲突检测器 (RwConflictDetect) + 写扩展检测 ------------
// 写握手 = 前级有效 且 有空闲空间
assign wir_wr_handshake = i_wr_vld && wir_has_free;
// 冲突检测：同拍读写同一ID且该ID仅剩1笔数据(head=tail)
always_comb begin
    wir_rw_conflict_override = 1'b0;
    if (wir_wr_handshake && wir_rd_handshake && (i_wr_id == reg_rd_head_id) && reg_tail_flag_d1)
        wir_rw_conflict_override = 1'b1;
end
// 调度同拍写扩展检测：同拍写操作向正在调度的ID追加了新节点（该ID原仅1笔head=tail）
// 用于RdPathReg覆写reg_tail_flag_d1和reg_rd_next_addr，防止链表断链
assign wir_wr_extends_single = wir_wr_handshake && wir_rd_head_found
                           && (i_wr_id == wir_rd_head_id) && wir_rd_head_is_tail;
//----------- 5a. bitmap 寄存器组 ------------
// 读写不会同时发生在同一地址，故同地址条件互斥，可使用 if-else if
generate
    for (genvar gi = 0; gi < MEM_DEPTH; gi++) begin : gen_bitmap
        always_ff @(posedge clk_in, negedge rst_n) begin
            if (!rst_n)
                reg_bitmap[gi] <= 1'b0;
            else if (wir_wr_handshake && (gi == wir_wr_alloc_addr))
                reg_bitmap[gi] <= 1'b1;
            else if (wir_rd_handshake && (gi == reg_rd_head_addr))
                reg_bitmap[gi] <= 1'b0;
        end
    end
endgenerate
//----------- 5b. head_flag 寄存器组 ------------
generate
    for (genvar gi = 0; gi < MEM_DEPTH; gi++) begin : gen_head_flag
        always_ff @(posedge clk_in, negedge rst_n) begin
            if (!rst_n)
                reg_head_flag[gi] <= 1'b0;
            else if (wir_rd_handshake && (gi == reg_rd_head_addr))
                reg_head_flag[gi] <= 1'b0;
            else if (wir_rd_handshake && !reg_tail_flag_d1 && (gi == reg_rd_next_addr))
                reg_head_flag[gi] <= 1'b1;
            else if (wir_wr_handshake && (gi == wir_wr_alloc_addr))
                reg_head_flag[gi] <= wir_rw_conflict_override ? 1'b1 : ~wir_wr_tail_found;
        end
    end
endgenerate
//----------- 5c. tail_flag 寄存器组 ------------
// 冲突场景 reg_rd_head_addr == wr_tail_addr 时，读释放与写旧尾降级均写0，值相同无冲突
generate
    for (genvar gi = 0; gi < MEM_DEPTH; gi++) begin : gen_tail_flag
        always_ff @(posedge clk_in, negedge rst_n) begin
            if (!rst_n)
                reg_tail_flag[gi] <= 1'b0;
            else if (wir_rd_handshake && (gi == reg_rd_head_addr))
                reg_tail_flag[gi] <= 1'b0;
            else if (wir_wr_handshake && (gi == wir_wr_alloc_addr))
                reg_tail_flag[gi] <= 1'b1;
            else if (wir_wr_handshake && wir_wr_tail_found && (gi == wir_wr_tail_addr))
                reg_tail_flag[gi] <= 1'b0;
        end
    end
endgenerate
//----------- 5d. link_id 寄存器组 ------------
// 仅写握手时赋值，无复位（bitmap=0时对应link_id为无效值）
generate
    for (genvar gi = 0; gi < MEM_DEPTH; gi++) begin : gen_link_id
        always_ff @(posedge clk_in) begin
            if (wir_wr_handshake && (gi == wir_wr_alloc_addr))
                reg_link_id[gi] <= i_wr_id;
        end
    end
endgenerate
//----------- 5e. link_addr 寄存器组 ------------
// 仅写握手时更新旧尾指针，无复位（bitmap=0时对应link_addr为无效值）
generate
    for (genvar gi = 0; gi < MEM_DEPTH; gi++) begin : gen_link_addr
        always_ff @(posedge clk_in) begin
            if (wir_wr_handshake && wir_wr_tail_found && (gi == wir_wr_tail_addr))
                reg_link_addr[gi] <= wir_wr_alloc_addr;
        end
    end
endgenerate
//----------- 6. 读通路锁存寄存器组 (RdPathReg) ------------
// 每拍无条件锁存T0拍RdHeadMatch的匹配结果和有效调度ID，T1拍驱动输出控制信号
// 调度同拍写扩展覆写：写操作延长了正调度的单节点ID链时，更新后继指针和tail标志
always_ff @(posedge clk_in, negedge rst_n) begin
    if (!rst_n) begin
        reg_rd_head_addr  <= '0;
        reg_rd_head_found <= 1'b0;
        reg_rd_next_addr  <= '0;
        reg_tail_flag_d1  <= 1'b0;
        reg_rd_head_id    <= '0;
        reg_rd_id         <= '0;
    end else begin
        reg_rd_head_addr  <= wir_rd_head_addr;
        reg_rd_head_found <= wir_rd_head_found;
        reg_rd_next_addr  <= wir_wr_extends_single ? wir_wr_alloc_addr : wir_rd_next_addr;
        reg_tail_flag_d1  <= wir_wr_extends_single ? 1'b0 : wir_rd_head_is_tail;
        reg_rd_head_id    <= wir_rd_head_id;
        reg_rd_id         <= wir_active_id;
    end
end
// T1拍输出控制信号：直接由RdPathReg锁存值驱动
assign o_rd_ready = reg_rd_head_found;
assign o_rd_last  = reg_tail_flag_d1;
assign o_schd_id  = reg_rd_id;
//----------- 7. 状态信号寄存器组 (StatusReg) ------------
// 7.1 o_free_cnt —— 剩余空闲空间计数器
always_ff @(posedge clk_in, negedge rst_n) begin
    if (!rst_n) begin
        reg_free_cnt <= FREE_CNT_WIDTH'(MEM_DEPTH);
    end else begin
        if (wir_wr_handshake && !wir_rd_handshake)
            reg_free_cnt <= reg_free_cnt - 1'b1;
        else if (!wir_wr_handshake && wir_rd_handshake)
            reg_free_cnt <= reg_free_cnt + 1'b1;
    end
end
// 有效调度ID：i_rd_id_vld有效时取输入ID，否则保持上次锁存值
assign wir_active_id = i_rd_id_vld ? i_rd_id : reg_schd_id;
assign o_free_cnt = reg_free_cnt;
// 7.2 reg_schd_id —— 调度ID锁存器（wir_active_id的fallback源）
always_ff @(posedge clk_in, negedge rst_n) begin
    if (!rst_n) begin
        reg_schd_id <= '0;
    end else if (i_rd_id_vld) begin
        reg_schd_id <= i_rd_id;
    end
end
// 7.3 o_schd_id_remain —— T1拍输出数据归属ID的剩余数据个数（组合逻辑popcount，跟随o_schd_id和寄存器状态）
always_comb begin
    wir_schd_id_remain = '0;
    for (int i = 0; i < MEM_DEPTH; i++) begin
        if (reg_bitmap[i] && (reg_link_id[i] == o_schd_id))
            wir_schd_id_remain = wir_schd_id_remain + 1'b1;
    end
end
assign o_schd_id_remain = wir_schd_id_remain;
//----------- 8. SDPRAM 数据存储体 (SdpramMem) ------------
// 例化假双口RAM：A口写、B口读，1周期读延迟实现T0→T1全流水
// 适配 sdpram_wrapper：纯数据通路无复位端口；地址位宽 = $clog2(MEM_DEPTH)
sdpram_wrapper #(
    .DATA_WIDTH              ( DATA_WIDTH             ),
    .ADDR_WIDTH              ( ADDR_WIDTH             ),
    .BYTE_EN_WIDTH           ( BYTE_EN_NUM            )  //全字节使能（整字读写）
) sdpram_wrapper_inst (
    .clk_in                    ( clk_in                 ),
    .i_wea                     ( wir_wr_handshake       ),
    .i_bea                     ( {BYTE_EN_NUM{1'b1}}    ),  //全字节使能
    .i_addra                   ( wir_wr_alloc_addr      ),
    .i_dina                    ( i_wr_data              ),
    .i_reb                     ( wir_rd_head_found      ),
    .i_addrb                   ( wir_rd_head_addr       ),
    .o_doutb                   ( wir_sdpram_rd_data     )
);
// SDPRAM读数据直连模块输出
assign o_rd_data = wir_sdpram_rd_data;

endmodule
