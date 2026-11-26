' 无控制台启动 Artist Toolkit:直接拉起已构建的界面 exe,不经过 cmd。
' 没有构建产物时回退到 start.bat(会编译,此时才需要控制台窗口)。
Option Explicit
Dim fso, shell, here, candidates, i
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
here = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = here

candidates = Array( _
    fso.BuildPath(here, "dist-gpui\ArtistToolkit.exe"), _
    fso.BuildPath(here, "ui\target\release\artist-toolkit-ui.exe"), _
    fso.BuildPath(here, "ui\target\debug\artist-toolkit-ui.exe"))

For i = 0 To UBound(candidates)
    If fso.FileExists(candidates(i)) Then
        shell.Run """" & candidates(i) & """", 1, False
        WScript.Quit 0
    End If
Next

shell.Run "cmd /c """ & fso.BuildPath(here, "start.bat") & """", 1, False
