"""Local, on-demand Windows device snapshots. Standard library only.

Only the bundled PowerShell collector is executed. Files in the selected library
are data, never programs. Each attempt has a distinct ID; old evidence is retained.
"""
from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

VERSION = "1.0.0"
SCENARIOS = {"idle": "開機後待機", "development": "日常開發", "compile-import": "編譯／匯入", "game": "遊戲運行", "custom": "自訂狀態"}
CATEGORIES = {"unity": "Unity", "blender": "Blender", "codex": "Codex／ChatGPT 及所屬工具", "visual-studio": "Visual Studio", "system": "已識別 Windows 進程", "other": "其他／歸屬未確認"}
PRESENCE_NAMES = {"unity": {"unity.exe", "unity hub.exe"}, "blender": {"blender.exe"}, "codex": {"codex.exe", "chatgpt.exe"}, "visual-studio": {"devenv.exe"}}
TERMINAL = {"completed", "partial", "cancelled", "timeout", "failed"}


def _now():
    return dt.datetime.now().astimezone().isoformat(timespec="milliseconds")


def _atomic(path: Path, value, *, json_data=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temp.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n" if json_data else value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _read(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return default


def _root(root):
    path = Path(root).expanduser().resolve()
    # A library is independent of Unity's generated/project asset directories.
    for parent in (path, *path.parents):
        if parent.name.lower() in {"assets", "library", "temp"} and (parent.parent / "ProjectSettings").is_dir():
            raise ValueError("資料庫不能放在 Unity 的 Assets、Library 或 Temp 內。")
    for child in ("snapshots", "reports", ".device-library"):
        target = path / child
        if target.resolve().parent != path:
            raise ValueError(f"資料庫子目錄 {child} 指向資料庫外部，請改用普通本地資料夾。")
    return path


def _identity(pid):
    """Creation time validates ownership without reading command lines."""
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return str(pid)
        except OSError:
            return None
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel.GetProcessTimes.argtypes = [ctypes.c_void_p, *([ctypes.c_void_p] * 4)]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(0x1000, False, int(pid))
    if not handle:
        return None
    try:
        values = [ctypes.c_uint64() for _ in range(4)]
        if kernel.GetProcessTimes(handle, *(ctypes.byref(v) for v in values)):
            return str(values[0].value)
        return None
    finally:
        kernel.CloseHandle(handle)


def _lock_active(lock):
    owner = _read(lock / "owner.json")
    if owner:
        return _identity(owner.get("pid", 0)) == owner.get("processIdentity") and owner.get("processIdentity") is not None
    try:
        return time.time() - lock.stat().st_mtime < 10
    except OSError:
        return False


def _clear_lock(lock):
    # Only our two known files may be removed. Never recursively delete a folder.
    for name in ("owner.json", "cancel"):
        (lock / name).unlink(missing_ok=True)
    lock.rmdir()


def status(root):
    meta = _root(root) / ".device-library"
    state = _read(meta / "status.json", {"status": "idle", "phase": "尚未採樣"})
    active = (meta / "collect.lock").is_dir() and _lock_active(meta / "collect.lock")
    if state.get("status") == "running" and not active:
        state = {**state, "status": "failed", "phase": "上次採樣程序已結束，原有記錄仍保留", "reason": "collector_interrupted"}
    elif active and state.get("status") != "running":
        state = {"status": "running", "phase": "正在準備採樣"}
    return state


def cancel(root):
    meta = _root(root) / ".device-library"
    lock = meta / "collect.lock"
    if lock.is_dir() and _lock_active(lock):
        try:
            (lock / "cancel").write_text(_now(), encoding="utf-8")
        except FileNotFoundError:
            return status(root)
        return {**status(root), "cancelRequested": True, "phase": "已要求取消；正在保存已取得的資料"}
    return {**status(root), "cancelRequested": False}


def _date(value):
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except (AttributeError, TypeError, ValueError):
        return None


def classify_processes(processes):
    """Verified executable identities and birth-time-checked ancestry; no keywords."""
    by_pid = {p["pid"]: p for p in processes}
    anchors = {p["pid"]: p.get("identityCategory") for p in processes if p.get("identityCategory") in CATEGORIES and p.get("identityCategory") != "other"}
    for proc in processes:
        category = anchors.get(proc["pid"])
        system_fallback = category == "system"
        if system_fallback:
            category = None
        basis = proc.get("identityReason") if category else None
        confidence = "verified" if category else "unknown"
        ancestor = proc
        seen = {proc["pid"]}
        while not category and ancestor.get("parentPid") in by_pid:
            parent = by_pid[ancestor["parentPid"]]
            if parent["pid"] in seen:
                basis = "父鏈循環，未推斷歸屬"
                break
            seen.add(parent["pid"])
            child_time, parent_time = _date(ancestor.get("startedAt")), _date(parent.get("startedAt"))
            if child_time is None or parent_time is None or child_time < parent_time:
                basis = "父子啟動時間缺失或不相容，可能有 PID 重用；未推斷歸屬"
                break
            if anchors.get(parent["pid"]) and anchors[parent["pid"]] != "system":
                category = anchors[parent["pid"]]
                basis = f"已核對啟動時間的父鏈 → {parent['name']} (PID {parent['pid']})"
                confidence = "verified-ancestry"
                break
            ancestor = parent
        if not category and system_fallback:
            category = "system"
            basis = proc.get("identityReason")
            confidence = "verified"
        proc["category"] = category or "other"
        proc["classificationConfidence"] = confidence
        proc["classificationReason"] = basis or "沒有可確認的應用身分或父鏈；名稱關鍵字不作歸屬證據"
    return processes


def _aggregate(snapshot):
    processes = classify_processes(snapshot.get("processes") or [])
    groups = []
    for key, label in CATEGORIES.items():
        members = [p for p in processes if p["category"] == key]
        known = [p.get("privateResidentBytes") for p in members if p.get("privateResidentBytes") is not None]
        unconfirmed = [p for p in processes if p["category"] == "other" and p.get("name", "").lower() in PRESENCE_NAMES.get(key, set())]
        groups.append({"category": key, "label": label, "processCount": len(members), "privateResidentBytes": sum(known) if members and known else (0 if snapshot.get("processInventoryComplete") and not members and not unconfirmed else None), "missingPrivateResidentCount": len(members) - len(known), "presenceUnconfirmed": bool(unconfirmed), "presenceReason": "發現同名進程但無法確認可執行檔身分，不能斷言本次未運行" if unconfirmed else None, "pids": [p["pid"] for p in members]})
    system = snapshot.setdefault("system", {})
    total, available = system.get("visiblePhysicalBytes"), system.get("availablePhysicalBytes")
    used = total - available if total is not None and available is not None else None
    residents = [p.get("privateResidentBytes") for p in processes if p.get("privateResidentBytes") is not None]
    remainder = used - sum(residents) if used is not None and residents else None
    system["physicalUsedBytes"] = used
    system["accountedPrivateResidentBytes"] = sum(residents) if residents else None
    system["systemSharedUnattributedBytes"] = remainder
    system["remainderMethod"] = "可見物理總量 − 可用量 − 已取得的各進程私有駐留；含共享、系統與缺失進程項，非全部核心或可清垃圾。採樣非同一原子時刻。"
    if remainder is not None and remainder < 0:
        snapshot.setdefault("errors", []).append({"metric": "memory.remainder", "reason": "分階段採樣期間狀態改變導致餘項為負，不能作互斥記憶體分解。"})
    snapshot["groups"] = groups


def _gib(value):
    return "未知／不可用" if value is None else f"{value / 1073741824:.3f} GiB"


def _mib(value):
    return "未知／不可用" if value is None else f"{value / 1048576:.1f} MiB"


def _text(value):
    return str(value if value is not None else "未知／不可用").replace("|", "／").replace("\r", " ").replace("\n", " ")


def _metric(value, suffix=""):
    return "未知／不可用" if value is None else f"{value:.2f}{suffix}"


def render_report(snapshot):
    s = snapshot.get("system") or {}
    cpu, disk, gpu = (snapshot.get(key) or {} for key in ("cpu", "disk", "gpu"))
    collector = snapshot.get("collector") or {}
    lines = [f"# 電腦狀態檢查 · {snapshot['id']}", "", f"這是 **{snapshot.get('sampledAt')}** 保存的歷史快照，不是即時監控。", "", f"- 場景：{_text(snapshot.get('scenario'))}（{SCENARIOS.get(snapshot.get('scenario'), '自訂標籤')}）", f"- 結果：{snapshot.get('status')}；採樣版本：{VERSION}", f"- 採樣開始／結束：{snapshot.get('startedAt')} ／ {snapshot.get('finishedAt')}", f"- Windows 開機時長：{_metric(s.get('uptimeSeconds'), ' 秒')}", f"- CPU 實測窗口：{_metric(cpu.get('windowSeconds'), ' 秒')}；磁碟：{_metric(disk.get('windowSeconds'), ' 秒')}；GPU 引擎：{_metric(gpu.get('windowSeconds'), ' 秒')}。各項讀取時間見 JSON。", "", "## 記憶體", "", "| 指標 | 數值 |", "| --- | ---: |"]
    for label, key in (("實装 RAM", "installedPhysicalBytes"), ("Windows 可見 RAM", "visiblePhysicalBytes"), ("可用 RAM（含 Standby 等可回收頁面）", "availablePhysicalBytes"), ("可見總量減可用量", "physicalUsedBytes"), ("系統提交", "committedBytes"), ("提交上限", "commitLimitBytes"), ("已取得的進程私有駐留合計", "accountedPrivateResidentBytes"), ("系統／共享及未細分部分", "systemSharedUnattributedBytes")):
        lines.append(f"| {label} | {_gib(s.get(key))} |")
    lines += ["", "提交量不等於物理 RAM 占用；總工作集有共享頁面，不能直接相加。", "", s.get("remainderMethod", ""), "Standby 已包含在可用量，記憶體壓縮不另加一次。", "", "## 應用分組（私有駐留）", "", "| 類別 | 進程數 | 已讀私有駐留 | 缺失項數 |", "| --- | ---: | ---: | ---: |"]
    for group in snapshot.get("groups", []):
        lines.append(f"| {group['label']} | {group['processCount']} | {_gib(group['privateResidentBytes'])} | {group['missingPrivateResidentCount']} |")
        if group.get("presenceUnconfirmed"):
            lines.append(f"| {group['label']} 身分限制 | — | {_text(group['presenceReason'])} | — |")
    lines += ["", "歸屬使用已核對可執行檔身分及啟動時間的父鏈。其他／歸屬未確認包括無權限與證據不足項。私有駐留不是應用完整記憶體需求，不能用來保證可釋放量。", "", "## CPU、磁碟與 GPU", "", "| 指標 | 數值 |", "| --- | ---: |", f"| CPU 平均活動（窗口） | {_metric(cpu.get('utilizationPercent'), '%')} |", f"| 磁碟讀取速率 | {_metric(None if disk.get('readBytesPerSecond') is None else disk['readBytesPerSecond'] / 1048576, ' MiB/s')} |", f"| 磁碟寫入速率 | {_metric(None if disk.get('writeBytesPerSecond') is None else disk['writeBytesPerSecond'] / 1048576, ' MiB/s')} |", f"| GPU 引擎最高忙碌度（短窗，非所有引擎之和） | {_metric(gpu.get('maxEngineUtilizationPercent'), '%')} |", f"| GPU 實際獨立記憶體使用 | {_gib(gpu.get('dedicatedUsedBytes'))} |", f"| GPU 實際共享記憶體使用 | {_gib(gpu.get('sharedUsedBytes'))} |", "", "獨立顯存另列；GPU 已用共享記憶體來自系統 RAM，不再加進 RAM 總占用。未讀取最大允許共享量。短窗不能證明長期卡頓、洩漏或磁碟瓶頸。", "", "## 主要進程（依已讀私有駐留排序）", "", "| 進程／PID | 分組 | 私有駐留 | 總工作集 | 私有提交 |", "| --- | --- | ---: | ---: | ---: |"]
    for p in sorted(snapshot.get("processes") or [], key=lambda p: p.get("privateResidentBytes") or -1, reverse=True)[:30]:
        lines.append(f"| {_text(p['name'])}／{p['pid']} | {CATEGORIES[p['category']]} | {_mib(p.get('privateResidentBytes'))} | {_mib(p.get('workingSetBytes'))} | {_mib(p.get('privateCommitBytes'))} |")
    lines += ["", "完整進程清單、父 PID、可讀啟動時間、分類依據及原始 bytes 保留於 JSON。", "", "## 缺失、限制與採集負担", "", f"- 採集耗時：{_metric(collector.get('elapsedSeconds'), ' 秒')}", f"- 採集 PowerShell 峰值工作集：{_mib(collector.get('powershellPeakWorkingSetBytes'))}", "- 上述峰值只計本次 PowerShell 子程序；不含共享的 WMI Provider 或宿主 Console，不等於系統淨增 RAM。", "- 不讀取完整命令列、帳號、金鑰、裝置序號或網路憑證。"]
    for error in snapshot.get("errors") or []:
        lines.append(f"- {_text(error.get('metric'))}：{_text(error.get('reason'))}")
    if not snapshot.get("errors"):
        lines.append("- 無記錄到指標讀取錯誤；這不代表硬體健康診斷。")
    lines += ["", f"原始資料：[snapshots/{snapshot['id']}.json](../snapshots/{snapshot['id']}.json)", ""]
    return "\n".join(lines)


def render_device_profile(snapshot):
    hardware, system = snapshot.get("hardware") or {}, snapshot.get("system") or {}
    lines = ["# 電腦檔案", "", f"更新於 **{snapshot.get('sampledAt')}**；這是保存的設備資料，不是即時狀態。所有下列項目使用這次更新時間。", "", "| 項目 | 已取得資料 |", "| --- | --- |", f"| 品牌／型號 | {_text(hardware.get('manufacturer'))}／{_text(hardware.get('model'))} |", f"| 實装／可見 RAM | {_gib(system.get('installedPhysicalBytes'))}／{_gib(system.get('visiblePhysicalBytes'))} |", f"| Windows | {_text(hardware.get('osCaption'))}／{_text(hardware.get('osVersion'))}，build {_text(hardware.get('osBuild'))} |"]
    for cpu in hardware.get("cpus") or []:
        lines.append(f"| CPU | {_text(cpu.get('name'))}；{cpu.get('cores')} 核心／{cpu.get('logicalProcessors')} 邏輯處理器 |")
    for ram in hardware.get("memoryModules") or []:
        lines.append(f"| RAM 模組 | {_gib(ram.get('capacityBytes'))}；標稱 {ram.get('speedMHz')}／配置 {ram.get('configuredSpeedMHz')} MT/s（WMI 原欄位） |")
    for gpu in hardware.get("gpus") or []:
        lines.append(f"| GPU | {_text(gpu.get('name'))}；驅動 {_text(gpu.get('driverVersion'))}；獨立容量 {_gib(gpu.get('dedicatedCapacityBytes'))}（{_text(gpu.get('capacityReason'))}） |")
    for disk in hardware.get("physicalDisks") or []:
        lines.append(f"| 實體磁碟 | {_text(disk.get('model'))}；{_gib(disk.get('sizeBytes'))}；介面 {_text(disk.get('interface'))}；WMI 狀態 {_text(disk.get('status'))} |")
    for volume in hardware.get("volumes") or []:
        lines.append(f"| 卷 {volume.get('letter')} | 容量 {_gib(volume.get('sizeBytes'))}／可用 {_gib(volume.get('freeBytes'))}；{_text(volume.get('fileSystem'))} |")
    lines += ["", "## 已識別的主要開發工具版本", "", "未運行或無權限讀取版本的工具可能缺失；不由資料缺失斷言未安裝。", "", "| 工具 | 版本 | 來源 |", "| --- | --- | --- |"]
    for tool in hardware.get("tools") or []:
        lines.append(f"| {_text(tool.get('name'))} | {_text(tool.get('version'))} | {_text(tool.get('source'))} |")
    lines += ["", "WMI 磁碟 Status 不是完整 SMART 診斷。Win32_VideoController.AdapterRAM 可能截斷，未當成可靠獨立顯存容量。", "", f"來源：[本次報告](reports/{snapshot['id']}.md)；[原始 JSON](snapshots/{snapshot['id']}.json)", ""]
    return "\n".join(lines)


def _measure_process_peak(process):
    if os.name != "nt":
        return None
    class MemoryCounters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_uint32), ("PageFaultCount", ctypes.c_uint32)] + [(name, ctypes.c_size_t) for name in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
    counters = MemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    api = ctypes.WinDLL("psapi", use_last_error=True).GetProcessMemoryInfo
    api.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32]
    return counters.PeakWorkingSetSize if api(ctypes.c_void_p(int(process._handle)), ctypes.byref(counters), counters.cb) else None


