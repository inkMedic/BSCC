// Released under the MIT License. See LICENSE for details.
#ifndef BALLISTICA_COMMUNITY_IOS_METAL_PRESENTER_H_
#define BALLISTICA_COMMUNITY_IOS_METAL_PRESENTER_H_

struct SDL_Window;

namespace ballistica::base {

// Present an OpenGL frame through Metal when enabled.
// The SDL window's color renderbuffer must already be bound. Returns false
// when the caller should use SDL's standard OpenGL presentation instead.
auto TryPresentIOSMetalFrame(SDL_Window* window, bool use_metal) -> bool;
void StopIOSMetalPresenter();

}  // namespace ballistica::base
#endif
