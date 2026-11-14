/*========================================FILE_HEADER=====================================
# Filename: tb_define.svh
# Author:   vick
# email：   ykun@yk9811.com
# 是否可综合：否
#-----------------------------------------------------------------------------------------
# VERSION      DATE           AUTHOR           DESCRIPTION
#   1.0     2026-08-01        vick             initial
#
#-----------------------------------------------------------------------------------------
# Description:
        轻量级 UVM 风格自测平台框架 - 公共宏定义（无类）
        提供：时钟周期/超时/日志级别默认值、四级日志打印宏、
              测试用例标记宏、仿真超时骨架宏
        使用方式：本文件由 tb_pkg.sv 与 sim_top 直接 `include 引入
#-----------------------------------------------------------------------------------------
=========================================FILE_HEADER====================================*/
`ifndef TB_DEFINE_SVH
`define TB_DEFINE_SVH

//======================== 默认参数宏 =================================
`define TB_CLK_PERIOD   10              //默认时钟周期(ns)
`define TB_TIMEOUT_NS   1000000000      //默认仿真超时(ns)，即1s
`ifndef TB_LOG_LEVEL
`define TB_LOG_LEVEL    2               //日志级别：0=ERROR 1=WARN 2=INFO 3=DEBUG（可编译命令行 +define+TB_LOG_LEVEL=3 覆盖）
`endif

//----------- 仿真超时默认值 ------------
// 超时块骨架宏 TB_TIMEOUT_INIT 使用 TB_TIMEOUT_NS 作为默认超时值，
// 仿真命令行可通过 plusarg 覆盖（见 TB_TIMEOUT_INIT 说明）

//----------- 波形 dump 标签默认值 ------------
// TB_CASE_BEGIN 宏在 DEBUG_CODE_EN 开启时切换波形文件，文件名前缀由 TB_DUMP_TAG 指定。
// 默认值 "wave"，无需在 sim_top 中定义；
// 自定义前缀时编译命令行 +define+TB_DUMP_TAG="<tag>" 覆盖（ifndef 保护，命令行定义优先）
//
// 波形格式由 TB_DUMP_FSDB 选择（编译命令行 +define+TB_DUMP_FSDB 启用）：
//   未定义 → VCD，文件名 <TB_DUMP_TAG>_case<N>.vcd
//   已定义 → FSDB，文件名 <TB_DUMP_TAG>_case<N>.fsdb（推荐，见 rules/tb.md 6.3）
// FSDB 档需配合的编译参数（否则链接报 LTO 错误）：
//   -debug_access+all -P $VERDI_HOME/share/PLI/VCS/LINUX64/novas.tab \
//                       $VERDI_HOME/share/PLI/VCS/LINUX64/pli.a \
//   -LDFLAGS "-no-pie -Wl,--no-as-needed -fno-lto"
`ifndef TB_DUMP_TAG
`define TB_DUMP_TAG    "wave"
`endif

//======================== 日志打印宏 =================================
// 四级日志：ERROR(0)/WARN(1)/INFO(2)/DEBUG(3)，按 TB_LOG_LEVEL 过滤
// 用法：`TB_INFO("case 1 done") 或 `TB_INFO($sformatf("value=%0d", val))
// msg 为字符串表达式（字面量或 $sformatf 结果），支持任意格式参数
// ERROR 不可屏蔽，始终打印
// 统一采用"单参数 msg"形式（消息为字符串表达式），功能与变参形式等价且更健壮

