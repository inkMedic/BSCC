// Released under the MIT License. See LICENSE for details.
#ifndef BALLISTICA_CORE_PLATFORM_ANDROID_PLATFORM_ANDROID_H_
#define BALLISTICA_CORE_PLATFORM_ANDROID_PLATFORM_ANDROID_H_
#if BA_PLATFORM_ANDROID
#include <cstdlib>
#include <optional>
#include <string>
#include <stdexcept>
#include "ballistica/core/platform/platform.h"
namespace ballistica::core {
// The Java host sets these paths before any engine/Python construction.
class PlatformAndroid : public Platform {
 public:
  auto DoHasTouchScreen() -> bool override { return true; }
  auto IsRunningOnDesktop() -> bool override { return false; }
  auto GetDefaultUIScale() -> UIScale override;
  auto GetLegacyPlatformName() -> std::string override { return "android"; }
  auto GetLegacySubplatformName() -> std::string override { return "community"; }
  auto GetDeviceV1AccountUUIDPrefix() -> std::string override { return "community-android"; }
  auto GetDeviceUUIDInputs() -> std::list<std::string> override {
    const char* id = std::getenv("BA_COMMUNITY_INSTALL_ID");
    if (!id) throw std::runtime_error("Missing Android installation id");
    return {id};
  }
  auto GetLocaleTag() -> std::string override;
  // External custom soundtracks are unsupported by this host. An empty
  // path maps to None in the Python API; bundled game music uses OpenAL.
  auto AndroidGetExternalFilesDir() -> std::string override { return {}; }
  auto HandleFatalError(bool exit_cleanly, bool in_top_level_exception_handler) -> bool override;
  void EmitPlatformLog(std::string_view, LogLevel, std::string_view) override;
  void HandleLowLevelDebugLog(const std::string&) override;
  void GetTextBoundsAndWidth(const std::string&, Rect*, float*) override;
  auto DoGetTextLineBreakOffsets(const std::string&) -> std::vector<int> override;
  auto CreateTextTexture(int, int, const std::vector<std::string>&,
      const std::vector<float>&, const std::vector<float>&, float) -> void* override;
  auto GetTextTextureData(void*) -> uint8_t* override;
  void FreeTextTexture(void*) override;
  auto DoGetDataDirectoryMonolithicDefault() -> std::string override { return RequiredPath("BA_COMMUNITY_DATA"); }
  auto DoGetConfigDirectoryMonolithicDefault() -> std::optional<std::string> override {
    return RequiredPath("BA_COMMUNITY_DATA") + "/config";
  }
  auto DoGetCacheDirectoryMonolithicDefault() -> std::optional<std::string> override {
    return RequiredPath("BA_COMMUNITY_CACHE");
  }
  auto DoGetUserPythonDirectoryMonolithicDefault() -> std::optional<std::string> override {
    return RequiredPath("BA_COMMUNITY_DATA") + "/mods";
  }
 private:
  static auto RequiredPath(const char* name) -> std::string {
    const char* path = std::getenv(name);
    if (!path || path[0] != '/') throw std::runtime_error(std::string("Missing Android host path: ") + name);
    return path;
  }
};
}  // namespace ballistica::core
#endif
#endif
