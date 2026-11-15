<!-- 作者：vick 邮箱：ykun@yk9811.com -->

# asic_design_agent

**IC 子系统流程框架：人只做判断，机器负责证据。**

把一个 IC 子系统从"信息输入"做到"中端签核"，拆成 12 个**停点**（阶段）：每个停点该写什么、审什么、怎样才算通过，都写成规则和可执行的判据；主持者（AI agent）按规则推进，你只在需要拍板的地方出现。

作者：vick · 邮箱：ykun@yk9811.com

> 第一次接触：直接读 [快速开始](#快速开始)。想先弄懂它是怎么运转的：读 [这是什么](#这是什么) 与 [人机交互只有三条通道](#人机交互只有三条通道)。

## 实践情况

本框架已在实际项目中全流程使用（信息输入 → 中端签核）：

| 项 | 情况 |
|----|------|
| 实践对象 | 复杂控制 + 较复杂计算类子系统 |
| 规模 | 逻辑规模几百万门级；先进工艺下总面积上百万 μm² |
| 效率 | 同复杂度子系统人工设计（需求 → 自测准出）约 9～12 个月，用本框架约 2～3 个月 |
| 消耗 | 月 token 消耗 100 亿～300 亿（含生成、审查、回归的全部往返） |
| 模型 | 纯国产模型的迭代与生成质量约为先进模型的 80%～90%（体感值，较主观） |
| 建议 | 越靠前的产物越要重点关注：流程文档与方案文档直接决定后续架构 |
| 后续方向 | 以本框架为基础扩展到 SoC 设计：各子系统/IP 挂到整芯片目录树下协同工作，顶层可直接获取各子系统/IP 的信息以供参考 |

以上数字为单项目口径，仅供参考。

## 这是什么

本框架不是代码生成器，也不是 EDA 工具。它是一套 **"给 AI 编程助手看的流程说明书 + 记录状态与证据的状态机"**：

- `rules/` 是方法论与各角色、各停点的写法规则（长文都在这里）；
- `framework/` 是流程引擎（闸门、指纹、裁决、审查、里程碑、运行记录）；
- `script/framework.py` 是唯一命令入口（`init` / `status` / `tick` / `milestone` / `run` / `fx` / `dbg` …）；
- `toolchain/` 是 EDA 环境（仿真器、综合器、时序与远端主机配置）；
- `skills/` 是交给 agent 宿主加载的角色技能卡；
- 每个子系统一个目录（如 `demo/`），`state.json` 记录进度，其余目录放产物。

适合你，如果你**想用 AI agent 做 IC 设计、但担心流程失控**：用固定停点、闸门和审查记录，把"agent 说做完了"变成"证据齐了才算完"。框架按 **agent 协同设计**组织：流程由主持者（AI agent）按规则推进，命令是它操作引擎的接口，不面向人工逐步推动流程。

它管到**中端签核**为止：文档 → 规格 → RTL → TB 与仿真回归 → 综合/STA → 签核。不包含布局布线、DFT、后端实现；也不提供工艺库，工具链按你的机器配（见 [工具链与环境](#工具链与环境)）。

### 它靠什么把流程控住

| 机制 | 作用 |
|------|------|
| **闸门**（gate） | 每个停点有一组机械判据：文档章节与占位符、位宽数字是否来自 `fx`、lint 是否 pass、端口是否对得上、用例枚举是否与 `tc_all` 一致、仿真/覆盖率/综合/STA 是否有通过记录……不通过就挡住，报规则号。 |
| **指纹**（fingerprint） | 停点完成时记下产物指纹。已完成停点的产物被改动，`tick` 会把它自动退回进行中并按依赖级联下游，防"偷偷改完当没发生"。 |
| **独立审查** | 停点/模块的审查记录必须作者 ≠ 审查者、阻断发现为 0，并绑定当前产物指纹；文件改了要重新审查。 |
| **裁决记录** | 方向性选择与数值必须由你点选，入库为正式 `D` 号；问题登记为 `I` 号。红线动作（改裁决、下调覆盖率阈值、带违例送审、M3 签核等）永不自动。 |
| **里程碑** | M1 方案确认、M2 规格冻结、M3 签核放行，把需要人判断的事情集中成三份审阅包，不逐停点打扰你。 |
| **审计轨迹** | 每次自动流转写进 `events.jsonl`、简报 `_brief.md`、状态 `state.json`，并在停点完成/里程碑通过后由主持者做 git 快照。 |

需要说明的边界：这套机制**防误推进、留确认记录，但不是安全边界**。agent 与你是同一个系统用户，能直接改 `state.json`。放行是否可信，最终看 `state.json` 的 git 历史与每条确认记录。

## 三个角色

| 角色 | 是谁 | 做什么 |
|------|------|--------|
| **开发者**（你） | 人 | 提供需求材料；回答方向/数值/冲突的**点选**；在 **M1/M2/M3** 读审阅包回答通过与否。不全过程盯盘。 |
| **主持者** | 主会话里的 AI agent | 唯一对你负责的接口。读 `AGENTS.md` 与规则、跑 `status`/`tick`、派发执行与审查子代理、登记问题与裁决、落盘 `state.json`、做 git 快照。 |
| **执行/审查角色** | 子代理 | 按角色卡写文档、写 RTL、搭 TB、跑仿真/综合，或做只读独立审查。一个工作包一个负责人，作者与审查者必须是不同的人。 |

不懂 agent 工作流也没关系：你只需要像对同事说话一样告诉主持者你的决定，其余动作由它按规则完成并汇报。

## 十二个停点

停点就是流程台阶，按顺序走；"行"与"停点"是同一个编号的两种叫法（如"行 2（处理流程梳理）"）。

| 行 | 停点 | 主要产物 | 完成方式 |
|----|------|----------|----------|
| 1 | 信息输入 | `info_input/<sys>_info_overview.md` | 自动完成（`tick`） |
| 2 | 处理流程梳理 | `flow_doc/<sys>_flow.md` | 自动完成（`tick`） |
| 3 | 系统方案 | `plan_doc/<sys>_plan.md` | 自动完成（`tick`） |
| 4 | 接口定义 | `spec_doc/<sys>_spec.md` | 自动完成（`tick`） |
| 5 | 结构生成 | `spec_doc/<模块>_spec.md`（骨架） | 自动完成（`tick`） |
| 6 | 逻辑块设计 | `spec_doc/<模块>_spec.md` | 由 **M2** 收口 |
| 7 | 模块 RTL | `rtl/*.sv` | 自动完成（`tick`） |
| 8 | 顶层 wrapper | `rtl/<sys>_top.sv` | 自动完成（`tick`） |
| 9 | TB 构建 | `testbench/` | 自动完成（`tick`） |
| 10 | 仿真回归 | `work/`（运行记录） | 自动完成（`tick`） |
| 11 | 综合/STA | `dc/`、`pt/`（报告） | 由 **M3** 收口 |
| 12 | 中端签核 | `signoff/<sys>_signoff.md` | 由 **M3** 收口 |

三个里程碑：

| 里程碑 | 名字 | 覆盖停点 | 阻塞 | 你要做什么 |
|--------|------|----------|------|------------|
| **M1** | 方案确认 | 行 1–3 | 阻塞行 4 | 读审阅包，点选"通过"或退回 |
| **M2** | 规格冻结 | 行 4–6 | 阻塞行 7 | 同上 |
| **M3** | 签核放行 | 行 7–12 | — | 读审阅包，在**交互终端**里照抄确认原话 |

## 人机交互只有三条通道

1. **决策点选**——只问方向、数值、冲突、回修升级与红线。出现即报、不攒批。选项里永远有"推迟决定"一项（有些决定要等前置条件达成）。你选完即入库，生成正式 `D` 号，不再追问"是否确认"。
2. **里程碑**——M1/M2 用 `--pick 通过` 点选确认，M3 才要求终端照抄原话。开发者只读一份审阅包、回答通过与否。
3. **其余动作全自动**——闸门、审查、证据齐备即完成，写进事件日志与简报，不打断你。主持者每个工作包后跑一次 `tick`，按它输出的两张清单行动。

红线动作（方向/数值裁决的入库改写撤回、下调覆盖率阈值、带违例送审、关闭需要取舍的阻断问题、修改动作策略表或里程碑定义、里程碑确认）**永不自动**，凭证就是你的点选来源记录。逐项归属见 `AGENTS.md` 的动作策略表（唯一事实源是 `framework/flow_model.yaml`）。

## 快速开始

全程你只出现在三处：**准备环境、给材料、回应判断**。其余每一步都由主持者（AI agent）按规则推进，命令面（见[命令](#命令)）由它调用，人不手工逐步推动流程。

### 第 0 步：准备环境（你唯一亲手做的部分）

只依赖 Python 3 与 PyYAML：

```text
git clone https://github.com/vick98/asic_design_agent.git
cd asic_design_agent
python3 -m pip install -r requirements.txt
```

可选自检（把仓库复制到临时目录，用夹具从行 1 走到行 12，不改动你的工作区）：

```text
python3 script/framework.py selftest
```

然后用支持读取仓库根 `AGENTS.md` 的 AI 编程宿主（本仓库在 **DeepSeek Harness** 下开发使用）打开 `asic_design_agent/`。

### 第 1 步：说一句"开始 demo"

新会话对主持者说：

```text
开始 demo
```

主持者会读 `AGENTS.md`、跑 `status`；发现还没有 `demo/` 时先执行 `init demo` 建工作区并向你汇报。子系统名可自取（字母开头）；同一仓库可以并行多个子系统，它用不带参数的 `status` 就能列出全部。恢复已有子系统时说"继续 demo"。它执行的每条命令都会带进汇报，可随时追问。

### 第 2 步：给材料（你唯一要动手放的东西）

把客户规格书、论文、接口文档、会议记录、邮件等原始材料放进 `demo/info_input/`（或直接发给主持者，由它归位并告诉你路径），然后说一声"材料在 info_input/"。这些是只读原始材料，不会被 agent 改写；没有书面材料时口述给主持者，由它登记成输入记录。行 1（信息输入）从这里开始。

### 第 3 步：只在需要判断时被找

之后主持者每个工作包跑一次 `tick` 自动推进，它看到的输出长这样：

```text
tick demo：自动启动停点 1（见事件日志）
可推进的工作：
- 停点 1 信息输入：进行中，判据齐备时 tick 自动完成（未满足：…）
需要开发者：
- （无：不等你裁决）
```

- **可推进的工作**：agent 接下来自动做的事；
- **需要开发者**：等你点选或做里程碑判断的事——出现即报，不攒批。

`status` 是只读版 `tick`（不写状态、不记事件），主持者随时用它核对位置并向你汇报。

到你面前的判断只有两类，都用一句话回答：

- **决策点选**：主持者把问题连同选项（含"推迟决定"）一起报给你。你回一句选择，它执行 `decision demo commit --from I001 --pick 取乙 --kind 方向` 入库并领正式 `D` 号——不再追问"是否确认"；
- **里程碑**：M1/M2/M3 就绪时它生成审阅包（`milestone demo show --id M1`）给你读。你回答"通过"或退回理由，由它落成 `milestone demo confirm --id M1 --pick 通过` 或 `milestone demo reject --id M1 --reason "接口归属还没定"`。

M3 是唯一需要"终端照抄"的确认：主持者会提示你在交互终端里运行 `milestone demo confirm --id M3 --confirm "确认 demo 签核放行（M3）通过"` 并照抄原话；非交互终端（管道、脚本）会直接拒绝。

### 第 4 步：签核完成

签核记录由引擎渲染到 `demo/signoff/demo_signoff.md`；停点完成/里程碑通过后主持者做 git 快照，提交历史就是审计轨迹。之后可继续新子系统，或把裁决与经验回写规则。

## 一次完整走查，人到底要做什么

| 阶段 | 停点 | agent 在做 | 你要做 |
|------|------|------------|--------|
| 输入与方案 | 行 1–3 | 整理输入、梳理流程、出系统方案 | 提供材料；回答方向/数值点选 |
| **M1 方案确认** | — | 生成审阅包 | 读一遍，点选通过/退回 |
| 详细设计 | 行 4–6 | 接口定义、结构生成、逻辑块规格 | 回答少量接口/定点取舍 |
| **M2 规格冻结** | — | 生成审阅包 | 读一遍，点选通过/退回 |
| 编码与验证 | 行 7–10 | 写 RTL、wrapper、TB，跑仿真与覆盖率 | 回修升级（L2/L3）、带违例送审等点选 |
| 中端 | 行 11–12 | 综合、STA、生成签核记录 | 确认 SDC 等点选 |
| **M3 签核放行** | — | 生成签核审阅包 | 终端照抄确认原话 |

大多数时间你什么都不用做。需要你时，主持者会把问题连同选项（含"推迟决定"）一起报给你。

## 命令

完整命令面，覆盖初始化、流转、裁决、运行与自检——由主持者（agent）按规则调用，人不手工逐步推动流程。每条命令都可加 `--help` 看参数。

```text
# —— 初始化与查看状态
python3 script/framework.py init <sys>
python3 script/framework.py status <sys>
python3 script/framework.py status <sys> --json
python3 script/framework.py status
python3 script/framework.py state verify <sys>
python3 script/framework.py new-doc <sys> --stop N [--module <模块>] [--kind leaf|group]
python3 script/framework.py hosts

# —— 停点流转（tick 是自动挡，advance 只用于主动退回/带违例送审）
python3 script/framework.py tick <sys>
python3 script/framework.py tick <sys> --json
python3 script/framework.py advance <sys> --stop 1 --to 进行中
python3 script/framework.py advance <sys> --stop 1 --to 已送审 --allow-violation --decision <D号>

# —— 里程碑
python3 script/framework.py milestone <sys> show --id M1
python3 script/framework.py milestone <sys> confirm --id M1 --pick 通过
python3 script/framework.py milestone <sys> reject --id M1 --reason "理由"

# —— 定点数值（位宽/合计/地址容量/饱和界只粘贴它的输出）
python3 script/framework.py fx mul '<8,2,t>' '<8,2,t>'
python3 script/framework.py fx sat '<8,3,t>'
python3 script/framework.py fx round --value -5 --n 1 --mode even
python3 script/framework.py fx tol '<8,2,t>' --lsb 1
python3 script/framework.py fx pack --widths 8 3 5
python3 script/framework.py fx addr --depths 16 32 --bits 10
python3 script/framework.py fx latency --cycles 1 2

# —— 审查、模块状态与追溯
python3 script/framework.py module <sys> --row 7 --name alu --state 退回
python3 script/framework.py review <sys> record --stop 7 --module alu --author a --reviewer b --report report/<文件>.md
python3 script/framework.py review <sys> record --stop 9 --author a --reviewer b --report report/<sys>_tb_review.md
python3 script/framework.py review <sys> --stop 1
python3 script/framework.py trace <sys>
python3 script/framework.py trace <sys> --json
python3 script/framework.py gate <sys> --json
python3 script/framework.py digest <sys>

# —— 问题（I 号）与裁决（D 号）
python3 script/framework.py problem <sys> add --kind 待裁决 --options "取甲|取乙" --stop 2 --text "接口归属"
python3 script/framework.py problem <sys> add --kind 阻断 --stop 3 --text 说明
python3 script/framework.py problem <sys> defer --id I001 --until M2 --reason "等接口定稿"
python3 script/framework.py problem <sys> list
python3 script/framework.py problem <sys> list --json --all --grep 违例
python3 script/framework.py problem <sys> close --id <阻断问题号> --evidence <R号|review:<停点>|D号>
python3 script/framework.py decision <sys> commit --from I001 --pick 取乙 --kind 方向
python3 script/framework.py decision <sys> list
python3 script/framework.py decision <sys> list --json --kind 记录 --stop 2 --grep 位宽 --limit 10
python3 script/framework.py decision <sys> list --id D1-002        # 单条全档：正文、来源、修订历史、关闭问题
python3 script/framework.py decision <sys> list --open             # 只看待裁决与已推迟问题
python3 script/framework.py decision <sys> similar --content "…"   # 入库前比对正文（重合度排名）
# 待裁决问题用 decision commit 收口；阻断问题用 problem close
# 带 options/blocks 的问题只能用 D号，其余可用 R号 | review:<停点> | D号

# —— 控制信息查询（只读：--json 与 status --json 同口径，stdout 只有一份 JSON）
python3 script/framework.py events <sys> --grep 裁决入库 --limit 20
python3 script/framework.py events <sys> --json
python3 script/framework.py item <sys> list --json

# —— 调试事项、小结与恢复入口
python3 script/framework.py item <sys> open --kind 调试 --side rtl --text "…"
python3 script/framework.py item <sys> list
python3 script/framework.py summary <sys> add --text "本轮小结"
python3 script/framework.py handoff <sys> set --text "恢复入口：…"

# —— 工具运行（仿真/lint/覆盖率/综合/时序）
python3 script/framework.py run sim --scenario pubip --module pubip_counter --dry-run
python3 script/framework.py run sim --scenario sys --sys <sys> --detach
python3 script/framework.py run wait --job <作业号>
python3 script/framework.py run jobs

# —— 夹具、测试与黄金数据
python3 script/framework.py golden <sys> register --data testbench/<dut>/data/<文件> --gen <生成脚本> --inputs <输入…>
python3 script/framework.py golden <sys> list
python3 script/framework.py selftest

# —— 环境、写权限台账与 EDA 调试
python3 script/framework.py doctor
python3 script/framework.py doctor --mcp
python3 script/framework.py eda-mcp install
python3 script/framework.py lock list
python3 script/framework.py tb-gen <sys> --dut <dut>
python3 script/framework.py waive <sys> add --rule S1 --where info_input/<sys>_info_overview.md --decision D0-001
python3 script/framework.py marks <sys>
python3 script/framework.py marks <sys> --harvest --kind 方向 --stop 2
python3 script/framework.py dbg <sys> waves --module <m>
python3 script/framework.py dbg <sys> signals --case <用例> --module <m>
python3 script/framework.py dbg <sys> wave --case <用例> --signal <信号>
python3 script/framework.py dbg <sys> value --case <用例> --signal <信号> --time <时间>
python3 script/framework.py dbg <sys> extract --case <用例> --clock <时钟>
python3 script/framework.py dbg <sys> npi trace <信号全路径>
```

补充说明：

- `status` 是只读版 `tick`：报当前位置，并列出同样两张清单（可推进的工作 / 需要开发者），不写 `state.json`、不记事件；`status --brief` 只打印简报前两节。
- 控制信息（裁决、问题、事项、事件、状态）的**读取也走命令**：`decision list`/`similar`、`problem list`、`item list`、`events`、`status --json`。`--json` 的口径统一：stdout 只有一份 JSON，错误走 stderr、退出码非 0。`*_status.md`/`*_decision.md`/`*_brief.md` 是引擎随每次事务重渲染的**派生物**——给人读、给 git diff，不手改（手改会在下一次事务被覆盖），agent 不以读信息为目的打开它们。
- `tick` 按四相位自动推进：指纹失效退回并级联、依赖定稿的未开始停点自动启动、判据齐备的停点自动完成或置送审态（待里程碑）、复核恢复。
- `advance` 只保留主动退回（`--to 进行中`）和带违例送审（`--to 已送审 --allow-violation --decision <D号>`）两种用法，其余调用不改状态。
- 结构生成（行 5）由 `tick` 自动完成，逻辑块设计（行 6）随 M2 收口；换机器只改 `toolchain/profiles/` 与 `toolchain/active`。
- `dbg` 是 EDA MCP 观察面：`waves`/`signals` 先看有什么、`wave` 出 WaveDrom 时序图、`extract` 按时钟沿与 valid 逐拍导出节点序列（整帧比对用它，别往 TB 里插探针）、`npi trace` 查 elaboration 后的真实驱动。装法与自检见 `rules/waveform.md`、`rules/debug.md`。

## 子系统目录结构

执行 `init demo` 后：

```text
demo/
├── state.json           # 唯一事实源：停点状态、指纹、裁决、问题、审查与运行记录
├── events.jsonl         # 事件日志（谁在何时改了什么，追加式）
├── demo_status.md       # 渲染物：当前位置与进度（引擎重渲染，不手改）
├── demo_decision.md     # 渲染物：裁决表与待裁决问题（同上）
├── demo_brief.md        # 渲染物：简报（同上）
├── info_input/          # 行 1：原始输入材料 + 信息总览
├── flow_doc/            # 行 2：处理流程
├── plan_doc/            # 行 3：系统方案
├── spec_doc/            # 行 4–6：子系统规格与模块规格书
├── rtl/                 # 行 7–8：模块 RTL 与顶层 wrapper
├── testbench/           # 行 9：TB 平台、用例与数据
├── work/                # 行 10：仿真运行记录与作业
├── dc/  pt/  lint/      # 行 7/11：综合、时序、lint 报告
├── signoff/             # 行 12：签核记录
├── report/              # 独立审查报告等底稿（需要时生成）
└── .state_backups/      # 状态滚动备份（保留最近 3 版）
```

`work/`、`dc/`、`pt/`、`lint/` 是工具产物目录，可不进版本库；`state.json` 与文档产物应进版本库，提交历史就是审计轨迹。

控制信息与渲染物的分界：`state.json` 与 `events.jsonl` 是唯一事实源，只由引擎经命令写入，查询同样走命令；三份 md 与审阅包、签核记录是渲染物，随每次事务自动重生成。裁决的唯一性由入库守卫执行——同一内容只保留一条：重合度达标即要求走 `override` 在原编号下改写（旧正文进 history），拿不准先 `decision <sys> similar` 比对。

## 停点怎么算通过（闸门与证据）

停点完成不靠逐个签字，判据是**证据齐备**。每个停点的闸门、完成方式、审查要求与所属里程碑见停点总表（`AGENTS.md` 开头，由 `python3 script/framework.py hosts` 从 `framework/flow_model.yaml` 生成）。

| 行 | 闸门要什么 |
|----|------------|
| 1–6 | `numeric` + `docs` 闸门通过（章节齐全、无占位、数字来自 `fx`），且送审后产物没被改动 |
| 7 | `numeric`、`lint`、`rtl` 通过：逐模块 lint 记录（`run lint --sys <sys> --rtl <sys>/rtl/<文件或目录>`）+ 独立审查记录（作者 ≠ 审查者、阻断发现为 0），都只对记录时那一版文件有效 |
| 8 | `conn` 通过：顶层 wrapper 审查记录对得上顶层产物指纹 → `连接通过` |
| 9 | `tc` 通过：用例文件 / factory / `tc_all` 三方一致；另有对当前 `testbench/` 指纹的 `tb_review` 独立审查记录 |
| 10 | `sim` + `coverage` 通过：`scenario=sys`、不带 `--tc`、用例数 = `tc_all` 枚举用例数 × seed 数，覆盖率通过且引用最近一次全量回归记录 |
| 11 | `synth` + `sta` 通过：综合有 latch 数（SDC 必须有 `create_clock`）+ 时序无约束路径判 `error`，未约束端点由行 11 闸门决定阻断 |
| 12 | `signoff` 通过：行 11 已完成，签核记录由引擎渲染到 `<sys>/signoff/<sys>_signoff.md` |

已完成停点的产物在完成后被改动时，跑 `tick` 会把它自动退回进行中并按依赖级联（`gate` 仍报 `fingerprint`，不可豁免）。里程碑覆盖范围内的停点进入"待里程碑"，随审阅包集中确认。

## 运行判定（仿真 / lint / 综合 / 时序）

`run` 的 `sim`、`lint`、`coverage`、`synth`、`sta` 不加 `--dry-run` 时，默认剖面会 rsync 到镜像并用 ssh 执行，结束后把报告目录拉回 `<sys>/lint|work|dc|pt/`；`transport: local` 的剖面在本机执行、不回拉。厂商日志的解析只在剖面 driver（`toolchain/profiles/<剖面>/drivers/`），框架按结构化 `checks` 判定。

- **仿真**：逐 seed 记退出码与 RESULT；崩溃（退出码非 0 且不是超时）判 `error`；用例数与 `tc_all` × seed 数不符判 `error`；`--compile-only` 只按编译结果判。
- **覆盖率**：取 DUT 实例在 URG 层次报告里的那一行；`--` 记 `na`；阈值顺序是框架默认 → 剖面 `coverage_defaults` → 子系统 `testbench/cov_gate.txt`，`cov_gate.txt` 只能上调，下调的每一项都要有指向已入库裁决的豁免（规则号 `COV`）。
- **综合**：从 elaborate / `check_design` 日志取 latch 数，取不到判 `error`；读 `--rtl-dir` 对应镜像路径，并逐层读入子系统例化的 `pub_code/` 模块。
- **时序**：分别解析 max 与 min 报告的最差 slack 与违例条数；出现"无约束路径"判 `error`；未约束端点数记进 `checks.unconstrained_endpoints`，由行 11 闸门决定阻断。
- **退出码**：`0` = pass / dry_run；`1` = fail / error；`3` = 当前剖面 `unavailable`（能力未提供，走规则与裁决豁免路径，不算通过）。
- **长任务**：加 `--detach`，作业文件落在 `<sys>/work/jobs/`，用 `run wait --job <号>` 取结论、`run jobs` 看状态。
- 工具输出按 UTF-8 容错解码；综合用过的 SDC 进输入摘要，改 SDC 会让之前的综合 pass 提示「输入已变更」。

## 工具链与环境

- 工具、主机、路径只写在 `toolchain/profiles/<剖面>/`；`toolchain/active` 一行指定当前剖面（仓库自带 `example`（占位符示例，按你的 EDA 主机与工具链改）与 `_template` 起手模板）。
- 换机器/换工具链通常只改剖面配置与 `toolchain/active`，不用动规则与流程。
- 远端 EDA 调试走 `eda-mcp`：`python3 script/framework.py eda-mcp install` 装到 EDA 主机，再用 `python3 script/framework.py doctor --mcp` 看结论；MCP 客户端配置见仓库根 `.mcp.json`。仓库内的 `toolchain/eda-mcp/` 是上游组件，保留其原始作者与许可信息。

## 夹具与自检

- 夹具在 `framework/fixtures/mini/` 与 `framework/fixtures/sample/`；`selftest` 把仓库复制到临时目录（环境变量 `ADF_ROOT`），在副本里用夹具从行 1 走到行 12，并确认失败的仿真不能把行 10 送审。
- 自测不改当前检出，也不改 `toolchain/active`；签核记录写在副本里。
- 框架自身测试在 `framework/tests/`。改框架先在这里补一个会失败的用例，再动实现（`python3 -m pytest framework/tests -q`）。

## 术语表

| 词 | 含义 |
|----|------|
| 停点 / 行 | 流程台阶，1–12；如"行 2（处理流程梳理）" |
| 里程碑 | 集中做人的判断的三次确认：M1 方案确认、M2 规格冻结、M3 签核放行 |
| 闸门（gate） | 停点的机械判据，不通过则报规则号 |
| 指纹（fingerprint） | 产物内容的摘要，用来判断"送审/完成之后有没有被改" |
| 裁决（D 号） | 你对方向/数值/冲突的点选记录，入库后成为正式依据 |
| 问题（I 号） | 待你点选或待证据关闭的问题（待裁决 / 阻断） |
| 红线 | 永不自动、必须由人确认的动作类别 |
| 主持者 | 主会话里的 AI agent，唯一对你负责、唯一写 `state.json` |
| 角色卡 | `skills/` 下给执行/审查子代理的技能说明 |
| 审阅包 | 里程碑时给你读的汇总（闸门摘要、产物、裁决、审查结论） |
| `tick` | 自动推进引擎：复核证据、自动完成/送审、输出两张清单 |
| 简报（brief） | `<sys>/<sys>_brief.md`，自愿阅读的进展摘要 |
| 渲染物 | 引擎随每次事务从 `state.json`/`events.jsonl` 重生成的派生物（`*_status.md`、`*_decision.md`、`*_brief.md`、里程碑审阅包、签核记录）：给人读、给 git diff，不手改 |
| `fx` | 定点数值计算器；位宽、合计、地址容量、饱和界只粘贴它的输出 |
| `run` | 工具运行入口：仿真、lint、覆盖率、综合、时序 |
| `dbg` | EDA MCP 调试观察面：波形、信号、逐拍导出、elaboration 驱动追溯 |

## 常见问题

**Q：我不懂 agent 工作流，能用吗？**
能。把仓库交给支持 `AGENTS.md` 的 AI 宿主，说"开始/继续 <sys>"，主持者会按规则推进；你只需要回答点选与里程碑。

**Q：agent 会不会自己乱改、偷偷把停点标完成？**
停点完成要过闸门、要有绑指纹的审查记录；完成后改产物会被 `tick` 退回并级联。所有自动流转进事件日志，git 历史可回查。但它不是安全边界，重要节点请读审阅包并保留 git 历史。

**Q：为什么总是让我点选，不能自己决定吗？**
方向、数值、冲突、回修升级与红线属于"取舍"，必须由人定，避免 agent 编数字或静默取舍。选项里给了"推迟决定"，前置条件没到可以先挂着。

**Q：工具还没装，能走到哪一步？**
行 1–9 主要产出文档与代码，可以先走；行 10 起需要仿真器/综合器/时序工具。装工具只改 `toolchain/profiles/`（或先用 `--dry-run` 验证命令线路）。

**Q：M3 为什么要终端照抄？**
签核放行是最高风险动作，`confirm` 会要求交互终端里输入与提示逐字相同的原话；管道、脚本、非交互环境一律拒绝。M1/M2 只需点选确认。

**Q：生成物能直接改吗？**
`AGENTS.md`、`skills/**`、`rules/steps.md`、`rules/pubip.md` 由 `python3 script/framework.py hosts` 从源生成（改源后重跑）。其余 `rules/**` 是手写源文档。仓库约定：脚本与文档首行带作者注释，生成物的作者注释由生成器写。

## 作者

- 作者：vick
- 邮箱：ykun@yk9811.com

本仓库的脚本代码与文档首行均带作者信息注释（`# 作者：vick 邮箱：ykun@yk9811.com` 或 Markdown 的 `<!-- 作者：vick 邮箱：ykun@yk9811.com -->`）；生成物（`AGENTS.md`、`skills/**`、`rules/steps.md`、`rules/pubip.md`）由生成器写入同一注释。无注释语法的 JSON 配置文件（`.mcp.json`、`framework/delivery_schema.json`）不写注释；`pub_code/` 的 IP 设计代码（文件头用 FILE_HEADER 注释）与 `toolchain/eda-mcp/` 的上游组件不在该注释范围内。
