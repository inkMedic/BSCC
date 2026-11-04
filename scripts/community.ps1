[CmdletBinding()]
param([ValidateSet('Check','Services','Migrate','Backend','Test','HeadlessBuild','AndroidBuild')][string]$Action='Check', [string]$Distribution='Ubuntu')
$ErrorActionPreference='Stop'
$repo=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$linuxRepo=(& wsl.exe -d $Distribution -- wslpath -a $repo.Replace('\','/')).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot map repository into WSL' }
switch ($Action) {
    'Check' { & wsl.exe -d $Distribution -- bash -lc 'python3 --version; command -v psql; command -v redis-server; command -v cmake' }
    'Services' { & wsl.exe -d $Distribution -- bash -lc "cd '$linuxRepo/community-backend' && docker compose up -d --wait" }
    'Migrate' { & wsl.exe -d $Distribution -- bash -lc "cd '$linuxRepo/community-backend' && ~/bscn-backend-py313/bin/alembic upgrade head" }
    'Backend' { & wsl.exe -d $Distribution -- bash -lc "cd '$linuxRepo/community-backend' && ~/bscn-backend-py313/bin/uvicorn community_backend.app:create_app --factory --host 0.0.0.0 --workers 1" }
    'Test' { & wsl.exe -d $Distribution -- bash -lc "cd '$linuxRepo/community-backend' && ~/bscn-backend-py313/bin/python -m pytest -q" }
    'HeadlessBuild' { & wsl.exe -d $Distribution -- bash "$linuxRepo/scripts/build-community-headless.sh" }
    'AndroidBuild' { & "$repo/tools/community-android/build.ps1" -Distribution $Distribution }
}
if ($LASTEXITCODE -ne 0) { throw "Community $Action failed ($LASTEXITCODE)" }
