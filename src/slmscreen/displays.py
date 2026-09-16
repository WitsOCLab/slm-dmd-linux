"""SLM and DMD outputs.

Each device is found by the monitor name in its EDID, which stays the same across ports, plugging
order and reboots (unlike "screen 2/3"). It is driven by its own process holding a fullscreen
OpenGL window vsynced to that connector. `show` returns after the buffer swap at vblank, with a
timestamp, so a camera exposure can start a known settle time after the pattern is really up.

Two session types are supported and picked automatically:
- X11: outputs from `xrandr --verbose` (EDID included), GLFW's X11 backend.
- Wayland, any compositor: the EDID of every connected connector is read from the kernel at
  /sys/class/drm/<card>-<connector>/edid, and GLFW's Wayland backend reports the same connector
  names with the geometry, so nothing compositor-specific is needed. `cosmic-randr` remains as a
  fallback for a driver that exposes no EDID in sysfs. The compositor places fullscreen windows
  on the requested wl_output.
"""

from __future__ import annotations

import glob
import json
import multiprocessing as mp
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Output:
    connector: str             # xrandr output name, e.g. "DP-5"
    edid_name: str | None      # EDID monitor name, e.g. "HE PLUTO-2.1"
    edid_serial: int | None
    width: int
    height: int
    x: int
    y: int
    primary: bool
    gamma: str | None          # must be 1.0:1.0:1.0 for phase-accurate output
    brightness: float | None
    scale: float = 1.0         # compositor scale; anything but 1 resamples every pattern


def _edid_fields(edid: bytes) -> tuple[str | None, int | None]:
    if len(edid) < 128:
        return None, None
    name = None
    for i in range(54, 126, 18):  # the four descriptor blocks
        block = edid[i:i + 18]
        if block[:3] == b"\0\0\0" and block[3] == 0xFC:
            name = block[5:].split(b"\n")[0].decode(errors="replace").strip()
    return name, int.from_bytes(edid[12:16], "little")


def session_is_wayland() -> bool:
    return bool(os.environ.get("WAYLAND_DISPLAY")) and os.environ.get("XDG_SESSION_TYPE", "wayland") != "x11"


def list_outputs() -> list[Output]:
    """Connected, active outputs of the current session."""
    if not session_is_wayland():
        return _list_outputs_x11()
    try:
        outputs = _list_outputs_drm()
    except Exception:  # noqa: BLE001  (no sysfs EDID, no GLFW: try the compositor's own tool)
        outputs = []
    if any(o.edid_name for o in outputs):
        return outputs
    return _list_outputs_wayland()


def _drm_edids() -> dict[str, bytes]:
    """EDID of every connected DRM connector, keyed by connector name ("DP-6"), from sysfs.
    Readable by any user in any session; stat reports the attribute as 0 bytes but the read
    returns the block."""
    edids = {}
    for path in glob.glob("/sys/class/drm/card*-*/edid"):
        connector_dir = os.path.dirname(path)
        try:
            with open(os.path.join(connector_dir, "status")) as f:
                if f.read().strip() != "connected":
                    continue
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            continue
        if len(data) >= 128:
            edids[os.path.basename(connector_dir).split("-", 1)[1]] = data
    return edids


_PROBE = """
import glfw, json
if not glfw.init():
    raise SystemExit("glfw init failed")
monitors = []
for m in glfw.get_monitors():
    mode = glfw.get_video_mode(m)
    x, y = glfw.get_monitor_pos(m)
    sx, sy = glfw.get_monitor_content_scale(m)
    monitors.append({"name": glfw.get_monitor_name(m).decode(), "width": mode.size.width,
                     "height": mode.size.height, "x": x, "y": y, "scale": float(sx)})
glfw.terminate()
print(json.dumps(monitors))
"""


