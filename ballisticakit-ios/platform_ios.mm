// Released under the MIT License. See LICENSE for details.
#include "platform_ios.h"
#import <CoreText/CoreText.h>
#import <Foundation/Foundation.h>
#include <Python.h>
#import <Security/Security.h>
#import <UIKit/UIKit.h>
#include <memory>
#include "ballistica/shared/math/rect.h"
#include "text_renderer_apple.h"

namespace {
NSString* String(const std::string& s) {
  return [[NSString alloc] initWithBytes:s.data() length:s.size() encoding:NSUTF8StringEncoding];
}
struct TextPixels {
  std::vector<uint8_t> bytes;
};
}  // namespace
namespace ballistica::core {
auto PlatformCommunityIOS::GetDefaultUIScale() -> UIScale {
  // Cached before threads start; never dispatch synchronously while holding GIL.
  return std::string(getenv("BA_COMMUNITY_TABLET")) == "1" ? UIScale::kMedium : UIScale::kSmall;
}
auto PlatformCommunityIOS::GetLocaleTag() -> std::string {
  @autoreleasepool {
    return NSLocale.currentLocale.localeIdentifier.UTF8String;
  }
}
auto PlatformCommunityIOS::GetDeviceUUIDInputs() -> std::list<std::string> {
  return {getenv("BA_COMMUNITY_INSTALL_ID")};
}
void PlatformCommunityIOS::GetTextBoundsAndWidth(const std::string& s, Rect* r, float* width) {
  @autoreleasepool {
    CTLineRef line = community_ios::CreateTextLine(s, 1.0);
    CGRect box = CTLineGetBoundsWithOptions(line, kCTLineBoundsUseGlyphPathBounds);
    *width = CTLineGetTypographicBounds(line, nullptr, nullptr, nullptr);
    *r = Rect(box.origin.x, box.origin.y, CGRectGetMaxX(box), CGRectGetMaxY(box));
    CFRelease(line);
  }
}
auto PlatformCommunityIOS::DoGetTextLineBreakOffsets(const std::string& s) -> std::vector<int> {
  @autoreleasepool {
    NSString* str = String(s);
    CFStringTokenizerRef tokens =
        CFStringTokenizerCreate(nullptr, (__bridge CFStringRef)str, CFRangeMake(0, str.length),
                                kCFStringTokenizerUnitLineBreak, nullptr);
    std::vector<int> out;
    while (CFStringTokenizerAdvanceToNextToken(tokens) != kCFStringTokenizerTokenNone) {
      auto range = CFStringTokenizerGetCurrentTokenRange(tokens);
      auto end = range.location + range.length;
      if (end > 0)
        out.push_back([[str substringToIndex:end] lengthOfBytesUsingEncoding:NSUTF8StringEncoding]);
    }
    CFRelease(tokens);
    if (out.empty() || out.back() != s.size()) out.push_back(static_cast<int>(s.size()));
    return out;
  }
}
auto PlatformCommunityIOS::CreateTextTexture(int width, int height,
                                             const std::vector<std::string>& strings,
                                             const std::vector<float>& positions,
                                             const std::vector<float>& widths, float scale)
    -> void* {
  @autoreleasepool {
    auto pixels = std::make_unique<TextPixels>();
    pixels->bytes = community_ios::RenderTextPixels(width, height, strings, positions, scale);
    return pixels.release();
  }
}
auto PlatformCommunityIOS::GetTextTextureData(void* tex) -> uint8_t* {
  return static_cast<TextPixels*>(tex)->bytes.data();
}
void PlatformCommunityIOS::FreeTextTexture(void* tex) { delete static_cast<TextPixels*>(tex); }
}  // namespace ballistica::core

// Runs on Python workers; Security.framework does not require the main queue.
extern "C" PyObject* BallisticaCommunityIOSRefresh(bool write, const char* value) {
  @autoreleasepool {
    NSDictionary* query = @{
      (__bridge id)kSecClass : (__bridge id)kSecClassGenericPassword,
      (__bridge id)kSecAttrService : NSBundle.mainBundle.bundleIdentifier,
      (__bridge id)kSecAttrAccount : @"community-refresh"
    };
    OSStatus status;
    if (write) {
      if (!value)
        status = SecItemDelete((__bridge CFDictionaryRef)query);
      else {
        NSData* data = [NSData dataWithBytes:value length:strlen(value)];
        NSDictionary* changes = @{(__bridge id)kSecValueData : data};
        status = SecItemUpdate((__bridge CFDictionaryRef)query, (__bridge CFDictionaryRef)changes);
        if (status == errSecItemNotFound) {
          NSMutableDictionary* item = query.mutableCopy;
          [item addEntriesFromDictionary:changes];
          item[(__bridge id)kSecAttrAccessible] =
              (__bridge id)kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly;
          status = SecItemAdd((__bridge CFDictionaryRef)item, nullptr);
        }
      }
      if (status == errSecSuccess || (!value && status == errSecItemNotFound)) Py_RETURN_NONE;
    } else {
      NSMutableDictionary* request = query.mutableCopy;
      request[(__bridge id)kSecReturnData] = @YES;
      CFTypeRef result = nullptr;
      status = SecItemCopyMatching((__bridge CFDictionaryRef)request, &result);
      if (status == errSecItemNotFound) Py_RETURN_NONE;
      if (status == errSecSuccess) {
        NSData* data = CFBridgingRelease(result);
        return PyUnicode_DecodeUTF8(static_cast<const char*>(data.bytes), data.length, "strict");
      }
    }
    PyErr_Format(PyExc_RuntimeError, "iOS Keychain operation failed (%d)",
                 static_cast<int>(status));
    return nullptr;
  }
}
