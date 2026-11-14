# 作者：vick 邮箱：ykun@yk9811.com

"""读取 flow_model.yaml。停点定义只此一份。

读取层助手（引擎与闸门从这里取流程模型事实）：
- milestones()                      全部里程碑（声明序）
- milestone(id)                     按号取单个里程碑，没有则 None
- milestone_of_stop(sid)            覆盖该停点的里程碑，没有则 None
- depends_on(sid)                   停点的直接依赖（int 列表）
- dependency_closure(sid)           依赖闭包（含自身，拓扑序：依赖在前）
- dependents(sid)                   直接下游停点（int 列表）
- actions()                         动作策略表（声明序）
- action(id)                        按号取单个动作，没有则 None
- action_ids()                      动作号集合
- requires_of(id)                   动作的前提标识列表（没写 requires 返回空列表）
- actions_by_class(cls)             按 class 过滤（auto/decision/milestone/redline）
- stop_ids()                        模型声明的停点号集合（停点集合的唯一事实源）
- stages() / stage_title(stage)     阶段号（声明序）与分阶段裁决表标题
- stage_of_stop(sid)                停点的阶段号（读 stage: 字段）
- product_path(stop, sys)           停点产物路径（{sys} 替换为子系统名）
- module_rows() / module_row_label() 模块行集合（由 review: 推导）与展示名
- stop_review(sid)                  停点的独立审查要求（spec_review / rtl_review_per_module /
                                    rtl_review / tb_review / none）
- stop_blocked_by_items(sid)        存在在途调试事项时是否挡该停点送审
- milestone_done_stops()            只能由里程碑确认置完成的停点集合

全部纯读、无副作用；解析结果按（路径, mtime, 大小）缓存，每次返回深拷贝。
测试在副本仓库里改 flow_model.yaml 后立即生效：副本是独立路径，且改动会变
mtime/大小，命中旧条目的条件不成立。load() 与 product_path() 行为不变（engine 依赖）；
其他 yaml 读取方（章节模型、角色表）可复用 cached_yaml() 拿到同一份缓存。
"""

import collections
import copy
import os

import yaml

from framework.paths import project_root

DONE = "完成（审核通过）"
PENDING = "已送审"
RUNNING = "进行中"
NOT_STARTED = "未开始"

# 解析缓存：绝对路径 -> (mtime_ns, size, 解析结果)。一次 summary add 曾把
# flow_model.yaml 解析 16 次、占掉大半耗时，这里只解析一次。
# 键带 mtime 与大小两栏：HFS+ 这类 mtime 只有秒级精度的文件系统上，同一秒内改
# 内容靠大小兜住（测试改 flow_model.yaml 就是同一秒内写的，2 -> 99 会变大小）。
# 按绝对路径分桶，RepoTest 每次复制出的新副本互不影响；上限兜住长时间 selftest
# 里不断累积的副本路径。
_YAML_CACHE = collections.OrderedDict()
_YAML_CACHE_MAX = 16


def model_path():
    """flow_model.yaml 的绝对路径（ADF_ROOT 可变，因此每次现算）。"""
    return os.path.join(project_root(), "framework", "flow_model.yaml")


def model_stamp():
    """(路径, mtime_ns, 大小)；文件缺失时 None。闸门备忘据此判断模型是否改过。"""
    path = model_path()
    if not os.path.isfile(path):
        return None
    st = os.stat(path)
    return (path, st.st_mtime_ns, st.st_size)


