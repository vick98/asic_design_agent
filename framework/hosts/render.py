# 作者：vick 邮箱：ykun@yk9811.com

"""把同一份短入口、停点执行索引与角色薄投影写到 DeepSeek Harness 会加载的路径。

动作策略表与停点总表（唯一事实源）：`flow_model.yaml` 的 `actions:` / `milestones:` /
`stops:` 是唯一事实源，渲染时生成进 `standing.md` 与 `steps.md` 的占位标记
`<!-- ACTIONS_TABLE -->` / `<!-- STOP_TABLE -->`，两张主持卡也带同一份总表。
占位标记缺失时报错，不静默退化。

生成的派生物：`AGENTS.md`、`rules/steps.md`、`rules/pubip.md`、
`skills/` 下的角色卡与两张主持卡、`.mcp.json`。
`rules/**` 里**只有** `rules/steps.md` 与 `rules/pubip.md` 是生成物：steps.md 的源是
`framework/hosts/steps.md`；pubip.md 的参数/端口表源是 `pub_code/` 的 RTL（见
`framework/pubip_doc.py`）。两份产物头部都标"生成物，请勿手改"，逐字节比对见
`framework/tests/test_hosts.py::test_generated_files_match_sources`；其余 `rules/**`
是手写源文档，本模块一个字节都不写（见 `test_hosts.py::test_render_does_not_touch_rules`）。
"""

import os

from framework import eda_mcp
from framework import flow
from framework import pubip_doc
from framework.paths import project_root
from framework.profile_run import load_profile

# 作者信息：写进生成的各类技能卡（含两张主持卡）的 Markdown 正文头部。
AUTHOR_NOTE = "<!-- 作者：vick 邮箱：ykun@yk9811.com -->"

SOURCE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "standing.md")
STEPS_SOURCE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "steps.md")
ROLES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "roles.yaml")
STEPS_OUTPUT = os.path.join("rules", "steps.md")
PUBIP_OUTPUT = os.path.join("rules", "pubip.md")

ACTIONS_MARKER = "<!-- ACTIONS_TABLE -->"
STOP_TABLE_MARKER = "<!-- STOP_TABLE -->"
# 生成物头部：紧跟在 rules/steps.md 的一级标题之后，"生成物，请勿手改"是约定措辞。
STEPS_HEADER = (
    "> **生成物，请勿手改**：本文由 `python3 script/framework.py hosts` 从 "
    "`framework/hosts/steps.md` 与 `framework/flow_model.yaml` 渲染。"
    "要改内容请编辑 `framework/hosts/steps.md`，再重跑该命令。\n\n"
)

# flow_model.yaml 的 review: 取值 → 停点总表"审查要求"列的中文。
REVIEW_LABELS = {
    "spec_review": "`spec_review`（停点级）",
    "tb_review": "`tb_review`（停点级）",
    "rtl_review_per_module": "`rtl_review`（逐模块）",
    "rtl_review": "`rtl_review`（顶层）",
    "none": "无（闸门与运行记录即审查）",
}

# flow_model.yaml 的 class → 表格里"归属"列的中文术语。
CLASS_LABELS = {
    "auto": "自动",
    "decision": "决策",
    "milestone": "里程碑",
    "redline": "红线",
}

# flow_model.yaml 的 requires 标识 → 表格里"前提"列的中文。未知标识按原样带反引号输出。
REQUIRE_LABELS = {
    "gate_pass": "闸门通过",
    "no_blocking": "无未关闭阻断",
    "no_open_item": "无在途调试事项",
    "review_record": "有独立审查记录",
    "author_ne_reviewer": "作者≠审查者",
    "blocking_zero": "阻断发现为 0",
    "decision_exists_directional": "引用开发者点选入库的裁决",
    "evidence_exists_later": "证据存在且晚于问题登记",
    "decision_id": "须带裁决号",
}


def _actions_table():
    """把 actions 与 milestones 渲染成一张 markdown 表（列：动作 / 归属 / 前提）。"""
    rows = ["| 动作 | 归属 | 前提 |", "|------|------|------|"]
    for action in flow.actions():
        cls = action.get("class")
        if cls not in CLASS_LABELS:
            raise ValueError(
                "flow_model.yaml 动作 %r 的 class %r 不在 auto/decision/milestone/redline 里，"
                "无法渲染动作策略表" % (action.get("id"), cls))
        requires = [REQUIRE_LABELS.get(req, "`%s`" % req)
                    for req in (action.get("requires") or [])]
        rows.append("| %s | %s | %s |" % (
            action.get("name"), CLASS_LABELS[cls], "；".join(requires) if requires else "—"))
    for m in flow.milestones():
        covers = "、".join(str(x) for x in (m.get("covers") or []))
        blocks = m.get("blocks") or []
        tail = "，阻塞行 %s" % "、".join(str(x) for x in blocks) if blocks else ""
        how = "终端照抄" if m.get("terminal") else "点选确认"
        rows.append("| 里程碑 %s %s（覆盖行 %s%s） | 里程碑 | 审阅包齐备后%s |" % (
            m["id"], m["name"], covers, tail, how))
    return (
        "动作策略表（唯一事实源：`framework/flow_model.yaml` 的 `actions:` 与 `milestones:`；"
        "红线永不自动，规则正文只引用本表不重复）：\n\n" + "\n".join(rows) + "\n"
    )


