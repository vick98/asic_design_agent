# eda-mcp —— EDA 工具链 MCP 服务

把 EDA 服务器上的工具链（Verdi NPI / FSDB 波形 / VCS / DC·PT / nLint）封装成
[MCP](https://modelcontextprotocol.io) 工具，供 DeepSeek Harness 等
客户端直接调用。

**设计目标：一次装好、换台 EDA 机只改配置。** 包里没有任何硬编码的机器路径。

> 本文出现的 `run_sim.sh`、`script/dc_flow.sh`、`script/pt_flow.sh` 是上游旧工作区的参考脚本，本仓库不随附；现行命令与判定口径见 `rules/sim.md`、`rules/syn.md`，实际调用由框架剖面 driver 完成。

---

## 1. 它解决什么问题

| 旧做法 | 现在 |
|--------|------|
| 本机编译 `aic_tool_trace`（依赖 Verible 全家桶，换平台要重编） | 服务器侧 `wave_gen`：FFR + Python，**零额外依赖、零编译**（除一次 `fsdbq`） |
| 波形只有 VCD，靠本机工具转时序图 | 原生 FSDB（框架 `run sim --wave fsdb`），服务器侧直读 |
| 每次查 RTL 层次都要人工开 Verdi | NPI 温进程 daemon，查询毫秒级 |

**整个方案里唯一需要编译的只有 `fsdbq`**（FFR 薄壳，`libnffr.so` 导出的是 C++
mangled 符号）。那是工具安装期编译一次，**与 RTL/TB 无关**，设计代码照旧每次仿真由 VCS 编译。

---

## 2. 快速开始

```bash
# 服务器侧（只需 python3 >= 3.9 与 g++，不需要 pip / sudo / 网络）
scp -r eda-mcp <eda-host>:~/
ssh <eda-host> 'bash ~/eda-mcp/install/install.sh --verdi-home /opt/synopsys/verdi'

# 自检
eda-mcp doctor
eda-mcp doctor --deep /path/to/wave_case1.fsdb

# 波形 -> WaveDrom JSON
eda-mcp signals wave_case1.fsdb                     # 列信号
eda-mcp query   wave_case1.fsdb reg_counter         # 查信号（支持叶子名模糊）
eda-mcp wave    wave_case1.fsdb -t 100ns -c 10 \
      -s top.u_dut.reg_counter -s top.u_dut.o_cnt_en -o out.json
```

客户端（DeepSeek Harness）：

```json
{ "mcpServers": { "eda": {
    "command": "ssh",
    "args": ["<eda-host>", "~/.local/bin/eda-mcp-server"]
} } }
```

---

## 3. 已实现

### 3.1 波形（FFR / FSDB）—— **不需要 Verdi、不需要 License、不需要 X**

| 工具 | 说明 |
|------|------|
| `fsdb_info(path)` | scale unit、仿真器版本/日期、min/max time |
| `fsdb_scopes(path, root, max_depth)` | 波形内层次树 |
| `fsdb_signals(path, scope, pattern, limit)` | 信号列表（含位宽） |
| `fsdb_find(path, pattern, limit)` | 按名找信号 |
| `fsdb_value(path, signal, time, fmt)` | 单点取值（`<= time` 最近值变） |
| `fsdb_wave(path, signals, t0, t1, max_changes, fmt)` | 值变序列，超限抽稀并告知 |
| `fsdb_check(path)` | 合法性与可读性 |

### 3.2 WaveDrom 时序图 —— 原 `aic_tool_trace` 的服务器侧等价实现

| 工具 | 等价旧选项 |
|------|-----------|
| `wave_gen(source, signals, time, cycles, start, end, clock, timescale, out)` | 主流程（VCD/FSDB 均可作输入） |
| `wave_list_signals(source)` | `--list-signals` |
| `wave_query(source, name)` | `--query` |

* **`time` + `cycles`**：以 `time` 为**中心**截取 `cycles` 个周期（对齐到时钟上升沿）
* **`start` + `end`**：截取区间（与 `time` 互斥）
* **`clock`**：缺省先在信号表里找 `*clk*`，找不到再自动检测（变异系数 + 上升沿数打分，带确定性 tie-break）
* 输出 JSON 与原工具 **逐字节一致**（回归见 §6）

### 3.3 Verdi NPI —— 设计模型（RTL 层次 / 信号 / 驱动负载）

**温进程 daemon**：`debImport` 一次、长期服务。实测启动 **2.2 s**（小设计；
大设计约 30 s），之后每次查询 **≈11 ms**。托管 Xvfb 自动挑空闲 display。

| 工具 | 说明 |
|------|------|
| `npi_open_design(design_id, files, filelist, top, sv)` | 打开/复用设计（冷启动只一次） |
| `npi_list_designs()` / `npi_close_design(design_id)` | 池概览 / 回收 |
| `npi_hierarchy(design_id, root, max_depth, pattern)` | **层次树**（定义名 + 源文件:行号），一次给整棵 |
| `npi_object(design_id, path)` | 对象详情：类型/位宽/左右界/方向/网络类型/**源码原文** |
| `npi_module(design_id, path)` | 模块详情：端口、网络与寄存器、参数、子实例（分组去重） |
| `npi_find(design_id, pattern, limit)` | 通配搜索信号/参数 |
| `npi_trace(design_id, signal, direction)` | **elaboration 后的真实驱动/负载**（NPI L1，零编译） |
| `npi_equivalent(design_id, signal)` | 等价信号 |

位宽的取法（实测校准）：源码声明行里的写死范围最可信；否则用 `npiSize`
——**对信号是「声明左界」**（`[8:0]` → 8 → 宽 9；标量恒为 1），
**对参数就是位宽本身**（`parameter int MAX_NUM` → 32）。三者在实现里分开处理。

> 复用已存活的 daemon 时**不会重新渲染 daemon 脚本**（客户端那侧没有设计来源信息）——
> 这是实测踩到的坑：早期版本会在每次查询前重新 `prepare()`，导致复用路径报「没有指定设计来源」。

### 3.4 环境

| 工具 | 说明 |
|------|------|
| `eda_env_info()` | 工具路径、VERDI_HOME、配置来源、逐项检查 |
| `eda_doctor(deep, fsdb)` | 一键自检；`deep` 追加真实波形冒烟 |

---

### 3.5 作业与流程（VCS / nLint / DC / PT）

长任务**一律作业化**：`submit` 立刻返回 `job_id`，用 `job_status` / `job_log` 轮询，
需要同步时给 `wait_seconds`。状态全部落盘（`<cache>/jobs/<id>/`），
MCP 服务端重启也不丢；进程 `start_new_session` 起独立进程组，可整组终止。

| 工具 | 说明 |
|------|------|
| `job_list(limit, state)` / `job_status(job_id)` / `job_log(job_id, tail_lines, grep)` / `job_kill(job_id)` | 作业管理；`job_status` 自动附流程判定 |
| `sim_compile(scenario, sys_name, module, wave, wave_vcd, cov, defines, wait_seconds)` | 对齐框架 `run sim` 场景 A/B/C；`wave` 走 FSDB（自动 `+nolibcell` + PLI），`wave_vcd` 退回 |
| `sim_run(scenario, ..., tc, seed, timeout_us, wall_timeout_s, wait_seconds)` | 运行 simv |
| `sim_summary(job_id)` | 解析 log 给 PASS/FAIL（**退出码不可靠**） |
| `sim_clean(...)` | 清理编译产物（保留日志与波形） |
| `lint_run(files)` | nLint（仅可综合 RTL；TB 不做 lint 工具检查） |
| `syn_run(target, top, lib, sdc, tcl, wall_timeout_s)` | **DC 综合**；`lib` 取 `std|stdht` |
| `sta_run(target, top, corner, netlist, sdc)` | **PT STA**；`corner` 取 `tt|ss|ff` |
| `shell_run(command, cwd, timeout_s)` | 逃生舱，**默认禁用**（`security.allow_shell`） |

判定一律**读报告不看退出码**（`rules/syn.md` 准出标准）：

* `dc.log` / `pt.log` 有 `^Error` → 运行错误
* `<top>_syn_timing.rpt` / `<top>_sta_{setup,hold}.rpt` 有 `slack (VIOLATED)` → 时序违例
* 报告里是 **`No constrained paths`** → 判 PASS 但**显式告警**（多半是 SDC 没给时钟约束）
  —— 别把"没有受约束路径"当时序达标

真机实测（pub_code/pubip_counter）：`sim_compile` FSDB 档 1.6 s、`sim_run` 0.7 s
（74/74 PASS）、`lint_run` 0.5 s（0 违规）、`syn_run` 18.9 s（PASS，报告齐全）、
`sta_run` 1.0 s（PASS，但无受约束路径——该模块当时没有 SDC 时钟约束）。

> `.f` 清单里的**旧机器前缀**会被自动替换成镜像根（按镜像 basename 对齐，
> 不依赖任何硬编码路径；也可用 `eda.local_prefix` 显式指定）。

## 4. 两个必须知道的坑

### 4.1 FSDB 波形缺 DUT 信号 —— 必须加 `+nolibcell`

VCS 默认把 `-y`/`-v` 找到的模块当作 **library cell**，而 Verdi 的 FSDB dumper
**会整棵跳过 library cell**。现象：FSDB 里只剩 TB 与接口信号，DUT 子树全缺，
而且**文件照常生成、不报任何错**。VCD 的 `$dumpvars` 不受影响，所以这个坑只在 FSDB 档暴露。

修法：编译命令行加 `+nolibcell`（框架 `run sim --wave fsdb` 已内置）。

已实测**无效**的修法：`$fsdbDumpvars(0, <top>)` 显式实例名、字符串实例名、
`$fsdbDumpvars("+all")`、`+fsdb+skip_cell_instance=1|2|3|4`（该选项只管
`` `celldefine`` 单元，不管 `-y` 库单元）。

自检：`eda-mcp signals <fsdb> | grep -c hier` 的信号数应与同一份 VCD 的 `$var` 条数一致。

### 4.2 FSDB PLI 需要 `-fno-lto`

`$VERDI_HOME/share/PLI/VCS/LINUX64/pli.a` 是 GCC 4.8 编译的胖 LTO 归档，
GCC 10+ 的 `lto1` 拒绝其字节码；加 `-fno-lto` 直接用其中的机器码即可，**不需要旧版 GCC**。
且 `vcs` 包装器会拦截 `-LDFLAGS` 原样透传，故必须写全：

```bash
-debug_access+all -P $VERDI_HOME/share/PLI/VCS/LINUX64/novas.tab \
  $VERDI_HOME/share/PLI/VCS/LINUX64/pli.a \
  -LDFLAGS "-no-pie -Wl,--no-as-needed -fno-lto"
```

---

## 5. 配置

分层（后者覆盖前者）：内置默认（按 `$VERDI_HOME` / PATH 探测）→
`/etc/eda-mcp/config.toml` → `~/.config/eda-mcp/config.toml` → 环境变量 `EDA_MCP_*`。

完整示例见 [`config/eda-mcp.example.toml`](config/eda-mcp.example.toml)。
**换到另一台 EDA 机时只需改路径类字段**（`eda.workspace_root`、各 `*_bin`、`verdi_home`）。

迁移 checklist：

1. `scp -r eda-mcp <新机>:~ && ssh <新机> 'bash ~/eda-mcp/install/install.sh'`
2. 写 `~/.config/eda-mcp/config.toml`
3. `eda-mcp doctor` → 4. `eda-mcp doctor --deep <fsdb>` → 5. 客户端改一行 ssh 别名

---

## 6. 回归证据（与旧工具逐字节比对）

对同一份设计（`pubip_counter`，7 个用例），用原 `aic_tool_trace`（读 VCD）与
`wave_gen`（读按用例切分的 FSDB）生成 JSON 并比 md5：

* 信号集覆盖：1 bit / 多 bit / **real** / 模糊叶子名 / 不存在信号（共 10 个）
* **用例内 7/7 逐字节一致**（`--time+--cycles` 6 例 + `--start+--end` 1 例）
* `--query` 输出与原工具逐字节一致

唯一差异（**属旧行为缺陷，非回归**）：当请求窗口越过**用例边界**时，旧工具读的是
「7 个用例同一个 VCD」，会**借用上一个用例的时钟沿**凑够周期数；新工具读的是
按用例切分的 FSDB，会在边界处正确夹紧，故周期数少于旧工具。

---

## 7. 目录

```
eda-mcp/
├── pyproject.toml
├── config/eda-mcp.example.toml
├── install/install.sh              # 无 pip 安装：编 fsdbq + 装包 + 生成启动器
├── src/eda_mcp/
│   ├── cli.py                      # eda-mcp 命令入口
│   ├── config.py                   # 分层配置 + 工具探测
│   ├── doctor.py                   # 环境自检
│   ├── fsdb.py                     # FFR 封装（fsdbq 子进程 + 行协议解析）
│   ├── wavedrom.py                 # clock_detector / wave_generator 的 Python 移植
│   ├── wavegen.py                  # wave_gen / wave_list_signals / wave_query
│   ├── server.py                   # MCP 装配（内置零依赖 stdio / 兼容 SDK v1·v2）
│   ├── mcp_stdio.py                # 零依赖 MCP stdio 实现（JSON-RPC 2.0 逐行）
│   ├── xvfb.py / daemon.py / npi.py# Verdi 设计模型温进程与查询
│   ├── tcl/prelude.tcl             # daemon 侧 TCL 查询过程
│   ├── jobs.py / workspace.py      # 作业管理 / 场景与路径护栏
│   ├── sim.py / syn.py             # VCS·nLint / DC·PT 流程
│   └── native/{fsdbq.cpp,Makefile} # FFR 薄壳（唯一需要编译的部分）
└── tests/
```

## 8. 尚未实现

覆盖率（`urg` / 覆盖率合并工具在本机不可用）、NPI L1 高级查询（表达式反编译 /
伪代码 / 跨模块连接）、`workspace_sync`（反向 SSH）、门级仿真（网表 + SDF 反标）流程、
设计 daemon 预热与导入缓存（前期探索记录未随本仓库发布）。