def cached_yaml(path):
    """按（路径, mtime, 大小）缓存一次 yaml 解析，每次返回深拷贝。

    深拷贝是必需的：调用方（含测试）会改返回的模型，共享同一个对象会让改动串到
    下一次 load()，而旧行为是每次重新解析、改动不串。
    """
    path = os.path.abspath(path)
    stamp = None
    if os.path.isfile(path):
        st = os.stat(path)
        stamp = (st.st_mtime_ns, st.st_size)
    if stamp is not None:
        hit = _YAML_CACHE.get(path)
        if hit is not None and hit[0] == stamp:
            _YAML_CACHE.move_to_end(path)
            return copy.deepcopy(hit[1])
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if stamp is not None:
        _YAML_CACHE[path] = (stamp, data)
        _YAML_CACHE.move_to_end(path)
        while len(_YAML_CACHE) > _YAML_CACHE_MAX:
            _YAML_CACHE.popitem(last=False)
    return copy.deepcopy(data)


def load():
    data = cached_yaml(model_path())
    data["by_id"] = {int(s["id"]): s for s in data["stops"]}
    return data


def product_path(stop, sys_name):
    return stop["product"].replace("{sys}", sys_name)


def milestones():
    return list(load().get("milestones") or [])


def milestone(mid):
    for item in milestones():
        if item["id"] == mid:
            return dict(item)
    return None


def milestone_of_stop(sid):
    sid = int(sid)
    for item in milestones():
        if sid in [int(x) for x in item.get("covers") or []]:
            return dict(item)
    return None


def depends_on(sid):
    stop = load()["by_id"].get(int(sid))
    if stop is None:
        return []
    return [int(x) for x in stop.get("depends_on") or []]


def dependency_closure(sid):
    """依赖闭包（含自身），拓扑序：被依赖的停点在前，自身最后。

    未知的停点号跳过；环由 seen 集合兜住（模型不该有环，错了也不死循环）。
    """
    sid = int(sid)
    by_id = load()["by_id"]
    order, seen = [], set()

    def visit(cur):
        if cur in seen:
            return
        seen.add(cur)
        stop = by_id.get(cur)
        for dep in [int(x) for x in (stop or {}).get("depends_on") or []]:
            if dep in by_id:
                visit(dep)
        order.append(cur)

    visit(sid)
    return order


def dependents(sid):
    sid = int(sid)
    out = []
    for stop in load()["stops"]:
        if sid in [int(x) for x in stop.get("depends_on") or []]:
            out.append(int(stop["id"]))
    return out


def stop_ids():
    """模型声明的停点号集合（int 集合；停点集合的唯一事实源）。"""
    return {int(stop["id"]) for stop in load()["stops"]}


def stages():
    """模型 `stages:` 声明的阶段号（声明序，int 列表）。

    阶段号只决定 D 号前缀与分阶段裁决表的分组；`state.blank()` 的分桶与裁决表渲染
    都从这里取，不在代码里另写阶段列表。
    """
    return [int(key) for key in (load().get("stages") or {})]


def stage_title(stage):
    """阶段号 → 分阶段裁决表的分组标题；模型没声明该阶段即报错。"""
    for key, title in (load().get("stages") or {}).items():
        if int(key) == int(stage):
            return str(title)
    raise KeyError("模型 stages: 里没有阶段 %s" % stage)


def stage_of_stop(sid):
    """停点 → 阶段号（字符串，D 号前缀）：读停点的 `stage:` 字段。

    停点缺 `stage:` 字段或字段非法直接报错——阶段号是 D 号与分桶的输入，
    不能静默退回某个默认阶段。
    """
    stop = load()["by_id"].get(int(sid))
    if stop is None:
        raise KeyError("没有停点 %s" % sid)
    if "stage" not in stop:
        raise ValueError("停点 %s 缺 stage: 字段（flow_model.yaml 是唯一事实源）" % sid)
    try:
        stage = str(int(stop["stage"]))
    except (TypeError, ValueError):
        raise ValueError("停点 %s 的 stage 取值 %r 非法（须为 stages: 里声明的整数）"
                         % (sid, stop.get("stage")))
    if stage not in {str(item) for item in stages()}:
        raise ValueError("停点 %s 的 stage %s 未在 stages: 表里声明"
                         % (sid, stage))
    return stage


