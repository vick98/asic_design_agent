# 作者：vick 邮箱：ykun@yk9811.com

"""按交付 IR 生成框架式 testbench 骨架。

结构与命名照 `rules/tb.md` 和 `pub_code/testbench/<ip>/` 的真实平台：组件继承 `tb_common/tb_pkg.sv`
的基类，时钟复位由 `tb_clk_rst_if` 提供，超时、用例进出与结果汇总都用框架宏。
骨架的用例在填写前记一次失败，参考模型与比对留给 `tb_build` 角色按规格书填。
已存在的文件不覆盖，要重写就加 `--force`。
"""

import os

CLOCKS = ("clk_in", "clk")
RESETS = ("rst_n",)
PENDING = "骨架未填写：按规格书测试要点编写激励与期望"
REFM_PENDING = "参考模型骨架未填写：compute 仍为透传，待按规格书填写"
# 行 9 的 T6 闸门（gates/tc.py）按这两个标记判"骨架还没填"：平台任用例文件或
# 参考模型文件含其中任一标记即阻断。生成器与闸门共用这里的常量，不各写一份字面量。
SKELETON_MARKS = (PENDING, REFM_PENDING)


def _guard(dut, comp):
    return "U_%s_TB_%s" % ("".join(ch if ch.isalnum() else "_" for ch in dut.upper()), comp)


def _header(filename, description):
    return "\n".join([
        "/*========================================FILE_HEADER=====================================",
        "# Filename: %s" % filename,
        "# 是否可综合：否",
        "#-----------------------------------------------------------------------------------------",
        "# Description:",
        "        %s（tb-gen 生成的骨架，待按规格书填写）" % description,
        "=========================================FILE_HEADER====================================*/",
        "",
    ])


def _width(port):
    width = int(port.get("width") or 1)
    return "" if width <= 1 else "[%d:0] " % (width - 1)


def _short(name):
    for prefix in ("io_", "o_", "i_"):
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def dut_ports(sys_root, sys_name, dut):
    """从交付 IR 取 DUT 端口；IR 里没有这个模块时返回空表。"""
    from framework.digest import digest
    data = digest(sys_root, sys_name)
    if dut in (sys_name, sys_name + "_top"):
        return data.get("ports") or []
    for item in data.get("module_details") or []:
        if item.get("name") == dut:
            return item.get("ports") or []
    return []


def dut_tests(sys_root, sys_name, dut):
    """从交付 IR 取 DUT 的测试要点（模块规格书第 9 节）。"""
    from framework.digest import digest
    data = digest(sys_root, sys_name)
    for item in data.get("module_details") or []:
        if item.get("name") == dut:
            return item.get("tests") or []
    return []


def port_check(sys_root, sys_name, dut):
    """生成前校验：RTL 实际端口 vs 交付 IR 端口。

    返回 (diffs, parser, errors)。diffs 非空即不一致——骨架照旧端口生成只会
    白写，直接拦截。errors 非空是"校验做不了"（IR 缺端口、RTL 解析失败）：
    生成器降级为提示继续，不阻断——解析器是可选依赖（rtlports）。
    """
    from framework import rtlports
    ir_ports = dut_ports(sys_root, sys_name, dut)
    if not ir_ports:
        return [], "", ["交付 IR 里没有 %s 的端口（检查模块名或重新生成 IR）" % dut]
    rtl_list, parser, errors = rtlports.parse_ports(sys_root, dut)
    if errors:
        return [], parser, errors
    return rtlports.diff_ports(ir_ports, rtl_list), parser, []


def cases_for(tests):
    """测试要点 → 用例名（一测试点一用例；没有要点时仍只生成 tc_basic）。"""
    if not tests:
        return [("basic", None)]
    return [("tp%d" % index, item) for index, item in enumerate(tests, 1)]


def _split(ports):
    """时钟复位端口接 tb_clk_rst_if，其余端口进 DUT 接口。"""
    clock = next((p["name"] for p in ports if p["name"] in CLOCKS), "")
    reset = next((p["name"] for p in ports if p["name"] in RESETS), "")
    signals = [p for p in ports if p["name"] not in (clock, reset)]
    inputs = [p for p in signals if (p.get("direction") or "input").lower() == "input"]
    outputs = [p for p in signals if (p.get("direction") or "").lower() == "output"]
    return clock, reset, inputs, outputs


