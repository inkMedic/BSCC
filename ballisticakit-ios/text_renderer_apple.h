// Released under the MIT License. See LICENSE for details.
#ifndef BALLISTICA_COMMUNITY_TEXT_RENDERER_APPLE_H_
#define BALLISTICA_COMMUNITY_TEXT_RENDERER_APPLE_H_
#import <CoreText/CoreText.h>
#import <Foundation/Foundation.h>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <vector>

namespace community_ios {
inline auto CreateTextLine(const std::string& text, float scale) -> CTLineRef {
  NSString* string = [[NSString alloc] initWithBytes:text.data()
                                              length:text.size()
                                            encoding:NSUTF8StringEncoding];
  CTFontRef font = CTFontCreateWithName(CFSTR("Helvetica"), 26.0 * scale, nullptr);
  NSDictionary* attrs = @{
    (__bridge id)kCTFontAttributeName : (__bridge id)font,
    (__bridge id)kCTForegroundColorFromContextAttributeName : @YES
  };
  NSAttributedString* attributed = [[NSAttributedString alloc] initWithString:string
                                                                   attributes:attrs];
  CTLineRef line = CTLineCreateWithAttributedString((__bridge CFAttributedStringRef)attributed);
  CFRelease(font);
  return line;
}

inline auto RenderTextPixels(int width, int height, const std::vector<std::string>& strings,
                             const std::vector<float>& positions, float scale)
    -> std::vector<uint8_t> {
  std::vector<uint8_t> pixels(static_cast<size_t>(width) * height * 4);
  CGColorSpaceRef space = CGColorSpaceCreateDeviceRGB();
  CGContextRef ctx =
      CGBitmapContextCreate(pixels.data(), width, height, 8, width * 4, space,
                            kCGImageAlphaPremultipliedLast | kCGBitmapByteOrder32Big);
  CGColorSpaceRelease(space);
  if (!ctx) throw std::runtime_error("Cannot create text bitmap");
  CGContextSetRGBFillColor(ctx, 1, 1, 1, 1);
  for (size_t i = 0; i < strings.size(); ++i) {
    CTLineRef line = CreateTextLine(strings[i], scale);
    // TextPacker baselines and UVs use row zero at the top. Quartz text
    // coordinates are y-up, so convert the baseline exactly once. The bitmap
    // already exposes top-down rows; reversing them again inverts the glyphs.
    CGContextSetTextPosition(ctx, positions[i * 2], height - positions[i * 2 + 1]);
    CTLineDraw(line, ctx);
    CFRelease(line);
  }
  CGContextRelease(ctx);
  return pixels;
}
}  // namespace community_ios
#endif
