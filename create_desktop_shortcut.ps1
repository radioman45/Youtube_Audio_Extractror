$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$distDirectories = Get-ChildItem -Path $root -Directory -Filter "dist*"
$candidates = foreach ($distDirectory in $distDirectories) {
    Join-Path $distDirectory.FullName "YouTubeAudioExtractor.exe"
    Join-Path $distDirectory.FullName "YouTubeAudioExtractor\YouTubeAudioExtractor.exe"
    Join-Path $distDirectory.FullName "YouTubeAudioExtractorDesktop\YouTubeAudioExtractorDesktop.exe"
}

$target = $candidates |
    Where-Object { Test-Path $_ } |
    Sort-Object { (Get-Item $_).LastWriteTimeUtc } -Descending |
    Select-Object -First 1

if (-not $target) {
    throw "Target executable not found in dist output."
}

$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutName = "YouTube Multi Extractor.lnk"
$shortcutPath = Join-Path $desktop $shortcutName
$legacyShortcutNames = @(
    "YouTube Extractor.lnk",
    "YouTube Audio Extractor.lnk",
    "YouTube Audio Extractor Desktop.lnk"
)

$shell = New-Object -ComObject WScript.Shell

foreach ($legacyShortcutName in $legacyShortcutNames) {
    $legacyShortcutPath = Join-Path $desktop $legacyShortcutName
    if ((Test-Path $legacyShortcutPath) -and ($legacyShortcutPath -ne $shortcutPath)) {
        Remove-Item $legacyShortcutPath -Force
        Write-Host "Removed legacy desktop shortcut: $legacyShortcutPath"
    }
}

$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $target
$shortcut.WorkingDirectory = Split-Path -Parent $target
$shortcut.IconLocation = "$target,0"
$shortcut.Description = "Launch YouTube Multi Extractor Desktop"
$shortcut.Save()
Write-Host "Desktop shortcut updated: $shortcutPath"
