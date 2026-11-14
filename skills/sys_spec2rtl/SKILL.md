---
name: "sys_spec2rtl"
description: "例化、连接和胶合，连接核对通过后才送审。"
---

<!-- 作者：vick 邮箱：ykun@yk9811.com -->

# 顶层 wrapper

输入：rtl/、spec_doc/{sys}_spec.md

输出：rtl/{sys}_top.sv

必读：`rules/roles/sys_spec2rtl.md`、`rules/wrapper.md`、`rules/coding.md`、`rules/pubip.md`

禁止：连接未核对不得送审、不写子模块内部逻辑

返回格式：返回小结，列出未连接端口和胶合说明。

规则正文只读 `rules/roles/sys_spec2rtl.md`。