def _done_label(sid, auto, done_ms):
    """停点总表"完成方式"列：完成归属只读动作表的 stops，不写死停点号。"""
    if sid in done_ms:
        m = flow.milestone_of_stop(sid)
        if m is None:
            raise ValueError("停点 %d 由里程碑完成但无覆盖里程碑，无法渲染停点总表" % sid)
        return "里程碑 %s 收口" % m["id"]
    if sid in auto:
        return "自动完成（`tick`）"
    raise ValueError(
        "停点 %d 既不在 stop_done_auto 也不在 stop_done_milestone 的 stops 里，"
        "无法渲染停点总表（完成归属必须唯一）" % sid)


def _stops_table():
    """把 stops 渲染成"停点总表"（列：行 / 名字 / 角色 / 闸门 / 完成方式 / 审查要求 / 所属里程碑）。

    行、名字、角色、闸门读 `stops:`；完成方式读 `actions:` 的两张 stops 表；审查要求读
    停点的 `review:`；所属里程碑读 `milestones.covers`。散文文档只引用本表，不复述。
    """
    auto = {int(x) for x in (flow.action("stop_done_auto") or {}).get("stops") or []}
    done_ms = {int(x) for x in (flow.action("stop_done_milestone") or {}).get("stops") or []}
    overlap = sorted(auto & done_ms)
    if overlap:
        raise ValueError("停点 %s 同时归属自动完成与里程碑完成，完成归属必须唯一"
                         % "、".join(str(x) for x in overlap))
    rows = ["| 行 | 名字 | 角色 | 闸门 | 完成方式 | 审查要求 | 所属里程碑 |",
            "|----|------|------|------|----------|----------|--------------|"]
    for stop in flow.load()["stops"]:
        sid = int(stop["id"])
        how = _done_label(sid, auto, done_ms)
        if flow.stop_blocked_by_items(sid):
            how += "；在途调试事项挡送审"
        review = flow.stop_review(sid)
        if review not in REVIEW_LABELS:
            raise ValueError("停点 %d 的 review 取值 %r 没有渲染标签" % (sid, review))
        owner = flow.milestone_of_stop(sid)
        rows.append("| %d | %s | `%s` | %s | %s | %s | %s |" % (
            sid, stop["name"], stop["role"], "、".join(stop.get("gates") or []) or "—",
            how, REVIEW_LABELS[review], owner["id"] if owner else "—"))
    return (
        "停点总表（唯一事实源：`framework/flow_model.yaml` 的 `stops:`、`actions:` 与 "
        "`milestones:`；行、角色、闸门、完成方式、审查要求、所属里程碑都由它生成）：\n\n"
        + "\n".join(rows) + "\n"
    )


def _fill_markers(text, where, required=()):
    """把占位标记换成生成的表；required 里的标记缺失即报错，不静默退化。"""
    for marker, builder in ((ACTIONS_MARKER, _actions_table), (STOP_TABLE_MARKER, _stops_table)):
        if marker in text:
            text = text.replace(marker, builder())
        elif marker in required:
            raise ValueError("%s 缺少占位标记 %s，生成的表无处插入（不得静默省略）" % (where, marker))
    return text


def _host_stops(mids):
    """主持卡覆盖的停点区间：由所列里程碑 covers 的并集推出（连续区间，如 1–6）。"""
    covered = set()
    for mid in mids:
        m = flow.milestone(mid)
        if m is None:
            raise ValueError("主持卡引用的里程碑 %s 不在 flow_model.yaml" % mid)
        covered.update(int(x) for x in m.get("covers") or [])
    if not covered:
        raise ValueError("主持卡没有覆盖任何停点：%s" % (mids,))
    lo, hi = min(covered), max(covered)
    if sorted(covered) != list(range(lo, hi + 1)):
        raise ValueError("主持卡覆盖的停点不连续：%s" % sorted(covered))
    return "%d–%d" % (lo, hi)