def _if_file(dut, inputs, outputs):
    lines = [_header("%s_if.sv" % dut, "%s 接口：与 DUT 端口一一对应" % dut),
             "`ifndef %s" % _guard(dut, "IF"), "`define %s" % _guard(dut, "IF"), "",
             "// 时钟复位由 tb_clk_rst_if 提供；drv_skew/mon_skew 为沿后偏移(ns)",
             "interface %s_if (input logic clk_in);" % dut, "",
             "    real drv_skew = 0.1;//驱动侧沿后偏移(ns)",
             "    real mon_skew = 0.1;//采样侧沿后偏移(ns)", ""]
    for port in inputs:
        lines.append("    logic %s%s = '0;//输入，初值不得为 X" % (_width(port), port["name"]))
    for port in outputs:
        lines.append("    logic %s%s;//输出" % (_width(port), port["name"]))
    lines += ["", "endinterface", "`endif //%s" % _guard(dut, "IF"), ""]
    return "\n".join(lines)


def _cfg_file(dut, inputs, outputs):
    lines = [_header("%s_tb_cfg.svh" % dut, "%s 平台参数：可调参数只写在这里" % dut),
             "`ifndef %s" % _guard(dut, "CFG"), "`define %s" % _guard(dut, "CFG"), "",
             "class %s_cfg;" % dut]
    for port in inputs + outputs:
        lines.append("    static const int W_%s = %d;" % (_short(port["name"]).upper(),
                                                         int(port.get("width") or 1)))
    lines += ["    static const int DRAIN_CYCLES = 200;", "endclass",
              "`endif //%s" % _guard(dut, "CFG"), ""]
    return "\n".join(lines)


def _item_file(dut, inputs, outputs):
    lines = [_header("%s_tb_item.svh" % dut, "%s 事务类：逐拍激励、期望与采集" % dut),
             "`ifndef %s" % _guard(dut, "ITEM"), "`define %s" % _guard(dut, "ITEM"), "",
             "class %s_item extends tb_item_base;" % dut, "",
             "    //----------- 激励 ------------"]
    for port in inputs:
        lines.append("    logic %sm_%s;" % (_width(port), _short(port["name"])))
    lines += ["", "    //----------- 比对窗口标记（monitor 回填） ------------",
              "    bit m_watch;", "", "    //----------- 期望（refm 计算） ------------"]
    for port in outputs:
        lines.append("    logic %sm_exp_%s;" % (_width(port), _short(port["name"])))
    lines += ["", "    //----------- 采集（monitor 回填） ------------"]
    for port in outputs:
        lines.append("    logic %sm_out_%s;" % (_width(port), _short(port["name"])))
    shown = " ".join("%s=%%0h/%%0h" % _short(p["name"]) for p in outputs) or "无输出"
    args = "".join(", m_exp_%s, m_out_%s" % (_short(p["name"]), _short(p["name"])) for p in outputs)
    lines += ["", "    function new(string name = \"%s_item\");" % dut, "        super.new(name);",
              "    endfunction", "",
              "    function string do_print();",
              "        return $sformatf(\"%%s id=%%0d %s\", m_name, m_id%s);" % (shown, args),
              "    endfunction", "endclass", "`endif //%s" % _guard(dut, "ITEM"), ""]
    return "\n".join(lines)


def _driver_file(dut, inputs):
    lines = [_header("%s_tb_driver.svh" % dut, "%s 驱动器：先广播给 refm，再在 negedge 驱动接口" % dut),
             "`ifndef %s" % _guard(dut, "DRIVER"), "`define %s" % _guard(dut, "DRIVER"), "",
             "class %s_driver extends tb_driver_base;" % dut, "",
             "    virtual %s_if m_dut_if;//DUT 接口（env 下发）" % dut, "",
             "    function new(string name = \"m_drv\");", "        super.new(name);", "    endfunction", "",
             "    virtual task drive(tb_item_base it);",
             "        %s_item dut_it;" % dut,
             "        $cast(dut_it, it);",
             "        m_drv_mb.put(it);",
             "        @(negedge m_dut_if.clk_in);"]
    for port in inputs:
        lines.append("        m_dut_if.%s = dut_it.m_%s;" % (port["name"], _short(port["name"])))
    lines += ["    endtask", "endclass", "`endif //%s" % _guard(dut, "DRIVER"), ""]
    return "\n".join(lines)


