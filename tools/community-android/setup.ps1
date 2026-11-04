[CmdletBinding()]
param([string]$Distribution = 'Ubuntu', [switch]$InstallSystemPackages)
$ErrorActionPreference = 'Stop'
if ($InstallSystemPackages) {
    & wsl.exe -d $Distribution -u root -- apt-get update
    if ($LASTEXITCODE -ne 0) { throw 'apt update failed' }
    & wsl.exe -d $Distribution -u root -- apt-get install -y build-essential pkg-config rsync unzip curl ninja-build zstd openjdk-21-jdk-headless python3-dev python3-venv autoconf automake libtool cmake
    if ($LASTEXITCODE -ne 0) { throw 'apt dependency installation failed' }
}
$script = (Join-Path $PSScriptRoot 'bootstrap-audit.sh').Replace('\', '/')
$linuxScript = & wsl.exe -d $Distribution -- wslpath -a $script
if ($LASTEXITCODE -ne 0) { throw 'Cannot map setup script into WSL' }
& wsl.exe -d $Distribution -- bash $linuxScript.Trim()
if ($LASTEXITCODE -ne 0) { throw 'Linux SDK/environment setup failed' }
