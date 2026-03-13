$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$candidates = @(
    (Join-Path $root "dist\YouTubeAudioExtractor.exe"),
    (Join-Path $root "dist\YouTubeAudioExtractor\YouTubeAudioExtractor.exe"),
    (Join-Path $root "dist\YouTubeAudioExtractorDesktop\YouTubeAudioExtractorDesktop.exe")
)
$target = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $target) {
    throw "Target executable not found in dist output."
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