def _monitor_file(dut, outputs):
    lines = [_header("%s_tb_monitor.svh" % dut, "%s 监视器：每拍采样输出，窗口开启后参与比对" % dut),
             "`ifndef %s" % _guard(dut, "MONITOR"), "`define %s" % _guard(dut, "MONITOR"), "",
             "class %s_monitor extends tb_monitor_base;" % dut, "",
             "    virtual %s_if m_dut_if;//DUT 接口（env 下发）" % dut,
             "    bit m_cmp_start = 1'b0;//比对窗口开关（用例控制）", "",
             "    function new(string name = \"m_mon\");", "        super.new(name);", "    endfunction", "",
             "    virtual task collect(ref tb_item_base it);",
             "        %s_item dut_it;" % dut,
             "        @(posedge m_dut_if.clk_in);",
             "        #(m_dut_if.mon_skew);",
             "        dut_it = new(\"mon_item\");",
             "        dut_it.m_watch = m_cmp_start;"]
    for port in outputs:
        lines.append("        dut_it.m_out_%s = m_dut_if.%s;" % (_short(port["name"]), port["name"]))
    lines += ["        it = dut_it;", "    endtask", "endclass", "`endif //%s" % _guard(dut, "MONITOR"), ""]
    return "\n".join(lines)


def _refm_file(dut):
    return "\n".join([
        _header("%s_tb_refm.svh" % dut, "%s 参考模型：compute 为无状态纯函数" % dut),
        "`ifndef %s" % _guard(dut, "REFM"), "`define %s" % _guard(dut, "REFM"), "",
        "class %s_refm extends tb_refm_base;" % dut, "",
        "    function new(string name = \"m_refm\");", "        super.new(name);", "    endfunction", "",
        "    // %s" % REFM_PENDING,
        "    // 由激励字段算出 m_exp_*；定点比对的容差用 fx tol 算出的 GOLDEN_TOL。",
        "    static function %s_item compute(%s_item in);" % (dut, dut),
        "        return in;",
        "    endfunction", "",
        "    virtual task model(tb_item_base it);",
        "        %s_item dut_it;" % dut,
        "        $cast(dut_it, it);",
        "        void'(compute(dut_it));",
        "    endtask",
        "endclass",
        "`endif //%s" % _guard(dut, "REFM"),
        "",
    ])


def _scoreboard_file(dut, outputs):
    diff = " ||\n                     ".join(
        "dut_it.m_out_%s !== exp_it.m_exp_%s" % (_short(p["name"]), _short(p["name"])) for p in outputs) or "1'b0"
    xcheck = " || ".join("$isunknown(dut_it.m_out_%s)" % _short(p["name"]) for p in outputs) or "1'b0"
    return "\n".join([
        _header("%s_tb_scoreboard.svh" % dut, "%s 计分板：期望队列逐拍比对，含 X 态与多余输出检查" % dut),
        "`ifndef %s" % _guard(dut, "SCOREBOARD"), "`define %s" % _guard(dut, "SCOREBOARD"), "",
        "class %s_scoreboard extends tb_scoreboard_base;" % dut, "",
        "    tb_item_base m_exp_q[$];//期望队列（先进先出）", "",
        "    function new(string name = \"m_scb\");", "        super.new(name);", "    endfunction", "",
        "    virtual task push_exp(tb_item_base it);",
        "        m_exp_q.push_back(it);",
        "    endtask", "",
        "    // 控制信号精确比较；定点数据按规格位宽截取后用 GOLDEN_TOL 比较（见 rules/tb.md）。",
        "    virtual task check(tb_item_base it);",
        "        %s_item dut_it;" % dut,
        "        %s_item exp_it;" % dut,
        "        $cast(dut_it, it);",
        "        if (dut_it.m_watch === 1'b0) return;",
        "        if (!m_enable) return;",
        "        if (m_exp_q.size() == 0) begin",
        "            `TB_ERROR($sformatf(\"%s: 多余有效输出（期望队列空）%s\", m_name, dut_it.do_print()));",
        "            m_fail_cnt = m_fail_cnt + 1;",
        "            return;",
        "        end",
        "        $cast(exp_it, m_exp_q.pop_front());",
        "        if (%s) begin" % xcheck,
        "            `TB_ERROR($sformatf(\"%s: 输出 X 态 %s\", m_name, dut_it.do_print()));",
        "            m_fail_cnt = m_fail_cnt + 1;",
        "        end",
        "        else if (%s) begin" % diff,
        "            `TB_ERROR($sformatf(\"%s: 比对失败 %s\", m_name, dut_it.do_print()));",
        "            m_fail_cnt = m_fail_cnt + 1;",
        "        end",
        "        else begin",
        "            m_pass_cnt = m_pass_cnt + 1;",
        "        end",
        "    endtask", "",
        "    virtual function int pending_count();",
        "        return m_exp_q.size();",
        "    endfunction",
        "endclass",
        "`endif //%s" % _guard(dut, "SCOREBOARD"),
        "",
    ])


