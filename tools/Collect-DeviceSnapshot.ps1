param(
    [Parameter(Mandatory=$true)][string]$OutputPath,
    [Parameter(Mandatory=$true)][string]$CancelPath,
    [ValidateRange(0.2,5.0)][double]$WindowSeconds = 1.0
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
trap {
    # Persist only exception type, fixed-source line number and error code; never
    # serialize InvocationInfo (which can contain the invocation/command line).
    $diagnostic = [ordered]@{type=$_.Exception.GetType().Name; line=$_.InvocationInfo.ScriptLineNumber; code=$_.FullyQualifiedErrorId}
    try { [IO.File]::WriteAllText(($OutputPath + '.diagnostic.json'), ($diagnostic | ConvertTo-Json), [Text.UTF8Encoding]::new($false)) } catch { }
    exit 1
}
$state = [ordered]@{
    sampledAt = [DateTimeOffset]::Now.ToString('o')
    phase = '初始化'
    errors = [System.Collections.Generic.List[object]]::new()
    system = [ordered]@{ installedPhysicalBytes=$null; visiblePhysicalBytes=$null; availablePhysicalBytes=$null; committedBytes=$null; commitLimitBytes=$null; uptimeSeconds=$null }
    hardware = [ordered]@{}
    processes = @()
    processInventoryComplete = $false
    hardwareComplete = $false
    cpu = [ordered]@{ utilizationPercent=$null; windowSeconds=$null; requestedWindowSeconds=$WindowSeconds }
    disk = [ordered]@{ readBytesPerSecond=$null; writeBytesPerSecond=$null; windowSeconds=$null; requestedWindowSeconds=$WindowSeconds }
    gpu = [ordered]@{ dedicatedUsedBytes=$null; sharedUsedBytes=$null; maxEngineUtilizationPercent=$null; windowSeconds=$null; requestedWindowSeconds=$WindowSeconds; adapters=@() }
    complete = $false
}
function Missing([string]$Metric, [string]$Reason) {
    $state.errors.Add([ordered]@{metric=$Metric; reason=$Reason})
}
function Save([string]$Phase) {
    $state.phase = $Phase
    $state.updatedAt = [DateTimeOffset]::Now.ToString('o')
    $temp = $OutputPath + '.tmp'
    $json = $state | ConvertTo-Json -Depth 12
    [IO.File]::WriteAllText($temp, $json, [Text.UTF8Encoding]::new($false))
    # Replace is atomic for an existing target on the same volume.
    if ([IO.File]::Exists($OutputPath)) {
        $backup = $OutputPath + '.bak'
        [IO.File]::Replace($temp,$OutputPath,$backup)
        [IO.File]::Delete($backup)
    }
    else { [IO.File]::Move($temp,$OutputPath) }
    if ([IO.File]::Exists($CancelPath)) { exit 2 }
}
function Read-Cim([string]$Class, [string[]]$Properties) {
    Get-CimInstance -ClassName $Class -Property $Properties -OperationTimeoutSec 8
}
function Iso($Value) {
    if ($null -eq $Value) { return $null }
    return ([DateTimeOffset]$Value).ToString('o')
}
function Number($Value) {
    if ($null -eq $Value) { return $null }
    return [long]$Value
}
function Sum-CapacityBytes([object[]]$Modules) {
    if ($Modules.Count -eq 0) { return $null }
    [long]$total = 0
    foreach ($module in $Modules) {
        if ($null -eq $module.capacityBytes -or $module.capacityBytes -le 0) { return $null }
        $total += [long]$module.capacityBytes
    }
    return $total
}
Save '讀取系統記憶體'
try {
    $os = Read-Cim 'Win32_OperatingSystem' @('Caption','Version','BuildNumber','TotalVisibleMemorySize','FreePhysicalMemory','LastBootUpTime')
    $state.system.visiblePhysicalBytes = [long]$os.TotalVisibleMemorySize * 1024
    $state.system.availablePhysicalBytes = [long]$os.FreePhysicalMemory * 1024
    $state.system.uptimeSeconds = [math]::Round(((Get-Date) - $os.LastBootUpTime).TotalSeconds, 3)
    $state.hardware.osCaption = $os.Caption
    $state.hardware.osVersion = $os.Version
    $state.hardware.osBuild = $os.BuildNumber
} catch { Missing 'system.physicalMemory' ('Windows CIM 無法讀取：' + $_.Exception.GetType().Name) }
try {
    $mem = Read-Cim 'Win32_PerfFormattedData_PerfOS_Memory' @('AvailableBytes','CommittedBytes','CommitLimit')
    $state.system.availablePhysicalBytes = Number $mem.AvailableBytes
    $state.system.committedBytes = Number $mem.CommittedBytes
    $state.system.commitLimitBytes = Number $mem.CommitLimit
} catch { Missing 'system.commit' ('Windows 記憶體效能計數器不可用：' + $_.Exception.GetType().Name) }
$state.system.sampledAt = [DateTimeOffset]::Now.ToString('o')
Save '讀取 CPU／磁碟／GPU 短窗'
$cpuBefore=$null; $diskBefore=$null; $gpuBefore=$null
try { $cpuBefore = Read-Cim 'Win32_PerfRawData_PerfOS_Processor' @('Name','PercentProcessorTime','Timestamp_Sys100NS') | Where-Object Name -eq '_Total' } catch { Missing 'cpu' ('CPU 原始計數器不可用：' + $_.Exception.GetType().Name) }
try { $diskBefore = Read-Cim 'Win32_PerfRawData_PerfDisk_PhysicalDisk' @('Name','DiskReadBytesPersec','DiskWriteBytesPersec','Timestamp_PerfTime','Frequency_PerfTime') | Where-Object Name -eq '_Total' } catch { Missing 'disk' ('磁碟原始計數器不可用：' + $_.Exception.GetType().Name) }
try { $gpuBefore = @(Read-Cim 'Win32_PerfRawData_GPUPerformanceCounters_GPUEngine' @('Name','RunningTime','Timestamp_Sys100NS')) } catch { Missing 'gpu.activity' ('GPU 引擎計數器不受驅動支援或無權限：' + $_.Exception.GetType().Name) }
$windowStart = [DateTimeOffset]::Now
Start-Sleep -Milliseconds ([int]($WindowSeconds * 1000))
if ($cpuBefore) {
    try {
        $cpuAfter = Read-Cim 'Win32_PerfRawData_PerfOS_Processor' @('Name','PercentProcessorTime','Timestamp_Sys100NS') | Where-Object Name -eq '_Total'
        $ticks = [double]$cpuAfter.Timestamp_Sys100NS - [double]$cpuBefore.Timestamp_Sys100NS
        if ($ticks -gt 0) {
            $state.cpu.utilizationPercent = [math]::Round([math]::Max(0,[math]::Min(100, 100 * (1 - ([double]$cpuAfter.PercentProcessorTime - [double]$cpuBefore.PercentProcessorTime) / $ticks))), 3)
            $state.cpu.windowSeconds = $ticks / 1e7
        } else { Missing 'cpu' 'CPU 計數器窗口無效' }
    } catch { Missing 'cpu' ('CPU 第二次計數器讀取失敗：' + $_.Exception.GetType().Name) }
}
if ($diskBefore) {
    try {
        $diskAfter = Read-Cim 'Win32_PerfRawData_PerfDisk_PhysicalDisk' @('Name','DiskReadBytesPersec','DiskWriteBytesPersec','Timestamp_PerfTime','Frequency_PerfTime') | Where-Object Name -eq '_Total'
        $seconds = ([double]$diskAfter.Timestamp_PerfTime - [double]$diskBefore.Timestamp_PerfTime) / [double]$diskAfter.Frequency_PerfTime
        if ($seconds -gt 0) {
            $state.disk.readBytesPerSecond = [math]::Max(0,([double]$diskAfter.DiskReadBytesPersec - [double]$diskBefore.DiskReadBytesPersec) / $seconds)
            $state.disk.writeBytesPerSecond = [math]::Max(0,([double]$diskAfter.DiskWriteBytesPersec - [double]$diskBefore.DiskWriteBytesPersec) / $seconds)
            $state.disk.windowSeconds = $seconds
        } else { Missing 'disk' '磁碟計數器窗口無效' }
    } catch { Missing 'disk' ('磁碟第二次計數器讀取失敗：' + $_.Exception.GetType().Name) }
}
if ($gpuBefore.Count -gt 0) {
    try {
        $previous = @{}
        foreach ($engine in $gpuBefore) { $previous[$engine.Name] = $engine }
        $gpuAfter = @(Read-Cim 'Win32_PerfRawData_GPUPerformanceCounters_GPUEngine' @('Name','RunningTime','Timestamp_Sys100NS'))
        $busy = [System.Collections.Generic.List[double]]::new()
        $windows = [System.Collections.Generic.List[double]]::new()
        foreach ($engine in $gpuAfter) {
            $old = $previous[$engine.Name]
            if ($old) {
                $ticks = [double]$engine.Timestamp_Sys100NS - [double]$old.Timestamp_Sys100NS
                if ($ticks -gt 0) {
                    $busy.Add([math]::Max(0,[math]::Min(100,100 * ([double]$engine.RunningTime - [double]$old.RunningTime) / $ticks)))
                    $windows.Add($ticks / 1e7)
                }
            }
        }
        if ($busy.Count -gt 0) {
            $state.gpu.maxEngineUtilizationPercent = ($busy | Measure-Object -Maximum).Maximum
            $state.gpu.windowSeconds = ($windows | Measure-Object -Maximum).Maximum
            $state.gpu.activityMethod = '短窗內各進程 GPU 引擎實例最高值；非整卡利用率，各引擎不相加。'
        } else { Missing 'gpu.activity' '未取得可比較的 GPU 引擎實例' }
    } catch { Missing 'gpu.activity' ('GPU 第二次讀取失敗：' + $_.Exception.GetType().Name) }
} elseif ($null -ne $gpuBefore) { Missing 'gpu.activity' 'GPU 計數器沒有可用實例' }
try {
    $adapters = @(Read-Cim 'Win32_PerfFormattedData_GPUPerformanceCounters_GPUAdapterMemory' @('Name','DedicatedUsage','SharedUsage'))
    if ($adapters.Count -gt 0) {
        $state.gpu.adapters = @($adapters | ForEach-Object { [ordered]@{counterInstance=$_.Name; dedicatedUsedBytes=(Number $_.DedicatedUsage); sharedUsedBytes=(Number $_.SharedUsage)} })
        $state.gpu.dedicatedUsedBytes = [long](($adapters | Measure-Object DedicatedUsage -Sum).Sum)
        $state.gpu.sharedUsedBytes = [long](($adapters | Measure-Object SharedUsage -Sum).Sum)
    } else { Missing 'gpu.memory' 'GPU adapter memory 計數器沒有可用實例' }
} catch { Missing 'gpu.memory' ('GPU 記憶體計數器不受驅動支援或無權限：' + $_.Exception.GetType().Name) }
$state.cpu.sampledAt = [DateTimeOffset]::Now.ToString('o')
$state.disk.sampledAt = $state.cpu.sampledAt
$state.gpu.sampledAt = $state.cpu.sampledAt
Save '讀取進程與核對身分'
try {
    $inventory = @(Read-Cim 'Win32_Process' @('ProcessId','ParentProcessId','CreationDate','Name','ExecutablePath'))
    $perfById = @{}
    try {
        $perf = @(Read-Cim 'Win32_PerfFormattedData_PerfProc_Process' @('IDProcess','WorkingSetPrivate','WorkingSet','PrivateBytes'))
        foreach ($entry in $perf) { if ($entry.IDProcess -gt 0) { $perfById[[int]$entry.IDProcess] = $entry } }
    } catch { Missing 'processes.memory' ('進程記憶體計數器不可用：' + $_.Exception.GetType().Name) }
    $confirmed = @{}
    foreach ($entry in @(Read-Cim 'Win32_Process' @('ProcessId','CreationDate'))) { $confirmed[[int]$entry.ProcessId] = (Iso $entry.CreationDate) }
    $tools = [System.Collections.Generic.List[object]]::new()
    $processes = [System.Collections.Generic.List[object]]::new()
    foreach ($entry in $inventory) {
        if ($entry.ProcessId -eq 0) { continue }
        $processId = [int]$entry.ProcessId
        $birth = Iso $entry.CreationDate
        $valid = $birth -and $confirmed.ContainsKey($processId) -and ($confirmed[$processId] -eq $birth)
        $sample = if ($valid) { $perfById[$processId] } else { $null }
        $category = $null; $identityReason = $null; $version = $null
        $executable = $entry.ExecutablePath
        # Full paths are transient only. They are never persisted.
        if ($valid -and $executable) {
            $name = [IO.Path]::GetFileName($executable).ToLowerInvariant()
            $candidate = switch ($name) { 'unity.exe' {'unity'} 'blender.exe' {'blender'} 'codex.exe' {'codex'} 'chatgpt.exe' {'codex'} 'devenv.exe' {'visual-studio'} default {$null} }
            if ($candidate) {
                try {
                    $info = [Diagnostics.FileVersionInfo]::GetVersionInfo($executable)
                    $product = $info.ProductName
                    $verified = switch ($candidate) { 'unity' {$product -match '^Unity'} 'blender' {$product -match 'Blender' -or $executable -match '\\Blender Foundation\\Blender[^\\]*\\blender\.exe$'} 'codex' {$product -match 'Codex|ChatGPT' -or $executable -match '\\OpenAI\.(Codex|ChatGPT)[^\\]*\\'} 'visual-studio' {$product -match 'Visual Studio'} }
                    if ($verified) { $category=$candidate; $identityReason='可執行檔名稱與產品資訊／已知安裝路徑一致'; $version=$info.ProductVersion }
                } catch { }
            }
            if (-not $category -and $executable.StartsWith(($env:SystemRoot + '\'), [StringComparison]::OrdinalIgnoreCase)) {
                $category='system'; $identityReason='可執行檔位於 Windows 系統目錄（含系統子程序）'
            }
        }
        if ($category -and $category -ne 'system' -and -not ($tools | Where-Object { $_.name -eq $entry.Name -and $_.version -eq $version })) {
            $versionSource = if ($category -eq 'codex') { '執行檔產品版本，可能為瀏覽器執行時；非已確認的 Codex 發行版本' } else { '本次運行進程的產品版本' }
            $tools.Add([ordered]@{name=$entry.Name; category=$category; version=$version; source=$versionSource})
        }
        $processes.Add([ordered]@{
            name=$entry.Name; pid=$processId; parentPid=[int]$entry.ParentProcessId; startedAt=$birth
            identityCategory=$category; identityReason=$identityReason
            privateResidentBytes=$(if ($sample) {Number $sample.WorkingSetPrivate} else {$null})
            workingSetBytes=$(if ($sample) {Number $sample.WorkingSet} else {$null})
            privateCommitBytes=$(if ($sample) {Number $sample.PrivateBytes} else {$null})
            metricReason=$(if (-not $valid) {'兩次進程清單間已退出、啟動時間無權讀取或 PID 重用；不配對記憶體計數器'} elseif (-not $sample) {'進程效能計數器缺失'} else {$null})
        })
    }
    $state.processes = @($processes.ToArray())
    $state.hardware.tools = @($tools.ToArray())
    $state.processInventoryComplete = $true
    $missing = @($state.processes | Where-Object {$null -eq $_.privateResidentBytes}).Count
    if ($missing -gt 0) { Missing 'processes.memory' ("有 $missing 個進程記憶體不可讀或身分變動；個別原因見 processes.metricReason。") }
} catch { Missing 'processes' ('進程清單讀取失敗：' + $_.Exception.GetType().Name) }
$state.processesSampledAt = [DateTimeOffset]::Now.ToString('o')
Save '讀取電腦配置'
try {
    $computer = Read-Cim 'Win32_ComputerSystem' @('Manufacturer','Model','TotalPhysicalMemory')
    $state.hardware.manufacturer = $computer.Manufacturer
    $state.hardware.model = $computer.Model
    $state.hardware.cpus = @(Read-Cim 'Win32_Processor' @('Name','NumberOfCores','NumberOfLogicalProcessors') | ForEach-Object { [ordered]@{name=$_.Name; cores=$_.NumberOfCores; logicalProcessors=$_.NumberOfLogicalProcessors} })
    $state.hardware.memoryModules = @(Read-Cim 'Win32_PhysicalMemory' @('Capacity','Speed','ConfiguredClockSpeed') | ForEach-Object { [ordered]@{capacityBytes=(Number $_.Capacity); speedMHz=$_.Speed; configuredSpeedMHz=$_.ConfiguredClockSpeed} })
    $state.system.installedPhysicalBytes = Sum-CapacityBytes $state.hardware.memoryModules
    if ($null -eq $state.system.installedPhysicalBytes) { Missing 'system.installedPhysicalBytes' '未取得全部 RAM 模組容量；不將 Windows 可見容量當成實裝容量' }
    $state.hardware.gpus = @(Read-Cim 'Win32_VideoController' @('Name','DriverVersion') | ForEach-Object { [ordered]@{name=$_.Name; driverVersion=$_.DriverVersion; dedicatedCapacityBytes=$null; capacityReason='未讀取可靠的驅動容量接口；WMI AdapterRAM 可能截斷，不作容量依據'} })
    $state.hardware.physicalDisks = @(Read-Cim 'Win32_DiskDrive' @('Model','Size','InterfaceType','Status') | ForEach-Object { [ordered]@{model=$_.Model; sizeBytes=(Number $_.Size); interface=$_.InterfaceType; status=$_.Status} })
    $state.hardware.volumes = @(Read-Cim 'Win32_LogicalDisk' @('DeviceID','Size','FreeSpace','FileSystem','DriveType') | Where-Object DriveType -eq 3 | ForEach-Object { [ordered]@{letter=$_.DeviceID; sizeBytes=(Number $_.Size); freeBytes=(Number $_.FreeSpace); fileSystem=$_.FileSystem} })
    $state.hardwareComplete = $true
} catch { Missing 'hardware' ('設備檔案部分不可用：' + $_.Exception.GetType().Name + '；固定採樣器第 ' + $_.InvocationInfo.ScriptLineNumber + ' 行') }
Save '查詢現有 NVIDIA 驅動容量接口'
$driver = $null
try {
    # Only trusted installation locations; never execute a program from the library.
    $driverCandidates = @((Join-Path $env:SystemRoot 'System32\nvidia-smi.exe'), (Join-Path $env:ProgramFiles 'NVIDIA Corporation\NVSMI\nvidia-smi.exe'))
    $driverPath = $driverCandidates | Where-Object { [IO.File]::Exists($_) } | Select-Object -First 1
    if ($driverPath) {
        $startInfo = [Diagnostics.ProcessStartInfo]::new()
        $startInfo.FileName = $driverPath
        $startInfo.Arguments = '--query-gpu=name,memory.total,driver_version --format=csv,noheader,nounits'
        $startInfo.UseShellExecute = $false
        $startInfo.CreateNoWindow = $true
        $startInfo.RedirectStandardOutput = $true
        $startInfo.RedirectStandardError = $true
        $driver = [Diagnostics.Process]::new()
        $driver.StartInfo = $startInfo
        [void]$driver.Start()
        $stdout = $driver.StandardOutput.ReadToEndAsync()
        $stderr = $driver.StandardError.ReadToEndAsync()
        if (-not $driver.WaitForExit(2000)) {
            $driver.Kill()
            [void]$driver.WaitForExit(1000)
            Missing 'hardware.gpuCapacity' 'nvidia-smi 驅動只讀查詢超過 2 秒，已結束本次查詢子程序'
        } elseif ($driver.ExitCode -eq 0) {
            foreach ($line in ($stdout.Result -split '\r?\n')) {
                if (-not $line.Trim()) { continue }
                $columns = $line -split ','
                $capacityMiB = 0L
                if ($columns.Count -ge 3 -and [long]::TryParse($columns[1].Trim(), [ref]$capacityMiB)) {
                    foreach ($adapter in $state.hardware.gpus) {
                        if ($adapter.name -eq $columns[0].Trim()) {
                            $adapter.dedicatedCapacityBytes = $capacityMiB * 1048576L
                            $adapter.capacityReason = '本次已安裝 NVIDIA 驅動 nvidia-smi 只讀查詢（MiB 轉 bytes）'
                        }
                    }
                }
            }
        } else { Missing 'hardware.gpuCapacity' 'nvidia-smi 驅動容量查詢失敗；容量保持未知' }
    }
} catch { Missing 'hardware.gpuCapacity' ('NVIDIA 驅動查詢不可用：' + $_.Exception.GetType().Name) }
finally {
    if ($driver) {
        try { if (-not $driver.HasExited) { $driver.Kill(); [void]$driver.WaitForExit(1000) } } catch { }
        $driver.Dispose()
    }
}
$requiredTools = [ordered]@{'unity'='Unity'; 'blender'='Blender'; 'codex'='Codex'; 'visual-studio'='Visual Studio'}
$knownTools = @($state.hardware.tools | Where-Object {$null -ne $_})
foreach ($requiredCategory in $requiredTools.Keys) {
    if (-not ($knownTools | Where-Object {$_.category -eq $requiredCategory -and $_.version})) {
        $knownTools += [ordered]@{name=$requiredTools[$requiredCategory]; category=$requiredCategory; version=$null; source='未運行或無讀取權限，本次未確認安裝版本'}
    }
}
$state.hardware.tools = $knownTools
$state.hardware.sampledAt = [DateTimeOffset]::Now.ToString('o')
$state.complete = $true
Save '指標讀取完成'
