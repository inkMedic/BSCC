[CmdletBinding()]
param([string]$Distribution = 'Ubuntu', [switch]$Clean,
      [string]$ApiUrl = $env:COMMUNITY_API_URL, [switch]$AllowHttp)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$script = Join-Path $repo 'tools/community-android/build-linux.sh'
$linuxScript = & wsl.exe -d $Distribution -- wslpath -a $script.Replace('\', '/')
if ($LASTEXITCODE -ne 0) { throw 'Cannot map build script into WSL' }
$linuxScript = $linuxScript.Trim()
$buildArgs = @($linuxScript)
if ($Clean) { $buildArgs += '--clean' }
$http = if ($AllowHttp) { '1' } else { '0' }
& wsl.exe -d $Distribution -- env "COMMUNITY_API_URL=$ApiUrl" "COMMUNITY_ALLOW_HTTP=$http" bash @buildArgs
if ($LASTEXITCODE -ne 0) { throw "Android build failed with exit $LASTEXITCODE; see artifacts/android/logs" }