def _env_file(dut):
    return "\n".join([
        _header("%s_tb_env.svh" % dut, "%s 环境：组件装配与邮箱连接" % dut),
        "`ifndef %s" % _guard(dut, "ENV"), "`define %s" % _guard(dut, "ENV"), "",
        "class %s_env extends tb_env_base;" % dut, "",
        "    %s_driver m_drv;//驱动器" % dut,
        "    %s_monitor m_mon;//监视器" % dut,
        "    %s_refm m_refm;//参考模型" % dut,
        "    virtual %s_if m_dut_if;//DUT 接口（tc 下发）" % dut,
        "    virtual tb_clk_rst_if m_rst_if;//时钟复位接口（tc 下发）", "",
        "    function new(string name = \"m_env\");",
        "        %s_scoreboard scb;" % dut,
        "        super.new(name);",
        "        m_drv = new(\"m_drv\");",
        "        add_child(m_drv);",
        "        m_mon = new(\"m_mon\");",
        "        add_child(m_mon);",
        "        m_refm = new(\"m_refm\");",
        "        add_child(m_refm);",
        "        scb = new(\"m_scb\");",
        "        m_scb = scb;",
        "        add_child(m_scb);",
        "    endfunction", "",
        "    function void connect();",
        "        m_drv.m_dut_if = m_dut_if;",
        "        m_drv.m_drv_mb.connect(m_refm.m_in_mb);",
        "        m_mon.m_dut_if = m_dut_if;",
        "        m_mon.m_out_mb.connect(m_scb.m_duv_mb);",
        "        m_refm.m_out_mb.connect(m_scb.m_exp_mb);",
        "    endfunction",
        "endclass",
        "`endif //%s" % _guard(dut, "ENV"),
        "",
    ])


def _cov_file(dut):
    return "\n".join([
        _header("%s_tb_cov.svh" % dut, "%s 覆盖率骨架：只收集规格书点名的场景" % dut),
        "`ifndef %s" % _guard(dut, "COV"), "`define %s" % _guard(dut, "COV"), "",
        "`ifdef TB_COV_EN",
        "// 按规格书测试要点补 covergroup；未定义 TB_COV_EN 时本文件为空。",
        "`endif",
        "`endif //%s" % _guard(dut, "COV"),
        "",
    ])


def _pkg_file(dut):
    return "\n".join([
        _header("%s_tb_pkg.sv" % dut, "%s TB 包：组件类集合" % dut),
        "`timescale 1ns/1ps",
        "`ifndef %s" % _guard(dut, "PKG"), "`define %s" % _guard(dut, "PKG"), "",
        "`include \"tb_define.svh\"",
        "package %s_tb_pkg;" % dut,
        "    import tb_pkg::*;", "",
        "`include \"%s_tb_cfg.svh\"" % dut,
        "`include \"%s_tb_item.svh\"" % dut,
        "`include \"%s_tb_driver.svh\"" % dut,
        "`include \"%s_tb_monitor.svh\"" % dut,
        "`include \"%s_tb_refm.svh\"" % dut,
        "`include \"%s_tb_scoreboard.svh\"" % dut,
        "`include \"%s_tb_env.svh\"" % dut,
        "`include \"%s_tb_cov.svh\"" % dut,
        "",
        "endpackage",
        "`endif //%s" % _guard(dut, "PKG"),
        "",
    ])


