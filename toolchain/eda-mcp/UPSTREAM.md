# eda-mcp 源码来源与保有方式

本目录是 `eda-mcp` 的源码并入点。

## 来源

| 项 | 值 |
|----|----|
| 来源提交 | `e2b5cd6`（*feat(flow): 作业管理 + VCS·nLint·DC·PT 全部作业化*） |
| 导入日期 | 2026-10-15 |
| 导入范围 | 该提交的全部 tracked 文件（32 个），逐文件与上游字节一致 |

未随附的内容：`.git/`、`__pycache__/`、编译产物
`src/eda_mcp/native/fsdbq` 与 `src/eda_mcp/native/*.o`、`install/site/`、
`install/vendor/*.whl`（`install/vendor/.gitkeep` 保留）。这些路径已在仓库根
`.gitignore` 中登记。

## 保有方式

**自本次导入起，以本仓库 `toolchain/eda-mcp/` 为唯一来源。**
来源仓库视为冻结的上一版，不再回同步：
本目录的后续修改（去主机化、波形导出、工具组开关等）只在此处进行，且一律使用宿主的
`read`/`edit`/`write` 文件工具。

主机相关的值不进本目录：只在剖面 `toolchain/profiles/<name>/profile.yaml`，
启动时经 `EDA_MCP_*` 环境变量传入（见 `toolchain/CONTRACT.md`）。

## 本地增量（相对上游 `e2b5cd6`）

以下为并入后在本仓库做的增量（波形导出、工具组开关与相应测试），日后与上游比对时只看这些：

