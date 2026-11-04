[CmdletBinding()]
param([string]$Distribution = 'Ubuntu', [string]$SdkRoot = "$env:USERPROFILE/AppData/Local/Android/Sdk")
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$outputDir = Join-Path $repo 'artifacts/android'
New-Item -ItemType Directory -Force $outputDir | Out-Null
function Probe([string]$Exe, [string[]]$Arguments) {
    try {
        $content = & $Exe @Arguments 2>&1 | Out-String
        return @{ exit = $LASTEXITCODE; output = $content.Replace("`0", '').Trim() }
    } catch { return @{ exit = -1; output = $_.Exception.Message } }
}
$report = [ordered]@{
    captured = (Get-Date).ToString('o')
    repository = $repo
    commit = Probe 'git' @('-C', $repo, 'rev-parse', 'HEAD')
    status = Probe 'git' @('-C', $repo, 'status', '--short')
    sdk = $SdkRoot
    java = Probe 'java' @('-version')
    python = Probe 'python' @('--version')
    cmake = Probe 'cmake' @('--version')
    wsl = Probe 'wsl' @('--list', '--verbose')
    linux = Probe 'wsl' @('-d', $Distribution, '--', 'bash', '-lc', 'uname -a; python3 --version; cmake --version; ninja --version; /usr/lib/jvm/java-21-openjdk-amd64/bin/java -version')
    adb = Probe (Join-Path $SdkRoot 'platform-tools/adb.exe') @('devices', '-l')
    sdkPackages = @{}
}
foreach ($part in @('ndk', 'platforms', 'build-tools', 'cmake')) {
    $report.sdkPackages[$part] = @(Get-ChildItem -LiteralPath (Join-Path $SdkRoot $part) -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name)
}
$json = $report | ConvertTo-Json -Depth 8
$json | Set-Content -LiteralPath (Join-Path $outputDir 'environment.json') -Encoding utf8
$json
