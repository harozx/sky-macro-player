Option Explicit

Dim fso, shell, shellApp, appDir, pythonPath, pythonwPath, appPath, setupPath
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
Set shellApp = CreateObject("Shell.Application")

appDir = fso.GetParentFolderName(WScript.ScriptFullName)
pythonPath = fso.BuildPath(appDir, ".venv\Scripts\python.exe")
pythonwPath = fso.BuildPath(appDir, ".venv\Scripts\pythonw.exe")
appPath = fso.BuildPath(appDir, "macro_player\app.py")
setupPath = fso.BuildPath(appDir, "setup.bat")

If Not fso.FileExists(appPath) Then
    MsgBox "Cannot start Sky Macro Player." & vbCrLf & vbCrLf & _
           "Missing application file:" & vbCrLf & appPath, _
           vbOKOnly + vbCritical, "Sky Macro Player - Missing File"
    WScript.Quit 2
End If

If Not fso.FileExists(pythonwPath) Or Not fso.FileExists(pythonPath) Then
    Dim answer
    answer = MsgBox( _
        "The local application environment is not installed." & vbCrLf & vbCrLf & _
        "Open setup now? Administrator rights are not required.", _
        vbYesNo + vbQuestion, "Sky Macro Player - Setup Required")

    If answer = vbYes Then
        If Not fso.FileExists(setupPath) Then
            MsgBox "Setup file is missing:" & vbCrLf & setupPath, _
                   vbOKOnly + vbCritical, "Sky Macro Player - Missing File"
            WScript.Quit 3
        End If
        shellApp.ShellExecute setupPath, "", appDir, "", 1
    End If
    WScript.Quit 0
End If

Dim command, result
command = """" & pythonPath & """ -c ""import PySide6, pynput"""
result = shell.Run(command, 0, True)
If result <> 0 Then
    MsgBox "The local environment is incomplete or damaged." & vbCrLf & vbCrLf & _
           "Run setup.bat to repair the pinned dependencies.", _
           vbOKOnly + vbCritical, "Sky Macro Player - Runtime Error"
    shellApp.ShellExecute setupPath, "", appDir, "", 1
    WScript.Quit 5
End If

shell.CurrentDirectory = appDir
command = """" & pythonwPath & """ -m macro_player.app"

On Error Resume Next
result = shell.Run(command, 0, False)
If Err.Number <> 0 Then
    MsgBox "Sky Macro Player could not be launched." & vbCrLf & vbCrLf & _
           "Error " & Err.Number & ": " & Err.Description & vbCrLf & _
           "Run setup.bat to repair the local environment.", _
           vbOKOnly + vbCritical, "Sky Macro Player - Launch Error"
    WScript.Quit 4
End If
On Error GoTo 0
