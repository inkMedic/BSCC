// Released under the MIT License. See LICENSE for details.
#if BA_PLATFORM_ANDROID
#include "ballistica/core/platform/android/platform_android.h"
#include <jni.h>
#include <android/log.h>
#include <SDL3/SDL_system.h>
#include <iterator>
#include <memory>
#include "external/utfcpp/utf8.h"
#include "ballistica/shared/math/rect.h"

extern "C" jclass BallisticaCommunityActivity();
extern "C" int BallisticaCommunitySmallestWidthDp();
namespace ballistica::core {
auto PlatformAndroid::GetDefaultUIScale() -> UIScale {
  // Android's logical dp sizing follows accessibility/display-size settings.
  // Physical xdpi/ydpi are diagnostic values, not the UI scaling density.
  return BallisticaCommunitySmallestWidthDp() >= 600 ? UIScale::kMedium
                                                   : UIScale::kSmall;
}
namespace {
// SDL attaches native worker threads to the JVM and detaches them on exit.
struct JavaCall {
  JNIEnv* env{static_cast<JNIEnv*>(SDL_GetAndroidJNIEnv())};
  jclass cls{BallisticaCommunityActivity()};
  JavaCall() {
    if (!env || !cls || env->PushLocalFrame(32) < 0) throw std::runtime_error("Android JVM unavailable");
  }
  ~JavaCall() { env->PopLocalFrame(nullptr); }
  auto String(const std::string& value) -> jstring {
    std::u16string text;
    utf8::utf8to16(value.begin(), value.end(), std::back_inserter(text));
    return env->NewString(reinterpret_cast<const jchar*>(text.data()), text.size());
  }
  void Check() {
    if (env->ExceptionCheck()) {
      env->ExceptionDescribe();
      env->ExceptionClear();
      throw std::runtime_error("Android text service failed; see logcat");
    }
  }
};
struct TextPixels { std::vector<uint8_t> bytes; };
}  // namespace

void PlatformAndroid::EmitPlatformLog(std::string_view name, LogLevel level, std::string_view message) {
  int priority = ANDROID_LOG_INFO;
  if (level == LogLevel::kDebug) priority = ANDROID_LOG_DEBUG;
  else if (level == LogLevel::kWarning) priority = ANDROID_LOG_WARN;
  else if (level == LogLevel::kError) priority = ANDROID_LOG_ERROR;
  else if (level == LogLevel::kCritical) priority = ANDROID_LOG_FATAL;
  std::string tag = "Ballistica/" + std::string(name);
  // Keep messages within logcat's per-entry payload limit.
  while (!message.empty()) {
    auto chunk = message.substr(0, 3000);
    __android_log_print(priority, tag.c_str(), "%.*s", static_cast<int>(chunk.size()), chunk.data());
    message.remove_prefix(chunk.size());
  }
}
void PlatformAndroid::HandleLowLevelDebugLog(const std::string& message) {
  __android_log_write(ANDROID_LOG_DEBUG, "Ballistica/native", message.c_str());
}

auto PlatformAndroid::HandleFatalError(bool exit_cleanly, bool) -> bool {
  // Android's Java/HWUI threads can still be running here. Running libc
  // global destructors via exit() destroys their mutexes concurrently.
  if (exit_cleanly) std::_Exit(1);
  return false;
}

auto PlatformAndroid::GetLocaleTag() -> std::string {
  JavaCall j;
  auto method = j.env->GetStaticMethodID(j.cls, "localeTag", "()Ljava/lang/String;");
  auto text = static_cast<jstring>(j.env->CallStaticObjectMethod(j.cls, method));
  j.Check();
  const char* data = j.env->GetStringUTFChars(text, nullptr);
  std::string result(data);
  j.env->ReleaseStringUTFChars(text, data);
  return result;
}

void PlatformAndroid::GetTextBoundsAndWidth(const std::string& text, Rect* r, float* width) {
  JavaCall j;
  auto method = j.env->GetStaticMethodID(j.cls, "measureText", "(Ljava/lang/String;)[F");
  auto values = static_cast<jfloatArray>(j.env->CallStaticObjectMethod(j.cls, method, j.String(text)));
  j.Check();
  float result[5];
  j.env->GetFloatArrayRegion(values, 0, 5, result);
  *r = Rect(result[0], result[1], result[2], result[3]);
  *width = result[4];
}

auto PlatformAndroid::DoGetTextLineBreakOffsets(const std::string& text) -> std::vector<int> {
  JavaCall j;
  auto method = j.env->GetStaticMethodID(j.cls, "lineBreaks", "(Ljava/lang/String;)[I");
  auto values = static_cast<jintArray>(j.env->CallStaticObjectMethod(j.cls, method, j.String(text)));
  j.Check();
  std::vector<int> result(j.env->GetArrayLength(values));
  j.env->GetIntArrayRegion(values, 0, result.size(), result.data());
  return result;
}

auto PlatformAndroid::CreateTextTexture(int width, int height,
    const std::vector<std::string>& strings, const std::vector<float>& positions,
    const std::vector<float>& widths, float scale) -> void* {
  JavaCall j;
  auto arr = j.env->NewObjectArray(strings.size(), j.env->FindClass("java/lang/String"), nullptr);
  for (size_t i = 0; i < strings.size(); ++i) {
    auto text = j.String(strings[i]);
    j.env->SetObjectArrayElement(arr, i, text);
    j.env->DeleteLocalRef(text);
  }
  auto pos = j.env->NewFloatArray(positions.size());
  j.env->SetFloatArrayRegion(pos, 0, positions.size(), positions.data());
  auto method = j.env->GetStaticMethodID(j.cls, "renderText", "(II[Ljava/lang/String;[FF)[I");
  auto pixels = static_cast<jintArray>(j.env->CallStaticObjectMethod(j.cls, method, width, height, arr, pos, scale));
  j.Check();
  std::vector<jint> argb(static_cast<size_t>(width) * height);
  j.env->GetIntArrayRegion(pixels, 0, argb.size(), argb.data());
  auto result = std::make_unique<TextPixels>();
  result->bytes.resize(argb.size() * 4);
  for (size_t i = 0; i < argb.size(); ++i) {
    // Canvas draws white text; premultiply white RGB by coverage.
    uint8_t a = (static_cast<uint32_t>(argb[i]) >> 24) & 255;
    result->bytes[i * 4] = a;
    result->bytes[i * 4 + 1] = a;
    result->bytes[i * 4 + 2] = a;
    result->bytes[i * 4 + 3] = a;
  }
  return result.release();
}

auto PlatformAndroid::GetTextTextureData(void* tex) -> uint8_t* {
  return static_cast<TextPixels*>(tex)->bytes.data();
}
void PlatformAndroid::FreeTextTexture(void* tex) { delete static_cast<TextPixels*>(tex); }
}  // namespace ballistica::core
#endif
