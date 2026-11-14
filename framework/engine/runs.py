# 作者：vick 邮箱：ykun@yk9811.com

"""工具运行记录、输入摘要与参考数据登记。"""

import hashlib, os, re
from framework.state import record_event, state_txn, sys_dir
from framework.engine.runtime import current_time as now
from framework.engine.runtime import (
    EngineError,
    _module_files,
    _path_digest,
    module_digest,
)


def register_golden(root, name, data, gen, inputs):
    """登记参考数据：产物路径、生成脚本、输入清单与产物摘要。

    复用 task-12 备好的持久化段（`state.golden_add/golden_find`，schema 仍 v3）；
    新鲜度由行 10 闸门按"生成脚本或输入的修改时间晚于登记时间"判定，不新增字段。
    返回 G 号。
    """
    from framework.state import golden_add
    data = str(data or "").strip()
    gen = str(gen or "").strip()
    paths = [str(item).strip() for item in (inputs or []) if str(item).strip()]
    base = sys_dir(root, name)
    if not data.startswith("testbench/"):
        raise EngineError("参考数据要放在 testbench/ 下（--data testbench/<dut>/data/<文件>），收到 %s" % data)
    if not os.path.isfile(os.path.join(base, data)):
        raise EngineError("参考数据不存在：%s" % data)
    if not os.path.isfile(os.path.join(base, gen)):
        raise EngineError("生成脚本不存在：%s" % gen)
    for rel in paths:
        if not os.path.exists(os.path.join(base, rel)):
            raise EngineError("生成输入不存在：%s" % rel)
    digest = _path_digest(root, name, data)
    with state_txn(root, name, cmd="golden_register") as state:
        gid = golden_add(state, data, gen, paths, digest)
        record_event(state, "参考数据登记", obj=gid,
                     evidence="产物 %s；生成脚本 %s；输入 %s；摘要 %s"
                              % (data, gen, "、".join(paths), digest[:12]))
    return gid


CAPABILITY_INPUTS = {
    "lint": ("rtl", "pub_code"),
    "sim": ("rtl", "testbench", "tb_common", "pub_code"),
    "coverage": ("rtl", "testbench", "tb_common", "pub_code"),
    "synth": ("rtl", "pub_code", "sdc"),
    "sta": ("netlist", "sdc"),
    "conn": ("netlist", "sdc"),
    "signoff": ("netlist", "sdc"),
    # 交接挂点：CDC 看 RTL 与约束（时钟定义在 SDC 里，跨域检查也依赖它），
    # 不给它定义输入集就会走"全量输入"的旧口径。
    "cdc": ("rtl", "pub_code", "sdc"),
    # 等价性检查（CEC）：候选 RTL 与黄金参考 RTL 的组合等价；黄金文件走
    # extra_paths（运行记录的 sdc_paths 通用扩展位）进输入摘要。
    "lec": ("rtl", "pub_code"),
}


_NETLIST_ONLY = ("sta", "conn", "signoff")


def _digest_folder(digest, base, folder):
    folder_path = os.path.join(base, folder)
    if not os.path.isdir(folder_path):
        return
    for dirpath, dirnames, files in os.walk(folder_path):
        dirnames[:] = sorted(item for item in dirnames if item != "__pycache__")
        for fn in sorted(files):
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, base).replace(os.sep, "/")
            digest.update(rel.encode())
            with open(path, "rb") as fh:
                digest.update(fh.read())


def _digest_lint_rtl(digest, base):
    """lint 的 RTL 输入：每个 HDL 文件连同 include 链与 digest-extra 附属文件。

    复用 _module_files 的展开（include 链、`// digest-extra:` 附属文件），非 HDL
    文件仍按字节进摘要。module_digest 是单模块口径，这里按 rtl/ 全目录算。
    """
    rtl = os.path.join(base, "rtl")
    if not os.path.isdir(rtl):
        return
    for dirpath, dirnames, files in os.walk(rtl):
        dirnames[:] = sorted(item for item in dirnames if item != "__pycache__")
        for fn in sorted(files):
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, base).replace(os.sep, "/")
            digest.update(rel.encode())
            if fn.endswith((".v", ".sv", ".svh", ".vh")):
                parts = sorted(_module_files(path))
                blob = "\n".join("%s:%s" % item for item in parts)
                digest.update(hashlib.sha256(blob.encode("utf-8")).hexdigest().encode())
            else:
                with open(path, "rb") as fh:
                    digest.update(fh.read())


