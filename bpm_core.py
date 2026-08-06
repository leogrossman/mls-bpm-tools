"""Core BPM I/Q data model, PV naming, and analysis helpers.

This module intentionally has no Tkinter or Matplotlib imports. It is the part
that can be unit-tested quickly and reused by future CLI, EPICS7/PVA, or batch
analysis tools.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np


DEFAULT_SAMPLE_RATE = 6.25e6
BUTTONS = ("A", "B", "C", "D")
COMBINATION_PRESETS = (
    ("Sum A+B+C+D", "A+B+C+D"),
    ("A", "A"),
    ("B", "B"),
    ("C", "C"),
    ("D", "D"),
    ("Horizontal diff", "(A+B)-(C+D)"),
    ("Vertical diff", "(A+D)-(B+C)"),
    ("Mean", "mean(A,B,C,D)"),
)


@dataclass
class BPMInfo:
    name: str
    s_m: float = 0.0
    section: str = ""
    dispersion_x_m: float = 0.0
    beta_x_m: float = math.nan
    beta_y_m: float = math.nan
    x_pv: str = ""
    y_pv: str = ""
    known_orbit_pvs: bool = False
    modes: List[str] = field(default_factory=lambda: ["user", "low_alpha"])


@dataclass
class StatusPV:
    label: str
    pv: str
    on_values: List[str] = field(default_factory=lambda: ["1", "ON", "On", "on"])
    direction: str = ""
    excitation: str = ""
    enabled: bool = True


@dataclass
class TunePV:
    label: str
    pv: str
    color: str
    unit: str = "auto"
    harmonics: int = 4
    enabled: bool = True


@dataclass
class SpectrumSettings:
    unwrap_phase: bool = True
    unwrap_discont_rad: float = math.pi
    detrend: str = "linear"
    window: str = "hann"
    nfft: int = 0
    frequency_resolution_hz: float = 0.0


@dataclass
class AppConfig:
    bpms: List[BPMInfo]
    pv_templates: Dict[str, str]
    status_pvs: List[StatusPV] = field(default_factory=list)
    tune_pvs: List[TunePV] = field(default_factory=list)
    sample_rate_hz: float = DEFAULT_SAMPLE_RATE
    ddc_frequency_hz: Optional[float] = None
    refresh_ms: int = 1000
    epics_array_timeout_s: float = 2.0
    epics_scalar_timeout_s: float = 0.25
    raw_scan_on_value: str = "1 second"
    raw_scan_off_value: str = "Passive"
    source_path: Optional[Path] = None

    @classmethod
    def load(cls, path: Path) -> "AppConfig":
        raw = json.loads(path.read_text())
        bpms = [BPMInfo(**item) for item in raw["bpms"]]
        return cls(
            bpms=bpms,
            pv_templates=raw["pv_templates"],
            status_pvs=[StatusPV(**item) for item in raw.get("status_pvs", [])],
            tune_pvs=[TunePV(**item) for item in raw.get("tune_pvs", [])],
            sample_rate_hz=float(raw.get("sample_rate_hz", DEFAULT_SAMPLE_RATE)),
            ddc_frequency_hz=raw.get("ddc_frequency_hz"),
            refresh_ms=int(raw.get("refresh_ms", 1000)),
            epics_array_timeout_s=float(raw.get("epics_array_timeout_s", 2.0)),
            epics_scalar_timeout_s=float(raw.get("epics_scalar_timeout_s", 0.25)),
            raw_scan_on_value=str(raw.get("raw_scan_on_value", "1 second")),
            raw_scan_off_value=str(raw.get("raw_scan_off_value", "Passive")),
            source_path=path,
        )

    def to_dict(self) -> Dict[str, object]:
        return {
            "sample_rate_hz": self.sample_rate_hz,
            "ddc_frequency_hz": self.ddc_frequency_hz,
            "refresh_ms": self.refresh_ms,
            "epics_array_timeout_s": self.epics_array_timeout_s,
            "epics_scalar_timeout_s": self.epics_scalar_timeout_s,
            "raw_scan_on_value": self.raw_scan_on_value,
            "raw_scan_off_value": self.raw_scan_off_value,
            "pv_templates": self.pv_templates,
            "tune_pvs": [item.__dict__ for item in self.tune_pvs],
            "status_pvs": [item.__dict__ for item in self.status_pvs],
            "bpms": [item.__dict__ for item in self.bpms],
        }

    def save(self, path: Optional[Path] = None) -> Path:
        target = path or self.source_path
        if target is None:
            raise RuntimeError("No config path is known")
        target.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=False) + "\n", encoding="utf-8")
        self.source_path = target
        return target


class Backend:
    def get_array(self, pv: str) -> np.ndarray:
        raise NotImplementedError

    def get_value(self, pv: str) -> object:
        raise NotImplementedError

    def put(self, pv: str, value: object) -> None:
        raise NotImplementedError


class DemoBackend(Backend):
    """Synthetic data for development outside the control room."""

    def __init__(self, n: int = 8192, fs: float = DEFAULT_SAMPLE_RATE):
        self.n = n
        self.fs = fs
        self.phase = 0.0

    def get_array(self, pv: str) -> np.ndarray:
        seed = abs(hash(pv)) % (2**32)
        rng = np.random.default_rng(seed)
        n = np.arange(self.n)
        f_syn = 13_500.0
        q = 0.15 * np.sin(2 * np.pi * f_syn * n / self.fs + self.phase)
        q += 0.02 * rng.normal(size=self.n)
        amp = 1.0 + 0.03 * np.sin(2 * np.pi * 42_000 * n / self.fs)
        button_scale = 1.0 + 0.08 * ((seed % 7) - 3) / 3
        z = button_scale * amp * np.exp(1j * q)
        self.phase += 0.05
        return z.imag if pv.endswith(("Qa", "Qb", "Qc", "Qd")) else z.real

    def get_value(self, pv: str) -> object:
        seed = abs(hash(pv)) % 11
        if "TUNEZRP:MEASX" in pv.upper():
            return 0.1779
        if "TUNEZRP:MEASY" in pv.upper():
            return 0.22
        if "TUNEZRP:MEASZ" in pv.upper():
            return 0.0065
        if "TYPE" in pv.upper():
            return ("off", "phase", "amplitude", "chirp")[seed % 4]
        return int(seed % 3 == 0)

    def put(self, pv: str, value: object) -> None:
        return None


def pv_for(cfg: AppConfig, bpm: str, key: str, button: Optional[str] = None) -> str:
    template = cfg.pv_templates[key]
    return template.format(bpm=bpm, button=(button or "").lower(), BUTTON=(button or "").upper())


def normalize_button_tokens(expr: str) -> List[str]:
    return sorted(set(re.findall(r"\b[ABCD]\b", expr.upper())))


def read_button_phasors(backend: Backend, cfg: AppConfig, bpm: str, buttons: Iterable[str]) -> Dict[str, np.ndarray]:
    out: Dict[str, np.ndarray] = {}
    for button in buttons:
        i = backend.get_array(pv_for(cfg, bpm, "i", button))
        q = backend.get_array(pv_for(cfg, bpm, "q", button))
        n = min(i.size, q.size)
        out[button] = i[:n] + 1j * q[:n]
    if not out:
        raise RuntimeError("No buttons selected")
    n_min = min(v.size for v in out.values())
    return {k: v[:n_min] for k, v in out.items()}


def tbt_scan_commands(cfg: AppConfig, names: Sequence[str], enabled: bool) -> List[Tuple[str, object]]:
    value = cfg.raw_scan_on_value if enabled else cfg.raw_scan_off_value
    commands: List[Tuple[str, object]] = []
    for bpm in names:
        commands.append((pv_for(cfg, bpm, "scan"), value))
        if cfg.pv_templates.get("synth_scan"):
            commands.append((pv_for(cfg, bpm, "synth_scan"), value))
    return commands


def combination_expression(data: Mapping[str, np.ndarray], expr: str) -> np.ndarray:
    expr = re.sub(r"\b([abcd])\b", lambda match: match.group(1).upper(), expr.strip())
    env = {k: np.asarray(v) for k, v in data.items()}
    env["mean"] = lambda *args: np.mean(np.vstack(args), axis=0)
    env["sum"] = lambda *args: np.sum(np.vstack(args), axis=0)
    env["conj"] = np.conjugate
    env["real"] = np.real
    env["imag"] = np.imag
    env["abs"] = np.abs
    allowed = set("ABCDmeanumsconjrealigab()+-*/, .")
    if any(ch not in allowed for ch in expr):
        raise ValueError("Expression supports A/B/C/D, mean(), sum(), abs(), real(), imag(), conj(), +, -, *, / and parentheses")
    try:
        value = eval(expr, {"__builtins__": {}}, env)  # noqa: S307 - restricted grammar/env
    except Exception as exc:
        raise ValueError(f"Invalid combination: {expr}") from exc
    arr = np.asarray(value, dtype=complex).ravel()
    if arr.size == 0:
        raise ValueError("Combination produced no data")
    return arr


def spectrum(x: np.ndarray, fs: float) -> Tuple[np.ndarray, np.ndarray]:
    result = spectrum_pipeline(x, fs, SpectrumSettings())
    return result["frequency_hz"], result["psd"]


def phase_pipeline(z: np.ndarray, settings: SpectrumSettings) -> Dict[str, np.ndarray]:
    z = np.asarray(z, dtype=complex).ravel()
    raw_phase = np.angle(z)
    if settings.unwrap_phase:
        phase = np.unwrap(raw_phase, discont=max(settings.unwrap_discont_rad, 1e-12))
    else:
        phase = raw_phase.copy()
    return {"raw_phase": raw_phase, "phase": phase}


def _detrend_signal(x: np.ndarray, mode: str) -> np.ndarray:
    x = np.asarray(x, dtype=float).ravel()
    x = np.nan_to_num(x, nan=np.nanmean(x) if np.any(np.isfinite(x)) else 0.0)
    mode = mode.lower()
    if mode in ("none", "off"):
        return x.copy()
    if mode in ("constant", "mean"):
        return x - np.mean(x)
    if mode == "linear":
        if x.size < 2:
            return x - np.mean(x)
        turns = np.arange(x.size, dtype=float)
        coeff = np.polyfit(turns, x, 1)
        return x - np.polyval(coeff, turns)
    raise ValueError(f"Unsupported detrend mode: {mode}")


def _window_values(n: int, name: str) -> np.ndarray:
    name = name.lower()
    if name in ("none", "rect", "rectangular", "boxcar"):
        return np.ones(n)
    if name in ("hann", "hanning"):
        return np.hanning(n)
    if name == "hamming":
        return np.hamming(n)
    if name == "blackman":
        return np.blackman(n)
    raise ValueError(f"Unsupported FFT window: {name}")


def _resolve_nfft(n_samples: int, fs: float, settings: SpectrumSettings) -> int:
    if settings.frequency_resolution_hz > 0:
        nfft = int(math.ceil(fs / settings.frequency_resolution_hz))
    elif settings.nfft > 0:
        nfft = int(settings.nfft)
    else:
        nfft = n_samples
    return max(n_samples, nfft, 1)


def spectrum_pipeline(x: np.ndarray, fs: float, settings: SpectrumSettings) -> Dict[str, np.ndarray]:
    raw = np.asarray(x, dtype=float).ravel()
    if raw.size == 0:
        raise ValueError("Cannot spectrum empty signal")
    detrended = _detrend_signal(raw, settings.detrend)
    window = _window_values(detrended.size, settings.window)
    windowed = np.nan_to_num(detrended) * window
    nfft = _resolve_nfft(detrended.size, fs, settings)
    spec = np.fft.rfft(windowed, n=nfft)
    freq = np.fft.rfftfreq(nfft, d=1.0 / fs)
    psd = (np.abs(spec) ** 2) / max(np.sum(window**2), 1.0)
    return {
        "raw": raw,
        "detrended": detrended,
        "window": window,
        "windowed": windowed,
        "frequency_hz": freq,
        "spectrum": spec,
        "psd": psd,
    }


def normalize_power(power: np.ndarray) -> np.ndarray:
    power = np.asarray(power, dtype=float)
    finite = power[np.isfinite(power)]
    scale = float(np.max(finite)) if finite.size else 0.0
    if scale <= 0:
        return power.copy()
    return power / scale


def find_spectrum_peaks(
    frequency_hz: np.ndarray,
    power: np.ndarray,
    max_peaks: int = 5,
    min_frequency_hz: float = 1.0,
    min_relative_height: float = 0.05,
) -> List[Tuple[float, float]]:
    freq = np.asarray(frequency_hz, dtype=float).ravel()
    p = np.asarray(power, dtype=float).ravel()
    n = min(freq.size, p.size)
    if n < 3:
        return []
    freq = freq[:n]
    p = np.nan_to_num(p[:n], nan=0.0, posinf=0.0, neginf=0.0)
    max_power = float(np.max(p))
    if max_power <= 0:
        return []
    candidates = []
    threshold = max_power * max(min_relative_height, 0.0)
    for i in range(1, n - 1):
        if freq[i] < min_frequency_hz:
            continue
        if p[i] >= threshold and p[i] >= p[i - 1] and p[i] >= p[i + 1]:
            candidates.append((freq[i], p[i]))
    candidates.sort(key=lambda item: item[1], reverse=True)
    return candidates[:max(max_peaks, 0)]


def parse_expressions(text: str) -> List[str]:
    expressions = [item.strip() for item in re.split(r"[;\n]", text) if item.strip()]
    return expressions or ["A+B+C+D"]


def combine_selected_expressions(presets: Sequence[str], custom: str = "", use_custom: bool = False) -> str:
    expressions = [expr.strip() for expr in presets if expr.strip()]
    if use_custom:
        expressions.extend(parse_expressions(custom))
    seen: set = set()
    unique = []
    for expr in expressions:
        if expr not in seen:
            unique.append(expr)
            seen.add(expr)
    return "; ".join(unique or ["A+B+C+D", "A"])


def tune_value_to_frequency(value: object, fs: float, unit: str = "auto") -> Optional[Tuple[float, float]]:
    try:
        numeric = float(np.asarray(value).ravel()[0])
    except Exception:
        return None
    if not np.isfinite(numeric) or numeric <= 0:
        return None
    unit = unit.lower()
    if unit == "tune" or (unit == "auto" and numeric <= 1.0):
        tune = numeric
        freq = numeric * fs
    elif unit == "khz":
        freq = numeric * 1000.0
        tune = freq / fs
    else:
        freq = numeric
        tune = freq / fs
    if freq <= 0 or freq > fs / 2:
        return None
    return freq, tune


def tune_markers_from_values(tunes: Mapping[str, Mapping[str, object]], fs: float, include_harmonics: bool) -> List[Tuple[float, str, str]]:
    markers: List[Tuple[float, str, str]] = []
    for label, info in tunes.items():
        converted = tune_value_to_frequency(info.get("value"), fs, str(info.get("unit", "auto")))
        if converted is None:
            continue
        base_freq, tune = converted
        color = str(info.get("color", "0.35"))
        harmonics = int(info.get("harmonics", 1)) if include_harmonics else 1
        for harmonic in range(1, max(harmonics, 1) + 1):
            freq = base_freq * harmonic
            if freq > fs / 2:
                break
            marker_label = f"{label} Q={tune:.4g}" if harmonic == 1 else f"{harmonic}{label}"
            markers.append((freq, marker_label, color))
    return markers


def nearest_bpm_marker(
    x: float,
    y: float,
    marker_positions: Mapping[str, Tuple[float, float]],
    max_distance: float = 12.0,
) -> Optional[str]:
    best_name: Optional[str] = None
    best_distance = max_distance
    for name, (mx, my) in marker_positions.items():
        distance = math.hypot(float(x) - mx, float(y) - my)
        if distance <= best_distance:
            best_name = name
            best_distance = distance
    return best_name
