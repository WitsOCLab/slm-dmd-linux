# slm-dmd-linux

Spatial light modulators and DMDs that connect over HDMI or DisplayPort, driven from Python on Linux. Finds the device by the name in its EDID, opens a fullscreen window on that output with no scaling, and tells you the vertical sync each pattern went up on. X11 and Wayland.

## Creator

**Warwick Brown**  
_School of Electrical and Information Engineering, University of the Witwatersrand, Johannesburg, South Africa_  
Email: [warwickb10@gmail.com](mailto:warwickb10@gmail.com)  
Homepage: [https://www.wits.ac.za/oclab](https://www.wits.ac.za/oclab)

If you use this in published work, please cite the repository (see CITATION.cff) or acknowledge the Wits OC Lab. Pull requests are welcome.

## Why not "the second monitor"

An SLM on HDMI is a monitor to the operating system. The usual approach, slmPy and others, opens a fullscreen window on screen 2. That stops working when a cable moves, a driver renumbers outputs, or the desktop is Wayland, where a program cannot pick the screen its window goes to and the compositor may scale it. It also never tells you when the pattern was actually on the panel, which is what a camera exposure has to be timed from. This package identifies the panel by its EDID, so the same config works after any replugging, and `show()` returns after the buffer swap with a timestamp.

Verified with a HOLOEYE PLUTO-2.1 (phase SLM) and a Texas Instruments DLP4710 EVM (binary DMD; see the lab's [DLP4710-SLM](https://github.com/WitsOCLab/DLP4710-SLM) for the mount) on the NVIDIA driver, under GNOME on Xorg and under COSMIC on Wayland.

## Install

```
pip install slm-dmd-linux                # or, before the PyPI release: pip install git+https://github.com/WitsOCLab/slm-dmd-linux
slmscreen list                          # the connected outputs and their EDID names
slmscreen show "HE PLUTO-2.1" blazed period_px=16 angle_deg=45
```

Needs GLFW 3.4 or newer (`sudo apt install libglfw3`) and a GPU driver in KMS mode; on NVIDIA that is `nvidia-drm.modeset=1` on the kernel command line. Turn off screen locking, idle blanking and night light for the session that drives the panel; `slmscreen list` warns if an output is scaled.

## From Python

```python
from slmscreen import Display, find_output, patterns

output = find_output(edid_name="HE PLUTO-2.1")
with Display("slm", output) as slm:
    frame = patterns.render("blazed", output.width, output.height, period_px=16, angle_deg=45)
    info = slm.show(frame)               # returns after the vsync it went up on: info["t_flip"]
    # settle, then trigger the camera
```

`frame` is any uint8 array of the panel's size: your own hologram, or one of the generators in `slmscreen.patterns` (blazed and binary gratings, Laguerre-Gauss and Lee holograms, crosshair, disc, checkerboard). For a DMD, `patterns.bayer()` gives an ordered-dither matrix to binarise a grey image. `SimDisplay` has the same interface and no window, for tests.

## From MATLAB

```matlab
pyenv(Version="/usr/bin/python3");
out = py.slmscreen.find_output(pyargs('edid_name', 'HE PLUTO-2.1'));
slm = py.slmscreen.Display('slm', out);
holo = uint8(mod((1:1920) * 16, 256)) .* ones(1080, 1, 'uint8');   % your hologram, 1080x1920 uint8
info = slm.show(py.numpy.array(holo));                               % MATLAB matrix to the panel
pause(0.05);                                                         % settle, then grab
slm.close();
```

`matlab/show_hologram.m` is a working script. Tested with R2026a.

## Command line

| Command | Does |
|---|---|
| `slmscreen list` | outputs, EDID names, geometry, scale |
| `slmscreen show <output> <pattern> k=v ...` | hold a pattern until Ctrl-C |
| `slmscreen show DP-6 hologram.npy --seconds 5` | your own array from a file |

## Troubleshooting

* `no connected output matches`: run `slmscreen list`; the EDID name is exactly what it prints. Two identical panels: add `edid_serial`.
* Output listed with `scale 1.5x`: set that display to 100 % in the desktop's display settings, or every pattern is resampled.
* Under X11 the pattern looks wrong in intensity: `xrandr --output DP-6 --gamma 1:1:1 --brightness 1`, and turn off night light.
* NVIDIA, after a driver update: reboot before the window can be created.

## Disclaimer

Not affiliated with or endorsed by HOLOEYE Photonics or Texas Instruments. "HOLOEYE", "PLUTO" and "DLP" are trademarks of their owners, used here only to say which devices this was tested with. The devices are driven as ordinary displays; no vendor software is used or included.

## License

MIT. Copyright (c) 2026 Wits OC Lab. See LICENSE.

## Acknowledgements

Written for the OC Lab optical computing rig. The DMD mount is Mitchell Cox's DLP4710-SLM.
