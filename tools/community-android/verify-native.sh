#!/usr/bin/env bash
set -euo pipefail
source_root="$(cd "$(dirname "$0")/../.." && pwd)"
output="$source_root/artifacts/android"
apk="$output/ballistica-community-arm64-debug.apk"
build_root="$HOME/bscn-android-d89c2d90"
sdk="$HOME/bscn-android-sdk"
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
export PATH="$JAVA_HOME/bin:$PATH"
"$sdk/build-tools/35.0.0/apksigner" verify --verbose --print-certs "$apk" > "$output/apk-signature.txt"
"$sdk/build-tools/35.0.0/aapt2" dump badging "$apk" > "$output/apk-badging.txt"
llvm="$sdk/ndk/28.2.13676358/toolchains/llvm/prebuilt/linux-x86_64/bin"
lib=$(find "$build_root/ballisticakit-android/BallisticaKit/build/intermediates/cxx/Debug" -path '*/obj/arm64-v8a/libmain.so' -print -quit)
test -n "$lib"
"$llvm/llvm-readelf" -h -l -d "$lib" > "$output/native-elf.txt"
"$llvm/llvm-nm" -D --defined-only "$lib" | \
  grep -E 'PyInit_|SDL_main|BallisticaCommunity|Java_org_ballistica_community' > "$output/native-exports.txt"
for symbol in SDL_main PyInit__babase PyInit__bascenev1 PyInit__bauiv1 PyInit__baplus \
  Java_org_ballistica_community_CommunityActivity_nativeConfigure \
  Java_org_ballistica_community_CommunityActivity_nativeAudioFocus BallisticaCommunityHasAudioFocus; do
  grep -q " $symbol$" "$output/native-exports.txt" || { printf 'Missing symbol %s\n' "$symbol"; exit 1; }
done
if grep -qi 'NEEDED.*ballisticaplus' "$output/native-elf.txt"; then
  printf 'Unexpected official Plus dependency\n'
  exit 1
fi
printf 'PASS: signature, manifest badging, ARM64 native exports, no official Plus dynamic dependency.\n'