//----------- ERROR：错误信息（不可屏蔽） ------------
`define TB_ERROR(msg) \
    $display("ERROR: %t - %s", $time, msg)

//----------- WARN：警告信息（TB_LOG_LEVEL>=1 打印） ------------
`define TB_WARN(msg) \
    if (`TB_LOG_LEVEL >= 1) begin \
        $display("WARN:  %t - %s", $time, msg); \
    end

//----------- INFO：普通信息（TB_LOG_LEVEL>=2 打印） ------------
`define TB_INFO(msg) \
    if (`TB_LOG_LEVEL >= 2) begin \
        $display("INFO:  %t - %s", $time, msg); \
    end

//----------- DEBUG：调试信息（TB_LOG_LEVEL>=3 打印） ------------
`define TB_DEBUG(msg) \
    if (`TB_LOG_LEVEL >= 3) begin \
        $display("DEBUG: %t - %s", $time, msg); \
    end

//======================== 测试用例标记宏 =================================
// 每个用例进入/结束必须打印时间标记（见 rules/tb.md 6.2 节），并可用 DEBUG_CODE_EN
// 控制按用例切换波形文件
// 注意：宏体中的 `ifdef DEBUG_CODE_EN / `ifdef TB_DUMP_FSDB 在宏定义处求值（IEEE 1800 标准行为），
//       因此启用调试波形切换时，需在编译命令行传入 +define+DEBUG_CODE_EN
//       （TB_DUMP_TAG 未定义时使用默认 "wave"，可用 +define+TB_DUMP_TAG="<tag>" 覆盖）

//----------- 用例开始标记 ------------
// 用法：`TB_CASE_BEGIN("TC1: basic test")
//       `TB_CASE_BEGIN($sformatf("TC%0d: test", i))   // 参数化用例名
// DEBUG_CODE_EN 开启时按用例切换波形文件（g_case_cnt 递增，文件名 <TB_DUMP_TAG>_case<N>.<ext>）
// 切换序列：关闭 dump → 切文件 → 开启 dump，具体调用按波形格式分档：
//   VCD （未定义 TB_DUMP_FSDB）：$dumpoff     → $dumpfile          → $dumpvars()    → $dumpon
//   FSDB（定义   TB_DUMP_FSDB）：$fsdbDumpoff → $fsdbDumpfile / $fsdbSwitchDumpfile
//                                              → $fsdbDumpvars() → $fsdbDumpon
// 说明：
//   1. $dumpvars() / $fsdbDumpvars() 无参形式均表示「记录全部信号」，不可省略
//      （VCS 2017.03 实测：未调用时 $dumpfile 不创建文件）
//   2. FSDB 档首次必须用 $fsdbDumpfile、后续用 $fsdbSwitchDumpfile
//      （实测 $fsdbSwitchDumpfile 不能作为首次调用，否则第一个文件不生成），故按 g_case_cnt==1 分支
`define TB_CASE_BEGIN(tc_name) \
    $display("INFO: %t - [CASE_START] %s", $time, tc_name); \
`ifdef DEBUG_CODE_EN \
    tb_pkg::g_case_cnt = tb_pkg::g_case_cnt + 1; \
`ifdef TB_DUMP_FSDB \
    $fsdbDumpoff; \
    if (tb_pkg::g_case_cnt == 1) begin \
        $fsdbDumpfile($sformatf("%s_case%0d.fsdb", `TB_DUMP_TAG, tb_pkg::g_case_cnt)); \
    end else begin \
        $fsdbSwitchDumpfile($sformatf("%s_case%0d.fsdb", `TB_DUMP_TAG, tb_pkg::g_case_cnt)); \
    end \
    $fsdbDumpvars(); \
    $fsdbDumpon; \
`else \
    $dumpoff; \
    $dumpfile($sformatf("%s_case%0d.vcd", `TB_DUMP_TAG, tb_pkg::g_case_cnt)); \
    $dumpvars(); \
    $dumpon; \
`endif \
`endif

//----------- 用例结束标记 ------------
// 用法：`TB_CASE_END("TC1: basic test", pass_cnt, fail_cnt)
`define TB_CASE_END(tc_name, pass_cnt, fail_cnt) \
    $display("INFO: %t - [CASE_END]   %s pass=%0d fail=%0d", $time, tc_name, pass_cnt, fail_cnt)

//======================== 仿真超时控制宏 =================================
// TB_TIMEOUT_INIT 展开为完整 initial 超时块骨架，sim_top 中直接调用一次即可：
//     `TB_TIMEOUT_INIT
// 默认超时 TB_TIMEOUT_NS(1s)；仿真命令行可用 plusarg 覆盖（单位 us）：
//     ./simv +TB_TIMEOUT_US=2000000            // 2s
// 超时触发时打印 ERROR 级信息并以 $finish(1) 强制结束，防止卡死仿真
`define TB_TIMEOUT_INIT \
    initial begin \
        longint tb_timeout_us; \
        tb_timeout_us = `TB_TIMEOUT_NS / 1000; \
        if ($value$plusargs("TB_TIMEOUT_US=%0d", tb_timeout_us)) begin \
            /* plusarg 覆盖默认超时值 */ \
        end \
        #(tb_timeout_us * 1000); \
        $display("============================================================"); \
        `TB_ERROR($sformatf("SIMULATION TIMEOUT at %0t! Test appears to be stuck.", $time)); \
        $display("       timeout_us = %0d us", tb_timeout_us); \
        $display("============================================================"); \
        $finish(1); \
    end

`endif
