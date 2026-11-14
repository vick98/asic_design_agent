/*========================================FILE_HEADER=====================================
# Filename: tb_pkg.sv
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-01        vick             initial
#   1.1     2026-09-30        vick             report_summary：零比对判 FAIL
#
#-----------------------------------------------------------------------------------------
# Description:
        轻量级 UVM 风格自测平台框架核心 package（tb_pkg）
        组件：item_base / analysis_mb / component_base / driver_base /
              monitor_base / refm_base / scoreboard_base / env_base /
              test_base / factory
        设计取舍：
          1. 不依赖 uvm_pkg，无宏注册机制（m_name 字符串代替 uvm_component_utils）
          2. 无 rand/constraint、无 clocking 块、无 config_db
          3. 随机使用 $urandom_range，播种使用 $srandom
          4. virtual interface 由 sim_top 直接赋值给 test_base.m_rst_if 传递
          5. 组件间用 mailbox 通信，analysis 广播经 tb_analysis_mb
          6. 不提供 stop()：disable fork 对嵌套 fork 不可靠，依赖超时/正常流程 $finish 收尾
        使用流程（sim_top）：
          实例化 tb_clk_rst_if -> 调 factory::create("case名") -> 赋 m_rst_if ->
          调 test.run()（框架固定流程，含 build/connect/run_all/body/等待排空/汇总/$finish）
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/
`include "tb_define.svh"
`timescale 1ns/1ps

package tb_pkg;

//======================== 包级静态变量 =================================
    int                         g_case_cnt  = 0      ;//用例计数器（供 TB_CASE_BEGIN 宏切换波形文件使用）

//======================== 基础事务类 =================================
//----------- tb_item_base ------------
// 事务基类：m_name 标识 + m_id 全局递增编号 + do_print 格式化描述
virtual class tb_item_base;
    string                      m_name                  ;//事务名称
    int                         m_id                    ;//事务全局递增编号
    static int                  s_id_cnt    = 0         ;//编号计数器

    function new(string name = "item");
        m_name = name;
        m_id   = s_id_cnt++;
    endfunction

    virtual function string do_print();
        return $sformatf("%s id=%0d", m_name, m_id);
    endfunction

    //----------- 深拷贝虚方法（子类必须覆写：new + 逐字段复制） ------------
    // 用途：driver 逐拍广播（如 BURST 每拍 new 副本并广播）、item 复用等场景
    virtual function tb_item_base do_clone();
        return null;   // 子类必须覆写
    endfunction
endclass

//======================== 通信类 =================================
//----------- tb_analysis_mb ------------
// 分析广播邮箱：monitor/refm 输出经此广播到多个 consumer 邮箱
class tb_analysis_mb #(
    type T = tb_item_base
);
    mailbox #(T)                m_outs[$]               ;//下游邮箱列表

    //----------- 连接下游邮箱 ------------
    function void connect(mailbox #(T) mb);
        m_outs.push_back(mb);
    endfunction

    //----------- 广播发送 ------------
    task put(T item);
        foreach (m_outs[i]) begin
            m_outs[i].put(item);
        end
    endtask
endclass

//======================== 组件基类 =================================
//----------- tb_component_base ------------
// 组件基类：统一名字/父指针/日志级别/启动状态与生命周期钩子
// 生命周期：build() -> connect() -> start()(fork run) -> $finish 收尾
// 不提供 stop()：disable fork 对嵌套 fork 不可靠，依赖超时/正常流程 $finish 收尾
virtual class tb_component_base;
    string                      m_name                  ;//组件名称
    tb_component_base           m_parent                ;//父组件指针（env）
    int                         m_log_level = `TB_LOG_LEVEL;//组件日志级别
    bit                         m_started   = 1'b0      ;//启动标志

    function new(string name = "comp");
        m_name = name;
    endfunction

    //----------- 构建阶段（空体，子类覆盖） ------------
    virtual function void build();
    endfunction

    //----------- 连接阶段（空体，子类覆盖） ------------
    virtual function void connect();
    endfunction

    //----------- 启动阶段：fork run 线程 ------------
    task start();
        fork run(); join_none
        m_started = 1'b1;
    endtask

    //----------- 主运行线程（空体，子类覆盖） ------------
    virtual task run();
    endtask
endclass

//======================== 驱动类 =================================
//----------- tb_driver_base ------------
// 驱动器基类：从 m_item_mb 取事务驱动 DUT，事务另广播到 m_drv_mb（供 refm/监测）
virtual class tb_driver_base #(
    type ITEM = tb_item_base
) extends tb_component_base;
    mailbox #(ITEM)             m_item_mb   = new()     ;//激励注入邮箱（test 侧 put）
    tb_analysis_mb #(ITEM)      m_drv_mb                ;//驱动事务广播邮箱

    function new(string name = "drv");
        super.new(name);
        m_drv_mb = new();
    endfunction

    //----------- 主运行线程：取事务 -> drive ------------
    virtual task run();
        ITEM it;
        forever begin
            m_item_mb.get(it);
            drive(it);
        end
    endtask

    //----------- 驱动单事务（空体，子类覆盖） ------------
    virtual task drive(ITEM it);
    endtask
endclass

//======================== 监视类 =================================
//----------- tb_monitor_base ------------
// 监视器基类：采集 DUT 输出为事务，广播到 m_out_mb（供 scoreboard/refm）
virtual class tb_monitor_base #(
    type ITEM = tb_item_base
) extends tb_component_base;
    tb_analysis_mb #(ITEM)      m_out_mb                ;//采集事务广播邮箱

    function new(string name = "mon");
        super.new(name);
        m_out_mb = new();
    endfunction

    //----------- 主运行线程：采集 -> 广播 ------------
    virtual task run();
        ITEM it;
        forever begin
            collect(it);
            m_out_mb.put(it);
        end
    endtask

    //----------- 采集单事务（空体，子类覆盖） ------------
    virtual task collect(ref ITEM it);
    endtask
endclass

//======================== 参考模型类 =================================
//----------- tb_refm_base ------------
// 参考模型基类：m_in_mb 取驱动事务 -> model 计算期望 -> 广播到 m_out_mb
// 【强制约定】子类核心算法必须写成无状态纯函数 compute(...)（输入->输出映射，
//   不依赖类成员/时间），便于子系统级 refm 以组合方式复用多个 compute
virtual class tb_refm_base #(
    type ITEM = tb_item_base
) extends tb_component_base;
    mailbox #(ITEM)             m_in_mb                 ;//驱动事务输入邮箱
    tb_analysis_mb #(ITEM)      m_out_mb                ;//期望事务广播邮箱

    function new(string name = "refm");
        super.new(name);
        m_in_mb  = new();
        m_out_mb = new();
    endfunction

    //----------- 主运行线程：取事务 -> model -> 广播 ------------
    virtual task run();
        ITEM it;
        forever begin
            m_in_mb.get(it);
            model(it);
            m_out_mb.put(it);
        end
    endtask

    //----------- 模型计算（空体，子类覆盖，内部调用纯函数 compute） ------------
    virtual task model(ITEM it);
    endtask
endclass

//======================== 计分板类 =================================
//----------- tb_scoreboard_base ------------
// 计分板基类：双邮箱消费（期望 push_exp / DUT 结果 check），
//   统计 pass/fail，提供排空等待与结果汇总
virtual class tb_scoreboard_base #(
    type ITEM = tb_item_base
) extends tb_component_base;
    mailbox #(ITEM)             m_exp_mb    = new()     ;//期望事务邮箱（refm 侧 put）
    mailbox #(ITEM)             m_duv_mb    = new()     ;//DUT 采集事务邮箱（monitor 侧 put）
    int                         m_pass_cnt  = 0         ;//通过计数
    int                         m_fail_cnt  = 0         ;//失败计数
    bit                         m_enable    = 1'b1      ;//比对使能

    // 显式构造函数：参数化类的构造函数不能经继承链解析（实测：继承的 new
    // 传参会报 "Too many arguments"），因此框架内所有参数化类自带构造函数，
    // 且派生框架参数化类的用户子类也必须在自身类内显式定义构造函数（super.new(name) 调用即可）
    function new(string name = "scb");
        super.new(name);
    endfunction

    //----------- 主运行线程：双线程并行消费 ------------
    virtual task run();
        fork
            //----------- 期望入队线程 ------------
            forever begin
                ITEM it;
                m_exp_mb.get(it);
                push_exp(it);
            end
            //----------- 采集比对线程 ------------
            forever begin
                ITEM it;
                m_duv_mb.get(it);
                check(it);
            end
        join
    endtask

    //----------- 期望入队处理（空体，子类覆盖） ------------
    virtual task push_exp(ITEM it);
    endtask

    //----------- 采集比对处理（空体，子类覆盖） ------------
    virtual task check(ITEM it);
    endtask

    //----------- 内部期望队列残留计数 ------------
    // 子类覆写返回内部队列（如 m_exp_q）的当前大小，供 wait_drain/report_summary 防漏比
    virtual function int pending_count();
        return 0;
    endfunction

    //----------- 排空等待：轮询双邮箱与内部期望队列为空，超时打印残留并计 fail ------------
    task wait_drain(int max_cycles);
        int t;
        t = 0;
        while ((m_exp_mb.num() != 0 || m_duv_mb.num() != 0 || pending_count() != 0) && t < max_cycles) begin
            #(`TB_CLK_PERIOD);
            t = t + 1;
        end
        if (m_exp_mb.num() != 0 || m_duv_mb.num() != 0 || pending_count() != 0) begin
            `TB_ERROR($sformatf("scoreboard [%s] drain timeout: exp left=%0d duv left=%0d pending=%0d",
                                m_name, m_exp_mb.num(), m_duv_mb.num(), pending_count()));
            m_fail_cnt = m_fail_cnt + 1;
        end
    endtask

    //----------- 结果汇总打印（内部队列残留计 fail，防漏比） ------------
    function void report_summary();
        if (pending_count() != 0) begin
            `TB_ERROR($sformatf("scoreboard [%s] 内部期望队列残留 %0d 项（漏比）", m_name, pending_count()));
            m_fail_cnt = m_fail_cnt + 1;
        end
        // 一次比对都没做的仿真不能算通过（空 TB、激励没进计分板）
        if (m_pass_cnt + m_fail_cnt == 0) begin
            `TB_ERROR($sformatf("scoreboard [%s] 没有任何比对", m_name));
            m_fail_cnt = m_fail_cnt + 1;
        end
        $display("============================================================");
        $display("INFO: %t - [SCOREBOARD SUMMARY] %s", $time, m_name);
        $display("       Total checks : %0d", m_pass_cnt + m_fail_cnt);
        $display("       PASS         : %0d", m_pass_cnt);
        $display("       FAIL         : %0d", m_fail_cnt);
        if (m_fail_cnt == 0) begin
            $display("       RESULT       : PASS");
        end
        else begin
            $display("       RESULT       : FAIL");
        end
        $display("============================================================");
    endfunction
endclass

//======================== 环境类 =================================
//----------- tb_env_base ------------
// 环境基类：持有子组件列表与计分板，统一生命周期
virtual class tb_env_base extends tb_component_base;
    tb_component_base           m_children[$]           ;//子组件列表
    tb_scoreboard_base          m_scb                   ;//计分板指针

    function new(string name = "env");
        super.new(name);
    endfunction

    //----------- 注册子组件 ------------
    function void add_child(tb_component_base child);
        child.m_parent = this;
        m_children.push_back(child);
    endfunction

    //----------- 启动全部子组件 ------------
    task run_all();
        foreach (m_children[i]) begin
            m_children[i].start();
        end
    endtask
endclass

//======================== 测试基类 =================================
//----------- tb_test_base ------------
// 测试基类（不继承 component，无 parent）：
//   持有 env 指针与 virtual interface（由 sim_top 直接赋值传入）
//   run() 为框架固定流程，子类不得重写，仅需实现 build_env() 与 body()
virtual class tb_test_base;
    string                      m_name                  ;//测试用例名称
    tb_env_base                 m_env                   ;//环境指针
    virtual tb_clk_rst_if       m_rst_if                ;//virtual interface（sim_top 赋值）

    function new(string name = "tc");
        m_name = name;
    endfunction

    //----------- 构建环境（空体，子类覆盖：创建 env 并装配组件/连接） ------------
    virtual function void build_env();
    endfunction

    //----------- 框架固定流程（子类不重写） ------------
    // build_env -> env.build -> env.connect -> env.run_all -> body
    // -> 等待计分板排空 -> 汇总 -> $finish（fail 置 1，信息量最小）
    task run();
        build_env();
        m_env.build();
        m_env.connect();
        m_env.run_all();
        body();
        m_env.m_scb.wait_drain(200);
        m_env.m_scb.report_summary();
        $finish(m_env.m_scb.m_fail_cnt ? 1 : 0);
    endtask

    //----------- 测试主体（空体，子类覆盖） ------------
    virtual task body();
    endtask
endclass

//======================== 工厂类 =================================
//----------- tb_factory ------------
// 工厂基类：create 按用例名生成测试对象；子类重写为 case 表
// 注意：static 函数无法多态覆盖，子类中直接重新定义同名函数即可遮蔽
virtual class tb_factory;
    static function tb_test_base create(string name);
        $fatal(1, "Unknown testcase: %s", name);
        return null;
    endfunction
endclass

endpackage
