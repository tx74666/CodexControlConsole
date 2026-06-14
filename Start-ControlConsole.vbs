Option Explicit

Dim shell, fso, appDir, pythonw, command, localAppData
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

appDir = fso.GetParentFolderName(WScript.ScriptFullName)
localAppData = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%")

pythonw = FindPythonw(localAppData)
If pythonw = "" Then
  MsgBox "Python was not found. Install Python 3.11 or newer, then run Start-ControlConsole again.", vbExclamation, "Codex Console"
  WScript.Quit 1
End If

shell.CurrentDirectory = appDir
command = """" & pythonw & """ """ & appDir & "\world_console.py"""
On Error Resume Next
shell.Run command, 0, False
If Err.Number <> 0 Then
  MsgBox "Codex Console could not start. Check that Python and the app files are still in this folder.", vbExclamation, "Codex Console"
End If

Function FindPythonw(localAppData)
  Dim paths, i
  paths = Array( _
    "C:\Program Files\Python313\pythonw.exe", _
    "C:\Program Files\Python312\pythonw.exe", _
    "C:\Program Files\Python311\pythonw.exe", _
    localAppData & "\Programs\Python\Python313\pythonw.exe", _
    localAppData & "\Programs\Python\Python312\pythonw.exe", _
    localAppData & "\Programs\Python\Python311\pythonw.exe", _
    "C:\Windows\pyw.exe" _
  )

  For i = 0 To UBound(paths)
    If fso.FileExists(paths(i)) Then
      FindPythonw = paths(i)
      Exit Function
    End If
  Next

  FindPythonw = ""
End Function
