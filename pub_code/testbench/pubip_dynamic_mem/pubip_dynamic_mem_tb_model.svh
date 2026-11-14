/*========================================FILE_HEADER=====================================
# Filename: pubip_dynamic_mem_tb_model.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             cycle 标定后实现（一拍一 item 全信号对拍）
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_dynamic_mem 行为级参考模型（用例侧使用）：数组+链表思想的独立模型，与 RTL 位操作无关。
        按"逐拍（一拍 = 一次握手窗口）"推进：step() 输入本拍激励 6 项，输出本拍响应在下一采样拍
        的期望值 7 项，并推进链表/位图/状态与 T0-T1 展示流水线（present pipe），与 DUT 每拍语义对齐：
          - 写：i_wr_vld && o_wr_ready（有空闲）→ 本拍末 posedge 入链
          - 读：T0 拍按调度ID匹配链头 → T1 拍展示（o_rd_ready/o_rd_data/o_rd_last/o_schd_id/o_schd_id_remain）
            ，展示拍末 posedge 由 i_rd_vld 消费（弹头）
          - 同拍读写冲突：写扩展正在展示的单节点链 → 新节点成为展示后新头（冲突覆盖），读展示仍为旧头
        期望生成在用例侧（逐拍模型），refm 纯函数透传（偏离说明见 tb_handoff_dynamic_mem.md）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_PUBIP_DYNAMIC_MEM_TB_MODEL
`define U_PUBIP_DYNAMIC_MEM_TB_MODEL

//----------- pubip_dynamic_mem_model ------------
// 行为级参考模型：bitmap/head/tail/link 数组 + 展示流水线，step 逐拍计算期望并推进
// 状态字段与 DUT 一一对应（初值 = DUT 复位后状态：全部空闲、无展示）
class pubip_dynamic_mem_model;

    int                             m_depth             ;//存储深度（= DUT MEM_DEPTH）
    //----------- 链表/位图状态（按地址索引） ------------
    bit                             m_used      [64]    ;//位图：1=占用
    bit                             m_is_head   [64]    ;//链头标志
    bit                             m_is_tail   [64]    ;//链尾标志
    logic [31:0]                    m_data      [64]    ;//各地址存储数据
    logic [3:0]                     m_id        [64]    ;//各地址所属 ID
    int                             m_next      [64]    ;//链表下一跳地址（-1=无）
    //----------- 状态寄存器 ------------
    int                             m_free_cnt          ;//剩余空闲计数
    logic [3:0]                     m_last_schd_id      ;//调度ID锁存（reg_schd_id）
    //----------- 展示流水线（T0匹配→T1展示，对应 DUT reg_rd_* 锁存组） ------------
    bit                             m_p_found           ;//当前展示有效（reg_rd_head_found）
    int                             m_p_addr            ;//当前展示头地址（reg_rd_head_addr）
    int                             m_p_next            ;//当前展示后继地址（reg_rd_next_addr）
    bit                             m_p_tail            ;//当前展示是否链尾（reg_tail_flag_d1）
    logic [3:0]                     m_p_schd_id         ;//当前展示归属调度ID（reg_rd_id）
    logic [3:0]                     m_p_head_id         ;//当前展示数据的链ID（reg_rd_head_id）

    function new(string name = "m_model");
    endfunction

    //----------- 复位（初值与 DUT 上电复位一致） ------------
    function void reset(int depth);
        int i;
        m_depth        = depth;
        for (i = 0; i < 64; i = i + 1) begin
            m_used[i]     = 1'b0;
            m_is_head[i]  = 1'b0;
            m_is_tail[i]  = 1'b0;
            m_data[i]     = '0;
            m_id[i]       = '0;
            m_next[i]     = -1;
        end
        m_free_cnt     = depth;
        m_last_schd_id = '0;
        m_p_found      = 1'b0;
        m_p_addr       = 0;
        m_p_next       = 0;
        m_p_tail       = 1'b0;
        m_p_schd_id    = '0;
        m_p_head_id    = '0;
    endfunction

    //----------- first-fit：最低空闲地址（-1=无空闲） ------------
    function int first_fit();
        int i;
        for (i = 0; i < m_depth; i = i + 1) begin
            if (!m_used[i]) return i;
        end
        return -1;
    endfunction

    //----------- 匹配链尾地址（-1=未找到；每 ID 至多一个尾节点） ------------
    function int tail_of(logic [3:0] id);
        int i;
        for (i = 0; i < m_depth; i = i + 1) begin
            if (m_is_tail[i] && (m_id[i] == id)) return i;
        end
        return -1;
    endfunction

    //----------- 统计某 ID 的占用条目数（popcount 语义） ------------
    function int count_of(logic [3:0] id);
        int i;
        int c;
        c = 0;
        for (i = 0; i < m_depth; i = i + 1) begin
            if (m_used[i] && (m_id[i] == id)) c = c + 1;
        end
        return c;
    endfunction

    //----------- 逐拍推进：输入本拍激励，输出本拍响应在下一采样拍的期望 ------------
    // 时序约定（与 DUT 对齐，见 tb_handoff_dynamic_mem.md）：
    //   本拍激励在 negedge 驱动，DUT 在下一 posedge 采样/提交；期望为本拍匹配结果
    //   （T1 展示）+ 提交后状态（free_cnt/wr_ready/remain），即下一采样拍 S(k+1) 的现值
    function void step(input bit wr_vld, input logic [3:0] wr_id, input logic [31:0] wr_data,
                       input bit rd_id_vld, input logic [3:0] rd_id, input bit rd_vld,
                       output bit exp_wr_ready, output bit exp_rd_ready,
                       output logic [31:0] exp_rd_data, output bit exp_rd_last,
                       output logic [3:0] exp_schd_id, output int exp_remain,
                       output int exp_free_cnt);
    begin
        //----------- 本地工作变量 ------------
        int             l_alloc     ;//first-fit 分配地址（-1=满）
        bit             l_wr_hsk    ;//写握手：前级有效 && 有空闲
        int             l_tail      ;//写 ID 链尾地址（-1=无链）
        bit             l_rd_hsk    ;//读握手：当前展示有效 && 后级有效（消费一拍）
        logic [3:0]     l_active_id ;//本轮有效调度ID
        bit             l_found     ;//T0 匹配到链头
        int             l_addr      ;//匹配地址
        bit             l_tailv     ;//匹配节点是否链尾
        int             l_nextv     ;//匹配节点后继
        logic [3:0]     l_head_id   ;//匹配节点链ID
        bit             l_wr_ext    ;//同拍写扩展检测：单节点链被追加
        bit             l_conflict  ;//冲突覆盖检测：同拍写扩展正在展示的单节点链
        int             gi          ;//循环变量
        bit             l_eff_hit   ;//有效链头（含同拍消费调整）

        //----------- 1. 写侧组合：first-fit 分配（按本拍提交前状态） ------------
        l_alloc = first_fit();
        l_wr_hsk = wr_vld && (l_alloc != -1);
        l_tail  = l_wr_hsk ? tail_of(wr_id) : -1;
        //----------- 2. 读侧组合：消费当前展示（提交于本拍末） ------------
        l_rd_hsk = m_p_found && rd_vld;
        l_active_id = rd_id_vld ? rd_id : m_last_schd_id;
        //----------- 3. T0 链头匹配（本拍提交前的链表状态，含同拍消费调整） ------------
        // 有效链头 = 链头标志 + (同拍消费时：正在展示的地址视为已弹出、其后继视为新链头)
        l_found = 1'b0;
        l_addr  = 0;
        l_tailv = 1'b0;
        l_nextv = 0;
        l_head_id = '0;
        for (gi = 0; gi < m_depth; gi = gi + 1) begin
            l_eff_hit = m_is_head[gi];
            if (l_rd_hsk) begin
                if (gi == m_p_addr)
                    l_eff_hit = 1'b0;
                else if (!m_p_tail && (gi == m_p_next))
                    l_eff_hit = 1'b1;
            end
            if (l_eff_hit && (m_id[gi] == l_active_id)) begin
                l_found   = 1'b1;
                l_addr    = gi;
                l_tailv   = m_is_tail[gi];
                l_nextv   = m_next[gi];
                l_head_id = m_id[gi];
            end
        end
        //----------- 4. 冲突/扩展检测 ------------
        l_wr_ext   = l_wr_hsk && l_found && (wr_id == l_active_id) && l_tailv;
        l_conflict = l_wr_hsk && l_rd_hsk && (wr_id == m_p_head_id) && m_p_tail;
        //----------- 5. 期望值（样本拍 = 本拍提交后的 T1 展示与状态） ------------
        exp_rd_ready = l_found;                       // T1 展示的是本拍匹配结果
        exp_rd_last  = l_wr_ext ? 1'b0 : l_tailv;     // 同拍写扩展后展示不再为链尾
        exp_schd_id  = l_active_id;
        exp_rd_data  = l_found ? m_data[l_addr] : '0;
        //----------- 6. 本拍提交（posedge：写入链 + 读弹头；地址互斥，任意顺序等价） ------------
        if (l_wr_hsk) begin
            m_used[l_alloc]     = 1'b1;
            m_data[l_alloc]     = wr_data;
            m_id[l_alloc]       = wr_id;
            m_is_tail[l_alloc]  = 1'b1;
            m_is_head[l_alloc]  = l_conflict ? 1'b1 : (l_tail != -1 ? 1'b0 : 1'b1);
            if (l_tail != -1) begin
                m_next[l_tail]     = l_alloc;
                m_is_tail[l_tail]  = 1'b0;
            end
        end
        if (l_rd_hsk) begin
            m_used[m_p_addr]     = 1'b0;
            m_is_head[m_p_addr]  = 1'b0;
            m_is_tail[m_p_addr]  = 1'b0;
            if (!m_p_tail)
                m_is_head[m_p_next] = 1'b1;      // 后继节点提升为链头
        end
        if (l_wr_hsk) m_free_cnt = m_free_cnt - 1;   // 写占一空间（读写同拍时 +1/-1 抵消）
        if (l_rd_hsk) m_free_cnt = m_free_cnt + 1;   // 读释放一空间
        //----------- 7. 展示流水与调度锁存 ------------
        m_p_found    = l_found;
        m_p_addr     = l_addr;
        m_p_next     = l_wr_ext ? l_alloc : l_nextv;   // 同拍写扩展：后继指向新节点
        m_p_tail     = l_wr_ext ? 1'b0 : l_tailv;      // 同拍写扩展：展示不再为链尾
        m_p_schd_id  = l_active_id;
        m_p_head_id  = l_found ? l_head_id : '0;
        if (rd_id_vld) m_last_schd_id = rd_id;
        //----------- 8. 提交后的状态（样本拍现值） ------------
        exp_free_cnt = m_free_cnt;
        exp_wr_ready = (m_free_cnt > 0) ? 1'b1 : 1'b0;
        exp_remain   = count_of(l_active_id);
    end
    endfunction
endclass
`endif //U_PUBIP_DYNAMIC_MEM_TB_MODEL
