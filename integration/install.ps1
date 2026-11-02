# Install or remove a folder-managed Reez extension for this Windows user.
# Old project-extension ZIPs were classified as Yarn packages although they
# installed as folders. Always close Studio first.
[CmdletBinding()]
param([switch]$Uninstall, [string]$ExtensionsPath = (Join-Path $env:APPDATA 'eezstudio\extensions'))
$ErrorActionPreference = 'Stop'
$extensionId = 'reez-rust-output'
$destination = Join-Path $ExtensionsPath $extensionId

if (Get-Process -Name 'EEZ Studio' -ErrorAction SilentlyContinue) {
    throw 'Close EEZ Studio completely before installing or removing Reez.'
}

function Assert-ReezFolder([string]$folder) {
    if (!(Test-Path -LiteralPath $folder)) { return }
    $manifestPath = Join-Path $folder 'package.json'
    if (!(Test-Path -LiteralPath $manifestPath)) {
        throw ('Refusing to replace a folder without package.json: ' + $folder)
    }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    if ($manifest.id -ne $extensionId -and ($manifest.id -or $manifest.name -ne $extensionId)) {
        throw ('Refusing to replace a different extension: ' + $folder)
    }
}

function Get-ReezFolders {
    $candidates = New-Object 'System.Collections.Generic.List[string]'
    if (Test-Path -LiteralPath $ExtensionsPath) {
        foreach ($item in (Get-ChildItem -LiteralPath $ExtensionsPath -Directory)) {
            if ($item.Name -ne 'cache' -and $item.Name -ne 'node_modules') {
                $candidates.Add($item.FullName)
            }
        }
    }
    $modules = Join-Path $ExtensionsPath 'node_modules'
    if (Test-Path -LiteralPath $modules) {
        foreach ($item in (Get-ChildItem -LiteralPath $modules -Directory)) {
            if ($item.Name.StartsWith('@')) {
                foreach ($scoped in (Get-ChildItem -LiteralPath $item.FullName -Directory)) {
                    $candidates.Add($scoped.FullName)
                }
            } else { $candidates.Add($item.FullName) }
        }
    }
    foreach ($folder in $candidates) {
        $manifestPath = Join-Path $folder 'package.json'
        if (!(Test-Path -LiteralPath $manifestPath)) { continue }
        $item = Get-Item -LiteralPath $folder -Force
        $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
        if ($manifest.id -eq $extensionId -or (!$manifest.id -and $manifest.name -eq $extensionId)) {
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw ('Refusing to remove a linked extension folder: ' + $folder)
            }
            [PSCustomObject]@{ Path = $folder; Name = $manifest.name }
        }
    }
}

function Remove-LegacyYarnRegistration {
    param([switch]$RemoveCurrent)
    $folders = @(Get-ReezFolders)
    $names = @($extensionId)
    $modules = [IO.Path]::GetFullPath((Join-Path $ExtensionsPath 'node_modules'))
    foreach ($folder in $folders) {
        if ([IO.Path]::GetFullPath($folder.Path).StartsWith($modules + '\', [StringComparison]::OrdinalIgnoreCase)) {
            $names += $folder.Name
        }
    }
    $rootPackage = Join-Path $ExtensionsPath 'package.json'
    if (Test-Path -LiteralPath $rootPackage) {
        $package = Get-Content -LiteralPath $rootPackage -Raw | ConvertFrom-Json
        $changed = $false
        foreach ($name in ($names | Select-Object -Unique)) {
            if ($name -and $package.dependencies -and $package.dependencies.PSObject.Properties[$name]) {
                $package.dependencies.PSObject.Properties.Remove($name)
                $changed = $true
            }
        }
        if ($changed) {
            $next = $package | ConvertTo-Json -Depth 100
            $temporary = $rootPackage + '.reez-' + [Guid]::NewGuid().ToString('N') + '.tmp'
            $backup = $rootPackage + '.before-reez-' + [Guid]::NewGuid().ToString('N')
            [IO.File]::WriteAllText($temporary, $next + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
            try { [IO.File]::Replace($temporary, $rootPackage, $backup) }
            finally { if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force } }
        }
    }
    foreach ($folder in $folders) {
        if (!$RemoveCurrent -and [IO.Path]::GetFullPath($folder.Path) -eq [IO.Path]::GetFullPath($destination)) { continue }
        Remove-Item -LiteralPath $folder.Path -Recurse -Force
        Write-Host ('Removed duplicate Reez extension: ' + $folder.Path)
    }
}

if ($Uninstall) {
    Remove-LegacyYarnRegistration -RemoveCurrent
    Write-Host 'Reez removed. Restart EEZ Studio. Project settings and generated files are preserved.'
    exit 0
}

$source = $PSScriptRoot
$manifest = Get-Content -LiteralPath (Join-Path $source 'package.json') -Raw | ConvertFrom-Json
if ($manifest.id -ne $extensionId) { throw 'This is not a Reez extension package.' }
if (!(Test-Path -LiteralPath (Join-Path $source 'backend\runtime\bin\c2rust-transpile'))) {
    throw 'Extract the complete Reez extension ZIP before installing.'
}
New-Item -ItemType Directory -Path $ExtensionsPath -Force | Out-Null
Assert-ReezFolder $destination
if ([IO.Path]::GetFullPath($source).TrimEnd('\') -eq [IO.Path]::GetFullPath($destination).TrimEnd('\')) {
    Remove-LegacyYarnRegistration
    Write-Host ('Reez ' + $manifest.version + ' is already in the installation folder. Restart EEZ Studio.')
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
    Remove-LegacyYarnRegistration
    if ($hadPrevious) { Move-Item -LiteralPath $destination -Destination $backup }
    try { Move-Item -LiteralPath $stage -Destination $destination }
    catch {
        if ($hadPrevious -and (Test-Path -LiteralPath $backup)) {
            Move-Item -LiteralPath $backup -Destination $destination
        }
        throw
    }
    if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Recurse -Force }
} finally {
    if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
}
Write-Host ('Installed Reez ' + $manifest.version + ' to ' + $destination)
Write-Host 'Restart EEZ Studio. Reez now appears in Project Editor Extensions.'