def _glfw_monitors() -> list[dict]:
    """Connector name and geometry of each monitor, from GLFW in a fresh process: the daemon
    itself must not initialise GLFW, because its display workers do that after a fork."""
    out = subprocess.run([sys.executable, "-c", _PROBE], capture_output=True, text=True, timeout=15, check=True).stdout
    return json.loads(out)


def _list_outputs_drm() -> list[Output]:
    edids = _drm_edids()
    outputs = []
    for i, m in enumerate(_glfw_monitors()):
        name, serial = _edid_fields(edids.get(m["name"], b""))
        outputs.append(Output(connector=m["name"], edid_name=name, edid_serial=serial,
                              width=m["width"], height=m["height"], x=m["x"], y=m["y"],
                              primary=(i == 0), gamma=None, brightness=None, scale=m.get("scale", 1.0)))
    return outputs


def _list_outputs_wayland() -> list[Output]:
    """Parse `cosmic-randr list`. Wayland has no EDID access, so the compositor's make + model
    string stands in for the EDID monitor name (it is derived from the same descriptor)."""
    try:
        text = subprocess.run(["cosmic-randr", "list"], capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError) as e:
        raise RuntimeError(f"cosmic-randr list failed ({e}); is this a COSMIC session?") from None
    text = re.sub(r"\x1b\[[0-9;]*m", "", text)  # cosmic-randr colours its output even when piped
    outputs = []
    for block in re.split(r"\n(?=\S)", text.strip()):
        head, *body = block.splitlines()
        name = head.split()[0].strip('"')
        fields = {}
        for line in body:
            if ":" in line:
                k, v = line.split(":", 1)
                fields[k.strip().lower()] = v.strip()
        if "disabled" in head.lower() or fields.get("enabled", "").lower() in ("false", "no"):
            continue
        model = fields.get("model") or (re.search(r'"([^"]+)"', head) or [None, None])[1]
        pos = re.search(r"(-?\d+)\s*[,x]\s*(-?\d+)", fields.get("position", "0,0"))
        mode = re.search(r"(\d+)\s*x\s*(\d+)", " ".join(l for l in body if "current" in l.lower()) or fields.get("mode", "")
                         or fields.get("resolution", ""))
        if not mode:
            continue
        outputs.append(Output(connector=name, edid_name=(model or "").strip() or None, edid_serial=None,
                              width=int(mode.group(1)), height=int(mode.group(2)),
                              x=int(pos.group(1)) if pos else 0, y=int(pos.group(2)) if pos else 0,
                              primary=False, gamma=None, brightness=None))
    return outputs


def _list_outputs_x11() -> list[Output]:
    text = subprocess.run(["xrandr", "--verbose"], capture_output=True, text=True, check=True).stdout
    outputs = []
    for block in re.split(r"\n(?=\S)", text):
        m = re.match(r"(\S+) connected (primary )?(\d+)x(\d+)\+(\d+)\+(\d+)", block)
        if not m:
            continue
        edid = re.search(r"EDID:[ \t]*\n((?:[ \t]+[0-9a-f]+\n)+)", block)
        name, serial = _edid_fields(bytes.fromhex("".join(edid.group(1).split()))) if edid else (None, None)
        gamma = re.search(r"Gamma:\s*(\S+)", block)
        brightness = re.search(r"Brightness:\s*(\S+)", block)
        outputs.append(Output(
            connector=m.group(1), edid_name=name, edid_serial=serial,
            width=int(m.group(3)), height=int(m.group(4)), x=int(m.group(5)), y=int(m.group(6)),
            primary=bool(m.group(2)),
            gamma=gamma.group(1) if gamma else None,
            brightness=float(brightness.group(1)) if brightness else None,
        ))
    return outputs


