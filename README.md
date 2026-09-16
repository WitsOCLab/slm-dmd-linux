# slm-dmd-linux

Drive spatial light modulators and digital micromirror devices as displays on Linux — X11 and
Wayland — the way a laboratory actually needs to: find the panel by what it is, put a pattern on
it pixel for pixel, and know which vertical sync it went up on.

## The problem it solves

An SLM or DMD on HDMI/DisplayPort is a monitor to the operating system. Every existing Python
approach (slmPy, python-SLM, slmsuite's `ScreenMirrored`) opens a fullscreen window on "screen
number 2". That breaks the moment a cable moves, a driver renumbers outputs, or the desktop is
Wayland — where an application cannot choose which output its window lands on and the
compositor may quietly scale or colour-manage it. None of them tell you *when* the pattern was
actually on the panel, which is what a camera exposure has to be timed from.

```
pip install slm-dmd-linux
```
```python
from slmscreen import Display, find_output, patterns
```

## What it does

- identifies outputs by the monitor name and serial in their EDID, read from the kernel
  (`/sys/class/drm`) under Wayland and from `xrandr` under X11 — the same panel is found regardless
  of port, plugging order or driver naming
- one process per device holding a fullscreen OpenGL window on that output, vsynced to it
- `show()` returns after the buffer swap at vblank, with a timestamp: settle a known time, then trigger the camera
- checks that defeat silent corruption: compositor scale must be 1, gamma 1:1:1, brightness 1
- an idle image so a driven panel is never mistaken for a dead one
- pattern generators in numpy: blazed and binary gratings, Laguerre–Gauss / OAM holograms, Lee
  amplitude holograms, crosshairs, discs, checkerboards, ordered dithering for binary devices
- a simulator with the same interface for tests without hardware

Verified with a HOLOEYE PLUTO-2.1 (phase SLM) and a TI DLP4710 EVM (binary DMD) on the NVIDIA
driver under both GNOME/Xorg and COSMIC/Wayland.

## Requirements

Python ≥ 3.10, numpy, scipy, glfw (GLFW ≥ 3.4 for Wayland), PyOpenGL. A GPU driver in KMS mode
(NVIDIA: `nvidia-drm.modeset=1`). Under Wayland the session's own screen locking, idle blanking
and night light must be off on the modulator outputs; the checks tell you when they are not.

## Status

Extracted from a working laboratory rig (Wits OCLab). The API is the rig's; it will settle over
the first releases. Other modulators that appear as displays should work unchanged — reports welcome.
