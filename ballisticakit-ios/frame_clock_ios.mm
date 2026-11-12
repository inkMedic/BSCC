// Released under the MIT License. See LICENSE for details.
#include "frame_clock_ios.h"

#import <QuartzCore/QuartzCore.h>
#include <SDL3/SDL_video.h>
#import <UIKit/UIKit.h>

#include <algorithm>
#include <cmath>

#include "ballistica/core/core.h"

@interface CommunityDisplayClock : NSObject
@property(nonatomic, strong) CADisplayLink* link;
@property(nonatomic) BOOL tickReady;
@property(nonatomic) BOOL waiting;
@property(nonatomic) float renderCap;
@property(nonatomic) CFTimeInterval nextFrame;
@property(nonatomic) CFTimeInterval tickTimestamp;
@property(nonatomic) CFTimeInterval sampleStart;
@property(nonatomic) NSInteger sampleFrames;
@property(nonatomic) NSInteger renderedFrames;
@property(nonatomic) NSInteger missedFrames;
@property(nonatomic) double drawMs;
@property(nonatomic) double presentMs;
@property(nonatomic) double lastLoggedRate;
- (void)resetSample;
- (void)onTick:(CADisplayLink*)link;
@end

@implementation CommunityDisplayClock
- (void)onTick:(CADisplayLink*)link {
  const CFTimeInterval step = 1.0 / self.renderCap;
  if (self.nextFrame == 0 || link.timestamp + 0.0002 >= self.nextFrame) {
    if (self.nextFrame == 0 || link.timestamp - self.nextFrame >= step) {
      self.nextFrame = link.timestamp;
    }
    self.nextFrame += step;
    self.tickTimestamp = link.timestamp;
    self.tickReady = YES;
    if (self.waiting) {
      CFRunLoopStop(CFRunLoopGetCurrent());
    }
  }

  if (self.sampleStart == 0) {
    self.sampleStart = link.timestamp;
    return;
  }
  ++self.sampleFrames;
  CFTimeInterval elapsed = link.timestamp - self.sampleStart;
  if (elapsed >= 2.0) {
    double rate = self.sampleFrames / elapsed;
    if (std::abs(rate - self.lastLoggedRate) >= 4.0) {
      const auto rendered = std::max<NSInteger>(1, self.renderedFrames);
      NSLog(@"Ballistica iOS display callbacks: %.1f Hz, rendered %.1f FPS, "
             "preferred %.0f Hz, cap %.0f FPS, draw %.2f ms, present %.2f ms, "
             "missed logic frames %ld",
            rate, self.renderedFrames / elapsed, link.preferredFrameRateRange.preferred,
            self.renderCap, self.drawMs / rendered, self.presentMs / rendered,
            (long)self.missedFrames);
      self.lastLoggedRate = rate;
    }
    [self resetSample];
    self.sampleStart = link.timestamp;
  }
}

- (void)resetSample {
  self.sampleStart = 0;
  self.sampleFrames = 0;
  self.renderedFrames = 0;
  self.missedFrames = 0;
  self.drawMs = 0;
  self.presentMs = 0;
}
@end

namespace ballistica::base {
namespace {
CommunityDisplayClock* clock;
}  // namespace

auto WaitForIOSDisplayTick(SDL_Window* window, int max_fps, bool visible) -> bool {
  @autoreleasepool {
    if (clock == nil) {
      clock = [[CommunityDisplayClock alloc] init];
      clock.link = [CADisplayLink displayLinkWithTarget:clock selector:@selector(onTick:)];
      [clock.link addToRunLoop:NSRunLoop.mainRunLoop forMode:NSRunLoopCommonModes];
    }

    UIWindow* ui_window = (__bridge UIWindow*)SDL_GetPointerProperty(
        SDL_GetWindowProperties(window), SDL_PROP_WINDOW_UIKIT_WINDOW_POINTER, nullptr);
    UIScreen* screen = ui_window.windowScene.screen ?: ui_window.screen;
    NSInteger screen_max = screen ? screen.maximumFramesPerSecond : 60;
    const float cap = max_fps == -1 ? screen_max : std::min<NSInteger>(screen_max, max_fps);
    // ProMotion offers 80 and 120 Hz, with no 110 Hz mode. Request the
    // top mode above 80 and pace custom caps against its timestamps.
    const float requested = cap > 80.0f ? screen_max : cap;
    if (clock.renderCap != cap || clock.link.preferredFrameRateRange.preferred != requested) {
      clock.link.preferredFrameRateRange =
          CAFrameRateRangeMake(std::min(80.0f, requested), requested, requested);
      clock.renderCap = cap;
      clock.nextFrame = 0;
      clock.tickReady = NO;
      [clock resetSample];
      clock.lastLoggedRate = 0;
      NSLog(@"Ballistica iOS display preference: %.0f Hz, screen maximum %ld Hz, low power %@",
            requested, (long)screen_max,
            NSProcessInfo.processInfo.lowPowerModeEnabled ? @"on" : @"off");
    }

    if (clock.link.paused == visible) {
      clock.link.paused = !visible;
    }
    if (!visible) {
      clock.tickReady = NO;
      clock.nextFrame = 0;
      [clock resetSample];
    }

    if (!clock.tickReady) {
      // SDL events still need processing between ticks and in the background.
      // Only the display-link callback marks a frame ready.
      clock.waiting = YES;
      CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.1, true);
      clock.waiting = NO;
    }
    bool ready = clock.tickReady && visible;
    clock.tickReady = NO;
    return ready;
  }
}

auto IOSDisplayWantsHighRefresh() -> bool {
  return clock.renderCap > 60.0f;
}

auto IOSDisplayTimeSeconds() -> double {
  const double now = core::g_core->AppTimeSeconds();
  if (clock == nil || clock.tickTimestamp == 0) return now;
  // CADisplayLink timestamps and CACurrentMediaTime share a clock. Convert
  // their difference instead of assuming app-time has the same epoch.
  return now - (CACurrentMediaTime() - clock.tickTimestamp);
}

void RecordIOSFrame(bool rendered, double draw_ms, double present_ms) {
  if (rendered) {
    ++clock.renderedFrames;
    clock.drawMs += draw_ms;
    clock.presentMs += present_ms;
  } else {
    ++clock.missedFrames;
  }
}

void StopIOSDisplayClock() {
  [clock.link invalidate];
  clock = nil;
}
}  // namespace ballistica::base
