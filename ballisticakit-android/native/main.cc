#include <jni.h>
#include <unistd.h>
#include <cstdlib>
#include <stdexcept>
#include <string>
#include <atomic>
#include <SDL3/SDL.h>
#include "ballistica/shared/ballistica.h"
#include "ballistica/core/support/core_config.h"
#include "ballistica/core/platform/platform.h"

static jclass community_activity{};
static std::atomic<bool> initial_audio_focus{true};
static int smallest_width_dp{360};
extern "C" int BallisticaCommunitySmallestWidthDp() { return smallest_width_dp; }
extern "C" jclass BallisticaCommunityActivity() { return community_activity; }
extern "C" bool BallisticaCommunityHasAudioFocus() { return initial_audio_focus.load(); }
extern "C" JNIEXPORT void JNICALL
Java_org_ballistica_community_CommunityActivity_nativeAudioFocus(JNIEnv*, jclass, jboolean focused) {
  initial_audio_focus.store(focused);
  SDL_Event event{};
  event.type = SDL_EVENT_USER;
  event.user.code = 0x42414643;
  event.user.data1 = focused ? reinterpret_cast<void*>(1) : nullptr;
  SDL_PushEvent(&event);
}

extern "C" JNIEXPORT void JNICALL
Java_org_ballistica_community_CommunityActivity_nativeConfigure(
    JNIEnv* env, jclass activity, jstring data, jstring cache, jstring installation, jboolean focused, jint smallest_dp) {
  smallest_width_dp = smallest_dp > 0 ? smallest_dp : 360;
  initial_audio_focus.store(focused);
  if (!community_activity) community_activity = static_cast<jclass>(env->NewGlobalRef(activity));
  const char* d = env->GetStringUTFChars(data, nullptr);
  const char* c = env->GetStringUTFChars(cache, nullptr);
  const char* id = env->GetStringUTFChars(installation, nullptr);
  setenv("BA_COMMUNITY_DATA", d, 1);
  setenv("BA_COMMUNITY_CACHE", c, 1);
  setenv("BA_COMMUNITY_ANDROID", "1", 1);
  for (const auto& item : {std::pair{"communityApiUrl", "COMMUNITY_API_URL"},
                           std::pair{"communityAllowHttp", "COMMUNITY_ALLOW_HTTP"}}) {
    auto method = env->GetStaticMethodID(activity, item.first, "()Ljava/lang/String;");
    auto value = static_cast<jstring>(env->CallStaticObjectMethod(activity, method));
    if (value) {
      const char* text = env->GetStringUTFChars(value, nullptr);
      setenv(item.second, text, 1);
      env->ReleaseStringUTFChars(value, text);
      env->DeleteLocalRef(value);
    }
  }
  setenv("BA_COMMUNITY_INSTALL_ID", id, 1);
  int result = chdir(d);
  env->ReleaseStringUTFChars(data, d);
  env->ReleaseStringUTFChars(cache, c);
  env->ReleaseStringUTFChars(installation, id);
  if (result != 0) {
    env->ThrowNew(env->FindClass("java/lang/IllegalStateException"), "Cannot select game data directory");
  }
}

extern "C" __attribute__((visibility("default"))) int SDL_main(int argc, char** argv) {
  auto config = ballistica::core::CoreConfig::ForArgsAndEnvVars(
      argc, argv, ballistica::core::Platform::TimeSinceEpochSeconds());
  int result = ballistica::MonolithicMain(config);
  SDL_Quit();
  // Ballistica's monolithic globals/Python runtime are process-scoped.
  // A later launcher start must get a fresh process, like desktop main().
  std::_Exit(result);
}
