Option Explicit

Dim shell, root, scriptPath, command
Set shell = CreateObject("WScript.Shell")

If WScript.Arguments.Count = 0 Then
    WScript.Quit 1
End If

root = WScript.Arguments(0)
If Right(root, 1) = "\" Then
    root = Left(root, Len(root) - 1)
End If
scriptPath = root & "\scripts\toggle_project.ps1"
command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & scriptPath & """ -Root """ & root & """"
shell.Run command, 0, False
