[CmdletBinding()]
param([string]$Distribution = 'Ubuntu')
$ErrorActionPreference = 'Stop'
$script = (Join-Path $PSScriptRoot 'verify-native.sh').Replace('\', '/')
$linuxScript = & wsl.exe -d $Distribution -- wslpath -a $script
if ($LASTEXITCODE -ne 0) { throw 'Cannot map verification script into WSL' }
& wsl.exe -d $Distribution -- bash $linuxScript.Trim()
if ($LASTEXITCODE -ne 0) { throw 'APK/native verification failed' }
