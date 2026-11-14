# 作者：vick 邮箱：ykun@yk9811.com

"""写权限台账（文件锁）：主持者用来协调"谁此刻能写哪些文件或目录"。

这是**协调机制，不是强制机制**：宿主的文件工具不会被脚本拦住，成员按规则在写前确认自己持有写权限。

- 成员不自行取锁：成员向主持者申请，由主持者授予（`lock grant`），任务完成即撤销。
- 只保留一份登记表 `locks/registry.json`；每次读写都先清掉已超时的条目，不积累文件。
- 超时即自动释放；要继续写就再向主持者申请（`lock renew` 由主持者执行）。
- 子代理不申请写权限：它的写范围由成员下发任务时限定；要扩范围由成员向主持者申请。
"""

import json
import os
import tempfile
import time

DEFAULT_TTL_MINUTES = 30
REGISTRY_REL = ("locks", "registry.json")


class LockError(Exception):
    """写权限台账的错误：路径冲突、找不到条目、参数不合法。"""


def registry_path(root):
    """登记表的绝对路径（只此一份，不按锁分文件）。"""
    return os.path.join(root, *REGISTRY_REL)


def _now():
    return time.time()


def _ttl(minutes):
    if minutes is None:
        return float(DEFAULT_TTL_MINUTES)
    try:
        value = float(minutes)
    except (TypeError, ValueError):
        raise LockError("--ttl 必须是分钟数")
    if value <= 0:
        raise LockError("--ttl 必须大于 0")
    return value


def normalize(root, raw):
    """把申请里的路径规范成显示名；目录以 / 结尾。

    末尾带 `/` 视为目录；否则若在仓库里已经是目录也视为目录；其余视为文件。
    """
    text = str(raw or "").strip().replace("\\", "/")
    if not text:
        raise LockError("路径不能为空")
    marked_dir = text.endswith("/")
    text = os.path.normpath(text)
    if text in (".", ""):
        raise LockError("路径不能是仓库根：%s" % raw)
    if text == os.pardir or text.startswith(os.pardir + os.sep):
        raise LockError("路径必须在仓库内：%s" % raw)
    if not marked_dir and os.path.isdir(os.path.join(root, text)):
        marked_dir = True
    return (text + "/") if marked_dir else text


def overlaps(left, right):
    """两个规范化路径是否相交（相等、一为另一的前缀、文件落在目录内）。"""
    if left == right:
        return True
    if left.endswith("/"):
        return right.startswith(left) or right == left.rstrip("/")
    if right.endswith("/"):
        return left.startswith(right) or left == right.rstrip("/")
    return False


def holds(granted, target):
    """已授予的 granted 是否覆盖 target（文件只能覆盖同名文件，目录覆盖其下全部）。"""
    if granted == target:
        return True
    if granted.endswith("/"):
        return target.startswith(granted) or target == granted.rstrip("/")
    return False


def _read(root):
    path = registry_path(root)
    if not os.path.isfile(path):
        return {"locks": []}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (ValueError,):
        raise LockError("登记表不是合法 JSON：%s" % path)
    if not isinstance(data, dict) or not isinstance(data.get("locks"), list):
        raise LockError("登记表结构不对（应含 locks 列表）：%s" % path)
    if "requests" in data and not isinstance(data["requests"], list):
        raise LockError("登记表结构不对（requests 应为列表）：%s" % path)
    data.setdefault("requests", [])
    return data


