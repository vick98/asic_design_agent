<!-- 作者：vick 邮箱：ykun@yk9811.com -->

# 波形渲染（WaveDrom JSON）

调试顺序是"先日志、再复现、再波形"（见 `rules/debug.md`）。本文只讲**波形那一步**的渲染规则：波形数据用 WaveDrom JSON 描述，由 Waveform Render 插件（或 wavedrom.com 在线渲染）画成时序图，用来在模块规格书里表达接口时序、握手节奏与流水关系，也用来对照调试时看到的节拍。本文沿用与旧工作区相同的 JSON 结构、字段与字符表。

## 生成与落点

框架命令 `python3 script/framework.py dbg <sys> wave --case N -s <信号>... -t 0ns -c 16`（窗口也可用 `--start/--end`）从 FSDB 取值并输出 WaveDrom JSON，落到子系统目录：

- `<sys>/work/dbg/case<N>_<标签>.json`——每次导出带用例号与信号标签，便于区分；`--case N` 的用例号与 `dbg <sys> signals` 列出的编号一致。
- 生成命令、镜像新鲜度与 FSDB 的两个坑（`+nolibcell`、`-fno-lto`）写在 `rules/debug.md` 的"波形与设计查询"一节；本文不重复。
- 本文只规定"**怎么渲染、字段什么意思**"。`rules/debug.md` 规定"**什么时候看波形、看哪几拍、看完怎么挂事项**"。

### 长窗口：翻转段摘要

窗口一长（上千周期），`wave` 字符串每周期一个字符，读它等于人工解码。要"恒值判读 / 翻转定位"时用摘要模式：

```text
python3 script/framework.py dbg <sys> wave --case N -s <信号>... -t T -c C --summary flip
```

- 每个信号给**翻转段** `[起, 止] 值`——段内恒定，只列翻转时刻，信息密度远高于逐字符；
- 段落另有落点 `<sys>/work/dbg/case<N>_<标签>_segments.json`（含 `window`/`clock`/`segments`/`width_truncated`），波形图本身仍写在 `case<N>_<标签>.json`，两者都可直接读；
- 默认不带摘要；翻转次数多时远端会给出 `summary_hint` 提示可用它。

### 取信号全名：`signals --as-args`

不想手抄层次全名时，先列匹配再把结果直接粘进 `-s`：

```text
python3 script/framework.py dbg <sys> signals --case N --pattern '*_set_id' --as-args
```

输出形如 `-s top.u.reg_set_id -s top.u.wir_req_set_id`，可直接拼进上一条 `wave` 命令。`-s` 本身也支持显式通配（含 `*` `?` `[` 的项按信号名展开成多个信号，与 `signals --pattern` 同一口径）。

### 超宽信号会被截断

多 bit 数据标签只保留**低 32 bit**（超过时标签写成 `..xxxxxxxx`）。导出结果里有 `width_truncated` / `label_truncated` 显式标出，命令文本模式也会打警告——**完整值**在给了 `-o` 时写进 `<out>_full_data.log`（含 `width=`）。别把被截断的标签当完整值用。

调试时默认走这条导出路线，不往 testbench 里插探针；确需 TB 探针时只允许改 `testbench/` 里 `//DBG_BEGIN` 与 `//DBG_END` 之间的块（见 `rules/roles/rtl_sim.md`）。

## 基本结构

```js
{ "signal" : [
    [ "组名", {信号对象1}, {信号对象2} ],   // 数组首元素为组名，组可嵌套
    {},                                     // 空对象 = 信号间空隙
    { "name" : "信号名", "wave" : "p.01=", "data" : ["A", "B"] }
]}
```

## 信号字段

| 字段 | 说明 |
|------|------|
| `name` | 信号标签 |
| `wave` | 波形字符串，每个字符代表一个周期 |
| `data` | 数据标签数组，与 wave 中 `=` 槽位一一对应 |
| `period` | 信号周期（自然数，1,2,3...） |
| `phase` | 相位偏移：正数 = 向未来偏移，负数 = 向过去偏移 |

## wave 字符速查

| 字符 | 含义 |
|------|------|
| `p` / `n` | 时钟上升沿 / 下降沿（须位于字符串首位） |
| `0` / `1` | 低电平 / 高电平 |
| `=` | 数据值（配合 `data` 显示具体值） |
| `2` ~ `5` | 数据值，分别使用 2~5 号颜色 |
| `x` | 不定态 |
| `z` | 高阻 |
| `.` | 延续上一周期 |
| `\|` | 延续上一周期，并在顶部画空隙 |

## edge 依赖箭头

```js
{ "signal" : [ ... ],
  "edge" : ["a->b 箭头标签文字"] }
```

- 箭头字符串首个字符 = 起点标记，最后一个字符 = 终点标记；倒数第二位为 `>` 产生箭头
- 形状字符：`-` 横向、`|` 纵向、`~` 曲线、`/` 斜线；`#` 标记箭头标签位置
- 例：`"a->b"` 直线箭头、`"b-~>c"` 曲线箭头

## config

| 字段 | 说明 |
|------|------|
| `hscale` | 时序图水平缩放（≥1 的数字） |

详细语法见官方文档：<https://wavedrom.com/tutorial.html>
