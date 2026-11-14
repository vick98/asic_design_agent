/*========================================FILE_HEADER=====================================
# Filename: sdpram_wrapper_tb_scoreboard.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#   1.1     2026-08-27        vick             读回数据比对（watch 过滤 + X 态检查 + 多余输出判 fail）
#
#-----------------------------------------------------------------------------------------
# Description:
        sdpram_wrapper 计分板：期望队列入队（仅读事务）/ 采集比对 o_doutb，
        m_exp_vld 为 0（无读）的事务不入队；watch=1（窗口内且读使能）才比对
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_SDPRAM_WRAPPER_TB_SCOREBOARD
`define U_SDPRAM_WRAPPER_TB_SCOREBOARD

//----------- sdpram_wrapper_scoreboard ------------
class sdpram_wrapper_scoreboard extends tb_scoreboard_base;

    tb_item_base                    m_exp_q[$]          ;//期望队列（先进先出，仅含读事务）

    function new(string name = "m_scb");
        super.new(name);
    endfunction

    //----------- 期望入队（仅读事务 m_exp_vld=1 入队，与 watch=1 采样 1:1 配对） ------------
    virtual task push_exp(tb_item_base it);
        sdpram_wrapper_item exp_it;
        $cast(exp_it, it);
        if (exp_it.m_exp_vld === 1'b1) begin
            m_exp_q.push_back(it);
        end
    endtask

    //----------- 采集比对（watch=1 才比对；X 态/数值不等记 fail） ------------
    virtual task check(tb_item_base it);
        sdpram_wrapper_item dut_it;
        sdpram_wrapper_item exp_it;
        $cast(dut_it, it);
        if (dut_it.m_watch === 1'b0) return;   // 窗口关闭/读使能为 0 的采样不比对
        if (!m_enable) return;
        if (m_exp_q.size() == 0) begin
            `TB_ERROR($sformatf("%s: 多余有效输出（期望队列空）%s", m_name, dut_it.do_print()));
            m_fail_cnt = m_fail_cnt + 1;
        end
        else begin
            exp_it = new();
            $cast(exp_it, m_exp_q.pop_front());
            if (^dut_it.m_out_dout === 1'bx) begin
                `TB_ERROR($sformatf("%s: 输出 X 态 exp=%h got=%h", m_name, exp_it.m_exp_dout, dut_it.m_out_dout));
                m_fail_cnt = m_fail_cnt + 1;
            end
            else if (dut_it.m_out_dout !== exp_it.m_exp_dout) begin
                `TB_ERROR($sformatf("%s: FAIL addr=%0h fmt(exp/got)=%h/%h",
                                    m_name, exp_it.m_addrb, exp_it.m_exp_dout, dut_it.m_out_dout));
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
`endif //U_SDPRAM_WRAPPER_TB_SCOREBOARD