def find_output(edid_name: str | None = None, connector: str | None = None,
                edid_serial: int | None = None) -> Output:
    """Match by EDID name (plus serial or connector to tell identical models apart), else by connector."""
    outputs = list_outputs()
    if edid_name:
        # Under Wayland the compositor reports "<make> <model>", e.g. "HOLOEYE HE PLUTO-2.1".
        matches = [o for o in outputs if o.edid_name == edid_name or (o.edid_name or "").endswith(" " + edid_name)]
        if edid_serial is not None:
            matches = [o for o in matches if o.edid_serial == edid_serial]
        if len(matches) > 1 and connector:
            matches = [o for o in matches if o.connector == connector]
    else:
        matches = [o for o in outputs if connector and o.connector == connector]
    if len(matches) == 1:
        return matches[0]
    connected = ", ".join(f"{o.connector}={o.edid_name!r}" for o in outputs) or "none"
    if len(matches) > 1:
        raise LookupError(f"several outputs match EDID name {edid_name!r} ({connected}); "
                          "add edid_serial or connector to the config")
    raise LookupError(f"no connected output matches edid_name={edid_name!r} connector={connector!r} "
                      f"(connected: {connected})")


# The window's app id: a compositor matches it to a .desktop file of the same name, which is
# what gives the fullscreen output a name and an icon in a dock. Callers pass their own.
WINDOW_APP_ID = "slmscreen.Display"


class Display:
    """Daemon-side handle to one display worker process."""

    def __init__(self, role: str, output: Output, start_timeout_s: float = 20.0, app_id: str = WINDOW_APP_ID):
        self.role, self.output = role, output
        ctx = mp.get_context("spawn")
        self._conn, child = ctx.Pipe()
        self._proc = ctx.Process(target=_worker, args=(child, output, app_id), name=f"display-{role}", daemon=True)
        self._proc.start()
        child.close()
        self.info = self._reply(start_timeout_s)

    def show(self, image: np.ndarray | None = None, key: str | None = None) -> dict:
        return self._call("show", image=image, key=key)

    def upload(self, key: str, image: np.ndarray) -> dict:
        return self._call("upload", key=key, image=image)

    def forget(self, key: str | None = None) -> dict:
        return self._call("forget", key=key)

    def __enter__(self) -> "Display":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def close(self) -> None:
        if self._proc.is_alive():
            try:
                self._call("close", timeout_s=3.0)
            except Exception:  # noqa: BLE001  (best effort; terminated below)
                pass
            self._proc.join(3.0)
        if self._proc.is_alive():
            self._proc.terminate()

    def _call(self, cmd: str, timeout_s: float = 10.0, **kwargs):
        self._conn.send((cmd, kwargs))
        return self._reply(timeout_s)

    def _reply(self, timeout_s: float):
        if not self._conn.poll(timeout_s):
            self._proc.terminate()  # a late reply would desynchronise the pipe
            raise TimeoutError(f"{self.role}: display worker did not answer within {timeout_s:.0f} s")
        try:
            status, value = self._conn.recv()
        except EOFError:
            raise RuntimeError(f"{self.role}: display worker exited (code {self._proc.exitcode})") from None
        if status != "ok":
            raise RuntimeError(f"{self.role}: {value}")
        return value


_WORKER_COMMANDS = {"show", "upload", "forget"}


def _worker(conn, output: Output, app_id: str = WINDOW_APP_ID) -> None:
    # Read by the NVIDIA GL library at load time, so set before importing glfw/OpenGL.
    os.environ["__GL_SYNC_TO_VBLANK"] = "1"
    os.environ["__GL_SYNC_DISPLAY_DEVICE"] = output.connector
    os.environ["__GL_MaxFramesAllowed"] = "1"
    # The glfw wheel ships an X11 and a Wayland build; pick before it is imported.
    os.environ["PYGLFW_LIBRARY_VARIANT"] = "wayland" if session_is_wayland() else "x11"
    try:
        window = _Window(output)
    except Exception as e:  # noqa: BLE001  (reported to the daemon)
        conn.send(("error", f"cannot open a window on {output.connector}: {e}"))
        return
    conn.send(("ok", window.describe()))
    try:
        while True:
            if conn.poll(0.02):
                try:
                    cmd, kwargs = conn.recv()
                except EOFError:
                    break
                if cmd == "close":
                    conn.send(("ok", None))
                    break
                try:
                    if cmd not in _WORKER_COMMANDS:
                        raise ValueError(f"unknown display command {cmd!r}")
                    conn.send(("ok", getattr(window, cmd)(**kwargs)))
                except Exception as e:  # noqa: BLE001  (reported to the daemon)
                    conn.send(("error", f"{type(e).__name__}: {e}"))
            window.poll()
    except KeyboardInterrupt:
        pass
    finally:
        window.close()


