<!-- 作者：vick 邮箱：ykun@yk9811.com -->

# 编码主持

停点 7 到 12 的主持卡。恢复方式与设计主持相同：status、恢复入口、阻断问题、marks；
流程索引与裁决、文档口径见 `rules/steps.md`、`rules/decision.md`、`rules/documents.md`。
每个动作的归属见 AGENTS.md 的动作策略表，本卡只写怎么做。

## 载入

1. 行 1–6 未全部完成（M2 未确认）时不进本卡，回 `rules/host/design.md`
2. 派发 `spec2rtl`、`tb_build` 前先出交付 IR：`python3 script/framework.py digest <sys>`，端口名、方向、位宽以 IR 为准
3. 编码与验证角色的返回只收输出小结；状态由主持者按命令落盘
4. **每个工作包后跑 tick**：`python3 script/framework.py tick <sys>`，按输出的两张清单行动；行 7 的模块级进展靠它逐模块收敛。

## 每行要点

每行的角色、闸门、完成方式、审查要求与所属里程碑见停点总表（`rules/steps.md` 开头，同表也在 `AGENTS.md` 开头；由 `python3 script/framework.py hosts` 从 `framework/flow_model.yaml` 生成）；本卡不复述。编码阶段特有的口径：

- 行 7 逐模块收敛：一个模块一份 lint 通过与 `rtl_review` 记录，记录只对那一版文件有效，文件改了要重新 lint 与审查
- 行 9 的 `tb-gen` 骨架用例在标记填完前判失败，不能直接拿去跑行 10
- 行 12 的签核记录只引用运行记录，不抄工具日志

行 11、12 由里程碑 M3 收口：覆盖停点就绪后进入"待里程碑"，`python3 script/framework.py milestone <sys> show --id M3` 生成审阅包（自动完成清单、回修清单、综合与时序运行记录、SDC 全文、覆盖率、抽样 2 个模块的 RTL 走查、签核记录），确认时唯一保留终端照抄：

```text
python3 script/framework.py milestone <sys> confirm --id M3 --confirm "确认 <sys> 签核放行（M3）通过"
```

确认语句按固定模板生成，开发者在自己终端照抄执行，不问措辞、主持者不模拟终端。

## 状态口径

- 与开发者交流停点用名字（例："模块 RTL"、"综合/STA"），首次出现写"行 7（模块 RTL）"；只报编号开发者不知道在干什么
- 行 7 的"lint 通过"来自该模块的运行记录，一次 lint 只覆盖 `--rtl` 覆盖到的模块
- 行 7 的"审查通过"由 `review <sys> record --stop 7 --module <m> --author <派工号> --reviewer <派工号> --report report/<文件>.md` 写入，不要终端；框架按报告发现表计发现数与阻断数，阻断必须为 0，作者与审查者必须不同。lint 与审查都只对记录时的那一版文件有效，模块文件一改就要重新 lint 与审查；重推不再分首达与否，一律按自动判据走
- 行 7 派工分批由主持者自行划分（动作策略表：自动），自动的是定位与触发，不是跳过抽查；`rtl_review` 派给没写这一批的子代理
- `tb-gen` 生成的骨架用例在填写前判失败，不能直接拿去跑行 10
- 行 8 的连接通过、行 9 的用例装配通过由闸门写入，不手工置位
- 仿真失败按 `rules/debug.md` 登记调试事项（`item <sys> open --kind 调试 --side tb|rtl|spec --text "<事项一句话>"`），收敛后 `item <sys> end --id <M号>` 闭合；存在在途调试事项时哪些停点不得送审，见停点总表的"完成方式"列（引擎按 `flow_model.yaml` 的 `blocked_by_items:` 常驻判定）
- RTL 改动先按 `rules/debug.md` 的 §调试回修 定级：L0/L1 由智能体按证据决定并进简报，L1 以上回修模块规格书并退回行 6，L2 还要上行子系统规格书；L2/L3 是决策（打断），收尾入库裁决（`item <sys> end --id <M号> --level L2|L3 --sync "<回修章>" --decision <D号>`）；定级结果与回修范围在派工前说清

## 并行派工

- **先划文件归属再派发**：同一文件同一时间只有一个写入者；要改别人负责的文件时先停下报告，不并行改
- 行 7 按模块分组时，一批只派一个子代理写，批与批的文件不重叠；`rtl_review` 派给没写这一批的子代理（走查与生产分离），作者与审查者派工号由主持者登记
- `tb_build` 独占 `testbench/`，`midend_flow` 独占 `dc|pt|lint/` 与 SDC；不要同时派两个改同一目录的子代理
- 完整约束（含公共文件串行、生成物只改源再重新生成）见 `rules/methodology.md` 的"派工与并行"

## 落盘

每轮刷新 summary、problem、恢复入口（`handoff set`）；停点完成或里程碑通过后的 git 快照由主持者自动提交，提交历史就是审计轨迹。
签核记录放 `<sys>/signoff/<sys>_signoff.md`，不抄日志。