def _write(root, data):
    path = registry_path(root)
    parent = os.path.dirname(path)
    os.makedirs(parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=parent, prefix=".registry-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)


def _drop_expired(data, now):
    kept, dropped = [], []
    for row in data.get("locks") or []:
        if float(row.get("expires_at") or 0) > now:
            kept.append(row)
        else:
            dropped.append(row)
    data["locks"] = kept
    return dropped


def load(root):
    """读登记表并顺手清掉超时条目；返回 (数据, 本次清掉的条目)。"""
    data = _read(root)
    dropped = _drop_expired(data, _now())
    if dropped:
        _write(root, data)
    return data, dropped


def _find(data, member):
    for row in data.get("locks") or []:
        if row.get("member") == member:
            return row
    return None


def _requests(data):
    rows = data.get("requests")
    if not isinstance(rows, list):
        rows = []
        data["requests"] = rows
    return rows


def _find_request(data, member):
    for row in _requests(data):
        if row.get("member") == member:
            return row
    return None


def _conflicts(data, member, wanted):
    """wanted 与**别人**的有效写权限相交的项：[(本侧路径, 对方路径, 对方成员, 对方任务)]。"""
    hits = []
    for row in data.get("locks") or []:
        if row.get("member") == member:
            continue
        for mine_path in wanted:
            for other in row.get("paths") or []:
                if overlaps(mine_path, other):
                    hits.append((mine_path, other, row.get("member"),
                                 "、".join(row.get("tasks") or [])))
    return hits


def grant(root, member, task, paths, ttl_minutes=None, note=""):
    """主持者授予 `member` 在 `task` 上写 `paths` 的权限；与他人有效条目相交即拒绝。"""
    member = str(member or "").strip()
    task = str(task or "").strip()
    if not member:
        raise LockError("必须指定成员（--to）")
    if not task:
        raise LockError("必须指定任务（--task）")
    wanted = [normalize(root, item) for item in (paths or [])]
    if not wanted:
        raise LockError("必须指定至少一个路径（--paths）")
    ttl = _ttl(ttl_minutes)
    data, _ = load(root)
    hits = _conflicts(data, member, wanted)
    if hits:
        asked, other, holder, tasks = hits[0]
        raise LockError("路径冲突：%s 与 %s 的 %s（任务：%s）相交；先协调或撤销再授予"
                        % (asked, holder, other, tasks))
    now = _now()
    row = _find(data, member)
    if row is None:
        row = {"member": member, "granted_at": now, "tasks": []}
        data["locks"].append(row)
    tasks = [item for item in row.get("tasks") or [] if item != task]
    tasks.append(task)
    row["tasks"] = sorted(tasks)
    if note:
        row["note"] = note
    merged = list(row.get("paths") or [])
    for item in wanted:
        if item not in merged:
            merged.append(item)
    row["paths"] = sorted(merged)
    row["ttl_minutes"] = ttl
    row["renewed_at"] = now
    row["expires_at"] = now + ttl * 60.0
    pending = _find_request(data, member)
    if pending is not None:
        _requests(data).remove(pending)
    _write(root, data)
    return row


def renew(root, member, ttl_minutes=None):
    """主持者续期：超时前把限时往后推，让成员继续写。"""
    member = str(member or "").strip()
    data, _ = load(root)
    row = _find(data, member)
    if row is None:
        raise LockError("%s 现在没有有效写权限（可能已超时释放）；请用 lock grant 重新申请" % member)
    ttl = _ttl(ttl_minutes) if ttl_minutes is not None else float(
        row.get("ttl_minutes") or DEFAULT_TTL_MINUTES)
    now = _now()
    row["ttl_minutes"] = ttl
    row["renewed_at"] = now
    row["expires_at"] = now + ttl * 60.0
    _write(root, data)
    return row


def revoke(root, member, path=""):
    """主持者撤销：任务完成即撤销；给 `path` 时只收窄那一项。"""
    member = str(member or "").strip()
    data, _ = load(root)
    row = _find(data, member)
    if row is None:
        raise LockError("%s 没有有效写权限" % member)
    if path:
        target = normalize(root, path)
        remaining = [item for item in row.get("paths") or [] if item != target]
        if len(remaining) == len(row.get("paths") or []):
            raise LockError("%s 的写权限里没有 %s" % (member, target))
        row["paths"] = remaining
        if not remaining:
            data["locks"].remove(row)
    else:
        data["locks"].remove(row)
    _write(root, data)


def check(root, member, path):
    """成员写前自查：`member` 是否被授予写 `path`。返回 (是否, 说明)。"""
    member = str(member or "").strip()
    target = normalize(root, path)
    data, _ = load(root)
    row = _find(data, member)
    if row is None:
        return False, "%s 没有有效写权限（可能已超时释放）；请向主持者申请" % member
    for item in row.get("paths") or []:
        if holds(item, target):
            return True, "%s（任务：%s）" % (item, "、".join(row.get("tasks") or []))
    return False, "%s 的写权限不含 %s；已授予：%s" % (
        member, target, "、".join(row.get("paths") or []) or "（空）")


def request(root, member, task, paths, note=""):
    """成员申请写权限：只排队、不产生写权限；等主持者 `grant` 时才真正授予。

    同一成员只留一条申请（后加的路径并入，**保留最初的排队位次**，避免加一条路径就掉队）。
    """
    member = str(member or "").strip()
    task = str(task or "").strip()
    if not member:
        raise LockError("必须指定成员（--to）")
    if not task:
        raise LockError("必须指定任务（--task）")
    wanted = [normalize(root, item) for item in (paths or [])]
    if not wanted:
        raise LockError("必须指定至少一个路径（--paths）")
    data, _ = load(root)
    held = _find(data, member)
    if held is not None and all(
            any(holds(item, want) for item in held.get("paths") or []) for want in wanted):
        raise LockError("%s 已经持有这些路径的写权限，不必排队；要扩范围请另开路径" % member)
    row = _find_request(data, member)
    if row is None:
        row = {"member": member, "requested_at": _now(), "tasks": []}
        _requests(data).append(row)
    tasks = [item for item in row.get("tasks") or [] if item != task]
    tasks.append(task)
    row["tasks"] = sorted(tasks)
    merged = list(row.get("paths") or [])
    for item in wanted:
        if item not in merged:
            merged.append(item)
    row["paths"] = sorted(merged)
    if note:
        row["note"] = note
    _write(root, data)
    return row


def cancel(root, member):
    """成员撤申请，或主持者清掉过期申请。"""
    member = str(member or "").strip()
    data, _ = load(root)
    row = _find_request(data, member)
    if row is None:
        raise LockError("%s 不在等待队列里" % member)
    _requests(data).remove(row)
    _write(root, data)


def waiting(root):
    """等待队列：按申请先后排序，并标出当前被谁挡住（空 = 可立即授予）。"""
    data, dropped = load(root)
    rows = []
    for row in sorted(_requests(data), key=lambda item: float(item.get("requested_at") or 0)):
        wanted = list(row.get("paths") or [])
        holders = []
        for _asked, _other, holder, _tasks in _conflicts(data, row.get("member"), wanted):
            if holder not in holders:
                holders.append(holder)
        rows.append({
            "member": row.get("member"),
            "tasks": list(row.get("tasks") or []),
            "paths": wanted,
            "requested_at": row.get("requested_at"),
            "note": row.get("note") or "",
            "blocked_by": holders,
        })
    return rows, dropped


def listing(root):
    """主持者看板：全部有效条目 + 剩余分钟；并回报本次清掉的超时条目。"""
    data, dropped = load(root)
    now = _now()
    rows = []
    for row in sorted(data["locks"], key=lambda item: str(item.get("member"))):
        left = (float(row.get("expires_at") or 0) - now) / 60.0
        rows.append({
            "member": row.get("member"),
            "tasks": list(row.get("tasks") or []),
            "paths": list(row.get("paths") or []),
            "remaining_minutes": max(0.0, left),
            "note": row.get("note") or "",
        })
    return rows, dropped
