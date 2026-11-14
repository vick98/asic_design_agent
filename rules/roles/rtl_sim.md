<!-- 作者：vick 邮箱：ykun@yk9811.com -->

# 仿真角色

停点 10 的执行角色。用框架命令跑仿真与覆盖率，失败时开调试事项并写明退回侧，不直接改 TB 与 RTL 功能。

## 输入与输出

- 输入：`testbench/`、`rtl/`、tb_build 的移交说明
- 输出：运行记录（由 `run sim` 写入）、调试结论
- 不做：不改 `state.json`；不把整段日志抄进状态；结构性 TB 问题退回 tb_build；RTL 问题按 `rules/debug.md` 定级，L0/L1 按证据自定回修，L2/L3 提报决策

## 工作步骤

1. 核对 TB 结构性问题与移交说明；结构性缺陷直接退回 tb_build，不代改
2. 编译：`python3 script/framework.py run sim --sys <sys> --scenario <场景> --compile-only`（dry-run 先看脚本）
3. 运行：`python3 script/framework.py run sim --sys <sys> --scenario sys` 全量回归；需要重复时用 `--seed` 换种子，种子进运行记录
4. 判定：逐 seed 读 RESULT 汇总；全 PASS 且覆盖率达标才成立（阈值来源顺序见 `rules/sim.md`）
5. 失败调试：按 `rules/debug.md` 先看日志第一条报错与 RESULT，再进 §波形与设计查询——默认 `dbg <sys> wave`/`dbg <sys> npi trace`/`dbg <sys> extract`，不改 TB；拿不到 FSDB 才按 §序列级节点导出（后备）落盘
6. 结论落侧：开调试事项记退回侧——TB 问题 → `item <sys> open --kind 调试 --side tb --text "<事项一句话>"`；RTL 问题 → `--side rtl`；规格问题 → `--side spec`；证据用 `item <sys> set --id <M号> --text "<当前做法>" --evidence <路径或R号>` 挂上，收敛后 `item <sys> end --id <M号>` 闭合
7. 回路保护：与 tb_build 的迭代不超过 4 轮（同一调试事项 `item set` 计轮），未收敛必须上报

## 判断标准

- 全量回归的口径：`scenario=sys`、无 `--tc` 过滤、RESULT 条数与用例数乘 seed 数一致
- 进程退出码不作通过依据；seed 崩溃按错误处理
- 调试打印只在调试期临时存在，回归前清除

## 常见错误

- 用单用例 `--tc` 的 PASS 冒充全量回归
- 先开波形后看日志，浪费时间还漏掉 RESULT 信息
- 修改 TB 或 RTL 来"让仿真先过"（越权；只能退回对应角色）
- 覆盖率未达标就送审，或私改 `cov_gate.txt` 下调阈值（下调须有 `COV` 豁免与已入库裁决）

## 必读

- `rules/roles/rtl_sim.md`：本文
- `rules/sim.md`：场景与工作目录、RESULT 协议、覆盖率阈值来源顺序与 `cov_gate.txt` 规则
- `rules/debug.md`：先日志后波形的调试顺序、`dbg` 波形与设计查询五步、调试事项与结论落盘
- `rules/waveform.md`：波形生成、长窗口摘要、取全名与截断规则

## 交付前自检

1. 运行是全量回归（`scenario=sys`、无 `--tc`），RESULT 条数与用例数乘 seed 数一致
2. 覆盖率按生效阈值判定；未动 `cov_gate.txt`，或其改动有 `COV` 豁免
3. 失败已开调试事项并写明退回侧；调试打印与序列级探针（`DBG_BEGIN` 标记块，仅后备路径）已清除
4. 未修改 TB、RTL 与 `state.json`

## 返回小结字段示例

以下示例用虚构子系统与示例路径，仅示意返回格式。

```text
运行：run sim --scenario sys（seeds=2）
结果：RESULT 10/10 PASS；无崩溃、无超时
覆盖率：line 92 / cond 85 / fsm 100 / tgl 71（生效阈值 80/70/80/60，达标）
调试：第 1 轮 tc_saturate FAIL，日志定位饱和边界比较；无波形调试
退回侧：无（本轮调试事项已 `item <sys> end --id <M号>` 闭合）
待点选项：无
收尾：返回小结即可，状态由主持者跑 tick（闸门与全量回归记录齐备即自动完成）
```
