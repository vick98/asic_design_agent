/*========================================FILE_HEADER=====================================
# Filename: sdpram_wrapper_tb_env.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-27        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        sdpram_wrapper 环境：组件装配与邮箱连接
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/

`ifndef U_SDPRAM_WRAPPER_TB_ENV
`define U_SDPRAM_WRAPPER_TB_ENV

//----------- sdpram_wrapper_env ------------
// 环境容器：持有具体类型组件句柄，完成组件创建/接线/接口下发
// m_scb 复用基类 tb_env_base.m_scb（不重声明，避免遮蔽基类成员），
// new() 中赋具体 sdpram_wrapper_scoreboard 实例（tb_test_base.run() 经基类句柄访问）
class sdpram_wrapper_env extends tb_env_base;

//======================== 组件句柄声明 =================================
    sdpram_wrapper_driver                 m_drv                   ;//驱动器
    sdpram_wrapper_monitor                m_mon                   ;//监视器
    sdpram_wrapper_refm                   m_refm                  ;//参考模型
    // m_scb（基类成员）在 new() 中赋具体 sdpram_wrapper_scoreboard 实例
    virtual sdpram_wrapper_if             m_dut_if            ;//DUT 接口（tc 下发）
    virtual tb_clk_rst_if           m_rst_if            ;//时钟复位接口（tc 下发）

    function new(string name = "m_env");
        sdpram_wrapper_scoreboard scb;
        super.new(name);
        m_drv = new("m_drv");
        add_child(m_drv);
        m_mon = new("m_mon");
        add_child(m_mon);
        m_refm = new("m_refm");
        add_child(m_refm);
        scb   = new("m_scb");
        m_scb = scb;
        add_child(m_scb);
    endfunction

    //----------- 接线：接口下发 + 邮箱连接 ------------
    function void connect();
        m_drv.m_dut_if = m_dut_if;
        m_drv.m_drv_mb.connect(m_refm.m_in_mb);
        m_mon.m_dut_if = m_dut_if;
        m_mon.m_out_mb.connect(m_scb.m_duv_mb);
        m_refm.m_out_mb.connect(m_scb.m_exp_mb);
    endfunction
endclass
`endif //U_SDPRAM_WRAPPER_TB_ENV
