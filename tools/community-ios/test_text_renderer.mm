// Released under the MIT License. See LICENSE for details.
// Run on macOS; exercises the same CoreText rasterizer used by the iOS app.
#import <ImageIO/ImageIO.h>
#include "text_renderer_apple.h"
#include <algorithm>
#include <cstdio>

int main(int argc, char** argv) {
  @autoreleasepool {
    constexpr int width = 128, height = 64;
    auto pixels = community_ios::RenderTextPixels(width, height, {"Fgj 中文"}, {8, 40}, 1.0);
    int upper = 0, lower = 0, left = 0, right = 0, descender = 0;
    // F is asymmetric both vertically and horizontally: its long top bar
    // must be above its foot, and its stem must remain on the left.
    for (int y = 0; y < height; ++y) {
      for (int x = 8; x < 23; ++x) {
        int alpha = pixels[(y * width + x) * 4 + 3];
        if (y >= 21 && y < 29) upper += alpha;
        if (y >= 32 && y < 40) lower += alpha;
        if (x < 13) left += alpha;
        if (x >= 18) right += alpha;
      }
      for (int x = 24; x < 50; ++x) {
        if (y >= 40 && y < 48) descender += pixels[(y * width + x) * 4 + 3];
      }
    }
    printf("F top=%d bottom=%d left=%d right=%d; gj descenders=%d\n",
           upper, lower, left, right, descender);
    if (!(upper > lower && lower > 0 && left > right && descender > 0)) return 1;
    // Optional preview writes these raw rows as a PNG for visual review.
    if (argc > 1) {
      CGColorSpaceRef space = CGColorSpaceCreateDeviceRGB();
      CGContextRef ctx = CGBitmapContextCreate(pixels.data(), width, height, 8, width * 4, space,
          kCGImageAlphaPremultipliedLast | kCGBitmapByteOrder32Big);
      CGImageRef image = CGBitmapContextCreateImage(ctx);
      NSURL* url = [NSURL fileURLWithPath:@(argv[1])];
      CGImageDestinationRef encoder = CGImageDestinationCreateWithURL(
          (__bridge CFURLRef)url, CFSTR("public.png"), 1, nullptr);
      CGImageDestinationAddImage(encoder, image, nullptr);
      if (!CGImageDestinationFinalize(encoder)) return 1;
      CFRelease(encoder); CGImageRelease(image); CGContextRelease(ctx); CGColorSpaceRelease(space);
    }
  }
  return 0;
}