HOSTS = (
    {
        "id": "host_design",
        "title": "设计主持",
        "description": "主持停点 1 到 6，按 status 派发设计角色，方向和数值交给开发者点选。",
        "milestones": ("M1", "M2"),
        "must_read": "rules/host/design.md",
    },
    {
        "id": "host_code",
        "title": "编码主持",
        "description": "主持停点 7 到 12，按 status 派发编码、验证和中端角色。",
        "milestones": ("M3",),
        "must_read": "rules/host/code.md",
    },
)


def standing_text():
    with open(SOURCE, encoding="utf-8") as fh:
        return fh.read().strip() + "\n"


def steps_text():
    with open(STEPS_SOURCE, encoding="utf-8") as fh:
        return fh.read().strip() + "\n"


def _steps_product(body):
    """在源正文的一级标题之后插入生成物头部；标题缺失即报错，不产出无标记的规则正文。"""
    head, _, rest = body.partition("\n")
    if not head.startswith("# "):
        raise ValueError(
            "framework/hosts/steps.md 必须以一级标题开头，生成的 rules/steps.md 无从插生成物头部")
    return head + "\n\n" + STEPS_HEADER + rest.lstrip("\n")


def load_roles():
    """角色薄投影的源数据；解析走 `flow.cached_yaml`（按路径、mtime、大小缓存，返回深拷贝）。"""
    return flow.cached_yaml(ROLES_PATH)["roles"]


def _quote(value):
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _frontmatter(fields):
    lines = ["---"]
    for key, value in fields.items():
        if isinstance(value, list):
            lines.append("%s: [%s]" % (key, ", ".join(value)))
        else:
            lines.append("%s: %s" % (key, _quote(value)))
    lines.append("---")
    return "\n".join(lines) + "\n"


def _role_body(role):
    must = "、".join("`%s`" % item for item in role["must_read"])
    forbidden = "、".join(role["forbidden"])
    return (
        AUTHOR_NOTE + "\n\n"
        "# %s\n\n"
        "输入：%s\n\n"
        "输出：%s\n\n"
        "必读：%s\n\n"
        "禁止：%s\n\n"
        "返回格式：%s\n\n"
        "规则正文只读 `rules/roles/%s.md`。\n"
    ) % (
        role["title"],
        "、".join(role["inputs"]),
        "、".join(role["outputs"]),
        must,
        forbidden,
        role["return_format"],
        role["id"],
    )


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def render():
    root = project_root()
    written = []
    standing = _fill_markers(standing_text(), "framework/hosts/standing.md",
                             required=(ACTIONS_MARKER, STOP_TABLE_MARKER))
    written.append(_write(os.path.join(root, "AGENTS.md"), standing))
    # rules/steps.md：正文源在 framework/hosts/steps.md，停点总表在这里填进去。
    steps = _fill_markers(_steps_product(steps_text()), "framework/hosts/steps.md",
                          required=(STOP_TABLE_MARKER,))
    written.append(_write(os.path.join(root, STEPS_OUTPUT), steps))
    # rules/pubip.md：正文、清单与例化示例手写在文件里，参数/端口生成区按 pub_code/ 的 RTL 重写。
    written.append(_write(os.path.join(root, PUBIP_OUTPUT), pubip_doc.pubip_markdown(root)))
    for role in load_roles():
        body = _role_body(role)
        skill = _frontmatter({
            "name": role["id"],
            "description": role["description"],
        }) + "\n" + body
        written.append(_write(os.path.join(root, "skills", role["id"], "SKILL.md"), skill))
    for host in HOSTS:
        body = (
            AUTHOR_NOTE + "\n\n"
            "# %s\n\n"
            "负责停点 %s。先读 `%s`，再按 `python3 script/framework.py status <sys>` 行动。\n"
            "人机交互只有三条通道：决策点选、里程碑、其余动作全自动。\n\n"
            + ACTIONS_MARKER + "\n\n" + STOP_TABLE_MARKER
        ) % (host["title"], _host_stops(host["milestones"]), host["must_read"])
        body = _fill_markers(body, "host %s 卡正文模板" % host["id"],
                             required=(ACTIONS_MARKER, STOP_TABLE_MARKER))
        skill = _frontmatter({
            "name": host["id"],
            "description": host["description"],
        }) + "\n" + body
        written.append(_write(os.path.join(root, "skills", host["id"], "SKILL.md"), skill))
    # 按当前剖面生成仓库根 `.mcp.json`（MCP 客户端经 SSH 启动远端
    # eda-mcp-server）。与 AGENTS.md 一样属于生成物，逐字节比对测试见
    # framework/tests/test_mcp_config.py。剖面没有 eda_mcp 字段时不生成；
    # 已存在的旧文件不在这里删（可能是手工配置，由开发者处置）。
    mcp_text = eda_mcp.mcp_json_text(load_profile())
    if mcp_text:
        written.append(_write(os.path.join(root, eda_mcp.MCP_JSON_REL), mcp_text))
    return written
