param(
    [ValidateSet("save", "restore", "list")]
    [string]$Action = "list",
    [string]$Path = ""
)

$ErrorActionPreference = "Stop"

$desktopApiSource = @'
using System;
using System.Text;
using System.Collections.Generic;
using System.Runtime.InteropServices;

public class DesktopIconInfo {
    public int Index { get; set; }
    public string Name { get; set; }
    public int X { get; set; }
    public int Y { get; set; }
}

public static class DesktopIconApi {
    const int LVM_FIRST = 0x1000;
    const int LVM_GETITEMCOUNT = LVM_FIRST + 4;
    const int LVM_GETITEMTEXTW = LVM_FIRST + 115;
    const int LVM_GETITEMPOSITION = LVM_FIRST + 16;
    const int LVM_SETITEMPOSITION = LVM_FIRST + 15;
    const int GWL_STYLE = -16;
    const int LVS_AUTOARRANGE = 0x0100;
    const uint LVIF_TEXT = 0x0001;
    const int PROCESS_VM_OPERATION = 0x0008;
    const int PROCESS_VM_READ = 0x0010;
    const int PROCESS_VM_WRITE = 0x0020;
    const uint MEM_COMMIT = 0x1000;
    const uint MEM_RESERVE = 0x2000;
    const uint MEM_RELEASE = 0x8000;
    const uint PAGE_READWRITE = 0x04;

