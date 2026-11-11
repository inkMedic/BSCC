// Released under the MIT License. See LICENSE for details.
#ifndef BALLISTICA_COMMUNITY_PLATFORM_IOS_H_
#define BALLISTICA_COMMUNITY_PLATFORM_IOS_H_
#include "ballistica/core/platform/platform.h"
namespace ballistica::core {
class PlatformCommunityIOS : public Platform {
 public:
  auto DoHasTouchScreen() -> bool override { return true; }
  auto IsRunningOnDesktop() -> bool override { return false; }
  auto GetDefaultUIScale() -> UIScale override;
  auto GetLegacyPlatformName() -> std::string override { return "ios"; }
  auto GetLocaleTag() -> std::string override;
  auto GetDeviceUUIDInputs() -> std::list<std::string> override;
  void GetTextBoundsAndWidth(const std::string&, Rect*, float*) override;
  auto DoGetTextLineBreakOffsets(const std::string&)
      -> std::vector<int> override;
  auto CreateTextTexture(int, int, const std::vector<std::string>&,
                         const std::vector<float>&, const std::vector<float>&,
                         float) -> void* override;
  auto GetTextTextureData(void*) -> uint8_t* override;
  void FreeTextTexture(void*) override;
};
}  // namespace ballistica::core
#endif