def _tc_prelude(dut, filename, description, comp):
    return [_header(filename, description), "`timescale 1ns/1ps", "`include \"tb_define.svh\"",
            "`include \"%s_tb_pkg.sv\"" % dut, "`ifndef %s" % _guard(dut, comp), "`define %s" % _guard(dut, comp),
            "import %s_tb_pkg::*;" % dut, "import tb_pkg::*;", ""]


def _tc_base_file(dut):
    lines = _tc_prelude(dut, "%s_tc_base.sv" % dut, "%s 用例基类：环境构建与公共时序任务" % dut, "TC_BASE")
    lines += [
        "class %s_tc_base extends tb_test_base;" % dut, "",
        "    %s_env m_my_env;//模块环境（具体类型）" % dut,
        "    virtual %s_if m_dut_if;//DUT 接口（sim_top 赋值）" % dut, "",
        "    function new(string name = \"tc\");", "        super.new(name);", "    endfunction", "",
        "    virtual function void build_env();",
        "        m_my_env = new(\"m_env\");",
        "        m_my_env.m_rst_if = m_rst_if;",
        "        m_my_env.m_dut_if = m_dut_if;",
        "        m_env = m_my_env;",
        "    endfunction", "",
        "    task wait_cycles(int n);",
        "        repeat (n) begin",
        "            @(posedge m_dut_if.clk_in);",
        "            #(m_dut_if.mon_skew);",
        "        end",
        "    endtask", "",
        "    task reset_wait();",
        "        do begin",
        "            @(posedge m_rst_if.clk_in);",
        "        end while (m_rst_if.rst_n !== 1'b1);",
        "        wait_cycles(1);",
        "    endtask", "",
        "    // 逐拍送入激励：窗口在第一拍响应前打开、最后一拍响应后关闭，期望与采样一一配对。",
        "    task drive_seq(%s_item seq[$]);" % dut,
        "        #(m_dut_if.mon_skew + 0.1);",
        "        m_my_env.m_mon.m_cmp_start = 1'b1;",
        "        foreach (seq[i]) m_my_env.m_drv.m_item_mb.put(seq[i]);",
        "        wait_cycles(seq.size());",
        "        #(m_dut_if.mon_skew + 0.1);",
        "        m_my_env.m_mon.m_cmp_start = 1'b0;",
        "        wait_cycles(2);",
        "    endtask",
        "endclass",
        "`endif //%s" % _guard(dut, "TC_BASE"),
        "",
    ]
    return "\n".join(lines)


def _case_file(dut, case, point=None):
    tag = "TC_%s" % case.upper()
    lines = _tc_prelude(dut, "%s_tc_%s.sv" % (dut, case), "%s 用例 tc_%s" % (dut, case), tag)
    lines += [
        "class %s_tc_%s extends %s_tc_base;" % (dut, case, dut), "",
        "    function new(string name = \"%s_tc_%s\");" % (dut, case), "        super.new(name);",
        "    endfunction", "",
        "    virtual task body();",
        "        reset_wait();",
        "        `TB_CASE_BEGIN(\"tc_%s\");" % case,
        "        m_env.m_scb.m_enable = 1'b1;",
    ]
    if point:
        lines += [
            "        // 测试要点 %s：%s" % (point.get("id", ""), point.get("scene", "")),
            "        // 激励：%s" % (point.get("stimulus", "") or "按规格书补"),
            "        // 期望：%s" % (point.get("expect", "") or "按规格书补"),
        ]
    lines += [
        "        // 填写时删掉下面两行，按测试要点构造 %s_item 序列并调用 drive_seq。" % dut,
        "        `TB_ERROR(\"%s\");" % PENDING,
        "        m_env.m_scb.m_fail_cnt = m_env.m_scb.m_fail_cnt + 1;",
        "        `TB_CASE_END(\"tc_%s\", m_env.m_scb.m_pass_cnt, m_env.m_scb.m_fail_cnt);" % case,
        "    endtask",
        "endclass",
        "`endif //%s" % _guard(dut, tag),
        "",
    ]
    return "\n".join(lines)


