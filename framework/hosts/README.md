<!-- 作者：vick 邮箱：ykun@yk9811.com -->

# 宿主投影（DeepSeek Harness）

角色元数据只在 `roles.yaml`。`render()` 把它写成 DeepSeek Harness 会加载的薄文件，正文只指向 `rules/`，不复制规则。

## Frontmatter

- 技能文件 `skills/<role>/SKILL.md` 的 YAML 头必填 `name`、`description`，`name` 与目录名一致。
- 宿主的常驻入口是仓库根的 `AGENTS.md`。
- 点选动作在 DSH 里以对话编号选项呈现；规则正文只写“点选”。
- `roles.yaml` 的 `tools`/`stops` 是派工与测试契约字段，不投影进 `SKILL.md`（技能卡头只有 `name`、`description`）。

## 生成物

- `AGENTS.md`（源 `standing.md`，含动作策略表与停点总表）
- `rules/steps.md`（源 `steps.md`，含停点总表；产物头部标「生成物，请勿手改」）
- `rules/pubip.md`（参数/端口生成区由 `pub_code/` 的 RTL 生成，正文手写）
- `skills/<role>/SKILL.md`
- 主持拆成 `host_design`（停点 1–6）和 `host_code`（停点 7–12），分别指向 `rules/host/design.md`、`rules/host/code.md`
- `.mcp.json`（剖面有 `eda_mcp` 配置时）

`rules/` 下**只有** `rules/steps.md` 与 `rules/pubip.md` 是生成物；其余 `rules/**` 是手写源文档，`render()` 一个字节都不写
（守卫见 `framework/tests/test_hosts.py::test_render_does_not_touch_rules`，产物与源一致见同文件的
`test_generated_files_match_sources`）。
