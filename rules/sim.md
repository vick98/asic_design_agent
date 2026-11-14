<!-- 作者：vick 邮箱：ykun@yk9811.com -->

# 仿真契约

`rtl_sim` 的工作规则。仿真、lint 等运行一律用 `python3 script/framework.py run`，工具与主机只写在 `toolchain/profiles/`。

## 场景

- `sys`：子系统级，工作目录 `<sys>/work/`，文件列表 `testbench/<sys>_tb.f`
- `module`：子系统内模块级，工作目录 `<sys>/work/<module>/`
- `pubip`：公共模块级，工作目录 `pub_code/work/<module>/`

## 通过协议

每条用例在日志里打印 `RESULT` 行表示通过或失败；判定逐 seed 解析 RESULT，全部 PASS 才算仿真通过。进程退出码不作通过依据；seed 崩溃记错误。行 10 只认全量回归：`scenario=sys`、不带 `--tc` 过滤，且用例数等于 `tc_all` 枚举用例数乘 seed 数。实现先按 `TB_CASE_END` 行数（`cases_run`）核对，运行记录里没有该计数时退回 RESULT 行数。dry-run 不写记录。

`run` 的进程退出码只分三档：`0` 通过或 dry-run，`1` 失败或错误，`3` 当前剖面未提供该能力（`unavailable`，走规则与裁决豁免路径，不算通过）。

## 等价性检查（lec，hint 级）

仿真对数据负责，等价性对设计负责，两者不互替：黄金参考数据验证"激励下输出对"，CEC（组合等价检查）验证"设计与参考实现是同一个函数"。行 10 登记了黄金参考数据却无 lec 通过记录时，闸门出一条 hint 提示（不阻断自动完成）。

- 命令：`run lec --sys <sys> --module <模块> --gold <黄金 RTL 文件>`——黄金参考是同一模块名的参考实现（上一版或独立参考设计），候选是 `rtl/<模块>.sv|.v`；需要剖面提供 lec 能力（`toolchain/profiles` 的 `tools.lec.available`，配远端 yosys）。
- 黄金文件作为输入进运行记录摘要：改过黄金参考，旧的 lec 记录自动判"输入已变更，需重跑"。
- 剖面没有 lec 能力时保持提示，不算失败；有黄金 RTL 而长期不核对等价性，在里程碑审阅时说明理由。

## 长任务与后台作业

同步运行会一直阻塞到同步、执行、回拉整段结束（缺省墙钟上限 3600 s），智能体宿主的前台超时会卡住会话。耗时运行用后台执行：

```text
python3 script/framework.py run sim --sys <sys> --detach
python3 script/framework.py run wait --job <作业号> [--timeout <秒>]
python3 script/framework.py run jobs [--sys <sys>]
```

- `--detach` 把请求写进 `<sys>/work/jobs/<作业号>.json`（请求、pid、状态、开始/结束时间、结果摘要），后台进程完整跑一遍同步运行的全流程——含 `record_run`、持同一把工作目录锁；父进程立即打印作业号并返回 `0`。`--detach` 必须带 `--sys`，不与 `--dry-run` 同用。
- `run wait` 等到作业结束，打印与同步运行一致的结论与运行记录号，退出码也一致（`0` / `1` / `3`）；等待上限缺省不限，`--timeout` 超时返回 `124` 且作业继续在后台跑。
- `run jobs` 列出作业摘要：作业号、能力、状态（`pending` / `running` / `done` / `failed`）、开始时间、结论。`--sys` 缺省时汇总仓库里所有子系统。
- 运行记录只在作业完成时写一次。运行结论是 fail/error 时照常写记录，作业状态记 `failed`；后台进程自己异常退出时作业状态也记 `failed`，原因留在 `error` 字段。
- 作业文件与后台输出 `<sys>/work/jobs/<作业号>.out` 都是运行产物，不手工改写。

## 覆盖率阈值（来源顺序）

覆盖率看 line、cond、fsm、tgl 四项。生效阈值按以下顺序取：

1. **框架默认**：80、70、80、60（`framework/coverage.py` 的 DEFAULTS）
2. **剖面 `coverage_defaults`**：当前剖面可整体上调（或在其权限内调整）四项默认值
3. **子系统 `testbench/cov_gate.txt`**：只对本子系统生效，**只能上调**

`cov_gate.txt` 规则：

- 位置固定为 `<sys>/testbench/cov_gate.txt`，每行 `key=value`，key 取 line/cond/fsm/tgl，`#` 开头为注释，允许百分号
- 某项高于当前生效值：生效值改为它（上调）
- 某项低于当前生效值：**不生效**，除非登记豁免——豁免必须带规则号 `COV` 并指向一条已入库裁决；无豁免的下调整体判 fail，运行记录备注"cov_gate.txt 下调了阈值但没有豁免"，同时把违规项逐项列出
- 四项中指标为 `--` 的项在检查里标 `na`，由框架决定是否按达标计，不在解析层改写
- 报告格式由剖面解析，框架只比较数值；比较由框架做，不在文档里手算

未达标项逐条归因：需补用例的回 `tb_build` 补用例；确属不可达或工具伪覆盖的，登记豁免并给出裁决号，不留未解释的未覆盖项。

## 波形与调试

波形开关、编译开关属于剖面。失败时调试顺序见 `rules/debug.md`：先看日志再看波形。换仿真器时仍遵守 RESULT 协议，不改 testbench 的通过协议。

命令：

```text
python3 script/framework.py run sim --scenario pubip --module <name> --dry-run
```
