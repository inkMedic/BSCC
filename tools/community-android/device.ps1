[CmdletBinding()]
param(
    [ValidateSet('Install', 'Launch', 'Collect')][string]$Action = 'Install',
    [string]$Serial,
    [string]$SdkRoot = "$env:USERPROFILE/AppData/Local/Android/Sdk",
    [string]$Apk
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
if (!$Apk) { $Apk = Join-Path $repo 'artifacts/android/ballistica-community-arm64-debug.apk' }
$adb = Join-Path $SdkRoot 'platform-tools/adb.exe'
$listing = & $adb devices -l
if ($LASTEXITCODE -ne 0) { throw 'Windows ADB cannot enumerate devices' }
$listing
$devices = @($listing | Where-Object { $_ -match '^([^\s]+)\s+device\b' } | ForEach-Object { ($_ -split '\s+')[0] })
if (!$Serial) {
    if ($devices.Count -ne 1) {
        $out = Join-Path $repo 'artifacts/android'
        New-Item -ItemType Directory -Force $out | Out-Null
        [ordered]@{ status = 'ENVIRONMENT_BLOCKED'; action = $Action; authorizedDeviceCount = $devices.Count;
            captured = (Get-Date).ToString('o'); reason = 'A single authorized Android device is required, or specify -Serial.' } |
            ConvertTo-Json | Set-Content -LiteralPath (Join-Path $out 'device-status.json') -Encoding utf8
        throw "Expected one authorized Android device, found $($devices.Count); connect a device or pass -Serial"
    }
    $Serial = $devices[0]
}
if ($Serial -notin $devices) { throw "Device $Serial is absent, offline or unauthorized" }
function Adb([string[]]$Arguments) {
    & $adb -s $Serial @Arguments
    if ($LASTEXITCODE -ne 0) { throw "ADB failed: $Arguments" }
}
$package = 'org.ballistica.community'
if ($Action -eq 'Install') {
    if (!(Test-Path -LiteralPath $Apk -PathType Leaf)) { throw "APK missing: $Apk" }
    Adb @('install', '-r', '-t', $Apk)
}
if ($Action -in @('Install', 'Launch')) {
    Adb @('shell', 'am', 'start', '-W', '-n', "$package/.CommunityActivity")
}
$record = Join-Path $repo ("artifacts/android/device-" + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Force $record | Out-Null
foreach ($property in @('ro.product.model', 'ro.build.version.release', 'ro.build.version.sdk', 'ro.product.cpu.abilist', 'ro.build.fingerprint')) {
    "$property=$(& $adb -s $Serial shell getprop $property)" | Add-Content -LiteralPath (Join-Path $record 'device.txt') -Encoding utf8
}
& $adb -s $Serial shell dumpsys package $package | Set-Content -LiteralPath (Join-Path $record 'package.txt') -Encoding utf8
$processId = (& $adb -s $Serial shell pidof $package | Out-String).Trim()
if ($processId -match '^\d+$') {
    & $adb -s $Serial logcat -d -v threadtime "--pid=$processId" | Set-Content -LiteralPath (Join-Path $record 'logcat.txt') -Encoding utf8
}
& $adb -s $Serial logcat -d -b crash -v threadtime | Set-Content -LiteralPath (Join-Path $record 'crash-buffer.txt') -Encoding utf8
if (Test-Path -LiteralPath $Apk) { Get-FileHash -LiteralPath $Apk -Algorithm SHA256 | Format-List | Out-File (Join-Path $record 'apk.txt') -Encoding utf8 }
Write-Output "Evidence saved to $record. This script does not certify gameplay, IME, touch or lifecycle acceptance."
