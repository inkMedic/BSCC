#!/usr/bin/env bash
set -euo pipefail
cd "$HOME/bscn-android-d89c2d90"
export PATH="$PWD/.bootstrap/bin:$PATH"
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
export ANDROID_SDK_ROOT="$HOME/bscn-android-sdk"
export ANDROID_HOME="$ANDROID_SDK_ROOT"
mkdir -p build/community-downloads "$ANDROID_SDK_ROOT/cmdline-tools"
archive=build/community-downloads/commandlinetools-linux-13114758_latest.zip
if [[ ! -f "$archive" ]]; then
  curl --fail --location --retry 2 --connect-timeout 20 --max-time 300 \
    https://dl.google.com/android/repository/commandlinetools-linux-13114758_latest.zip \
    -o "$archive.part"
  mv "$archive.part" "$archive"
fi
if [[ ! -d "$ANDROID_SDK_ROOT/cmdline-tools/19.0" ]]; then
  unzip -q "$archive" -d "$ANDROID_SDK_ROOT/cmdline-tools"
  mv "$ANDROID_SDK_ROOT/cmdline-tools/cmdline-tools" "$ANDROID_SDK_ROOT/cmdline-tools/19.0"
fi
# sdkmanager exits after reading its license responses; SIGPIPE from yes is expected.
set +o pipefail
yes | "$ANDROID_SDK_ROOT/cmdline-tools/19.0/bin/sdkmanager" --licenses
set -o pipefail
"$ANDROID_SDK_ROOT/cmdline-tools/19.0/bin/sdkmanager" \
  'platform-tools' 'platforms;android-35' 'build-tools;35.0.0' 'ndk;28.2.13676358' 'cmake;3.22.1'
make env VENV_LOCK=pconfig/requirements_build_lock.txt
