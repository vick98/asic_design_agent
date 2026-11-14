<!-- 作者：vick 邮箱：ykun@yk9811.com -->

# 工具剖面契约

框架通过统一结果认识仿真、lint、覆盖率、综合和时序。剖面可以声明某项 `unavailable`。换主机或换工具时只改 `toolchain/profiles/<name>/`，并把 `toolchain/active` 指过去。

## transport

剖面用 `transport` 声明脚本送到哪里执行。驱动只出命令文本，通道由运行层按这个字段选。

| 取值 | 通道 | 同步 | 说明 |
|------|------|------|------|
| `ssh`（缺省） | `SshTransport` | `rsync -avz --delete` | 远端执行；跑完把报告目录 rsync 回本地 `<sys>/lint`、`work`、`dc`、`pt` |
| `local` | `LocalTransport` | 无 | 本机执行，工作目录就是剖面的 `local_root`；产物已在本机，不回拉 |

`ssh` 还要 `ssh_alias` 与 `mirror_root`；`local` 只用 `local_root`（缺省为仓库根）。
字段缺省或为空按 `ssh` 处理；取值不在这张表里时 `run` 落一条 `error` 运行记录，不抛异常。

## Transport 接口

`framework/profile_run.py` 的 `Transport` 是运行层与执行主机之间的唯一通道。
`run_sim` 与 `run_other` 只组装请求、解析、判定与记录，执行流程只有一份实现。

| 成员 | 语义 |
|------|------|
| `sync()` | 把本地工作树同步到执行主机；本机执行是空操作。返回是否同步成功 |
| `execute(script, wall)` | 在主机上执行脚本，返回 `(log, returncode)` |
| `pull(paths)` | 把主机产物收回本地，返回本次运行的产物清单（含 `paths`） |
| `run(script, wall, sync)` | 运行层用的整段：`sync` → `execute` → `pull`，全程持同一把工作目录锁。返回 `(log, returncode, artifacts, lock, error)` |
| `preview(script, sync)` | `dry_run` 打印的"将要执行什么"：ssh 通道含 rsync 行，本机只有脚本 |
| `waves(wave)` | 这次仿真写出的波形路径；本机执行不列（本机波形不进运行记录） |

`wall` 是墙钟上限：本机执行按子进程超时落实（超时回 124，并把 `WALL_TIMEOUT` 拼进日志），
ssh 通道仍由远端脚本自己落实（超时同样回 124）。`wall` 不替代仿真自己的 `timeout_us`。

工作目录锁保护同一 `(sys, scenario, module)` 的工作目录：并行派工时同步、执行与回拉必须串行。
锁在 `run()` 内部取得，**回拉也必须在锁内**——锁外回拉会拉到下一次运行正在覆盖的半成品。

驱动契约不变：`drivers/*.py` 仍然负责把命令拼成脚本（`remote_script`、`lint_script`、
`coverage_script`、`synth_script`、`sta_script`）与解析输出（`parse`、`synth_products`）。
`transport: local` 的剖面里 `rsync_line` 与 `pull_line` 不会被调用（运行层只在 ssh 通道调用它们），
但接口表不分通道，剖面照旧提供即可。

## 工具版本

驱动在脚本开头打一行 `TOOL_VERSION <能力> <版本串>`（sim 取仿真器版本、synth 取综合、
sta 取时序，lint 与 coverage 各取自己的工具；版本串只取首行）。`parse` 把它收进
`checks.tool_versions`（能力 → 版本串），运行记录因此能回答"这份证据是哪个工具版本
跑出来的"——同一剖面换了工具版本，旧记录仍判新鲜，但能看出证据来自另一套工具。
工具不在 PATH 上时这一行只剩标记，这个字段就不写（宁缺勿错），不影响运行。

剖面可选声明 `expect_versions`（能力 → 期望版本里应出现的片段）：

```yaml
expect_versions:
  sim: "V-2025.06"
  synth: "V-2025.06"
```

实测版本串含该片段即算一致。不一致、或声明了却没取到版本时，运行记录多一条 `note`，
**不阻断**运行、不改 `status`、不影响闸门判据；`tick` 的清单据此提示主持者核对工具版本。

## 请求

仿真请求字段：`scenario`（`sys` / `module` / `pubip`）、`sys`、`module`、`tc`、`seed`、`wave`（`off` / `fsdb` / `vcd`）、`coverage`、`compile_only`、`dry_run`、`defines`（变体编译宏，可重复，标识符或 标识符=值；pubip 变体回归用，日志与回拉落 `pub_code/work/<module>/`）。

## 结果

| 字段 | 含义 |
|------|------|
| capability | sim、lint、coverage、synth、sta、conn、tc 之一；CLI 的 `run` 还接受扩展能力 cdc、lec（当前剖面未提供时按 unavailable 处理） |
| status | pass、fail、error、unavailable、dry_run。dry_run 不写入 state.json |
| summary | 短结论 |
| checks | 名值对；`tool_versions` 是这次用的工具版本（能力 → 版本串，见下） |
| artifacts | 日志或报告的相对路径 |
| profile_id | 剖面 id |

`run` 的进程退出码：`0` = pass 或 dry_run；`1` = fail / error；`3` = 剖面声明 `unavailable`（当前剖面未提供该能力，走规则与裁决豁免路径，不算通过）。

仿真是否通过看日志里的 `RESULT` 行，不看仿真器进程退出码。覆盖率阈值的比较在框架里，报告解析在剖面里。
