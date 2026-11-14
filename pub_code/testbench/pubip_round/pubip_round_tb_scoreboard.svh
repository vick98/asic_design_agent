/*========================================FILE_HEADER=====================================
# Filename: pubip_round_tb_scoreboard.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-10-06        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        pubip_round 计分板：FIFO 期望队列入队、逐拍比对 o_data（含 X 态检查、队列空判 fail），
        并逐拍检查"输出不得为补码负最大值（非对称最小 2^(W-1)）"这条对称收尾不变量
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_PUBIP_ROUND_TB_SCOREBOARD
`define U_PUBIP_ROUND_TB_SCOREBOARD

//----------- pubip_round_scoreboard ------------
class pubip_round_scoreboard extends tb_scoreboard_base;

    tb_item_base                    m_exp_q[$]          ;//期望队列（先进先出）
    int                             m_asym_min_cnt = 0  ;//负满码泄漏计数（独立统计，便于定位）

    function new(string name = "m_scb");
        super.new(name);
    endfunction

    //----------- 期望入队 ------------
    virtual task push_exp(tb_item_base it);
        m_exp_q.push_back(it);
    endtask

    //----------- 采集比对（watch=1 才比对；X 态/数值不等/负满码泄漏记 fail） ------------
    virtual task check(tb_item_base it);
        pubip_round_item dut_it;
        pubip_round_item exp_it;
        dut_it = new();
        $cast(dut_it, it);
        if (dut_it.m_watch === 1'b0) return;   // 关闭窗口的采样不比对（保持队列配对）
        if (!m_enable) return;
        //对称收尾不变量：输出不得等于补码负最大值 2^(W-1)（非对称最小），与期望对不对无关
        if (dut_it.m_out === `PUBIP_ROUND_OUT_TOTAL'(`PUBIP_ROUND_NEG_ASYM)) begin
            `TB_ERROR($sformatf("%s: 输出负满码（补码负最大值）out=%h", m_name, dut_it.m_out));
            m_asym_min_cnt = m_asym_min_cnt + 1;
            m_fail_cnt     = m_fail_cnt + 1;
        end
        if (m_exp_q.size() == 0) begin
            `TB_ERROR($sformatf("%s: 多余有效输出（期望队列空）%s", m_name, dut_it.do_print()));
            m_fail_cnt = m_fail_cnt + 1;
        end
        else begin
            exp_it = new();
            $cast(exp_it, m_exp_q.pop_front());
            if ($isunknown(dut_it.m_out)) begin
                `TB_ERROR($sformatf("%s: 输出 X 态 out=%h (exp=%h)", m_name, dut_it.m_out, exp_it.m_exp));
                m_fail_cnt = m_fail_cnt + 1;
            end
            else if (dut_it.m_out !== exp_it.m_exp) begin
                `TB_ERROR($sformatf("%s: FAIL exp=%h got=%h in=%h",
                                    m_name, exp_it.m_exp, dut_it.m_out, exp_it.m_data));
                m_fail_cnt = m_fail_cnt + 1;
            end
            else begin
                m_pass_cnt = m_pass_cnt + 1;
            end
        end
    endtask

    //----------- 覆盖：返回内部期望队列大小（防漏比） ------------
    virtual function int pending_count();
        return m_exp_q.size();
    endfunction
endclass
`endif //U_PUBIP_ROUND_TB_SCOREBOARD