    [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)]
    struct LVITEMW {
        public uint mask;
        public int iItem;
        public int iSubItem;
        public uint state;
        public uint stateMask;
        public IntPtr pszText;
        public int cchTextMax;
        public int iImage;
        public IntPtr lParam;
        public int iIndent;
        public int iGroupId;
        public uint cColumns;
        public IntPtr puColumns;
        public IntPtr piColFmt;
        public int iGroup;
    }

    [DllImport("user32.dll", SetLastError=true)] static extern IntPtr FindWindow(string lpClassName, string lpWindowName);
    [DllImport("user32.dll", SetLastError=true)] static extern IntPtr FindWindowEx(IntPtr hwndParent, IntPtr hwndChildAfter, string lpszClass, string lpszWindow);
    delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern IntPtr SendMessage(IntPtr hWnd, int Msg, IntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll", EntryPoint="GetWindowLongPtrW", SetLastError=true)] static extern IntPtr GetWindowLongPtr64(IntPtr hWnd, int nIndex);
    [DllImport("user32.dll", EntryPoint="SetWindowLongPtrW", SetLastError=true)] static extern IntPtr SetWindowLongPtr64(IntPtr hWnd, int nIndex, IntPtr dwNewLong);
    [DllImport("user32.dll", EntryPoint="GetWindowLongW", SetLastError=true)] static extern int GetWindowLong32(IntPtr hWnd, int nIndex);
    [DllImport("user32.dll", EntryPoint="SetWindowLongW", SetLastError=true)] static extern int SetWindowLong32(IntPtr hWnd, int nIndex, int dwNewLong);
    [DllImport("user32.dll")] static extern bool InvalidateRect(IntPtr hWnd, IntPtr lpRect, bool bErase);
    [DllImport("user32.dll")] static extern bool UpdateWindow(IntPtr hWnd);
    [DllImport("kernel32.dll", SetLastError=true)] static extern IntPtr OpenProcess(int dwDesiredAccess, bool bInheritHandle, uint dwProcessId);
    [DllImport("kernel32.dll", SetLastError=true)] static extern bool CloseHandle(IntPtr hObject);
    [DllImport("kernel32.dll", SetLastError=true)] static extern IntPtr VirtualAllocEx(IntPtr hProcess, IntPtr lpAddress, UIntPtr dwSize, uint flAllocationType, uint flProtect);
    [DllImport("kernel32.dll", SetLastError=true)] static extern bool VirtualFreeEx(IntPtr hProcess, IntPtr lpAddress, UIntPtr dwSize, uint dwFreeType);
    [DllImport("kernel32.dll", SetLastError=true)] static extern bool WriteProcessMemory(IntPtr hProcess, IntPtr lpBaseAddress, byte[] lpBuffer, int nSize, out IntPtr lpNumberOfBytesWritten);
    [DllImport("kernel32.dll", SetLastError=true)] static extern bool ReadProcessMemory(IntPtr hProcess, IntPtr lpBaseAddress, byte[] lpBuffer, int nSize, out IntPtr lpNumberOfBytesRead);

    public static IntPtr GetListView() {
        IntPtr progman = FindWindow("Progman", null);
        IntPtr defView = FindWindowEx(progman, IntPtr.Zero, "SHELLDLL_DefView", null);
        if (defView != IntPtr.Zero) {
            IntPtr list = FindWindowEx(defView, IntPtr.Zero, "SysListView32", "FolderView");
            if (list != IntPtr.Zero) return list;
        }
        IntPtr result = IntPtr.Zero;
        EnumWindows(delegate(IntPtr hwnd, IntPtr lparam) {
            IntPtr shell = FindWindowEx(hwnd, IntPtr.Zero, "SHELLDLL_DefView", null);
            if (shell != IntPtr.Zero) {
                IntPtr list = FindWindowEx(shell, IntPtr.Zero, "SysListView32", "FolderView");
                if (list != IntPtr.Zero) { result = list; return false; }
            }
            return true;
        }, IntPtr.Zero);
        return result;
    }

    static byte[] StructureToBytes(object obj) {
        int size = Marshal.SizeOf(obj);
        byte[] data = new byte[size];
        IntPtr ptr = Marshal.AllocHGlobal(size);
        try {
            Marshal.StructureToPtr(obj, ptr, false);
            Marshal.Copy(ptr, data, 0, size);
            return data;
        } finally {
            Marshal.FreeHGlobal(ptr);
        }
    }

    public static List<DesktopIconInfo> GetIcons() {
        IntPtr list = GetListView();
        if (list == IntPtr.Zero) throw new Exception("Desktop SysListView32 not found");
        uint pid;
        GetWindowThreadProcessId(list, out pid);
        IntPtr proc = OpenProcess(PROCESS_VM_OPERATION | PROCESS_VM_READ | PROCESS_VM_WRITE, false, pid);
        if (proc == IntPtr.Zero) throw new Exception("OpenProcess failed");
        List<DesktopIconInfo> icons = new List<DesktopIconInfo>();
        IntPtr remoteText = IntPtr.Zero, remoteItem = IntPtr.Zero, remotePoint = IntPtr.Zero;
        try {
            int count = SendMessage(list, LVM_GETITEMCOUNT, IntPtr.Zero, IntPtr.Zero).ToInt32();
            int textBytes = 1024;
            int itemBytes = Marshal.SizeOf(typeof(LVITEMW));
            remoteText = VirtualAllocEx(proc, IntPtr.Zero, (UIntPtr)textBytes, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
            remoteItem = VirtualAllocEx(proc, IntPtr.Zero, (UIntPtr)itemBytes, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
            remotePoint = VirtualAllocEx(proc, IntPtr.Zero, (UIntPtr)8, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
            for (int i = 0; i < count; i++) {
                LVITEMW item = new LVITEMW();
                item.mask = LVIF_TEXT;
                item.iItem = i;
                item.iSubItem = 0;
                item.pszText = remoteText;
                item.cchTextMax = textBytes / 2;
                byte[] itemData = StructureToBytes(item);
                IntPtr written;
                WriteProcessMemory(proc, remoteItem, itemData, itemData.Length, out written);
                SendMessage(list, LVM_GETITEMTEXTW, (IntPtr)i, remoteItem);
                byte[] textData = new byte[textBytes];
                IntPtr read;
                ReadProcessMemory(proc, remoteText, textData, textData.Length, out read);
                string name = Encoding.Unicode.GetString(textData).Split('\0')[0];
                WriteProcessMemory(proc, remotePoint, new byte[8], 8, out written);
                SendMessage(list, LVM_GETITEMPOSITION, (IntPtr)i, remotePoint);
                byte[] pointData = new byte[8];
                ReadProcessMemory(proc, remotePoint, pointData, 8, out read);
                icons.Add(new DesktopIconInfo {
                    Index = i,
                    Name = name,
                    X = BitConverter.ToInt32(pointData, 0),
                    Y = BitConverter.ToInt32(pointData, 4)
                });
            }
            return icons;
        } finally {
            if (remoteText != IntPtr.Zero) VirtualFreeEx(proc, remoteText, UIntPtr.Zero, MEM_RELEASE);
            if (remoteItem != IntPtr.Zero) VirtualFreeEx(proc, remoteItem, UIntPtr.Zero, MEM_RELEASE);
            if (remotePoint != IntPtr.Zero) VirtualFreeEx(proc, remotePoint, UIntPtr.Zero, MEM_RELEASE);
            CloseHandle(proc);
        }
    }

    public static void SetIconPosition(int index, int x, int y) {
        IntPtr list = GetListView();
        if (list == IntPtr.Zero) throw new Exception("Desktop SysListView32 not found");
        int lparam = (y << 16) | (x & 0xFFFF);
        SendMessage(list, LVM_SETITEMPOSITION, (IntPtr)index, (IntPtr)lparam);
    }

    static long GetWindowStyle(IntPtr hwnd) {
        if (IntPtr.Size == 8) return GetWindowLongPtr64(hwnd, GWL_STYLE).ToInt64();
        return GetWindowLong32(hwnd, GWL_STYLE);
    }

    public static void DisableAutoArrange() {
        IntPtr list = GetListView();
        if (list == IntPtr.Zero) throw new Exception("Desktop SysListView32 not found");
        long style = GetWindowStyle(list);
        long next = style & ~((long)LVS_AUTOARRANGE);
        if (next == style) return;
        if (IntPtr.Size == 8) SetWindowLongPtr64(list, GWL_STYLE, new IntPtr(next));
        else SetWindowLong32(list, GWL_STYLE, (int)next);
        InvalidateRect(list, IntPtr.Zero, true);
        UpdateWindow(list);
    }
}
'@

function Initialize-DesktopApi {
    if (-not ([System.Management.Automation.PSTypeName]"DesktopIconApi").Type) {
        Add-Type -TypeDefinition $desktopApiSource -Language CSharp
    }
}

function Get-DesktopIconSize {
    $bagPath = "HKCU:\Software\Microsoft\Windows\Shell\Bags\1\Desktop"
    if (Test-Path $bagPath) {
        return (Get-ItemProperty -Path $bagPath -ErrorAction SilentlyContinue).IconSize
    }
    return $null
}

function Get-ScreenInfo {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.Screen]::AllScreens | ForEach-Object {
        [pscustomobject]@{
            Device = $_.DeviceName
            Primary = $_.Primary
            Bounds = @{
                X = $_.Bounds.X
                Y = $_.Bounds.Y
                Width = $_.Bounds.Width
                Height = $_.Bounds.Height
            }
            WorkingArea = @{
                X = $_.WorkingArea.X
                Y = $_.WorkingArea.Y
                Width = $_.WorkingArea.Width
                Height = $_.WorkingArea.Height
            }
        }
    }
}

function Get-DesktopIcons {
    Initialize-DesktopApi
    [DesktopIconApi]::GetIcons() | Sort-Object X, Y
}

function Save-DesktopLayout {
    param([string]$TargetPath)
    if (-not $TargetPath) { throw "Use -Path with save." }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $TargetPath) | Out-Null
    $layout = [pscustomobject]@{
        SavedAt = (Get-Date).ToString("o")
        ComputerName = $env:COMPUTERNAME
        UserName = $env:USERNAME
        IconSize = Get-DesktopIconSize
        Screens = @(Get-ScreenInfo)
        Icons = @(Get-DesktopIcons | ForEach-Object {
            [pscustomobject]@{ Name = $_.Name; X = $_.X; Y = $_.Y }
        })
    }
    $layout | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $TargetPath -Encoding UTF8
    Write-Output $TargetPath
}

function Get-StagingPositions {
    param([int]$Count)
    $positions = New-Object System.Collections.Generic.List[object]
    $columns = 12
    $rows = [Math]::Max(1, [Math]::Ceiling($Count / [double]$columns))
    for ($row = 0; $row -lt $rows; $row++) {
        for ($column = 0; $column -lt $columns; $column++) {
            if ($positions.Count -ge $Count) { break }
            $positions.Add([pscustomobject]@{
                X = 12 + ($column * 90)
                Y = 8 + ($row * 92)
            }) | Out-Null
        }
    }
    return $positions
}

function Restore-DesktopLayout {
    param([string]$SourcePath)
    if (-not $SourcePath -or -not (Test-Path -LiteralPath $SourcePath)) {
        throw "Layout file not found: $SourcePath"
    }
    $layout = Get-Content -LiteralPath $SourcePath -Raw | ConvertFrom-Json
    $items = @($layout.Icons)
    if (-not $items.Count) { throw "Layout does not contain any icons." }

    Initialize-DesktopApi
    [DesktopIconApi]::DisableAutoArrange()
    $icons = @([DesktopIconApi]::GetIcons())
    $byName = @{}
    foreach ($icon in $icons) {
        if ($icon.Name -and -not $byName.ContainsKey($icon.Name)) {
            $byName[$icon.Name] = $icon
        }
    }

    $available = @($items | Where-Object { $byName.ContainsKey($_.Name) })
    $staging = @(Get-StagingPositions -Count $available.Count)
    for ($i = 0; $i -lt $available.Count; $i++) {
        $icon = $byName[$available[$i].Name]
        [DesktopIconApi]::SetIconPosition($icon.Index, [int]$staging[$i].X, [int]$staging[$i].Y)
    }
    Start-Sleep -Milliseconds 250

    $moved = 0
    foreach ($item in $available) {
        $icon = $byName[$item.Name]
        [DesktopIconApi]::SetIconPosition($icon.Index, [int]$item.X, [int]$item.Y)
        $moved++
    }
    Start-Sleep -Milliseconds 500
    Write-Output "Restored $moved icons from $SourcePath"
}

switch ($Action) {
    "list" {
        Get-DesktopIcons | Select-Object Index, Name, X, Y | Format-Table -AutoSize
    }
    "save" {
        Save-DesktopLayout -TargetPath $Path
    }
    "restore" {
        Restore-DesktopLayout -SourcePath $Path
    }
}
