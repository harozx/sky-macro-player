' Macro Player Launcher
' - Check for Python & pynput
' - If missing: run setup.bat to install
' - If ready: launch gui.py silently (no CMD window)

Dim objFSO, objShell, strDir
Set objFSO   = CreateObject("Scripting.FileSystemObject")
Set objShell = CreateObject("Shell.Application")
strDir = objFSO.GetParentFolderName(WScript.ScriptFullName)

' === CHECK PYTHON & PYNPUT ===
Dim objExec, bNeedSetup
bNeedSetup = False

On Error Resume Next
Set objExec = CreateObject("WScript.Shell").Exec("python -c ""import pynput""")
objExec.StdOut.ReadAll()
If objExec.ExitCode <> 0 Then bNeedSetup = True
On Error GoTo 0

' === NEED SETUP? ===
If bNeedSetup Then
    Dim answer
    answer = MsgBox("Python or pynput not found." & Chr(13) & Chr(13) & _
                    "Press YES to auto-install and run." & Chr(13) & _
                    "Press NO to exit.", _
                    vbYesNo + vbQuestion, "Macro Player - Setup Required")
    If answer = vbYes Then
        ' Run setup.bat with admin rights (needed for Python install)
        objShell.ShellExecute "cmd.exe", _
            "/c """ & strDir & "\setup.bat""", strDir, "runas", 1
    End If
Else
    ' === ALL GOOD: LAUNCH WITHOUT ADMIN ===
    CreateObject("WScript.Shell").Run "pythonw.exe """ & strDir & "\gui.py""", 0, False
End If