def _digest_extra_file(digest, root, path):
    if not path or not os.path.isfile(path):
        return
    digest.update(os.path.abspath(path).encode())
    with open(path, "rb") as fh:
        digest.update(fh.read())


def inputs_digest(root, name, extra_paths=None, scenario="", module="", capability="", netlist=""):
    """运行输入摘要。capability 决定输入集（见 CAPABILITY_INPUTS）。

    capability 不在表里时保持旧的全量口径（rtl+testbench+spec_doc+tb_common+pub_code），
    停点指纹等既有调用语义不变。netlist 是子系统相对或绝对路径，只有时序类输入集用。
    """
    digest = hashlib.sha256()
    base = sys_dir(root, name)
    items = CAPABILITY_INPUTS.get(capability)
    legacy = items is None
    if legacy:
        items = ("rtl", "testbench", "spec_doc", "tb_common", "pub_code")
    for folder in items:
        if folder == "pub_code":
            for path in _pub_code_used(root, base):
                digest.update(("pub_code/" + os.path.basename(path)).encode())
                with open(path, "rb") as fh:
                    digest.update(fh.read())
        elif folder == "tb_common":
            common = os.path.join(root, "tb_common")
            if os.path.isdir(common):
                for fn in sorted(os.listdir(common)):
                    path = os.path.join(common, fn)
                    if os.path.isfile(path):
                        digest.update(("tb_common/" + fn).encode())
                        with open(path, "rb") as fh:
                            digest.update(fh.read())
        elif folder == "sdc":
            for extra in extra_paths or []:
                _digest_extra_file(digest, root, extra)
        elif folder == "netlist":
            if netlist:
                _digest_extra_file(digest, root,
                                   netlist if os.path.isabs(netlist) else os.path.join(root, netlist))
        elif folder == "rtl" and capability == "lint":
            _digest_lint_rtl(digest, base)
        else:
            _digest_folder(digest, base, folder)
    if scenario == "pubip" and capability not in _NETLIST_ONLY:
        for path in _pubip_used(root, scenario, module):
            digest.update(os.path.relpath(path, root).replace(os.sep, "/").encode())
            with open(path, "rb") as fh:
                digest.update(fh.read())
    if legacy:
        # 旧口径一律把 SDC 等附加路径算进摘要，保持既有调用语义。
        for extra in extra_paths or []:
            _digest_extra_file(digest, root, extra)
    return digest.hexdigest()


def _pubip_used(root, scenario, module):
    """pubip 场景的输入：公共 IP 的 RTL 与它自己的 TB 平台。

    这两处都不在 `--sys` 指向的子系统目录里，只按子系统目录算摘要的话，
    改了公共 IP 或它的 TB，旧运行记录仍会被判“新鲜”。
    """
    if scenario != "pubip" or not module:
        return []
    paths = []
    for ext in (".sv", ".v"):
        path = os.path.join(root, "pub_code", module + ext)
        if os.path.isfile(path):
            paths.append(path)
    tb = os.path.join(root, "pub_code", "testbench", module)
    for dirpath, dirnames, files in os.walk(tb):
        dirnames[:] = sorted(item for item in dirnames if item != "__pycache__")
        for fn in sorted(files):
            paths.append(os.path.join(dirpath, fn))
    return paths


def run_inputs_digest(root, name, run):
    """按运行记录自己的能力与场景重算输入摘要（输入集见 CAPABILITY_INPUTS）。"""
    scope = run.get("scope") or {}
    return inputs_digest(root, name, run.get("sdc_paths") or [],
                         scenario=scope.get("scenario") or "", module=scope.get("module") or "",
                         capability=run.get("capability") or "",
                         netlist=scope.get("netlist") or "")


