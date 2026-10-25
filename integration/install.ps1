# Optional per-user installation after extracting the extension ZIP.
# The standard EEZ Studio Extensions Manager can import the ZIP directly.
[CmdletBinding()]
param([switch]$Uninstall, [string]$ExtensionsPath = (Join-Path $env:APPDATA 'eezstudio\extensions'))
$ErrorActionPreference = 'Stop'
$extensionId = 'reez-rust-output'
$destination = Join-Path $ExtensionsPath $extensionId
if ($Uninstall) {
    if (Test-Path -LiteralPath $destination) { Remove-Item -LiteralPath $destination -Recurse -Force }
    Write-Host 'Reez removed. Restart EEZ Studio. Project settings and generated files are preserved.'
    exit 0
}
$source = $PSScriptRoot
$manifest = Get-Content -LiteralPath (Join-Path $source 'package.json') -Raw | ConvertFrom-Json
if ($manifest.id -ne $extensionId) { throw 'This is not a Reez extension package.' }
if (!(Test-Path -LiteralPath (Join-Path $source 'bin\reez.wasm'))) { throw 'Extract the complete Reez extension ZIP before installing.' }
if ([IO.Path]::GetFullPath($source).TrimEnd('\') -eq [IO.Path]::GetFullPath($destination).TrimEnd('\')) {
    Write-Host 'Reez is already installed in this folder. Restart EEZ Studio.'
    exit 0
}
$cache = Join-Path $ExtensionsPath 'cache'
New-Item -ItemType Directory -Path $cache -Force | Out-Null
$stage = Join-Path $cache ('reez-stage-' + [Guid]::NewGuid().ToString('N'))
$backup = Join-Path $cache ('reez-backup-' + [Guid]::NewGuid().ToString('N'))
$hadPrevious = Test-Path -LiteralPath $destination
try {
    New-Item -ItemType Directory -Path $stage | Out-Null
    Get-ChildItem -LiteralPath $source -Force | Copy-Item -Destination $stage -Recurse -Force
    if ($hadPrevious) { Move-Item -LiteralPath $destination -Destination $backup }
    try { Move-Item -LiteralPath $stage -Destination $destination }
    catch {
        if ($hadPrevious -and (Test-Path -LiteralPath $backup)) { Move-Item -LiteralPath $backup -Destination $destination }
        throw
    }
    if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Recurse -Force }
} finally {
    if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
}
Write-Host ('Installed Reez ' + $manifest.version + ' to ' + $destination)
Write-Host 'Restart EEZ Studio, open a project, and enable it in the Rust output panel.'
