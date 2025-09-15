$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("$Home\Desktop\OmniAnki.lnk")
$Shortcut.TargetPath = "C:\Users\MAX\Desktop\Arcanum\2.py"
$Shortcut.Save()