def _child_job(process):
    """Close the job to clean up only this collector and its driver-query child."""
    if os.name != "nt":
        return None
    class BasicLimits(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64), ("LimitFlags", ctypes.c_uint32), ("MinimumWorkingSetSize", ctypes.c_size_t), ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", ctypes.c_uint32), ("Affinity", ctypes.c_size_t), ("PriorityClass", ctypes.c_uint32), ("SchedulingClass", ctypes.c_uint32)]
    class IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount", "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]
    class ExtendedLimits(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", BasicLimits), ("IoInfo", IoCounters), ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.restype = ctypes.c_void_p
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
    kernel.SetInformationJobObject.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
    kernel.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.CreateJobObjectW(None, None)
    limits = ExtendedLimits()
    limits.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if handle and kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)) and kernel.AssignProcessToJobObject(handle, ctypes.c_void_p(int(process._handle))):
        return handle
    if handle:
        kernel.CloseHandle(handle)
    return None


def _close_job(handle):
    if handle:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.CloseHandle(handle)


def _has_metrics(snapshot):
    system = snapshot.get("system") or {}
    if any(system.get(key) is not None for key in ("visiblePhysicalBytes", "availablePhysicalBytes", "committedBytes", "installedPhysicalBytes")):
        return True
    if snapshot.get("processes") or (snapshot.get("hardware") or {}).get("model"):
        return True
    return any((snapshot.get(group) or {}).get(key) is not None for group, key in (("cpu", "utilizationPercent"), ("disk", "readBytesPerSecond"), ("gpu", "dedicatedUsedBytes")))


