<!-- 作者：vick 邮箱：ykun@yk9811.com -->

# asic_design_agent

这是 IC 子系统框架的常驻入口。长文在 `rules/`，停点定义在 `framework/flow_model.yaml`。不要把规则正文抄进对话。

开始或恢复一个子系统时：

1. `python3 script/framework.py status <sys>`。向开发者报告停点时用停点名字（如"处理流程梳理"），不只报编号；首次提到写"行 2（处理流程梳理）"，之后直接用名字，编号只留在命令与状态字段里。
2. 位宽、合计、地址容量、饱和界只使用 `python3 script/framework.py fx` 的输出，再写入文档。
3. 仿真、lint、综合、时序使用 `python3 script/framework.py run`。工具和主机只在 `toolchain/profiles/`。
4. 停点流转使用 `python3 script/framework.py tick`：它按四相位自动做——指纹失效退回并级联、依赖定稿的未开始停点自动启动、判据齐备的停点自动完成或置送审态（待里程碑）、复核恢复。`advance` 只保留主动退回（`--to 进行中`）与带违例送审（`--to 已送审 --allow-violation`），其余调用不改状态。
5. 裁决使用 `decision`：写走 `commit`/`override`/`withdraw`，查走 `decision <sys> list`（`--json`/`--grep`/`--id`/`--open`）与 `decision <sys> similar --content "…"`（入库前比对正文）。方向性选择和数值由开发者点选。
6. 人机交互只有三条通道，逐项归属见下方动作策略表（唯一事实源在 `framework/flow_model.yaml`）：
   **决策点选**：只问方向、数值、冲突、回修升级、红线；**出现即报，不攒批**，协调性内容与简单决定由主持者自行处理。呈现选项时一并给出"推迟决定"一项（有些决定要等前置条件达成后才能继续）；选了"推迟决定"就用 `python3 script/framework.py problem <sys> defer --id I00x --until <停点号|M1|M2|M3> [--reason "…"]` 落盘，问题保持打开，条件满足后 tick/status 会重新列出。回答后点选即入库，不再追问"是否确认"。
   **里程碑**：M1 方案确认 / M2 规格冻结 / M3 签核放行，开发者读一份审阅包回答通过与否；只有 M3 才要终端照抄。
   **其余动作全自动**：闸门与独立审查记录齐备即完成，写进事件日志与简报，不打断开发者。每个工作包后跑 tick，按 `framework.py tick <sys>` 输出的两张清单（智能体下一步可做的工作 / 等待开发者的事项）行动。
7. 执行与走查鼓励派给子代理并行做，但先按 `rules/methodology.md` 的"派工与并行"划文件归属：同一文件同一时间只有一个写入者，`state.json` 与 `hosts` 生成物只由主持者处理。
8. 写入只用宿主的文件工具（`read`/`edit`/`write`）；**不得**用 `sed`/`awk`/`python`/`perl` 等脚本或 `cat`/`tee` 重定向改写文档、规格、RTL、规则与 `state.json`。脚本只允许生成**全新的派生物**（如旋转因子表 `.svh`），且生成器与产物一起登记、产物头部标"生成物，请勿手改"。理由与处置见 `rules/methodology.md` 的"派工与并行"。读控制信息（裁决、问题、状态、事件）也一律走命令：`decision list`/`similar`、`problem list`、`status --json`、`events`；不以取信息为目的打开 `state.json` 与 `*_status.md`/`*_decision.md`/`*_brief.md`（引擎渲染物，手改会在下一次事务被覆盖）。
9. 调试取证据用 `python3 script/framework.py dbg <sys> …`——这是 EDA MCP 观察面，经 SSH 调远端 `eda-mcp`：`doctor` 自检、`signals`/`waves` 先看有什么、`wave` 出 WaveDrom 时序图、`extract` 按时钟沿与 valid 逐拍导出节点序列（整帧比对用它，**别往 TB 里插探针**）、`npi trace` 查 elaboration 后的真实驱动；静态×动态联立用 `trace`（驱动链带真实值回溯，`--x` 找 X 根因）与 `active`（某一拍哪条驱动在起作用，寄存器给 `--clock` 按采集沿取值）、`windows`（布尔表达式→成立区间）、`diff`（回归 pass/fail 首分歧定位）、`fsm`（状态寄存器实际转移表）；`ctx set` 定一套调试会话的默认用例/信号/时钟/窗口（后续命令自动继承，`fp` 行声明出处与继承项）。装法与自检：`python3 script/framework.py eda-mcp install`，再用 `python3 script/framework.py doctor --mcp` 看结论；MCP 客户端配置见仓库根 `.mcp.json`。细则见 `rules/waveform.md`、`rules/debug.md`。

动作策略表（唯一事实源：`framework/flow_model.yaml` 的 `actions:` 与 `milestones:`；红线永不自动，规则正文只引用本表不重复）：

