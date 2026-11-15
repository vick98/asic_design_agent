<!-- 作者：vick 邮箱：ykun@yk9811.com -->

# 环境配置作业书（给 AI agent 读）

> 本文写给**执行配置的 AI agent**，不写给人。人只需要回答[第 1 步](#第-1-步信息收集)的信息清单并做两次点选；其余步骤由 agent 完成，完成后向人汇报 `doctor` 结论。
> 环境值（主机、账号、路径、license、工艺库）只写进 `toolchain/profiles/<你的剖面>/`；**不得**写进 `rules/`、规格、RTL 注释或事件记录。

## 第 0 步：基线自检与部署形态

先跑一次基线，确认框架本体可用（此时 `toolchain/active` 还是 `example` 占位剖面，ssh 一项失败是预期）：

```text
python3 -m pip install -r requirements.txt   # PyYAML；pyslang 可选（位宽解析增强，不装不阻断）
python3 script/framework.py doctor           # 本地各项应通过；ssh 项失败不阻塞后续
```

然后与人确认部署形态（二选一）：

| 形态 | 适用 | 后果 |
|------|------|------|
| A：纯本地 | 本机没有 EDA 工具，或暂不接 EDA 主机 | 复制 `_template` 即完成配置；文档/规格/RTL/TB 阶段照常推进，仿真、lint、综合、STA 闸门按 `unavailable` 走豁免路径，`run`/`dbg` 不可用 |
| B：远端 EDA | 有 SSH 可达的 EDA 主机（仿真器、lint、综合、STA 至少其一） | 走完本文全部步骤 |

形态 A 到此结束：把 `toolchain/active` 改成 `_template`（或复制一份改名），向人汇报即可。以下步骤都针对形态 B。

## 第 1 步：信息收集

向人**一次性**问全（不要挤牙膏式追问；标注"可默认"的项人答"默认"就用默认值）：

| # | 问题 | 必答/可默认 |
|---|------|------------|
| 1 | SSH 别名（`~/.ssh/config` 里的名字）与是否免密（BatchMode 可通） | 必答 |
| 2 | 远端账号名 | 必答 |
| 3 | 镜像根目录（仓库在远端的镜像位置，如 `/home/<账号>/proj/asic_design_agent`） | 必答 |
| 4 | 工具根目录（如 `/opt/synopsys`）与已装工具清单（仿真器/lint/综合/STA 及版本串） | 必答 |
| 5 | license 服务器（如 `27000@<host>`） | 必答 |
| 6 | 工艺库：库名、路径、corner→db 映射（tt/ss/ff） | 接综合/STA 必答 |
| 7 | lint 工具：是否 nLint（是→规则库版本；否→提供批处理调用方式与判定行） | 必答 |
| 8 | 覆盖率阈值（line/cond/fsm/tgl） | 可默认（80/70/80/60） |
| 9 | FSDB/Verdi：`VERDI_HOME` 路径，eda-mcp 要启用的组（env/fsdb/wave/npi） | 可默认 |
| 10 | 结果判定：日志里的通过/失败判定行约定 | 可默认（`RESULT` 行） |

## 第 2 步：建剖面（不改 `example`）

**禁止修改 `toolchain/profiles/example/`**：`framework/tests` 直接对 example 的驱动与占位名断言，改了测试就挂；example 是给测试和阅读用的样例。

```text
cp -r toolchain/profiles/_template toolchain/profiles/<剖面id>
```

剖面 id 用机器别名（如 `lab-vcs01`），**不要**用真实主机名或 IP。然后改写其中的 `profile.yaml`，字段对照 `example/profile.yaml` 逐项填：

| 字段 | 填什么 | 备注 |
|------|--------|------|
| `transport` | `ssh` | 本地形态才用 `local` |
| `ssh_alias` / `account` | 第 1 步 #1、#2 | 别名必须在 `~/.ssh/config` 里可解析 |
| `mirror_root` | 第 1 步 #3 | rsync 目标；**不要**把 `eda_mcp.prefix` 放在它里面（`rsync --delete` 会删掉），也不要用 `~/.local`（会覆盖其他项目的安装） |
| `tool_root` | 第 1 步 #4 | |
| `tools` | 各能力 `available: true/false` | 没装的工具必须 `false`，框架按不可用处理 |
| `sync_excludes` | 照抄 example | `.git/`、`work/`、`dc/`、`pt/`、`lint/` |
| `expect_versions` | 第 1 步 #4 的版本片段 | 空表=不核对；对不上只写运行记录 note，不阻断 |
| `license` | 第 1 步 #5 | |
| `coverage_defaults` | 第 1 步 #8 | **下调阈值是红线动作**：须由人点选入库裁决（D 号）后才能改，agent 不得自行调低 |
| `vcs` | 编译开关、FSDB PLI 路径 | `fsdb_pli_*` 用 `$VERDI_HOME` 变量或实际路径 |
| `eda_mcp` | `prefix`、`verdi_home`、`groups` | 要用 `dbg` 才需要这段；不配则 `.mcp.json` 不生成 |

## 第 3 步：驱动改造（工艺库与工具路径）

从 example 复制驱动到自己的剖面再改，**不要**原地改 example：

```text
cp toolchain/profiles/example/drivers/*.py toolchain/profiles/<剖面id>/drivers/
```

- 把 `eda.py` 里所有 `yourtech_*` 占位库名替换为第 1 步 #6 的真实库名、搜索路径与 corner 映射。
- 换仿真器/lint/综合工具时，按 `toolchain/CONTRACT.md` 的结果契约改写对应 driver——框架只认契约里的统一结果，不认具体工具。
- driver 的判定逻辑读日志汇总行（如 nLint 的 Fatals+Errors、仿真的 `RESULT` 行），按第 1 步 #10 核对后在 `notes.md` 里记一笔。

## 第 4 步：lint 规则库（仅 nLint）

复制并按自己的规则库改写：`nLint_ws.rs`（规则集与 goal）与 `nLint_filter.txt`（豁免条目）。豁免条目的写法照 example：规则号 + 文件/对象 + 一句话依据；真实豁免要有裁决号支撑。用其他 lint 工具则跳过本步（driver 里实现）。

## 第 5 步：notes.md

照 `example/notes.md` 的格式写自己机器的说明：SSH 别名与账号、工具版本、调用方式与特殊开关、结果判定行、license、工艺库路径、镜像目录。这份文件给人看，也给出下次换机器时要改哪里。

## 第 6 步：切换剖面

```text
echo <剖面id> > toolchain/active
```

## 第 7 步：验证链

按顺序跑，前一级通过才跑下一级：

1. `python3 script/framework.py doctor` —— ssh 项用 `ssh -o BatchMode=yes <别名> true` 的口径；失败先查 `~/.ssh/config` 与本机代理，再查账号密码方式（不支持交互输密码）。
2. `python3 script/framework.py eda-mcp install` —— 同步镜像并把 eda-mcp 装到 EDA 主机、写 SOURCE_DIGEST（只有配了 `eda_mcp` 段才需要）。
3. `python3 script/framework.py doctor --mcp` —— 远端观察面自检。
4. `python3 script/framework.py hosts` —— 按剖面重新生成仓库根 `.mcp.json`（自动写，不手改）。
5. 可选：`python3 script/framework.py selftest` —— 验证框架本体（复制到临时目录跑，不改当前配置）。

## 第 8 步：收尾汇报

向人汇报：`doctor`/`doctor --mcp` 逐项结论、剖面 id、可用的能力位（哪些工具 available）、覆盖率阈值取值。此时人可以直接开一个子系统试跑（`init` → `status`）。

**敏感信息纪律**：剖面里的真实主机名、账号、IP、license 地址、工艺库路径属于环境敏感信息。这个仓库的远端是公开的——若要把本地改动推回去，先 `git status` 与 `git diff` 确认环境值没有被带进 `example/`、`rules/` 或其他被跟踪文件；自己的剖面目录是否进版本库由人决定，默认建议本地保留（需要时加入 `.gitignore`）。

## 附：常见失败对照

| 现象 | 处置 |
|------|------|
| `doctor` 报 ssh 失败 | 先手工 `ssh -o BatchMode=yes <别名> true`；本机开着代理先关掉再试；不支持交互输密码，必须免密 |
| 版本片段对不上 | 只进运行记录 note，不阻断；核对 `expect_versions` 片段是否与实测版本串一致 |
| 综合找不到库 | `eda.py` 的搜索路径与 corner→db 映射没替换干净，回第 3 步 |
| `eda-mcp install` 后 `--mcp` 仍失败 | 看 `prefix` 是否在 `mirror_root` 内或等于 `~/.local`；确认 `EDA_MCP_ENABLED_GROUPS` 与剖面 `groups` 一致 |
| 测试挂了 | 先确认没改 `example/`；自己的剖面不参与 `framework/tests`，用 doctor 与实跑验证 |