def collect(root, scenario="idle", timeout=45, window=1.0, cancel_event=None):
    root = _root(root)
    scenario = str(scenario).strip()
    if not scenario or len(scenario) > 100 or any(ord(char) < 32 for char in scenario):
        raise ValueError("場景必須是 1–100 字元的單行標籤。")
    timeout, window = float(timeout), float(window)
    if not 1 <= timeout <= 120 or not 0.2 <= window <= 5:
        raise ValueError("timeout 必須為 1–120 秒，window 為 0.2–5 秒。")
    meta = root / ".device-library"
    meta.mkdir(parents=True, exist_ok=True)
    lock = meta / "collect.lock"
    try:
        lock.mkdir()
    except FileExistsError:
        if _lock_active(lock):
            return {**status(root), "alreadyRunning": True}
        try:
            _clear_lock(lock)
            lock.mkdir()
        except OSError:
            return {"status": "running", "phase": "採樣鎖仍存在，請稍後重試", "alreadyRunning": True}
    run_id = dt.datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f") + "-" + uuid.uuid4().hex[:6]
    owner = {"pid": os.getpid(), "processIdentity": _identity(os.getpid()), "id": run_id}
    _atomic(lock / "owner.json", owner)
    checkpoint = meta / (run_id + ".checkpoint.json")
    state = {"id": run_id, "status": "running", "phase": "準備採樣", "startedAt": _now(), "scenario": scenario}
    _atomic(meta / "status.json", state)
    started = time.monotonic()
    process, snapshot, peak, result_status, child_job = None, {}, None, "failed", None
    try:
        script = Path(__file__).resolve().parent / "tools" / "Collect-DeviceSnapshot.ps1"
        if os.name != "nt":
            raise RuntimeError("此採樣器需要 Windows；已有報告仍可閱讀及對比。")
        if not script.is_file():
            raise RuntimeError("固定採樣器缺失，請修復 Console 安裝。")
        powershell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
        if cancel_event is not None and cancel_event.is_set():
            result_status = "cancelled"
            raise InterruptedError("採樣啟動前已取消")
        process = subprocess.Popen([str(powershell), "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script), "-OutputPath", str(checkpoint), "-CancelPath", str(lock / "cancel"), "-WindowSeconds", str(window)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        child_job = _child_job(process)
        while process.poll() is None:
            measured = _measure_process_peak(process)
            if measured is not None:
                peak = max(peak or 0, measured)
            current = _read(checkpoint, {})
            if current.get("phase") and current["phase"] != state["phase"]:
                state["phase"] = current["phase"]
                _atomic(meta / "status.json", state)
            if (lock / "cancel").exists() or (cancel_event is not None and cancel_event.is_set()):
                result_status = "cancelled"
                process.terminate()
                break
            if time.monotonic() - started >= timeout:
                result_status = "timeout"
                process.terminate()
                break
            time.sleep(0.10)
        process.wait(timeout=5)
        snapshot = _read(checkpoint, {})
        measured = _measure_process_peak(process)
        peak = max(peak or 0, measured or 0) or None
        if result_status not in {"cancelled", "timeout"}:
            result_status = "completed" if process.returncode == 0 and snapshot.get("complete") and _has_metrics(snapshot) else ("partial" if _has_metrics(snapshot) else "failed")
            if result_status == "completed" and snapshot.get("errors"):
                result_status = "partial"
        if result_status == "cancelled":
            snapshot.setdefault("errors", []).append({"metric": "collector", "reason": "使用者取消；只保留取消前已完成的階段。"})
        elif result_status == "timeout":
            snapshot.setdefault("errors", []).append({"metric": "collector", "reason": f"達 {timeout:g} 秒期限；只保留期限前已完成的階段。"})
        elif process.returncode:
            snapshot.setdefault("errors", []).append({"metric": "collector", "reason": f"固定採樣器結束碼 {process.returncode}；保留已完成階段。"})
        diagnostic = _read(checkpoint.with_name(checkpoint.name + ".diagnostic.json"))
        if isinstance(diagnostic, dict):
            snapshot.setdefault("errors", []).append({"metric": "collector.script", "reason": f"固定採樣器第 {diagnostic.get('line', '?')} 行：{str(diagnostic.get('type', 'unknown'))[:100]}；代碼 {str(diagnostic.get('code', 'unknown'))[:300]}"})
    except InterruptedError:
        snapshot = {"errors": [{"metric": "collector", "reason": "採樣開始前使用者已取消；沒有啟動採樣程序。"}]}
        result_status = "cancelled"
    except Exception as exc:
        snapshot = _read(checkpoint, {})
        snapshot.setdefault("errors", []).append({"metric": "collector", "reason": str(exc) if isinstance(exc, RuntimeError) else f"採樣失敗（{type(exc).__name__}），原有記錄保留。"})
        result_status = "partial" if _has_metrics(snapshot) else "failed"
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        _close_job(child_job)
    try:
        snapshot.update({"schemaVersion": 1, "id": run_id, "status": result_status, "scenario": scenario, "startedAt": state["startedAt"], "sampledAt": snapshot.get("sampledAt", state["startedAt"]), "finishedAt": _now(), "isLive": False})
        snapshot.setdefault("collector", {}).update({"version": VERSION, "elapsedSeconds": round(time.monotonic() - started, 3), "powershellPeakWorkingSetBytes": peak, "peakScope": "本次 PowerShell 子程序峰值工作集；不含共享 WMI Provider／宿主 Console，非系統淨增量。"})
        _aggregate(snapshot)
        _atomic(root / "snapshots" / (run_id + ".json"), snapshot)
        _atomic(root / "reports" / (run_id + ".md"), render_report(snapshot), json_data=False)
        if snapshot.get("hardwareComplete"):
            _atomic(root / "設備檔案.md", render_device_profile(snapshot), json_data=False)
        if result_status in {"completed", "partial"} and snapshot.get("system", {}).get("availablePhysicalBytes") is not None:
            _atomic(root / "最新檢查.md", "\n".join(["# 最新檢查", "", f"這是 **{snapshot['sampledAt']}** 保存的歷史快照，不是即時监控。", "", f"場景：{_text(scenario)}；狀態：{result_status}。", "", f"[打開完整檢查報告](reports/{run_id}.md) · [原始 JSON](snapshots/{run_id}.json)", "", f"Windows 可見 RAM：{_gib(snapshot['system'].get('visiblePhysicalBytes'))}；可用 RAM：{_gib(snapshot['system'].get('availablePhysicalBytes'))}；系統提交：{_gib(snapshot['system'].get('committedBytes'))}。", "", "缺失指標與統計口徑請見完整報告。", ""]), json_data=False)
        rows = list_snapshots(root)
        history = ["# 歷史檢查", "", "以下均是保存的歷史快照；失敗、取消、逾時紀錄不代表有效完整採樣。", "", "| 採樣時間 | 場景 | 結果 | 資料 |", "| --- | --- | --- | --- |"]
        for row in rows:
            history.append(f"| {_text(row['sampledAt'])} | {_text(row['scenario'])} | {row['status']} | [報告]({row['report']}) · [JSON]({row['path']}) |")
        _atomic(root / "歷史檢查.md", "\n".join(history) + "\n", json_data=False)
        state.update({"status": result_status, "phase": {"completed": "採樣完成", "partial": "採樣完成，部分指標不可用", "timeout": "採樣逾時，已保存已完成階段", "cancelled": "採樣已取消，已保存已完成階段", "failed": "採樣失敗，既有記錄仍保留"}[result_status], "finishedAt": snapshot["finishedAt"], "sampledAt": snapshot["sampledAt"], "snapshot": f"snapshots/{run_id}.json", "report": f"reports/{run_id}.md", "errors": snapshot.get("errors", []), "collector": snapshot["collector"]})
        _atomic(meta / "status.json", state)
        return state
    finally:
        checkpoint.unlink(missing_ok=True)
        checkpoint.with_name(checkpoint.name + ".tmp").unlink(missing_ok=True)
        checkpoint.with_name(checkpoint.name + ".bak").unlink(missing_ok=True)
        checkpoint.with_name(checkpoint.name + ".diagnostic.json").unlink(missing_ok=True)
        if (_read(lock / "owner.json") or {}).get("id") == run_id:
            _clear_lock(lock)


def list_snapshots(root):
    root = _root(root)
    rows = []
    for path in (root / "snapshots").glob("*.json"):
        item = _read(path)
        if not isinstance(item, dict) or item.get("schemaVersion") != 1 or item.get("id") != path.stem:
            continue
        rows.append({"id": item["id"], "path": f"snapshots/{path.name}", "report": f"reports/{path.stem}.md", "sampledAt": item.get("sampledAt"), "scenario": item.get("scenario"), "status": item.get("status")})
    return sorted(rows, key=lambda row: row.get("sampledAt") or "", reverse=True)


def _load_snapshot(root, value):
    if isinstance(value, str) and value.startswith("snapshots/"):
        value = value[len("snapshots/"):]
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+(?:\.json)?", value):
        raise ValueError("只能選擇 snapshots 內的快照 ID 或 JSON 檔名。")
    path = root / "snapshots" / (value if value.endswith(".json") else value + ".json")
    if path.resolve().parent != (root / "snapshots").resolve():
        raise ValueError("快照路徑超出資料庫。")
    data = _read(path)
    if not data or data.get("schemaVersion") != 1 or data.get("id") != path.stem:
        raise ValueError("快照不存在或格式不受支援；歷史原始證據請在 evidence 內查閱。")
    return data


def compare(root, before, after):
    root = _root(root)
    a, b = _load_snapshot(root, before), _load_snapshot(root, after)
    if a["id"] == b["id"]:
        raise ValueError("請選擇兩份不同快照。")
    limitations = []
    if a.get("scenario") != b.get("scenario"):
        limitations.append("場景標籤不同，條件不相同。")
    fingerprints = lambda snap: sorted((g["category"], g["processCount"]) for g in snap.get("groups", []) if g["category"] in {"unity", "blender", "codex", "visual-studio"})
    if fingerprints(a) != fingerprints(b):
        limitations.append("主要應用進程數不同；工作狀態可能改變。")
    if a.get("collector", {}).get("version") != b.get("collector", {}).get("version"):
        limitations.append("採樣器版本不同，統計口徑可能改變。")
    if a.get("system", {}).get("installedPhysicalBytes") != b.get("system", {}).get("installedPhysicalBytes"):
        limitations.append("實装 RAM 不同，可能為硬體升級或不同電腦。")
    hardware_signature = lambda snap: {key: snap.get("hardware", {}).get(key) for key in ("manufacturer", "model", "cpus", "memoryModules", "gpus", "physicalDisks", "osVersion", "osBuild", "tools")}
    if hardware_signature(a) != hardware_signature(b):
        limitations.append("硬體、系統或已識別工具版本不同（或缺失），無法視為同條件。")
    for key in ("cpu", "disk", "gpu"):
        old_window, new_window = (a.get(key) or {}).get("windowSeconds"), (b.get(key) or {}).get("windowSeconds")
        if old_window is None or new_window is None or abs(old_window - new_window) > max(old_window, new_window) * 0.25:
            limitations.append(f"{key} 指標窗口不同或缺失；速率讀數可比性有限。")
    boot_times = []
    for snap in (a, b):
        sampled = _date(snap.get("system", {}).get("sampledAt") or snap.get("sampledAt"))
        uptime = snap.get("system", {}).get("uptimeSeconds")
        boot_times.append(sampled - dt.timedelta(seconds=uptime) if sampled and uptime is not None else None)
    if None in boot_times or abs((boot_times[1] - boot_times[0]).total_seconds()) > 60:
        limitations.append("Windows 開機會話不同或開機時間缺失；重啟後讀數下降本身不證明持久優化。")
    if any(snap.get("status") != "completed" for snap in (a, b)):
        limitations.append("至少一份快照含缺失指標或採樣未完整結束。")
    if not limitations:
        limitations.append("標籤與主要應用進程數一致；尚未驗證專案、負载、文件及暖機狀態完全一致。")
    limitations.append("兩次短窗只能比較當時讀數，不能單獨證明優化收益、長期穩定或記憶體洩漏。")
    run_id = "compare-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f") + "-" + uuid.uuid4().hex[:6]
    lines = ["# 歷史快照對比", "", f"產生於 {_now()}。差值為 **後者 − 前者**，不是自動判定的优化收益。", "", f"- 前者：{a.get('sampledAt')}／{_text(a.get('scenario'))}／[報告]({a['id']}.md)", f"- 後者：{b.get('sampledAt')}／{_text(b.get('scenario'))}／[報告]({b['id']}.md)", "", "## 條件可比性", ""] + ["- " + text for text in limitations] + ["", "## 記憶體讀數", "", "| 指標 | 前者 | 後者 | 差值 |", "| --- | ---: | ---: | ---: |"]
    for label, key in (("可用 RAM", "availablePhysicalBytes"), ("物理使用（可見減可用）", "physicalUsedBytes"), ("系統提交", "committedBytes"), ("提交上限", "commitLimitBytes"), ("系統／共享及未細分部分", "systemSharedUnattributedBytes")):
        old, new = a.get("system", {}).get(key), b.get("system", {}).get(key)
        lines.append(f"| {label} | {_gib(old)} | {_gib(new)} | {_gib(new - old if old is not None and new is not None else None)} |")
    lines += ["", "## 應用私有駐留", "", "| 類別 | 前者 | 後者 | 差值 |", "| --- | ---: | ---: | ---: |"]
    for key, label in CATEGORIES.items():
        old = next((g.get("privateResidentBytes") for g in a.get("groups", []) if g["category"] == key), None)
        new = next((g.get("privateResidentBytes") for g in b.get("groups", []) if g["category"] == key), None)
        lines.append(f"| {label} | {_gib(old)} | {_gib(new)} | {_gib(new - old if old is not None and new is not None else None)} |")
    lines += ["", "## 活動與顯存讀數", "", "| 指標 | 前者 | 後者 | 差值 |", "| --- | ---: | ---: | ---: |"]
    for label, group, key, suffix, scale in (("CPU", "cpu", "utilizationPercent", "%", 1), ("磁碟讀取", "disk", "readBytesPerSecond", " MiB/s", 1048576), ("磁碟寫入", "disk", "writeBytesPerSecond", " MiB/s", 1048576), ("GPU 最高引擎", "gpu", "maxEngineUtilizationPercent", "%", 1), ("獨立顯存已用", "gpu", "dedicatedUsedBytes", " GiB", 1073741824), ("共享顯存已用", "gpu", "sharedUsedBytes", " GiB", 1073741824)):
        old, new = (a.get(group) or {}).get(key), (b.get(group) or {}).get(key)
        old, new = (old / scale if old is not None else None), (new / scale if new is not None else None)
        change_suffix = " 百分點" if suffix == "%" else suffix
        lines.append(f"| {label} | {_metric(old, suffix)} | {_metric(new, suffix)} | {_metric(new - old if old is not None and new is not None else None, change_suffix)} |")
    lines += ["", "指標窗口與缺失原因見兩份原報告；各 GPU 引擎沒有直接相加。提交、私有駐留與共享顯存不能混作互斥 RAM 分解。", ""]
    _atomic(root / "reports" / (run_id + ".md"), "\n".join(lines), json_data=False)
    return {"status": "completed", "id": run_id, "report": f"reports/{run_id}.md", "before": a["id"], "after": b["id"], "comparability": limitations}


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Codex Console 電腦與工作環境資料庫（按需，只讀採樣）")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("collect", "status", "cancel", "list", "compare"):
        child = sub.add_parser(command)
        child.add_argument("--root", required=True)
        if command == "collect":
            child.add_argument("--scenario", default="idle")
            child.add_argument("--timeout", type=float, default=45)
            child.add_argument("--window", type=float, default=1.0)
        elif command == "compare":
            child.add_argument("--before", required=True)
            child.add_argument("--after", required=True)
    args = vars(parser.parse_args(argv))
    command = args.pop("command")
    try:
        result = {"collect": collect, "status": status, "cancel": cancel, "list": list_snapshots, "compare": compare}[command](**args)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({"status": "failed", "reason": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
