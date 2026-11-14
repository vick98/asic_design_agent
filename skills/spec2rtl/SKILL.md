---
name: "spec2rtl"
description: "按模块规格书和交付 IR 写 RTL，端口位宽以 IR 为准。"
---

<!-- 作者：vick 邮箱：ykun@yk9811.com -->

# 模块 RTL

输入：spec_doc/、digest

输出：rtl/

必读：`rules/roles/spec2rtl.md`、`rules/coding.md`、`rules/pubip.md`、`rules/decision.md`

禁止：不手改未在规格书出现的端口、不写主机名、不写子模块内部逻辑以外的胶合

返回格式：返回小结，列出模块文件和与 IR 不一致的端口。

规则正文只读 `rules/roles/spec2rtl.md`。