| 项 | 文件 | 内容 |
|----|------|------|
| `wave_extract` | `src/eda_mcp/server.py` | 新增 `wave_extract()`：时钟沿采样、valid 门控、不抽稀（`max_changes=0`）、每节点写一个 `<名>.txt`（每行 `拍号 时间 值`，拍号按 valid 放行的拍从 0 编号，值为 fsdbq 原始值），返回含每个节点文件路径与行数的 JSON |
| `wave_extract` 子命令 | `src/eda_mcp/cli.py` | 新增同名子命令 `wave_extract`（`--fsdb` 为位置参数，`--clock/--edge/--valid/--node NAME=PATH（可重复）/--start/--end/--out-dir`），只输出机器可解析的 JSON |
| 工具组开关 | `src/eda_mcp/config.py` | 新增 `ALL_GROUPS`（env/fsdb/wave/npi/flow/shell）与 `enabled_groups()`；`defaults()` 增加 `security.enabled_groups`（空 = 全开）；`ENV_MAP` 增加 `EDA_MCP_ENABLED_GROUPS` |
| 工具组开关 | `src/eda_mcp/server.py` | 新增 `TOOL_GROUPS` 映射；`tool_functions(cfg)` 按组过滤（未启用组的工具不注册）；`make_server` 透传 cfg |
| 工具组开关 | `src/eda_mcp/cli.py` | 新增 `CLI_GROUPS` 映射；`build_parser(cfg)` 按组注册子命令（未启用组不注册）；`serve` 不分组 |
| 工具组开关示例配置 | `config/eda-mcp.example.toml` | `[security]` 增加 `enabled_groups` 注释与示例（本框架只用 `env,fsdb,wave,npi`，flow 与 shell 关闭） |
| 去主机化 | `tests/integration/npi_smoke.py` | 默认路径改占位符（主机相关值不进本目录，只在剖面，启动时经 `EDA_MCP_*` 环境变量传入） |
| 测试 | `tests/test_wave_extract.py` | 新增 10 个用例：valid 门控与拍号、无 valid 全沿、negedge、时间窗口、多节点各一文件、`--max-changes 0` 不抽稀、JSON 契约、5 类错误路径（假 fsdbq 支持窗口过滤并把调用参数记入 `$EDA_MCP_TEST_ARGS_LOG`） |
| 测试 | `tests/test_groups.py` | 新增 9 个用例：缺省全开、映射覆盖全部工具、子集过滤 MCP 工具列表、未知组报错、`EDA_MCP_ENABLED_GROUPS` 覆盖、CLI 子命令按组注册/不注册、`wave_extract` 子命令参数、缺省全注册 |
| 路径报错基准 | `src/eda_mcp/fsdb.py` | `Fsdb.__init__` 报"FSDB 文件不存在"时附上**入参原样**、**当前 CWD** 与"本工具在远端主机上解析路径"提示。实测踩过：拿本机绝对路径在远端必然不存在，而原报错只回显拼接后的绝对路径，看不出差异 |
| `-s` 显式通配 | `src/eda_mcp/wavegen.py` | 新增 `_is_glob` / `_expand_globs`：`-s` 里含 `*` `?` `[` 的项按 **`signals --pattern` 同一口径**展开成多个信号（只有显式通配才模糊，非通配名字行为不变）；命中为空按"无命中"处理——fsdbq 一行不输出时 `_run` 会当成错误，这里不再让它冒成"fsdbq 无输出"，而是留给精确解析报 not-found；返回值增加 `glob_expanded` 明细 |
| 翻转段摘要 | `src/eda_mcp/wavegen.py`、`cli.py`、`server.py` | 新增 `flip_segments()` 与 `wave_gen(summary="flip")`：窗口内每个信号给 `[t0, t1, 值]` 翻转段（相邻同值合并、不产生零长末段、时钟不进摘要）；CLI 增加 `wave --summary flip`，MCP 工具 `wave_gen` 同步；**默认关**，翻转次数 ≥ 64 时在返回值里给 `summary_hint` |
| 位宽截断显式化 | `src/eda_mcp/wavegen.py`、`cli.py` | 每信号 `detail` 增加 `label_bits` / `label_truncated`，顶层增加 `width_truncated`；超 32 bit 时 CLI 打警告并指向 `-o` 写出的 `<out>_full_data.log`。**现有 `truncated` 语义不变**（值变被 `max_changes` 截断），两者不混 |
| 测试 | `tests/test_wave_modes.py` | 新增 20 个用例：翻转段纯函数（窗口裁剪、同值合并、单点窗、raw 模式）、路径报错三要素、显式通配展开与叶子名族抓取、未命中通配不冒 fsdbq 错误、摘要默认关/超阀提示/非法值拒绝、位宽截断正反与 `truncated` 语义隔离、CLI 与 MCP 门面 |
| `signals --as-args` | `src/eda_mcp/wavedrom.py`、`cli.py` | 新增 `signals_as_args()` 与 `signals --as-args`：把信号列表输出成可直接粘进 `wave -s` 的参数串，配合 `--pattern` 一步取全名（实测：同时抓三个同族信号要抄三次全名） |
| `wave --json` 带图 | `src/eda_mcp/cli.py` | `--json` 改为输出**完整结果对象**（原先把 `json` 字段排除掉，既与 MCP 工具 `wave_gen` 的返回不一致，也让调用方拿不到波形图）；框架 `dbg wave --summary flip` 依赖它一次取全图与段 |
| 框架接线 | `../../framework/dbg.py`、`../../rules/waveform.md` | `dbg wave --summary flip` 透传并落 `case<N>_<标签>_segments.json`、文本模式直接打印段与截断警告；`dbg signals --as-args` 透传；`rules/waveform.md` 增三节（长窗口摘要、取全名、超宽截断）。默认路径不变（不带 `--summary` 时远端命令不加 `--json`） |
| 示例工艺库占位 | `src/eda_mcp/syn.py`、`server.py`、`tests/test_flows.py` | 库名与测试夹具层次名占位化：`TECH_ROOT`/库名改 `yourtech*`（工艺库属于机器剖面，测试断言同步）；`tests/test_join.py` 夹具层次名改 `demo_sys*`/`op_blk*` |
| 宿主口径清理 | `README.md`、`src/eda_mcp/sim.py`、`syn.py`、`workspace.py`、`install/install.sh` | 去掉旧宿主名称与旧路径引用：README 与安装脚本的客户端统一写 DeepSeek Harness；sim/syn 模板依据改为框架剖面 driver（上游旧脚本 `run_sim.sh`/`dc_flow.sh`/`pt_flow.sh` 不随附）；workspace 的跳过目录去掉旧宿主目录。仅文字与注释/一处跳过集合变化，EDA 命令与判定逻辑不变 |

上游原有 6 个测试文件与全部测试逻辑未改动；`tests/test_config.py` 等仍按原样通过。