def _tcall_file(dut, cases):
    lines = _tc_prelude(dut, "%s_tc_all.sv" % dut, "%s 聚合用例：共享环境依次执行全部用例" % dut, "TC_ALL")
    lines += ["class %s_tc_all extends %s_tc_base;" % (dut, dut), "",
              "    function new(string name = \"%s_tc_all\");" % dut, "        super.new(name);",
              "    endfunction", "", "    virtual task body();"]
    for index, case in enumerate(cases, 1):
        lines.append("        %s_tc_%s tc%d = new(\"tc%d\");" % (dut, case, index, index))
    for index, _case in enumerate(cases, 1):
        lines.append("        tc%d.m_rst_if = m_rst_if; tc%d.m_dut_if = m_dut_if; "
                     "tc%d.m_env = m_env; tc%d.m_my_env = m_my_env;" % (index, index, index, index))
    for index, _case in enumerate(cases, 1):
        lines.append("        tc%d.body();" % index)
    lines += ["    endtask", "endclass", "`endif //%s" % _guard(dut, "TC_ALL"), ""]
    return "\n".join(lines)


def _factory_file(dut, cases):
    lines = _tc_prelude(dut, "%s_tc_factory.svh" % dut, "%s 用例工厂：按用例名创建" % dut, "TC_FACTORY")
    lines += ["class %s_tc_factory extends tb_factory;" % dut, "",
              "    static function tb_test_base create(string name);", "        case (name)"]
    for case in list(cases) + ["all"]:
        lines.append("            \"tc_%s\": begin %s_tc_%s t = new(\"tc_%s\"); return t; end"
                     % (case, dut, case, case))
    lines += ["            default: $fatal(1, \"Unknown testcase: %s\", name);", "        endcase",
              "        return null;", "    endfunction", "endclass",
              "`endif //%s" % _guard(dut, "TC_FACTORY"), ""]
    return "\n".join(lines)


def _sim_top_file(dut, clock, reset, inputs, outputs):
    conns = []
    if clock:
        conns.append((clock, "mo_rst_if.clk_in"))
    if reset:
        conns.append((reset, "mo_rst_if.rst_n"))
    conns += [(p["name"], "mo_%s_if.%s" % (dut, p["name"])) for p in inputs + outputs]
    body = ",\n".join("        .%s ( %s )" % (port, net) for port, net in conns)
    return "\n".join([
        _header("%s_sim_top.sv" % dut, "%s 仿真顶层：时钟复位、DUT 例化、用例选择、超时" % dut),
        "`timescale 1ns/1ps",
        "`include \"tb_define.svh\"",
        "`include \"%s_tb_pkg.sv\"" % dut,
        "`ifndef %s" % _guard(dut, "SIM_TOP"), "`define %s" % _guard(dut, "SIM_TOP"),
        "import tb_pkg::*;",
        "import %s_tb_pkg::*;" % dut, "",
        "module %s_sim_top;" % dut, "",
        "    tb_clk_rst_if mo_rst_if ();//时钟复位接口（内嵌时钟生成）",
        "    %s_if mo_%s_if (mo_rst_if.clk_in);//DUT 接口" % (dut, dut), "",
        "    initial begin",
        "        mo_rst_if.rst_n = 1'b0;",
        "        #(`TB_CLK_PERIOD * 3);",
        "        mo_rst_if.rst_n = 1'b1;",
        "    end", "",
        "    // 参数按模块规格书补全。",
        "    %s u_dut (" % dut,
        body,
        "    );", "",
        "    initial begin",
        "        string tc_name;",
        "        int    seed;",
        "        %s_tc_base t;" % dut,
        "        tb_test_base tb;",
        "        if (!$value$plusargs(\"TC=%s\", tc_name)) tc_name = \"tc_all\";",
        "        if ($value$plusargs(\"SEED=%d\", seed)) $srandom(seed);",
        "        tb = %s_tc_factory::create(tc_name);" % dut,
        "        if (!$cast(t, tb)) $fatal(1, \"TC cast fail: %s\", tc_name);",
        "        t.m_rst_if = mo_rst_if;",
        "        t.m_dut_if = mo_%s_if;" % dut,
        "        t.run();",
        "    end", "",
        "    `TB_TIMEOUT_INIT",
        "endmodule",
        "`endif //%s" % _guard(dut, "SIM_TOP"),
        "",
    ])


