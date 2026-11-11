// Released under the MIT License. See LICENSE for details.
#include "metal_presenter_ios.h"

#import <IOSurface/IOSurfaceRef.h>
#import <Metal/Metal.h>
#import <OpenGLES/EAGLIOSurface.h>
#import <OpenGLES/ES3/gl.h>
#import <OpenGLES/ES3/glext.h>
#import <QuartzCore/CAMetalLayer.h>
#include <SDL3/SDL_video.h>
#import <UIKit/UIKit.h>

#include <array>
#include <cstdlib>
#include <mutex>

namespace ballistica::base {
namespace {

struct SharedFrame {
  GLuint texture{};
  GLuint framebuffer{};
  id<MTLTexture> metal_texture;
  id<MTLCommandBuffer> command;
};

// GL finishes writing a frame before Metal reads it. Keep three shared
// surfaces so an in-flight Metal copy never stalls the next GL write.
std::array<SharedFrame, 3> frames;
CAMetalLayer* layer;
id<MTLCommandQueue> queue;
EAGLContext* gl_context;
__weak UIView* configured_view;
int width;
int height;

void Reset() {
  [layer removeFromSuperlayer];
  layer = nil;
  queue = nil;
  for (auto& frame : frames) {
    if (gl_context && EAGLContext.currentContext == gl_context) {
      glDeleteFramebuffers(1, &frame.framebuffer);
      glDeleteTextures(1, &frame.texture);
    }
    frame = {};
  }
  gl_context = nil;
  configured_view = nil;
}

// Keep the failed configuration cached so we can fall back to SDL without
// retrying allocation every frame. A resize or a new context retries it.
void DisableForView(UIView* view) {
  Reset();
  gl_context = EAGLContext.currentContext;
  configured_view = view;
}

void Configure(UIView* view, int w, int h) {
  Reset();
  gl_context = EAGLContext.currentContext;
  configured_view = view;
  width = w;
  height = h;
  if (!gl_context || !view || w <= 0 || h <= 0) return;
  auto device = MTLCreateSystemDefaultDevice();
  auto command_queue = [device newCommandQueue];
  if (!command_queue) return;

  GLint texture, read, draw;
  glGetIntegerv(GL_TEXTURE_BINDING_2D, &texture);
  glGetIntegerv(GL_READ_FRAMEBUFFER_BINDING, &read);
  glGetIntegerv(GL_DRAW_FRAMEBUFFER_BINDING, &draw);
  bool ok = true;
  for (auto& frame : frames) {
    auto surface = IOSurfaceCreate((__bridge CFDictionaryRef)@{
      (__bridge NSString*)kIOSurfaceWidth : @(w),
      (__bridge NSString*)kIOSurfaceHeight : @(h),
      (__bridge NSString*)kIOSurfaceBytesPerElement : @4,
      (__bridge NSString*)kIOSurfacePixelFormat : @0x42475241,  // BGRA
    });
    if (!surface) {
      ok = false;
      break;
    }
    auto descriptor = [MTLTextureDescriptor
        texture2DDescriptorWithPixelFormat:MTLPixelFormatBGRA8Unorm
                                     width:w
                                    height:h
                                 mipmapped:NO];
    descriptor.storageMode = MTLStorageModeShared;
    frame.metal_texture = [device newTextureWithDescriptor:descriptor iosurface:surface plane:0];
    glGenTextures(1, &frame.texture);
    glBindTexture(GL_TEXTURE_2D, frame.texture);
    const BOOL attached = [gl_context texImageIOSurface:surface
                                                target:GL_TEXTURE_2D
                                        internalFormat:GL_RGBA
                                                 width:w
                                                height:h
                                                format:GL_BGRA_EXT
                                                  type:GL_UNSIGNED_BYTE
                                                 plane:0];
    CFRelease(surface);
    glGenFramebuffers(1, &frame.framebuffer);
    glBindFramebuffer(GL_DRAW_FRAMEBUFFER, frame.framebuffer);
    glFramebufferTexture2D(GL_DRAW_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
                           GL_TEXTURE_2D, frame.texture, 0);
    if (!attached || !frame.metal_texture ||
        glCheckFramebufferStatus(GL_DRAW_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE) {
      NSLog(@"Cannot share an iOS game frame with Metal (GL attach %d, texture %@, error %x)",
            attached, frame.metal_texture, glGetError());
      ok = false;
      break;
    }
  }
  glBindTexture(GL_TEXTURE_2D, texture);
  glBindFramebuffer(GL_READ_FRAMEBUFFER, read);
  glBindFramebuffer(GL_DRAW_FRAMEBUFFER, draw);
  if (!ok) {
    DisableForView(view);
    return;
  }

  layer = [CAMetalLayer layer];
  layer.device = device;
  layer.pixelFormat = MTLPixelFormatBGRA8Unorm;
  layer.opaque = YES;
  layer.framebufferOnly = NO;  // The drawable is a Metal blit destination.
  layer.drawableSize = CGSizeMake(w, h);
  layer.frame = view.bounds;
  [view.layer addSublayer:layer];
  queue = command_queue;
}

void CountPresented(id<MTLDrawable> drawable) {
  static std::mutex mutex;
  static double first;
  static int count;
  const double now = drawable.presentedTime;
  if (now == 0) return;
  std::lock_guard lock(mutex);
  if (first == 0) first = now;
  ++count;
  if (now - first >= 2.0) {
    NSLog(@"Ballistica Metal actual presentation: %.1f FPS", (count - 1) / (now - first));
    count = 1;
    first = now;
  }
}
}  // namespace

void StopIOSMetalPresenter() {
  if (gl_context || layer) Reset();
}

auto TryPresentIOSMetalFrame(SDL_Window* window, bool use_metal) -> bool {
  if (!use_metal) {
    StopIOSMetalPresenter();
    return false;
  }
  @autoreleasepool {
    auto properties = SDL_GetWindowProperties(window);
    const auto source = SDL_GetNumberProperty(
        properties, SDL_PROP_WINDOW_UIKIT_OPENGL_FRAMEBUFFER_NUMBER, 0);
    if (!source) {
      StopIOSMetalPresenter();
      return false;
    }
    int w = 0;
    int h = 0;
    glGetRenderbufferParameteriv(GL_RENDERBUFFER, GL_RENDERBUFFER_WIDTH, &w);
    glGetRenderbufferParameteriv(GL_RENDERBUFFER, GL_RENDERBUFFER_HEIGHT, &h);
    UIWindow* ui_window = (__bridge UIWindow*)SDL_GetPointerProperty(
        properties, SDL_PROP_WINDOW_UIKIT_WINDOW_POINTER, nullptr);
    auto view = ui_window.rootViewController.view;
    if (configured_view != view || width != w || height != h ||
        gl_context != EAGLContext.currentContext) {
      Configure(view, w, h);
    }
    if (!layer) return false;
    if (!CGRectEqualToRect(layer.frame, view.bounds)) {
      [CATransaction begin];
      [CATransaction setDisableActions:YES];
      layer.frame = view.bounds;
      [CATransaction commit];
    }
    SharedFrame* free_frame = nullptr;
    for (auto& frame : frames) {
      const auto status = frame.command.status;
      if (status == MTLCommandBufferStatusError) {
        NSLog(@"iOS Metal presentation failed: %@", frame.command.error);
        DisableForView(view);
        return false;
      }
      if (!frame.command || status == MTLCommandBufferStatusCompleted) {
        free_frame = &frame;
        break;
      }
    }
    if (!free_frame) return true;
    id<CAMetalDrawable> drawable = [layer nextDrawable];
    if (!drawable) {
      DisableForView(view);
      return false;
    }
    GLint read, draw;
    glGetIntegerv(GL_READ_FRAMEBUFFER_BINDING, &read);
    glGetIntegerv(GL_DRAW_FRAMEBUFFER_BINDING, &draw);
    const bool scissor = glIsEnabled(GL_SCISSOR_TEST);
    if (scissor) glDisable(GL_SCISSOR_TEST);
    glBindFramebuffer(GL_READ_FRAMEBUFFER, static_cast<GLuint>(source));
    glBindFramebuffer(GL_DRAW_FRAMEBUFFER, free_frame->framebuffer);
    // Flip Y from OpenGL's bottom-left origin to Metal's top-left origin.
    glBlitFramebuffer(0, 0, w, h, 0, h, w, 0, GL_COLOR_BUFFER_BIT, GL_NEAREST);
    glBindFramebuffer(GL_READ_FRAMEBUFFER, read);
    glBindFramebuffer(GL_DRAW_FRAMEBUFFER, draw);
    if (scissor) glEnable(GL_SCISSOR_TEST);
    glFinish();  // Make the OpenGL writes visible before Metal reads them.

    auto command = [queue commandBuffer];
    auto blit = [command blitCommandEncoder];
    if (!blit) {
      DisableForView(view);
      return false;
    }
    [blit copyFromTexture:free_frame->metal_texture toTexture:drawable.texture];
    [blit endEncoding];
    static const bool log_presentation = getenv("BA_IOS_LOG_PRESENTATION") != nullptr;
    if (log_presentation) {
      [drawable addPresentedHandler:^(id<MTLDrawable> value) {
        CountPresented(value);
      }];
    }
    [command presentDrawable:drawable];
    [command commit];
    free_frame->command = command;
    return true;
  }
}
}  // namespace ballistica::base