# flow_model.yaml 的 review: 字段合法取值（唯一事实源）。含义见 flow_model.yaml 顶部注释。
STOP_REVIEWS = ("spec_review", "tb_review", "rtl_review_per_module", "rtl_review", "none")

# 带"模块清单"的审查要求：模块行集合（state 的 modules 键、module --row 的 choices）
# 由 review: 取值推导，不写死停点号。
MODULE_REVIEWS = ("rtl_review_per_module", "rtl_review", "tb_review")
MODULE_ROW_LABELS = {
    "rtl_review_per_module": "模块",
    "rtl_review": "顶层",
    "tb_review": "平台",
}


def module_rows():
    """模块行集合：review 属于 MODULE_REVIEWS 的停点号（字符串，停点声明序）。"""
    return [str(stop["id"]) for stop in load()["stops"]
            if str(stop.get("review")) in MODULE_REVIEWS]


def module_row_label(key):
    """模块行在状态文档里的展示名，如"行 7 模块"（标签由 review: 推导）。"""
    stop = load()["by_id"].get(int(key))
    if stop is None:
        raise KeyError("没有停点 %s" % key)
    kind = str(stop.get("review"))
    return "行 %s %s" % (key, MODULE_ROW_LABELS.get(kind, "模块"))


def stop_review(sid):
    """停点的独立审查要求，读 flow_model.yaml 的 `review:` 字段。

    取值必须是 STOP_REVIEWS 之一；缺字段或取值非法直接报错——判据不能静默退化
    （少写一个字段就等于悄悄放行一个停点的审查要求）。
    """
    stop = load()["by_id"].get(int(sid))
    if stop is None:
        raise KeyError("没有停点 %s" % sid)
    if "review" not in stop:
        raise ValueError("停点 %s 缺 review: 字段（flow_model.yaml 是唯一事实源）" % sid)
    kind = str(stop.get("review"))
    if kind not in STOP_REVIEWS:
        raise ValueError("停点 %s 的 review 取值 %r 非法（须为 %s 之一）"
                         % (sid, kind, " / ".join(STOP_REVIEWS)))
    return kind


def stop_blocked_by_items(sid):
    """存在在途调试事项时是否挡该停点送审，读 flow_model.yaml 的 `blocked_by_items:`。"""
    stop = load()["by_id"].get(int(sid))
    if stop is None:
        raise KeyError("没有停点 %s" % sid)
    if "blocked_by_items" not in stop:
        raise ValueError("停点 %s 缺 blocked_by_items: 字段（flow_model.yaml 是唯一事实源）" % sid)
    return bool(stop.get("blocked_by_items"))


def actions():
    return list(load().get("actions") or [])


def action(aid):
    for item in actions():
        if item["id"] == aid:
            return dict(item)
    return None


def action_ids():
    """动作策略表里的全部动作号（集合）。"""
    return {item["id"] for item in actions()}


def requires_of(aid):
    """动作的前提标识列表（按表序）。动作不存在报 KeyError。

    没写 `requires:` 的动作返回空列表——这是读取层，不替调用方判定"空表是否合法"；
    哪些动作必须有前提由执行层（framework/policy.py）按自己的强制动作表判，
    动作表仍是唯一事实源。
    """
    act = action(aid)
    if act is None:
        raise KeyError("没有动作 %s" % aid)
    return [str(item) for item in act.get("requires") or []]


def actions_by_class(cls):
    return [dict(item) for item in actions() if item.get("class") == cls]


def milestone_done_stops():
    """动作表 `stop_done_milestone` 的 stops：只能由里程碑确认置完成、advance/tick 不置完成的停点。

    引擎与闸门共用这一处：这类停点"已送审"即算产品定稿——只有里程碑确认
    才能把它变成"完成"，而覆盖它们的里程碑（M3）又要求它们先送审；若坚持"必须已完成"，
    行 11 与行 12、M3 会互相等待（死锁）。
    """
    act = action("stop_done_milestone") or {}
    return {int(x) for x in act.get("stops") or []}
