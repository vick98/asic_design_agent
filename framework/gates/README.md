<!-- 作者：vick 邮箱：ykun@yk9811.com -->

# 闸门规则号

`gate` 与 `advance` 都经 `framework/gates/run.py` 的 `run_gates`。

本表与代码里的 `rule` 字段逐条对应，`framework/tests/test_docs_gate_numeric.py` 会双向比对：代码里出现的每个规则号都在表中，表中每个编号都能在代码里找到（COV 是覆盖率豁免规则号，由 `framework/coverage.py` 消费，属表内显式例外）。

| 编号 | 含义 | 所属闸门 | 原来的编号 |
|------|------|----------|------------|
| docs | 停点产出文件缺失 | docs | 引擎缺文件检查 |
| K1 | 文档仍有 `mark:` 或 `@@` | docs | 原与参数检查共用 M1 |
| P1 | 标题与正文之间有表，或简介超过一句 | docs | P1 |
| P2 | 标题含过程字样 | docs | P2 |
| P3 | 仍写旧的 `s` 符号 | docs | P3 |
| P4 | 章节正文超过 80 行 | docs | P4 |
| P5 | 同一文档内长句重复 | docs | P5 |
| P6 | 两份文档长句重复 | docs | P6 |
| S1 | 章节缺失或顺序不对 | docs | S1 |
| S2 | 必填章节正文为空 | docs | S2 |
| S3 | 产物从第 1 节写起 | docs | S3 |
| S4 | 规格书交叉引用落空 | docs | S4 |
| S5 | 模块表有名字但没有规格书 | docs | S5 |
| S6 | 表列与章节定义不一致 | docs | S6 |
| S7 | 章节正文或开篇简介仍是占位（`待填写`、`待设计`、`TODO`、`TBD`） | docs | 新增 |
| fx | 算式结果与工具箱不一致 | numeric | fx |
| fx-stamp | 算式戳记缺失或不匹配 | numeric | fx-stamp |
| fx-bare | 裸格式没有算式、命名节点或戳记。合法写法只有三种（见 `rules/dsp.md`）：算式加 `stamp:`（戳记在本行或下一行，按就近归属）；`` `节点名` <W,I,t> ``；`N（<W,I,t>）` 且 N 等于格式总位宽 | numeric | fx-bare |
| D1b | 流程运算链与节点表不一致 | numeric | D1b |
| D2 | 位域合计与声明的「合计」不符 | numeric | D2 |
| D3 | 区段合计字数与声明的「合计 N 字」不符 | numeric | D3 |
| D4 | 端口位宽与定点格式总位宽不一致 | numeric | D4 |
| D5 | 同名定点格式在不同位置不一致 | numeric | D5 |
| D6 | 区段字数超过地址位宽容量 | numeric | D6 |
| D6a | 区段深度因子乘积与声明不符 | numeric | D6a |
| D6b | 定点格式不合法 | numeric | D6b |
| D7 | 参数取值不唯一：同一份文档内阻断；跨文档默认提示，子系统规格书全局参数表里的阻断 | numeric | D7 |
| D8 | 观测口不是 16 位 | numeric | D8 |
| latency | 逻辑块描述没有拍数 | numeric | latency |
| M0 | RTL 或 module 声明缺失 | rtl | M0 |
| M1 | RTL 参数与规格书不一致 | rtl | M1 |
| M2 | 端口只在一侧出现 | rtl | M2 |
| M3 | 端口方向不一致 | rtl | M3 |
| M4 | 端口位宽不一致 | rtl | M4 |
| C0 | 顶层或例化缺失 | conn | C0 |
| C1 | 例化端口未连或多连 | conn | C1 |
| C2 | 例化未传参数 | conn | C2 |
| C3 | 规格书连接表与端口表不闭合 | docs | C3 |
| CD1 | 连接表两端的时钟域不同，但说明列没有已登记的跨域单元名，也没有有效裁决号 | conn | 新增 |
| cdc | 端口表出现两个以上时钟域时缺 cdc 通过记录或点选入库的裁决豁免 | conn | 新增 |
| W3 | 裁决注记对不上裁决表 | docs | W3 |
| U1 | 「待确认」标注的同一行缺仍打开的问题号（`〔I0xx〕` 或 `[I0xx]`） | docs | 新增 |
| TR1 | 强约束输入要点没有任何测试要点追溯（行 6 起检查，沿各表「来源」列逐级追溯；权威/参考档只提示） | docs（行 6 起） | 新增 |
| T0 | 没有用例目录或用例文件 | tc | T0 |
| T1 | factory 或 tc_all 缺失 | tc | T1 |
| T2 | 用例文件、factory、tc_all 不一致 | tc | T2 |
| T3 | ifdef 包裹的用例未纳入 tc_all（提示） | tc | T3 |
| T4 | 类名与文件名不一致 | tc | T4 |
| T5 | `spec_doc/` 规格书测试要点第 N 条没有对应用例（用例名 `<dut>_tc_tp<N>.sv`，或用例文件头注释声明 `testpoint: N`；列表项与表格数据行都算；只核对存在同名 TB 平台的规格书） | tc | T5 |
| T6 | 平台用例文件或参考模型文件仍是 tb-gen 骨架（含 `骨架未填写` 或参考模型透传标记） | tc | 新增 |
| mod | 模块进度未到该行要求的状态 | rtl / conn / tc | 引擎模块检查 |
| run | 最近一次运行记录缺失、范围不符或未通过 | lint / sim / coverage / synth / sta | 引擎运行检查 |
| run-log | 运行记录登记的日志文件缺失或与登记摘要不一致——输出侧证据被改动，结论不可信（不可豁免，须重跑） | lint / sim / coverage / synth / sta | 引擎输出复核 |
| lec | 行 10 提示（hint 级，不阻断）：登记了黄金参考数据但无 lec（CEC 等价性检查）通过记录 | sim | 引擎等价性提示 |
| COV | 覆盖率阈值下调缺少带裁决号的豁免（非闸门规则号，见 `rules/sim.md`） | coverage | 新增 |
| golden | 参考数据未登记，或生成脚本/输入在登记之后改过（须重新生成） | sim | 新增 |
| signoff | 行 12 时行 11 尚未完成 | signoff | 引擎签核检查 |
| sta-unconstrained | 时序检查报有端点未约束（可经人确认登记豁免） | sta | 新增 |
| stop | 停点编号不存在 | 入口 | 引擎停点检查 |
| fingerprint | 已完成停点的产物在完成后有改动（不可豁免，须退回该停点重新送审） | 入口 | 原 status 提示 |

`run_gates` 在返回前丢掉与 `state.waivers` 中规则号和位置都相同、且裁决号仍在 `decisions` 里的发现；`fingerprint` 在豁免过滤之后才加入，不受豁免影响。

各条判定的现行口径另见 `rules/sim.md`（行 10 的全量回归与覆盖率阈值）、`rules/syn.md`（综合与 STA 的约束要求）。