def _filelist(dut, cases, prefix):
    """编译清单。路径相对仿真工作目录：模块级在 <sys>/work/<dut>，子系统级在 <sys>/work。"""
    common = prefix + "../tb_common"
    plat = "%stestbench/%s" % (prefix, dut)
    lines = [
        "# %s 框架式平台编译清单（tb-gen 生成）" % dut,
        "+incdir+%s" % common,
        "+incdir+%s" % plat,
        "+incdir+%s/tc" % plat,
        "%s/tb_define.svh" % common,
        "%s/tb_clk_rst_if.sv" % common,
        "%s/tb_pkg.sv" % common,
        "%s/%s_if.sv" % (plat, dut),
        "%s/%s_tb_pkg.sv" % (plat, dut),
        "%s/tc/%s_tc_base.sv" % (plat, dut),
    ]
    lines += ["%s/tc/%s_tc_%s.sv" % (plat, dut, case) for case in cases]
    lines += [
        "%s/tc/%s_tc_all.sv" % (plat, dut),
        "%s/tc/%s_tc_factory.svh" % (plat, dut),
        "%s/%s_sim_top.sv" % (plat, dut),
    ]
    return "\n".join(lines) + "\n"


def plan(sys_root, sys_name, dut, force=False):
    """返回 [(相对路径, 内容, 是否已存在)]。"""
    clock, reset, inputs, outputs = _split(dut_ports(sys_root, sys_name, dut))
    specs = cases_for(dut_tests(sys_root, sys_name, dut))
    cases = [name for name, _point in specs]
    base = "testbench/%s" % dut
    files = [
        ("%s/%s_if.sv" % (base, dut), _if_file(dut, inputs, outputs)),
        ("%s/%s_tb_cfg.svh" % (base, dut), _cfg_file(dut, inputs, outputs)),
        ("%s/%s_tb_item.svh" % (base, dut), _item_file(dut, inputs, outputs)),
        ("%s/%s_tb_driver.svh" % (base, dut), _driver_file(dut, inputs)),
        ("%s/%s_tb_monitor.svh" % (base, dut), _monitor_file(dut, outputs)),
        ("%s/%s_tb_refm.svh" % (base, dut), _refm_file(dut)),
        ("%s/%s_tb_scoreboard.svh" % (base, dut), _scoreboard_file(dut, outputs)),
        ("%s/%s_tb_env.svh" % (base, dut), _env_file(dut)),
        ("%s/%s_tb_cov.svh" % (base, dut), _cov_file(dut)),
        ("%s/%s_tb_pkg.sv" % (base, dut), _pkg_file(dut)),
        ("%s/%s_sim_top.sv" % (base, dut), _sim_top_file(dut, clock, reset, inputs, outputs)),
        ("%s/tc/%s_tc_base.sv" % (base, dut), _tc_base_file(dut)),
    ]
    files += [("%s/tc/%s_tc_%s.sv" % (base, dut, case), _case_file(dut, case, point))
              for case, point in specs]
    files += [
        ("%s/tc/%s_tc_all.sv" % (base, dut), _tcall_file(dut, cases)),
        ("%s/tc/%s_tc_factory.svh" % (base, dut), _factory_file(dut, cases)),
        ("%s/%s_tb.f" % (base, dut), _filelist(dut, cases, "../../")),
    ]
    # 子系统级清单只属于子系统顶层：模块级平台先跑一次就占住它的话，
    # 后面真正的子系统级编译清单就再也写不进去了。
    if dut in (sys_name, sys_name + "_top"):
        files.append(("testbench/%s_tb.f" % sys_name, _filelist(dut, cases, "../")))
    return [(rel, text, os.path.isfile(os.path.join(sys_root, rel))) for rel, text in files]


def generate(sys_root, sys_name, dut, force=False):
    """写出骨架。返回逐条说明；已存在的文件不覆盖，除非 force。"""
    written = []
    for rel, text, exists in plan(sys_root, sys_name, dut, force=force):
        path = os.path.join(sys_root, rel)
        if exists and not force:
            written.append("跳过（已存在）%s" % rel)
            continue
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        written.append("写入 %s" % rel)
    return written
