$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$target = Join-Path $root "dist\YouTubeAudioExtractor.exe"
if (-not (Test-Path $target)) {
    throw "Target executable not found: $target"
}

$desktop = [Environment]::GetFolderPath("Desktop")

$shell = New-Object -ComObject WScript.Shell
$shortcutNames = @(
    "YouTube Extractor.lnk",
    "YouTube Audio Extractor.lnk"
)

foreach ($shortcutName in $shortcutNames) {
    $shortcutPath = Join-Path $desktop $shortcutName
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $target
    $shortcut.WorkingDirectory = Split-Path -Parent $target
    $shortcut.IconLocation = "$target,0"
    $shortcut.Description = "Launch YouTube Multi Extractor Desktop"
    $shortcut.Save()
    Write-Host "Desktop shortcut updated: $shortcutPath"
}