| 动作 | 归属 | 前提 |
|------|------|------|
| 停点送完成（自动归属，逐行见停点总表） | 自动 | 闸门通过；无未关闭阻断；无在途调试事项；有独立审查记录 |
| 停点送完成（里程碑归属，逐行见停点总表） | 里程碑 | — |
| 方向/数值裁决的入库、改写、撤回 | 红线 | — |
| 记录类裁决的入库、改写 | 自动 | — |
| 停点/模块审查记录 | 自动 | 作者≠审查者；阻断发现为 0 |
| 豁免 | 自动 | 引用开发者点选入库的裁决 |
| 关闭阻断问题 | 自动 | 证据存在且晚于问题登记 |
| 关闭需要取舍的阻断问题 | 红线 | — |
| 调试事项闭合 | 自动 | — |
| 调试定修法 L0/L1 | 自动 | — |
| 调试回修升级 L2/L3 | 决策 | — |
| 带违例送审 | 红线 | 须带裁决号 |
| 下调覆盖率阈值 | 红线 | 须带裁决号 |
| 走查标记收割 | 自动 | — |
| 停点完成或里程碑通过后的 git 快照 | 自动 | — |
| 行 7 派工分批范围 | 自动 | — |
| SDC 约束 | 决策 | — |
| 里程碑确认 | 红线 | — |
| 修改动作策略表或里程碑定义 | 红线 | — |
| 多子系统在途时的消歧选择 | 决策 | — |
| 里程碑 M1 方案确认（覆盖行 1、2、3，阻塞行 4） | 里程碑 | 审阅包齐备后点选确认 |
| 里程碑 M2 规格冻结（覆盖行 4、5、6，阻塞行 7） | 里程碑 | 审阅包齐备后点选确认 |
| 里程碑 M3 签核放行（覆盖行 7、8、9、10、11、12） | 里程碑 | 审阅包齐备后终端照抄 |


停点总表（唯一事实源：`framework/flow_model.yaml` 的 `stops:`、`actions:` 与 `milestones:`；行、角色、闸门、完成方式、审查要求、所属里程碑都由它生成）：

| 行 | 名字 | 角色 | 闸门 | 完成方式 | 审查要求 | 所属里程碑 |
|----|------|------|------|----------|----------|--------------|
| 1 | 信息输入 | `step0_info_input` | numeric、docs | 自动完成（`tick`） | `spec_review`（停点级） | M1 |
| 2 | 处理流程梳理 | `step1_sys_flow` | numeric、docs | 自动完成（`tick`） | `spec_review`（停点级） | M1 |
| 3 | 系统方案 | `step2_sys_plan` | numeric、docs | 自动完成（`tick`） | `spec_review`（停点级） | M1 |
| 4 | 接口定义 | `step3_sys_spec` | numeric、docs | 自动完成（`tick`） | `spec_review`（停点级） | M2 |
| 5 | 结构生成 | `step3_module_spec` | numeric、docs | 自动完成（`tick`） | `spec_review`（停点级） | M2 |
| 6 | 逻辑块设计 | `step3_module_spec` | numeric、docs | 里程碑 M2 收口 | `spec_review`（停点级） | M2 |
| 7 | 模块 RTL | `spec2rtl` | numeric、lint、rtl | 自动完成（`tick`）；在途调试事项挡送审 | `rtl_review`（逐模块） | M3 |
| 8 | 顶层 wrapper | `sys_spec2rtl` | conn | 自动完成（`tick`）；在途调试事项挡送审 | `rtl_review`（顶层） | M3 |
| 9 | TB 构建 | `tb_build` | tc | 自动完成（`tick`）；在途调试事项挡送审 | `tb_review`（停点级） | M3 |
| 10 | 仿真回归 | `rtl_sim` | sim、coverage | 自动完成（`tick`）；在途调试事项挡送审 | 无（闸门与运行记录即审查） | M3 |
| 11 | 综合/STA | `midend_flow` | synth、sta | 里程碑 M3 收口；在途调试事项挡送审 | 无（闸门与运行记录即审查） | M3 |
| 12 | 中端签核 | `midend_flow` | signoff | 里程碑 M3 收口；在途调试事项挡送审 | 无（闸门与运行记录即审查） | M3 |


角色技能在 `skills/`。

**团队模式必读**：团队模式下，主持者与每个成员开工前必读 `rules/team.md` 并遵守，派工提示词带上该必读。

需要细则时再读：`rules/methodology.md`、`rules/steps.md`、`rules/dsp.md`、`rules/spec.md`、`rules/sim.md`、`rules/syn.md`、`rules/waveform.md`、`rules/debug.md`。触发：① 停点上下文（必读）——进入/恢复停点按 `status <sys>` 给出的角色卡、主持卡与模板读，执行角色按角色卡"必读"清单读全套（`framework/hosts/roles.yaml`）；② 动作指向（按需）——规格 `rules/spec.md`、RTL `rules/coding.md`、TB/回归 `rules/tb.md`+`rules/sim.md`、综合 `rules/syn.md`、定点 `rules/dsp.md`、调试 `rules/debug.md`（取证模板 `rules/templates/debug_evidence.md`，经验检索与登记 `rules/pitfalls.md`）、波形 `rules/waveform.md`、wrapper `rules/wrapper.md`；③ 争议回查（兜底）——规则冲突或归属不明，回本表与 `rules/methodology.md`、`framework/flow_model.yaml` 对原文，不凭记忆执行。
