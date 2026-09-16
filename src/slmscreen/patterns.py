"""Pattern generators for the SLM and DMD: plain numpy, uint8 (height, width), no hardware.

Phase patterns are built in radians, wrapped to [0, 2pi) and mapped to grey levels so that
`grey_2pi` (default 255) is one full wave: the SLM's calibrated 2pi level for the wavelength in use.
Pixel coordinates are (x, y) with (0, 0) at the top-left; `centre` defaults to (width//2, height//2),
the same origin as the lab's MATLAB PhysicalMeshGrid. All angles are degrees from the +x axis towards
+y (down the image). LG modes use the lab's exp(-i*l*phi) sign convention and the Lee threshold
cos(carrier + phi) > cos(asin(A)) from AddBinaryGrating.m, so holograms match the experiment code.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.special import genlaguerre  # scipy is a numpy dependency-neighbour; see pyproject


def _grid(width: int, height: int, centre=None):
    cx, cy = centre if centre is not None else (width // 2, height // 2)
    y, x = np.mgrid[0:height, 0:width].astype(np.float64)
    return x - cx, y - cy


def to_grey(phase: np.ndarray, grey_2pi: float = 255.0) -> np.ndarray:
    """Wrap a phase (radians) to [0, 2pi) and map to uint8 with `grey_2pi` = one wave."""
    frac = np.mod(phase, 2 * np.pi) / (2 * np.pi)
    levels = np.floor(frac * grey_2pi + 0.5 + 1e-9)   # round half up, immune to 1e-15 float noise
    levels[levels >= grey_2pi] = 0                      # exactly one wave is the same phase as zero
    return np.clip(levels, 0, 255).astype(np.uint8)


def blank(width: int, height: int, level: int = 0) -> np.ndarray:
    return np.full((height, width), int(level), np.uint8)


def crosshair(width: int, height: int, centre=None, size: int = 200, thickness: int = 3,
              rings=(50, 150), level: int = 255, background: int = 0) -> np.ndarray:
    """A cross with optional rings: for centring a beam or spotting an image on the camera."""
    x, y = _grid(width, height, centre)
    img = np.full((height, width), background, np.uint8)
    t = thickness / 2.0
    mask = ((np.abs(x) <= t) & (np.abs(y) <= size)) | ((np.abs(y) <= t) & (np.abs(x) <= size))
    r = np.hypot(x, y)
    for radius in rings or ():
        mask |= np.abs(r - radius) <= t
    img[mask] = level
    return img


def disc(width: int, height: int, radius: float, centre=None, level: int = 255, background: int = 0) -> np.ndarray:
    x, y = _grid(width, height, centre)
    img = np.full((height, width), background, np.uint8)
    img[np.hypot(x, y) <= radius] = level
    return img


def grating_phase(width: int, height: int, period_px: float, angle_deg: float = 0.0, centre=None) -> np.ndarray:
    """Linear phase ramp (radians) of a blazed grating: one 2pi wave per `period_px` along `angle_deg`."""
    if period_px <= 0:
        return np.zeros((height, width))
    x, y = _grid(width, height, centre)
    a = math.radians(angle_deg)
    return 2 * np.pi * (x * math.cos(a) + y * math.sin(a)) / period_px


def blazed_grating(width: int, height: int, period_px: float, angle_deg: float = 0.0, depth: float = 1.0,
                   grey_2pi: float = 255.0, centre=None) -> np.ndarray:
    """Sawtooth grating. `depth` scales the sawtooth height after wrapping (1 = full 2pi blaze: maximum
    first-order efficiency; lower values send more light to the zero order, useful while aligning)."""
    return to_grey(grating_phase(width, height, period_px, angle_deg, centre), grey_2pi * float(depth))


def binary_grating(width: int, height: int, period_px: float, angle_deg: float = 0.0, duty: float = 0.5,
                   centre=None) -> np.ndarray:
    """0/255 square-wave grating (a DMD's natural pattern; also fine as an SLM test target)."""
    phase = np.mod(grating_phase(width, height, period_px, angle_deg, centre), 2 * np.pi)
    return np.where(phase < 2 * np.pi * duty, 255, 0).astype(np.uint8)


def lg_field(width: int, height: int, ell: int, p: int, waist_px: float, centre=None) -> np.ndarray:
    """Complex Laguerre-Gauss LG_p^ell field at the waist, sampled on the pixel grid (unit peak)."""
    x, y = _grid(width, height, centre)
    r2 = (x * x + y * y) / (waist_px ** 2)
    phi = np.arctan2(y, x)
    rad = (np.sqrt(2 * r2)) ** abs(ell) * genlaguerre(p, abs(ell))(2 * r2) * np.exp(-r2)
    field = rad * np.exp(-1j * ell * phi)      # lab convention (LaguerreGauss.m)
    peak = np.abs(field).max()
    return field / peak if peak else field


def oam_hologram(width: int, height: int, ell: int, p: int = 0, waist_px: float = 150.0,
                 period_px: float = 16.0, angle_deg: float = 0.0, grey_2pi: float = 255.0,
                 encoding: str = "phase", centre=None) -> np.ndarray:
    """Hologram that puts LG_p^ell into the first diffraction order of a blazed grating.

    encoding="phase": phase-only (helical phase + grating), the usual cheap choice.
    encoding="amplitude": complex-amplitude encoding (Bolduc et al. 2013), which also shapes the
    amplitude by modulating the blaze depth with sinc^-1 of the normalised amplitude: cleaner modes,
    lower efficiency.
    """
    field = lg_field(width, height, ell, p, waist_px, centre)
    carrier = grating_phase(width, height, period_px, angle_deg, centre)
    if encoding == "phase":
        return to_grey(np.angle(field) + carrier, grey_2pi)
    if encoding == "amplitude":
        amp = np.abs(field)
        # depth M with sinc(1 - M) = amp  (M in [0, 1]); a fast lookup avoids solving per pixel
        m_table = np.linspace(0, 1, 2048)
        sinc_table = np.sinc(1 - m_table)                    # numpy sinc is sin(pi x)/(pi x)
        depth = np.interp(amp, sinc_table, m_table)
        phase = np.angle(field) + carrier
        return to_grey(depth * np.mod(phase - np.pi * (1 - depth), 2 * np.pi), grey_2pi)
    raise ValueError("encoding must be 'phase' or 'amplitude'")


def lee_hologram(width: int, height: int, ell: int, p: int = 0, waist_px: float = 150.0,
                 period_px: float = 8.0, angle_deg: float = 0.0, centre=None) -> np.ndarray:
    """Binary amplitude (Lee) hologram for a DMD: 1 where cos(carrier + phase) exceeds the
    threshold set by the local amplitude, so the first order carries LG_p^ell."""
    field = lg_field(width, height, ell, p, waist_px, centre)
    carrier = grating_phase(width, height, period_px, angle_deg, centre)
    amp, phase = np.abs(field), np.angle(field)
    on = np.cos(carrier + phase) - np.cos(np.arcsin(np.clip(amp, 0, 1))) > 0
    return (on * 255).astype(np.uint8)


def checkerboard(width: int, height: int, cell: int = 120) -> np.ndarray:
    yy, xx = np.indices((height, width))
    return (((xx // cell + yy // cell) % 2) * 255).astype(np.uint8)


def render(kind: str, width: int, height: int, **params) -> np.ndarray:
    """Dispatch by name, used by the CLI and the alignment window."""
    fn = PATTERNS.get(kind)
    if fn is None:
        raise ValueError(f"unknown pattern {kind!r}; choose from {sorted(PATTERNS)}")
    return fn(width, height, **params)


def experiment_presets(role: str, width: int, height: int, pitch_um: float) -> dict[str, tuple[str, dict]]:
    """Named parameter sets reproducing the OAM-Multiplexing experiment holograms (config_phase3.m)
    and the standard alignment target, converted to pixels for this display's pitch."""
    px_per_mm = 1000.0 / pitch_um
    presets = {}
    if "slm" in role.lower() or pitch_um >= 7:
        # AddBlazedGrating(mode, 8e-6, 200, 150 deg, 'none', 1, 532e-9) with refWavelength 632.8e-9:
        # Gx = 200 cos150 / (1080 px * 8 um), Gy = 200 sin150 / (1920 px * 8 um)  [the code's axis swap], x 632.8/532
        scale = 632.8 / 532.0
        gx = scale * 200 * math.cos(math.radians(150)) / (height * pitch_um * 1e-3)   # cycles per mm
        gy = scale * 200 * math.sin(math.radians(150)) / (width * pitch_um * 1e-3)
        g = math.hypot(gx, gy)
        presets["SLM experiment: LG(0,0) + blazed carrier (532 nm)"] = ("oam", {
            "ell": 0, "p": 0, "waist_px": 0.5 * px_per_mm, "period_px": px_per_mm / g,
            "angle_deg": math.degrees(math.atan2(gy, gx)), "grey_2pi": 255})
        presets["SLM: blazed carrier only"] = ("blazed", {"period_px": px_per_mm / g, "angle_deg": math.degrees(math.atan2(gy, gx)), "depth": 1.0, "grey_2pi": 255})
    else:
        # AddBinaryGrating(E, 5.4e-6, 38 lines/mm, 22.5 deg from +Y): period 1/38 mm, direction 67.5 deg from +X
        presets["DMD alignment target: LG(2,1) donut, experiment carrier"] = ("lee", {
            "ell": 2, "p": 1, "waist_px": 0.5 * px_per_mm, "period_px": px_per_mm / 38.0, "angle_deg": 90 - 22.5})
        presets["DMD experiment: LG(l,0) Lee hologram"] = ("lee", {
            "ell": 1, "p": 0, "waist_px": 0.5 * px_per_mm, "period_px": px_per_mm / 38.0, "angle_deg": 90 - 22.5})
        presets["DMD: binary carrier only"] = ("binary_grating", {"period_px": px_per_mm / 38.0, "angle_deg": 90 - 22.5, "duty": 0.5})
    presets["Crosshair with rings"] = ("crosshair", {"size": 300, "thickness": 3})
    presets["Uniform grey (level sweep = power vs level)"] = ("blank", {"level": 128})
    return presets


def fit(image: np.ndarray, width: int, height: int) -> np.ndarray:
    """Scale a picture to fit the panel, keeping its shape, centred on black."""
    h, w = image.shape
    scale = min(width / w, height / h)
    new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))
    rows = np.clip((np.arange(new_h) / scale).astype(int), 0, h - 1)
    cols = np.clip((np.arange(new_w) / scale).astype(int), 0, w - 1)
    small = image[rows][:, cols]
    out = np.zeros((height, width), image.dtype)
    r0, c0 = (height - new_h) // 2, (width - new_w) // 2
    out[r0:r0 + new_h, c0:c0 + new_w] = small
    return out


def bayer(levels: int = 3) -> np.ndarray:
    """An ordered dither matrix, so a binary device still shows a recognisable photograph."""
    m = np.zeros((1, 1))
    for _ in range(levels):
        m = np.block([[4 * m, 4 * m + 2], [4 * m + 3, 4 * m + 1]])
    return (m + 0.5) / m.size


PATTERNS = {
    "blank": blank, "crosshair": crosshair, "disc": disc, "blazed": blazed_grating, "binary_grating": binary_grating,
    "oam": oam_hologram, "lee": lee_hologram, "checker": checkerboard,
}
