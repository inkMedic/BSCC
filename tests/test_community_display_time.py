# Released under the MIT License. See LICENSE for details.

"""Run timing regressions against the native display-time clock on the host."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class DisplayTimeTest(unittest.TestCase):
    def test_display_tick_timing(self):
        compiler = shutil.which('clang++') or shutil.which('c++')
        if compiler is None:
            self.skipTest('A C++ compiler is required')
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'display_time_test.cc'
            binary = Path(directory) / 'display_time_test'
            source.write_text(r'''
#include <cassert>
#include <cmath>
#include "ballistica/base/support/display_time_clock.h"

void Near(double actual, double expected) {
  assert(std::abs(actual - expected) < 1e-9);
}

int main() {
  ballistica::base::DisplayTimeClock clock;
  double timestamp = 100.0;
  Near(clock.Step(timestamp), 0.0);
  double total = 0.0;
  // Changes in ProMotion refresh rate must immediately change the step,
  // without a moving-average tail or a lasting speed error.
  for (double hz : {120.0, 80.0, 60.0, 120.0, 110.0}) {
    for (int frame = 0; frame < 300; ++frame) {
      timestamp += 1.0 / hz;
      const double elapsed = clock.Step(timestamp);
      Near(elapsed, 1.0 / hz);
      total += elapsed;
    }
  }
  Near(total, timestamp - 100.0);

  // Missing a logic frame accounts for both ticks once, then immediately
  // returns to the normal interval. Uneven caps also conserve elapsed time.
  for (int ticks : {1, 2, 1, 1, 3, 1, 2, 1}) {
    timestamp += ticks / 120.0;
    Near(clock.Step(timestamp), ticks / 120.0);
  }

  // Long stalls are bounded and do not create subsequent catch-up frames.
  timestamp += 10.0;
  Near(clock.Step(timestamp), 0.25);
  timestamp += 1.0 / 120.0;
  Near(clock.Step(timestamp), 1.0 / 120.0);
  Near(clock.Step(timestamp - 0.1), 0.0);
  Near(clock.Step(timestamp), 0.0);

  // Resuming does not advance the game by the time spent suspended.
  clock.Reset();
  timestamp += 30.0;
  Near(clock.Step(timestamp), 0.0);
  timestamp += 1.0 / 60.0;
  Near(clock.Step(timestamp), 1.0 / 60.0);
}
''')
            subprocess.run(
                [compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
                 '-I', str(root / 'src'), str(source), '-o', str(binary)],
                check=True,
            )
            subprocess.run([str(binary)], check=True)


if __name__ == '__main__':
    unittest.main()
