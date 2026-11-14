<!-- 作者：vick 邮箱：ykun@yk9811.com -->

# TB 构建角色

停点 9 的执行角色。按测试要点生成框架式 testbench，与仿真角色构成构建—仿真回路。

## 输入与输出

- 输入：各模块规格书测试要点章（或交付 IR 的结构化测试点）、`rtl/`、`rules/tb.md`
- 输出：`testbench/` 下整套框架 TB（接口、组件、用例、factory、tc_all、sim_top、`.f` 清单）
- 不做：不改被测 RTL 功能；不自研时钟复位、超时与结果统计；不做仿真执行（属行 10）

## 工作步骤

1. 从测试要点章逐条取测试点，一测试点一用例，编号对应
2. 搭接口：与 DUT 端口一一对应，输入信号赋初值不得为 X
3. 实现组件：driver、monitor、refm（纯函数计算）、scoreboard、env；参数只写在一份 `*_cfg.svh`
4. sim_top：DUT 例化、时钟复位接口、用例选择、全局超时、虚拟接口布线
5. 用例：`tc/<dut>_tc_<name>.sv`，注册进 factory，聚合进 `tc_all`；`ifdef` 用例单独标注
6. 容差比对：需要与算法数据或定点模型比对时按 `rules/tb.md` 的 `GOLDEN_TOL` 用法实现
7. 自检：用例文件、factory 注册、tc_all 三方一致；类名与文件名一致；`.f` 清单齐全
8. 行 9 完成前要有**一条独立审查记录**：`review <sys> record --stop 9 --author <派工号> --reviewer <派工号> --report report/<sys>_tb_review.md`（作者≠审查者、阻断发现为 0、报告要晚于 `testbench/` 最后一次修改）。这是 `tb_review`，与 `tc` 闸门**并列**：闸门过且有这条记录，`tick` 才会把行 9 置完成；卡见 `rules/review/tb.md`

## 判断标准

- 测试要点每条都要有用例；用例数少于测试要点数是缺口，列入小结
- 结果只走统一计数与汇总，不逐用例打印 RESULT；整次仿真结束由记分板汇总一行 `RESULT : PASS/FAIL`
- 随机化与种子：种子写进运行参数，不写进用例正文

## 常见错误

- 自写时钟生成或复位序列（框架统一提供）
- 波形转储自行命名（由用例标记宏管理）
- 裸 `$display` 代替分级日志宏
- 覆盖组没有用宏隔离，未启用时也参与编译
- 控制信号放进容差比较（控制信号必须精确比较）

## 必读

- `rules/roles/tb_build.md`：本文
- `rules/review/tb.md`：行 9 的独立审查卡（`tb_review`，报告的固定格式）
- `rules/tb.md`：组件职责、命名表、时钟复位超时约定、参数与宏、GOLDEN_TOL 用法
- `rules/sim.md`：三种场景、RESULT 协议与覆盖率口径（TB 侧要配合的约定）

## 交付前自检

1. 用例文件、factory 注册、tc_all 三方一致；类名与文件名一致
2. 测试要点逐条有用例；`ifdef` 用例已单独标注
3. 时钟、复位、超时、统计全部用框架提供，未自研
4. 参数单一来源在 `*_cfg.svh`；接口输入初值非 X

## 返回小结字段示例

以下示例用虚构子系统与示例路径，仅示意返回格式。

```text
产物路径：testbench/fir_core/（组件 6、用例 5、factory 1、tc_all 1）
用例覆盖：测试要点 5/5（tc_basic、tc_boundary、tc_saturate、tc_ramp、tc_hold）
factory 注册：5/5，tc_all 聚合 5/5
容差比对：tc_ramp 使用 GOLDEN_TOL=2（`fx tol '<16,6,t>'` 输出）；控制信号精确比较
待点选项：tc_hold 的保持拍数规格书未给（已查 fir_core §4）
自检：TB 闸门通过
收尾：返回小结即可，状态由主持者跑 tick
```
