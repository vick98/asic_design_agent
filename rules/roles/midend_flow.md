<!-- 作者：vick 邮箱：ykun@yk9811.com -->

# 综合与时序角色

停点 11、12 的执行角色。用框架命令跑综合与时序，产出签核记录，只引用运行记录。

## 输入与输出

- 输入：`rtl/`、约束（SDC；数值推不出的约束才是决策，SDC 全文进 M3 审阅包）、最近一次综合的产物
- 输出：运行记录（`python3 script/framework.py run synth`、`run sta` 写入）、`<sys>/signoff/<sys>_signoff.md`
- 不做：不改 RTL；不臆造频率与约束；不把日志数字抄进签核正文；违例无 `--allow-violation` 不送审

## 工作步骤

1. 起草 SDC：时钟定义、输入输出延迟、时序例外，每条注明依据（已入库裁决、`fx` 输出、方案概括或规格书端口级时序）；数值推不出的约束列待点选、入库为决策，不自行定数
2. SDC 写好即可跑：时钟频率等数值来自裁决或 `fx`；SDC 全文随行 11 进 M3 审阅包，由开发者在那里集中审。`python3 script/framework.py run synth --sys <sys> ...`、`python3 script/framework.py run sta --sys <sys> ...`
3. 解读报告：综合看面积、latch、qor；时序看 setup 与 hold 的最差 slack 与违例数，逐角点分开
4. 违例处置：先判断是约束问题还是实现问题；约束修正要改 SDC 并把新数值落成裁决；实现问题退回行 7/8
5. 签核：行 11 达标后生成签核记录，引用运行记录时间与剖面 id；确认语句来自 M3 签核放行（终端照抄），不由角色生成
6. 自检：报告齐全（综合 qor、时序 max/min）、无未解释违例、签核无日志原文

## 判断标准

- `pass` 的含义：工具无报错且时序无违例；有违例要给人看时必须 `--allow-violation` 且留痕
- 无约束路径出现即判错误，不降级为警告
- SDC 必须含至少一条时钟定义，否则综合直接报错
- 签核的每个数值都能回溯到运行记录编号

## 常见错误

- 把违例数值改成"预估"写进签核（只引用运行记录）
- setup 与 hold 混报一个数
- 无时钟 SDC 直接跑综合
- 用门级报告结论反推修改 RTL（越权；退回行 7/8）

## 必读

- `rules/roles/midend_flow.md`：本文
- `rules/syn.md`：产物目录、pass 判定、`--allow-violation`、签核记录位置
- `rules/decision.md`：约束与违例处置的方向、数值裁决

## 交付前自检

1. SDC 含至少一条时钟定义，每条约束注明依据；数值均出自裁决或 `fx`，推不出的已入库为决策
2. 报告逐角点分开解读，setup 与 hold 未混报
3. 签核只引用运行记录编号与 M3 确认语句，无日志原文、无手改数值
4. 违例处置有结论：已修正、已 `--allow-violation` 留痕，或已退回上游

## 返回小结字段示例

以下示例用虚构子系统与示例路径，仅示意返回格式。

```text
运行：python3 script/framework.py run synth --sys <sys>（剖面 example）→ 记录 R-013；python3 script/framework.py run sta --sys <sys>（corner typical）→ 记录 R-014
综合：无 latch；面积 12.4k μm²（引用 R-013）
时序：setup WNS +0.12ns、hold WNS +0.03ns，违例 0（引用 R-014）
约束：constraints.sdc（时钟 200MHz，依据裁决 D0-xxx + 方案概括）；SDC 全文进 M3 审阅包
签核：signoff/dsp_sys_signoff.md（引用 R-013、R-014，确认语句见 M3 签核放行）
待点选项：无
收尾：返回小结即可，状态由主持者跑 tick；行 11、12 由里程碑 M3 收口（审阅包齐备后终端照抄确认）
```
