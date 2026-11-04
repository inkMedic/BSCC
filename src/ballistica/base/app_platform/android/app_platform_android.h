// Released under the MIT License. See LICENSE for details.
#ifndef BALLISTICA_BASE_APP_PLATFORM_ANDROID_APP_PLATFORM_ANDROID_H_
#define BALLISTICA_BASE_APP_PLATFORM_ANDROID_APP_PLATFORM_ANDROID_H_
#if BA_PLATFORM_ANDROID
#include "ballistica/base/app_platform/app_platform.h"
namespace ballistica::base {
// Generic capabilities deliberately retain the base class's unavailable
// purchases/login behavior. No Google/Amazon SDK or account endpoint.
class AppPlatformAndroid : public AppPlatform {};
}  // namespace ballistica::base
#endif
#endif
