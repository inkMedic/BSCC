#!/usr/bin/env bash
set -euo pipefail
source_root="$(cd "$(dirname "$0")/../.." && pwd)"
build_root="$HOME/bscn-android-d89c2d90"
test "$source_root" != "$build_root"
test "$(git -C "$source_root" rev-parse HEAD)" = d89c2d90cae1593899bd17a1510fef2465acb437
mkdir -p "$build_root" "$source_root/artifacts/android/logs"
rsync -a --checksum --no-times --exclude=.git --exclude=build --exclude=.cache --exclude=.venv --exclude=.bootstrap \
  --exclude=artifacts --exclude=.gradle --exclude=.cxx "$source_root/" "$build_root/"
cd "$build_root"
export ANDROID_SDK_ROOT="$HOME/bscn-android-sdk"
export ANDROID_HOME="$ANDROID_SDK_ROOT"
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
export PATH="$JAVA_HOME/bin:$PWD/.bootstrap/bin:$PATH"
export BA_BUILD_JOBS="${BA_BUILD_JOBS:-6}"
export BA_ANDROID_BUILD_PYTHON=/usr/bin/python3.14
mkdir -p ballisticakit-android
printf 'sdk.dir=%s\n' "$ANDROID_SDK_ROOT" > ballisticakit-android/local.properties
log_root="$source_root/artifacts/android/logs"
history="$log_root/history/$(date -u +%Y%m%dT%H%M%S)"
mkdir -p "$history"
find "$log_root" -maxdepth 1 -name '*.log' -type f -exec cp '{}' "$history/" \;
printf 'build in progress\n' > "$log_root/last-build-status.txt"
trap 'status=$?; printf "build exit=%s\n" "$status" > "$log_root/last-build-status.txt"' EXIT
make env VENV_LOCK=pconfig/requirements_build_lock.txt 2>&1 | tee "$log_root/environment.log"
make codegen VENV_LOCK=pconfig/requirements_build_lock.txt 2>&1 | tee "$log_root/codegen.log"
.venv/bin/python tools/community-android/ensure-assets.py 2>&1 | tee "$log_root/assets.log"
for stage in sources python audio stage; do
  .venv/bin/python -u tools/community-android/dependencies.py "$stage" > "$log_root/dependencies-$stage.log" 2>&1 || {
    tail -n 60 "$log_root/dependencies-$stage.log"
    exit 1
  }
done
gradle_zip=build/community-downloads/gradle-8.13-bin.zip
if [[ ! -f "$gradle_zip" ]]; then
  curl --fail --location --retry 2 https://services.gradle.org/distributions/gradle-8.13-bin.zip -o "$gradle_zip.part"
  mv "$gradle_zip.part" "$gradle_zip"
fi
if [[ ! -d build/community-deps/gradle-8.13 ]]; then
  unzip -q "$gradle_zip" -d build/community-deps
fi
.venv/bin/python tools/community-android/verify-dependency-lock.py > "$log_root/dependency-lock.log"
if [[ "${1:-}" == --clean ]]; then
  build/community-deps/gradle-8.13/bin/gradle --no-daemon -p ballisticakit-android \
    :BallisticaKit:externalNativeBuildCleanDebug :BallisticaKit:clean 2>&1 | tee "$log_root/clean.log"
fi
build/community-deps/gradle-8.13/bin/gradle --no-daemon -p ballisticakit-android \
  :BallisticaKit:assembleDebug 2>&1 | tee "$log_root/gradle.log"
cp ballisticakit-android/BallisticaKit/build/outputs/apk/debug/BallisticaKit-debug.apk \
  "$source_root/artifacts/android/ballistica-community-arm64-debug.apk"
sha256sum "$source_root/artifacts/android/ballistica-community-arm64-debug.apk" \
  > "$source_root/artifacts/android/apk-sha256.txt"
.venv/bin/python tools/community-android/verify-apk.py \
  "$source_root/artifacts/android/ballistica-community-arm64-debug.apk" \
  > "$source_root/artifacts/android/apk-verification.json"
.venv/bin/python tools/community-android/record-build.py "$source_root/artifacts/android"
cp build/community-downloads/sources.json "$source_root/artifacts/android/dependency-sources.json"
