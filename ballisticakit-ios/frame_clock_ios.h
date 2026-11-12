// Released under the MIT License. See LICENSE for details.
#ifndef BALLISTICA_COMMUNITY_IOS_FRAME_CLOCK_H_
#define BALLISTICA_COMMUNITY_IOS_FRAME_CLOCK_H_

struct SDL_Window;

namespace ballistica::base {

// Run UIKit until the next display tick or until an event needs servicing.
// Only call on the app's main thread.
auto WaitForIOSDisplayTick(SDL_Window* window, int max_fps, bool visible)
    -> bool;
auto IOSDisplayWantsHighRefresh() -> bool;
// Latest accepted display tick in the engine's app-time domain. Main thread only.
auto IOSDisplayTimeSeconds() -> double;
void RecordIOSFrame(bool rendered, double draw_ms, double present_ms);
void StopIOSDisplayClock();

}  // namespace ballistica::base
#endif
