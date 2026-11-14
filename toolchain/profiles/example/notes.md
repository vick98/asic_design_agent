<!-- 作者：vick 邮箱：ykun@yk9811.com -->

# example

这份说明只描述当前这台 EDA 机器，不属于框架方法。克隆本仓库后，按你的机器改写本文件与 `profile.yaml`。

- SSH 别名（`~/.ssh/config`）、账号、地址：示例里是 `your_eda_host` / `your_account`，按实际填写。
- 工具根目录与版本：如 `/opt/synopsys` 下的 VCS / Verdi / Design Compiler / PrimeTime 版本号；`profile.yaml` 的 `expect_versions` 按实测版本片段填。
- 调用方式：写清用包装器还是直接调二进制；特殊编译开关（如 `-assert svaext`）与 FSDB 所需的 `-LDFLAGS` 在这里记一笔。
- 结果判定：读日志里的 `RESULT` 行，不看仿真器进程退出码（按你的环境确认）。
- lint：lint 工具的批处理调用方式、goal 与判定行（本剖面示例用 nLint，见 `drivers/eda.py` 与 `nLint_ws.rs`；判定读日志汇总行，Fatals+Errors 计入 errors）。
- license：如 `27000@<license-server>`；示例里 `27000@127.0.0.1` 按你的 license 服务器改。
- 工艺库：`.db`/`.lib` 的存放路径与 corner→db 映射。`drivers/eda.py` 里的 `yourtech_*` 是占位库名，替换为你的工艺库，并同步更新 `framework/tests` 里对库名的断言。
- 镜像目录是 `profile.yaml` 的 `mirror_root`。换机器时改 `profile.yaml` 与本文件，不要改 `rules/`。