def _hdl_text(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return re.sub(r"//[^\n]*", " ", text)


def _pub_code_used(root, base):
    """子系统 RTL 例化到的 pub_code 模块文件，含公共 IP 内部再例化的，按例化关系逐层展开。"""
    pub = os.path.join(root, "pub_code")
    rtl = os.path.join(base, "rtl")
    if not os.path.isdir(pub) or not os.path.isdir(rtl):
        return []
    own = {fn.rsplit(".", 1)[0] for fn in os.listdir(rtl) if fn.endswith((".sv", ".v"))}
    library = {fn.rsplit(".", 1)[0]: os.path.join(pub, fn)
               for fn in sorted(os.listdir(pub)) if fn.endswith((".sv", ".v"))}
    pending = [_hdl_text(os.path.join(rtl, fn)) for fn in sorted(os.listdir(rtl))
               if fn.endswith((".sv", ".v"))]
    used = {}
    while pending:
        text = pending.pop()
        for mod, path in library.items():
            if mod in own or mod in used:
                continue
            if re.search(r"\b%s\s*(#\s*\(|[A-Za-z_]\w*\s*\()" % re.escape(mod), text):
                used[mod] = path
                pending.append(_hdl_text(path))
    return [used[mod] for mod in sorted(used)]


def _short_summary(text):
    lines = []
    for line in (text or "").splitlines():
        if line.strip():
            lines.append(line[:200])
        if len(lines) == 5:
            break
    return "\n".join(lines)


def _coverage_basis(state, scope):
    """覆盖率记录依据的那次仿真。

    取同场景、同模块、带 `--coverage` 的最近一次仿真；一次都没有时退到同场景
    同模块的最近一次仿真，让记录里至少留下一个可核对的现象号（闸门会再比对）。
    """
    scenario = scope.get("scenario") or "sys"
    module = scope.get("module") or ""
    fallback = ""
    for run in reversed(state.get("runs") or []):
        if run.get("capability") != "sim":
            continue
        rscope = run.get("scope") or {}
        if (rscope.get("scenario") or "sys") != scenario:
            continue
        if (rscope.get("module") or "") != module:
            continue
        if rscope.get("coverage"):
            return run.get("id") or ""
        if not fallback:
            fallback = run.get("id") or ""
    return fallback


def record_run(root, name, result):
    if result.get("status") == "dry_run":
        raise EngineError("dry-run 不记入运行记录")
    with state_txn(root, name, cmd="record_run") as state:
        state["seq"]["R"] = state["seq"].get("R", 0) + 1
        rid = "R%03d" % state["seq"]["R"]
        extras = result.get("sdc_paths") or []
        scope = dict(result.get("scope") or {})
        capability = result.get("capability") or ""
        if capability == "coverage" and not scope.get("based_on_sim"):
            # 覆盖率工作目录里的 simv.vdb 是上一次仿真留下的，记下它依据的是哪一次。
            scope["based_on_sim"] = _coverage_basis(state, scope)
        status = result.get("status") or "error"
        summary = result.get("summary", "")
        # 摘要在 rsync 前（profile_run 放进结果）与拉回后各算一次，
        # 不一致说明运行期间有人改了输入，这份记录不能判新鲜。
        digest = result.get("inputs_digest") or inputs_digest(
            root, name, extras, scenario=scope.get("scenario") or "",
            module=scope.get("module") or "", capability=capability,
            netlist=scope.get("netlist") or "")
        pre = result.get("inputs_digest_pre")
        if pre and pre != digest:
            status = "error"
            summary = "输入在运行期间变更：运行开始前与拉回后的输入摘要不一致"
        if capability == "lint" and scope.get("modules") and "module_digests" not in scope:
            base = sys_dir(root, name)
            scope["module_digests"] = {mod: module_digest(base, mod) for mod in scope["modules"]}
            pre_mods = result.get("module_digests_pre") or {}
            moved = sorted(mod for mod in scope["modules"]
                           if pre_mods and pre_mods.get(mod) != scope["module_digests"][mod])
            if moved:
                status = "error"
                summary = "输入在运行期间变更：模块摘要不一致 %s" % "、".join(moved)
        state["runs"].append({
            "id": rid,
            "time": now(),
            "capability": capability,
            "status": status,
            "summary": _short_summary(summary),
            "profile_id": result.get("profile_id", ""),
            "checks": result.get("checks") or {},
            "scope": scope,
            "artifacts": result.get("artifacts") or [],
            "sdc_paths": list(extras),
            "inputs_digest": digest,
            "note": result.get("note", ""),
            # 输出侧证据：日志相对路径与内容摘要（闸门判新鲜时复算比对，日志被
            # 改过即"结论不可信"），加上结构化诊断清单（回修入口，不改判定）。
            **({"log": result["log"],
                "log_digest": result.get("log_digest") or ""}
               if result.get("log") else {}),
            **({"diagnostics": result["diagnostics"],
                "diagnostics_total": result.get("diagnostics_total") or 0}
               if result.get("diagnostics") else {}),
            # 本次运行写出的远端波形路径列表（run sim --wave fsdb 时由
            # profile_run 放进结果）；dbg 按它精确匹配产生波形的运行记录，
            # 旧记录没有这个字段时 dbg 退回按最近同场景运行推断。
            **({"waves": list(result["waves"])} if result.get("waves") is not None else {}),
        })
        record_event(state, "运行记录", obj=rid,
                     evidence="%s %s" % (capability, status))
    return rid