class _Window:
    """Fullscreen, cursorless, never-iconifying GL window showing uint8 images pixel-for-pixel."""

    def __init__(self, output: Output, app_id: str = WINDOW_APP_ID):
        import glfw
        from OpenGL import GL

        self._glfw, self._gl = glfw, GL
        self._output = output
        errors: list[str] = []
        glfw.set_error_callback(lambda _code, msg: errors.append(msg.decode(errors="replace")))
        if not glfw.init():
            raise RuntimeError(f"glfw.init failed (DISPLAY={os.environ.get('DISPLAY')!r}): {'; '.join(errors)}")
        monitors = glfw.get_monitors()
        monitor = next((m for m in monitors if glfw.get_monitor_name(m).decode() == output.connector), None)
        if monitor is None:  # Wayland compositors may report a description instead of the connector name
            monitor = next((m for m in monitors if tuple(glfw.get_monitor_pos(m)) == (output.x, output.y)), None)
        if monitor is None:
            names = [glfw.get_monitor_name(m).decode() for m in monitors]
            raise RuntimeError(f"GLFW has no monitor named {output.connector} at {output.x},{output.y} (has {names})")
        mode = glfw.get_video_mode(monitor)
        for hint in ("WAYLAND_APP_ID", "X11_CLASS_NAME"):
            if hasattr(glfw, hint):
                glfw.window_hint_string(getattr(glfw, hint), app_id)
        glfw.window_hint(glfw.AUTO_ICONIFY, False)   # stay up when focus moves to the desktop
        glfw.window_hint(glfw.FOCUSED, False)
        glfw.window_hint(glfw.FOCUS_ON_SHOW, False)
        glfw.window_hint(glfw.REFRESH_RATE, mode.refresh_rate)
        self.win = glfw.create_window(mode.size.width, mode.size.height, f"{app_id} {output.connector}", monitor, None)
        if not self.win:
            raise RuntimeError(f"could not create an OpenGL window: {'; '.join(errors) or 'unknown error'} "
                               "(after an NVIDIA driver update this means: reboot)")
        glfw.make_context_current(self.win)
        glfw.swap_interval(1)
        glfw.set_input_mode(self.win, glfw.CURSOR, glfw.CURSOR_HIDDEN)
        # The window manager applies fullscreen a moment after creation; until then GLFW reports a
        # smaller framebuffer (the desktop's panel height missing). Size everything by the video mode.
        self.width, self.height = mode.size.width, mode.size.height
        self.refresh_hz = mode.refresh_rate
        glfw.set_framebuffer_size_callback(self.win, lambda _w, fw, fh: GL.glViewport(0, 0, fw, fh))
        deadline = time.perf_counter() + 2.0
        while glfw.get_framebuffer_size(self.win) != (self.width, self.height) and time.perf_counter() < deadline:
            glfw.wait_events_timeout(0.05)
        if glfw.get_framebuffer_size(self.win) != (self.width, self.height):
            raise RuntimeError(f"window on {output.connector} is {glfw.get_framebuffer_size(self.win)}, "
                               f"not fullscreen {self.width}x{self.height} (window manager interference?)")
        self.renderer = GL.glGetString(GL.GL_RENDERER).decode()

        GL.glDisable(GL.GL_DITHER)
        GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 1)
        GL.glEnable(GL.GL_TEXTURE_2D)
        self._textures: dict[str, int] = {}
        self._scratch = self._new_texture()
        self._current = self._scratch
        self.frame = 0
        glfw.set_window_refresh_callback(self.win, lambda _win: self._draw())
        self.show(image=np.zeros((self.height, self.width), np.uint8))

    def describe(self) -> dict:
        return {"connector": self._output.connector, "edid_name": self._output.edid_name,
                "width": self.width, "height": self.height, "refresh_hz": self.refresh_hz,
                "renderer": self.renderer}

    def show(self, image=None, key=None) -> dict:
        if key is not None:
            if key not in self._textures:
                raise KeyError(f"no uploaded pattern named {key!r}")
            self._current = self._textures[key]
        elif image is not None:
            self._load(self._scratch, image)
            self._current = self._scratch
        else:
            raise ValueError("show needs an image or the key of an uploaded pattern")
        self._draw()
        self.frame += 1
        return {"frame": self.frame, "t_flip": time.perf_counter()}

    def upload(self, key: str, image) -> dict:
        self._check(image)
        tex = self._textures.get(key) or self._new_texture()
        self._load(tex, image)
        self._textures[key] = tex
        return {"key": key, "uploaded": len(self._textures)}

    def forget(self, key=None) -> dict:
        for k in list(self._textures) if key is None else [key]:
            tex = self._textures.pop(k, None)
            if tex is not None:
                if tex == self._current:
                    self._current = self._scratch
                self._gl.glDeleteTextures([tex])
        return {"uploaded": len(self._textures)}

    def poll(self) -> None:
        self._glfw.poll_events()
        if self._glfw.window_should_close(self.win):   # ignore Alt+F4 / close requests
            self._glfw.set_window_should_close(self.win, False)

    def close(self) -> None:
        self._glfw.terminate()

    def _check(self, image) -> np.ndarray:
        img = np.ascontiguousarray(image)
        if img.dtype != np.uint8:
            raise TypeError(f"images must be uint8, got {img.dtype}")
        if img.shape[:2] != (self.height, self.width) or img.ndim not in (2, 3) or (img.ndim == 3 and img.shape[2] != 3):
            raise ValueError(f"image shape {img.shape} does not fit the display: need ({self.height}, {self.width}) "
                             f"or ({self.height}, {self.width}, 3)")
        return img

    def _new_texture(self) -> int:
        GL = self._gl
        tex = int(GL.glGenTextures(1))
        GL.glBindTexture(GL.GL_TEXTURE_2D, tex)
        for param in (GL.GL_TEXTURE_MIN_FILTER, GL.GL_TEXTURE_MAG_FILTER):
            GL.glTexParameteri(GL.GL_TEXTURE_2D, param, GL.GL_NEAREST)
        for param in (GL.GL_TEXTURE_WRAP_S, GL.GL_TEXTURE_WRAP_T):
            GL.glTexParameteri(GL.GL_TEXTURE_2D, param, GL.GL_CLAMP_TO_EDGE)
        return tex

    def _load(self, tex: int, image) -> None:
        GL = self._gl
        img = self._check(image)
        fmt = GL.GL_LUMINANCE if img.ndim == 2 else GL.GL_RGB
        GL.glBindTexture(GL.GL_TEXTURE_2D, tex)
        GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, fmt, self.width, self.height, 0, fmt, GL.GL_UNSIGNED_BYTE, img)

    def _draw(self) -> None:
        GL = self._gl
        GL.glBindTexture(GL.GL_TEXTURE_2D, self._current)
        GL.glBegin(GL.GL_QUADS)
        # Texture row 0 (numpy row 0) sits at v=0, which is mapped to the top edge.
        for u, v, x, y in ((0, 1, -1, -1), (1, 1, 1, -1), (1, 0, 1, 1), (0, 0, -1, 1)):
            GL.glTexCoord2f(u, v)
            GL.glVertex2f(x, y)
        GL.glEnd()
        self._glfw.swap_buffers(self.win)  # returns at vblank (swap interval 1)
        GL.glFinish()
