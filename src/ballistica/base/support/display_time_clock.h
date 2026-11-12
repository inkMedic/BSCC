// Released under the MIT License. See LICENSE for details.

#ifndef BALLISTICA_BASE_SUPPORT_DISPLAY_TIME_CLOCK_H_
#define BALLISTICA_BASE_SUPPORT_DISPLAY_TIME_CLOCK_H_

#include <algorithm>

namespace ballistica::base {

// For display-link-driven rendering, use elapsed display time rather than
// estimating a frame rate. Rate smoothing can turn dropped ticks and refresh
// rate changes into prolonged simulation slowdowns/speedups.
class DisplayTimeClock {
 public:
  auto Step(double timestamp) -> double {
    if (last_timestamp_ < 0.0) {
      last_timestamp_ = timestamp;
      return 0.0;
    }
    const double elapsed = std::max(0.0, timestamp - last_timestamp_);
    last_timestamp_ = std::max(last_timestamp_, timestamp);
    // Consume long gaps without building up a catch-up backlog.
    return std::min(elapsed, 0.25);
  }

  void Reset() { last_timestamp_ = -1.0; }

 private:
  double last_timestamp_{-1.0};
};

}  // namespace ballistica::base

#endif  // BALLISTICA_BASE_SUPPORT_DISPLAY_TIME_CLOCK_H_
