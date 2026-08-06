#!/usr/bin/env python3
"""Minimal MLS BPM I/Q viewer prototype.

Read-only by default. Any EPICS write requires an explicit GUI confirmation.
Designed for Python 3.9 + tkinter + matplotlib + numpy + pyepics.

This is intentionally a compact prototype, not an operator-certified tool.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import logging
import math
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np

try:
    import tkinter as tk
    from tkinter import messagebox, ttk, filedialog
except ImportError as exc:  # pragma: no cover
    TK_IMPORT_ERROR = exc

    class _MissingTkWidget:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("tkinter is required to launch the BPM I/Q viewer") from TK_IMPORT_ERROR

    class _MissingTkModule:
        Tk = _MissingTkWidget
        Toplevel = _MissingTkWidget
        StringVar = _MissingTkWidget
        BooleanVar = _MissingTkWidget
        END = "end"
        BOTH = "both"
        X = "x"
        TOP = "top"
        LEFT = "left"
        EXTENDED = "extended"
        GROOVE = "groove"

        class Listbox(_MissingTkWidget):
            pass

        class Label(_MissingTkWidget):
            pass

        class Text(_MissingTkWidget):
            pass

    class _MissingTkDialogs:
        def __getattr__(self, name):
            raise RuntimeError("tkinter is required to launch the BPM I/Q viewer") from TK_IMPORT_ERROR

    tk = _MissingTkModule()  # type: ignore[assignment]
    messagebox = _MissingTkDialogs()  # type: ignore[assignment]
    ttk = _MissingTkDialogs()  # type: ignore[assignment]
    filedialog = _MissingTkDialogs()  # type: ignore[assignment]
else:
    TK_IMPORT_ERROR = None

from matplotlib.figure import Figure

if TK_IMPORT_ERROR is None:
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
else:  # pragma: no cover - exercised only in headless/broken-Tk environments
    class FigureCanvasTkAgg:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            raise RuntimeError("tkinter is required to launch the BPM I/Q viewer") from TK_IMPORT_ERROR

    class NavigationToolbar2Tk:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            raise RuntimeError("tkinter is required to launch the BPM I/Q viewer") from TK_IMPORT_ERROR

try:
    import epics  # pyepics
except ImportError:
    epics = None


DEFAULT_SAMPLE_RATE = 6.25e6
BUTTONS = ("A", "B", "C", "D")
DEFAULT_LOG_ROOT = Path(".mls_bpm_local") / "logs"


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


class SessionLogger:
    def __init__(self, session_dir: Path):
        self.session_dir = session_dir
        self.events_path = session_dir / "events.jsonl"

    def event(self, event_type: str, **payload: Any) -> None:
        record = {
            "timestamp": _dt.datetime.now().isoformat(timespec="milliseconds"),
            "event": event_type,
            **payload,
        }
        try:
            with self.events_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")
        except Exception:
            logging.exception("Failed to write structured event: %s", event_type)


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


class EpicsBackend(Backend):
    def __init__(self, array_timeout: float = 2.0, scalar_timeout: float = 0.25):
        if epics is None:
            raise RuntimeError("pyepics is not installed")
        self.array_timeout = array_timeout
        self.scalar_timeout = scalar_timeout

    def get_array(self, pv: str) -> np.ndarray:
        try:
            value = epics.caget(pv, timeout=self.array_timeout, connection_timeout=self.array_timeout)
        except TypeError:
            value = epics.caget(pv, timeout=self.array_timeout)
        if value is None:
            raise RuntimeError(f"No value returned from {pv}")
        arr = np.asarray(value, dtype=float).ravel()
        if arr.size == 0:
            raise RuntimeError(f"Empty waveform from {pv}")
        return arr

    def get_value(self, pv: str) -> object:
        try:
            value = epics.caget(pv, timeout=self.scalar_timeout, connection_timeout=self.scalar_timeout)
        except TypeError:
            value = epics.caget(pv, timeout=self.scalar_timeout)
        if value is None:
            raise RuntimeError(f"No value returned from {pv}")
        return value

    def put(self, pv: str, value: object) -> None:
        ok = epics.caput(pv, value, wait=True, timeout=self.array_timeout)
        if ok is None or ok == 0:
            raise RuntimeError(f"Write failed: {pv} <- {value!r}")


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
        logging.info("DEMO write: %s <- %r", pv, value)


def pv_for(cfg: AppConfig, bpm: str, key: str, button: Optional[str] = None) -> str:
    template = cfg.pv_templates[key]
    return template.format(bpm=bpm, button=(button or "").lower(), BUTTON=(button or "").upper())


def normalize_button_tokens(expr: str) -> List[str]:
    return sorted(set(re.findall(r"\b[ABCD]\b", expr.upper())))


def read_button_phasors(backend: Backend, cfg: AppConfig, bpm: str, buttons: Iterable[str]) -> Dict[str, np.ndarray]:
    out: Dict[str, np.ndarray] = {}
    for button in buttons:
        i_pv = pv_for(cfg, bpm, "i", button)
        q_pv = pv_for(cfg, bpm, "q", button)
        i = backend.get_array(i_pv)
        q = backend.get_array(q_pv)
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
    """Evaluate a deliberately tiny safe expression language.

    Examples: A, A+B+C+D, (A+B)-(C+D), A-B, mean(A,B,C,D)
    """
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


def parse_expressions(text: str) -> List[str]:
    expressions = [item.strip() for item in re.split(r"[;\n]", text) if item.strip()]
    return expressions or ["A+B+C+D"]


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


class PlotWindow(tk.Toplevel):
    def __init__(
        self,
        app: "BPMViewer",
        bpm_names: Sequence[str],
        expression: str = "A+B+C+D",
        plot_kind: str = "spectra",
        show_tunes: bool = True,
    ):
        super().__init__(app.root)
        self.app = app
        self.bpm_names = list(bpm_names)
        self.title("BPM I/Q plots — " + ", ".join(self.bpm_names))
        self.geometry("1320x820")
        self.running = True
        self.after_id: Optional[str] = None
        self.bpm_enabled: Dict[str, tk.BooleanVar] = {}

        controls = ttk.Frame(self)
        controls.pack(side=tk.TOP, fill=tk.X, padx=6, pady=4)
        ttk.Label(controls, text="Combination:").pack(side=tk.LEFT)
        self.expr = tk.StringVar(value=expression)
        ttk.Entry(controls, textvariable=self.expr, width=34).pack(side=tk.LEFT, padx=4)
        ttk.Label(controls, text="Plot:").pack(side=tk.LEFT, padx=(12, 2))
        self.plot_kind = tk.StringVar(value=plot_kind)
        ttk.Combobox(
            controls,
            textvariable=self.plot_kind,
            values=("I/Q", "raw buttons", "magnitude", "phase", "phase spectrum", "magnitude spectrum", "spectra", "phase debug", "position-like", "all"),
            state="readonly",
            width=16,
        ).pack(side=tk.LEFT)
        self.live = tk.BooleanVar(value=True)
        ttk.Checkbutton(controls, text="Live", variable=self.live).pack(side=tk.LEFT, padx=10)
        self.show_tunes = tk.BooleanVar(value=show_tunes)
        ttk.Checkbutton(controls, text="Tunes", variable=self.show_tunes).pack(side=tk.LEFT)
        self.show_harmonics = tk.BooleanVar(value=True)
        ttk.Checkbutton(controls, text="Harmonics", variable=self.show_harmonics).pack(side=tk.LEFT)
        ttk.Button(controls, text="Refresh now", command=self.refresh).pack(side=tk.LEFT)
        ttk.Button(controls, text="Pause", command=self.toggle_pause).pack(side=tk.LEFT, padx=4)
        ttk.Button(controls, text="Save data", command=self.save_data).pack(side=tk.LEFT, padx=4)

        self.status = tk.StringVar(value="Ready")
        ttk.Label(self, textvariable=self.status, anchor="w").pack(fill=tk.X, padx=6)

        body = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True)

        side = ttk.Frame(body, padding=6)
        body.add(side, weight=0)
        bpm_box = ttk.LabelFrame(side, text="BPM overlays", padding=6)
        bpm_box.pack(fill=tk.BOTH, expand=True)
        add_row = ttk.Frame(bpm_box)
        add_row.pack(fill=tk.X, pady=(0, 4))
        self.add_bpm_var = tk.StringVar()
        self.add_bpm_combo = ttk.Combobox(
            add_row,
            textvariable=self.add_bpm_var,
            values=[bpm.name for bpm in self.app.cfg.bpms],
            width=16,
        )
        self.add_bpm_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(add_row, text="Add", command=self.add_bpm_from_combo).pack(side=tk.LEFT, padx=(4, 0))
        ttk.Button(bpm_box, text="Add main selection", command=self.add_main_selection).pack(fill=tk.X, pady=2)
        toggle_row = ttk.Frame(bpm_box)
        toggle_row.pack(fill=tk.X, pady=2)
        ttk.Button(toggle_row, text="All on", command=lambda: self.set_all_bpms(True)).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(toggle_row, text="All off", command=lambda: self.set_all_bpms(False)).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))
        ttk.Button(bpm_box, text="Remove off", command=self.remove_disabled_bpms).pack(fill=tk.X, pady=2)
        ttk.Separator(bpm_box).pack(fill=tk.X, pady=4)
        self.bpm_rows = ttk.Frame(bpm_box)
        self.bpm_rows.pack(fill=tk.BOTH, expand=True)

        tune_box = ttk.LabelFrame(side, text="Spectrum markers", padding=6)
        tune_box.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(
            tune_box,
            text="Tunes are read only when the Tunes toggle is on or you click Refresh now.",
            wraplength=210,
            justify=tk.LEFT,
        ).pack(anchor="w")

        fft_box = ttk.LabelFrame(side, text="FFT / phase settings", padding=6)
        fft_box.pack(fill=tk.X, pady=(8, 0))
        self.unwrap_phase = tk.BooleanVar(value=True)
        ttk.Checkbutton(fft_box, text="unwrap(angle)", variable=self.unwrap_phase, command=self.refresh).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(fft_box, text="unwrap jump rad").grid(row=1, column=0, sticky="w")
        self.unwrap_discont = tk.StringVar(value=f"{math.pi:.6g}")
        ttk.Entry(fft_box, textvariable=self.unwrap_discont, width=10).grid(row=1, column=1, sticky="ew")
        ttk.Label(fft_box, text="detrend").grid(row=2, column=0, sticky="w")
        self.detrend_mode = tk.StringVar(value="linear")
        ttk.Combobox(fft_box, textvariable=self.detrend_mode, values=("linear", "constant", "none"), state="readonly", width=10).grid(row=2, column=1, sticky="ew")
        ttk.Label(fft_box, text="window").grid(row=3, column=0, sticky="w")
        self.window_name = tk.StringVar(value="hann")
        ttk.Combobox(fft_box, textvariable=self.window_name, values=("hann", "hamming", "blackman", "rectangular"), state="readonly", width=10).grid(row=3, column=1, sticky="ew")
        ttk.Label(fft_box, text="NFFT").grid(row=4, column=0, sticky="w")
        self.nfft_text = tk.StringVar(value="")
        ttk.Entry(fft_box, textvariable=self.nfft_text, width=10).grid(row=4, column=1, sticky="ew")
        ttk.Label(fft_box, text="df Hz").grid(row=5, column=0, sticky="w")
        self.freq_res_text = tk.StringVar(value="1000")
        ttk.Entry(fft_box, textvariable=self.freq_res_text, width=10).grid(row=5, column=1, sticky="ew")
        self.log_raw_snapshots = tk.BooleanVar(value=True)
        ttk.Checkbutton(fft_box, text="log first raw snapshot", variable=self.log_raw_snapshots).grid(row=6, column=0, columnspan=2, sticky="w")
        ttk.Button(fft_box, text="Apply + refresh", command=self.refresh).grid(row=7, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        fft_box.columnconfigure(1, weight=1)

        plot_frame = ttk.Frame(body)
        body.add(plot_frame, weight=1)
        self.figure = Figure(figsize=(10, 7), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.figure, master=plot_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        NavigationToolbar2Tk(self.canvas, plot_frame).update()
        self.last_data: Dict[str, Dict[str, np.ndarray]] = {}
        self.last_errors: Dict[str, str] = {}
        self.logged_raw_snapshots: set = set()
        for bpm in self.bpm_names:
            self.add_bpm(bpm, refresh=False)
        self.rebuild_bpm_rows()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh()

    def update_title(self) -> None:
        names = self.active_bpm_names()
        suffix = ", ".join(names[:5]) + ("..." if len(names) > 5 else "")
        self.title("BPM I/Q plots — " + (suffix or "no active BPMs"))

    def rebuild_bpm_rows(self) -> None:
        for child in self.bpm_rows.winfo_children():
            child.destroy()
        if not self.bpm_names:
            ttk.Label(self.bpm_rows, text="No BPMs loaded.").pack(anchor="w")
            return
        for bpm in self.bpm_names:
            info = self.app.bpm_by_name.get(bpm)
            label = f"* {bpm}" if info and info.known_orbit_pvs else bpm
            ttk.Checkbutton(
                self.bpm_rows,
                text=label,
                variable=self.bpm_enabled[bpm],
                command=self.refresh,
            ).pack(anchor="w", fill=tk.X)
        self.update_title()

    def active_bpm_names(self) -> List[str]:
        return [bpm for bpm in self.bpm_names if self.bpm_enabled.get(bpm, tk.BooleanVar(value=False)).get()]

    def add_bpm(self, bpm: str, refresh: bool = True) -> None:
        bpm = bpm.strip()
        if not bpm:
            return
        if bpm not in self.app.bpm_by_name:
            messagebox.showwarning("Unknown BPM", f"{bpm} is not in bpm_config.json.", parent=self)
            return
        if bpm not in self.bpm_names:
            self.bpm_names.append(bpm)
        if bpm not in self.bpm_enabled:
            self.bpm_enabled[bpm] = tk.BooleanVar(value=True)
        else:
            self.bpm_enabled[bpm].set(True)
        self.app.session.event("plot_bpm_added", bpm=bpm, bpms=self.bpm_names)
        if refresh:
            self.rebuild_bpm_rows()
            self.refresh()

    def add_bpm_from_combo(self) -> None:
        self.add_bpm(self.add_bpm_var.get())

    def add_main_selection(self) -> None:
        names = self.app.selected_names()
        if not names:
            messagebox.showinfo("Select BPM", "Select BPMs in the main window first.", parent=self)
            return
        for bpm in names:
            self.add_bpm(bpm, refresh=False)
        self.rebuild_bpm_rows()
        self.refresh()

    def set_all_bpms(self, enabled: bool) -> None:
        for var in self.bpm_enabled.values():
            var.set(enabled)
        self.refresh()

    def remove_disabled_bpms(self) -> None:
        self.bpm_names = [bpm for bpm in self.bpm_names if self.bpm_enabled[bpm].get()]
        self.bpm_enabled = {bpm: self.bpm_enabled[bpm] for bpm in self.bpm_names}
        self.rebuild_bpm_rows()
        self.refresh()

    def toggle_pause(self) -> None:
        self.running = not self.running
        self.status.set("Live updates resumed" if self.running else "Paused")
        if self.running:
            self.refresh()

    def close(self) -> None:
        self.running = False
        if self.after_id:
            self.after_cancel(self.after_id)
        self.destroy()

    def save_data(self) -> None:
        if not self.last_data:
            messagebox.showinfo("No data", "Refresh once before saving.", parent=self)
            return
        path = filedialog.asksaveasfilename(
            parent=self, defaultextension=".npz", filetypes=[("NumPy archive", "*.npz")]
        )
        if not path:
            return
        flat = {}
        for bpm, items in self.last_data.items():
            for key, value in items.items():
                flat[f"{bpm}_{key}"] = value
        np.savez_compressed(path, **flat)
        self.app.session.event("save_data", path=path, bpms=list(self.last_data))
        self.status.set(f"Saved {path}")

    def spectrum_settings(self) -> SpectrumSettings:
        try:
            unwrap_discont = float(self.unwrap_discont.get() or math.pi)
        except ValueError:
            unwrap_discont = math.pi
        try:
            nfft = int(self.nfft_text.get()) if self.nfft_text.get().strip() else 0
        except ValueError:
            nfft = 0
        try:
            freq_res = float(self.freq_res_text.get()) if self.freq_res_text.get().strip() else 0.0
        except ValueError:
            freq_res = 0.0
        return SpectrumSettings(
            unwrap_phase=bool(self.unwrap_phase.get()),
            unwrap_discont_rad=unwrap_discont,
            detrend=self.detrend_mode.get(),
            window=self.window_name.get(),
            nfft=nfft,
            frequency_resolution_hz=freq_res,
        )

    def log_raw_snapshot_once(self, bpm: str, expr: str, phasors: Mapping[str, np.ndarray], z: np.ndarray) -> None:
        if not self.log_raw_snapshots.get():
            return
        key = (bpm, expr)
        if key in self.logged_raw_snapshots:
            return
        self.logged_raw_snapshots.add(key)
        try:
            snapshot_dir = self.app.session.session_dir / "raw_snapshots"
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            stamp = _dt.datetime.now().strftime("%H%M%S_%f")
            safe_expr = re.sub(r"[^A-Za-z0-9_.+-]+", "_", expr)[:40]
            path = snapshot_dir / f"{stamp}_{bpm}_{safe_expr}.npz"
            limit = min(z.size, 4096)
            arrays = {f"{button}_complex": value[:limit] for button, value in phasors.items()}
            arrays["combined"] = z[:limit]
            arrays["raw_phase"] = np.angle(z[:limit])
            arrays["unwrapped_phase"] = np.unwrap(np.angle(z[:limit]))
            np.savez_compressed(path, **arrays)
            self.app.session.event("raw_snapshot_saved", bpm=bpm, expression=expr, path=str(path), samples=limit)
        except Exception as exc:
            self.app.session.event("raw_snapshot_error", bpm=bpm, expression=expr, error=str(exc))

    def refresh(self) -> None:
        if not self.running and self.live.get():
            return
        try:
            self._refresh_impl()
        except Exception as exc:
            logging.exception("Plot refresh failed")
            self.status.set(str(exc))
        finally:
            if self.running and self.live.get() and self.winfo_exists():
                self.after_id = self.after(self.app.cfg.refresh_ms, self.refresh)

    def _refresh_impl(self) -> None:
        kind = self.plot_kind.get()
        active_bpms = self.active_bpm_names()
        self.update_title()
        self.figure.clear()
        if kind == "all":
            axes = [self.figure.add_subplot(221), self.figure.add_subplot(222), self.figure.add_subplot(223), self.figure.add_subplot(224)]
        elif kind == "phase debug":
            axes = [self.figure.add_subplot(411), self.figure.add_subplot(412), self.figure.add_subplot(413), self.figure.add_subplot(414)]
        elif kind == "spectra":
            axes = [self.figure.add_subplot(211), self.figure.add_subplot(212)]
        elif kind == "phase spectrum":
            axes = [self.figure.add_subplot(111)]
        elif kind == "magnitude spectrum":
            axes = [self.figure.add_subplot(211), self.figure.add_subplot(212)]
        else:
            axes = [self.figure.add_subplot(111)]

        expr_text = self.expr.get().strip()
        expressions = parse_expressions(expr_text)
        buttons_needed = sorted(set(button for expr in expressions for button in normalize_button_tokens(expr)))
        if kind in ("position-like", "raw buttons"):
            buttons_needed = list(BUTTONS)
        settings = self.spectrum_settings()
        self.last_data = {}
        self.last_errors = {}
        tune_markers = self.app.current_tune_markers(include_harmonics=self.show_harmonics.get()) if self.show_tunes.get() else []
        if not active_bpms:
            axes[0].text(
                0.5,
                0.5,
                "No active BPM overlays.\nTurn on a BPM checkbox or add one.",
                ha="center",
                va="center",
                transform=axes[0].transAxes,
            )
        for bpm in active_bpms:
            try:
                phasors = read_button_phasors(self.app.backend, self.app.cfg, bpm, buttons_needed)
            except Exception as exc:
                message = str(exc)
                self.last_errors[bpm] = message
                logging.warning("Skipping %s in plot refresh: %s", bpm, message)
                self.app.session.event(
                    "plot_refresh_error",
                    bpm=bpm,
                    expression=expr_text,
                    plot_kind=kind,
                    error=message,
                )
                continue
            self.last_data[bpm] = dict(phasors)
            for expr in expressions:
                try:
                    z = combination_expression(phasors, expr)
                except Exception as exc:
                    message = str(exc)
                    self.last_errors[f"{bpm} {expr}"] = message
                    self.app.session.event("expression_error", bpm=bpm, expression=expr, error=message)
                    continue
                phase_steps = phase_pipeline(z, settings)
                phase = phase_steps["phase"]
                mag = np.abs(z)
                label = bpm if len(expressions) == 1 else f"{bpm} {expr}"
                self.last_data[bpm][f"combined_{expr}"] = z
                self.last_data[bpm][f"raw_phase_{expr}"] = phase_steps["raw_phase"]
                self.last_data[bpm][f"phase_{expr}"] = phase
                self.last_data[bpm][f"magnitude_{expr}"] = mag
                self.log_raw_snapshot_once(bpm, expr, phasors, z)
                turns = np.arange(z.size)

                if kind == "I/Q":
                    axes[0].plot(z.real, z.imag, ".-", ms=2, label=label)
                    axes[0].set_xlabel("I")
                    axes[0].set_ylabel("Q")
                elif kind == "raw buttons":
                    for button in BUTTONS:
                        raw = phasors[button]
                        axes[0].plot(turns, raw.real, label=f"{bpm} {button} I", alpha=0.75)
                        axes[0].plot(turns, raw.imag, label=f"{bpm} {button} Q", alpha=0.75, linestyle="--")
                    axes[0].set_ylabel("raw I/Q [arb.]")
                    break
                elif kind == "magnitude":
                    axes[0].plot(turns, mag, label=label)
                    axes[0].set_ylabel("|phasor|")
                elif kind == "phase":
                    axes[0].plot(turns, phase, label=label)
                    axes[0].set_ylabel("unwrapped phase [rad]")
                elif kind == "position-like":
                    denom = phasors.get("A", 0) + phasors.get("B", 0) + phasors.get("C", 0) + phasors.get("D", 0)
                    with np.errstate(divide="ignore", invalid="ignore"):
                        value = np.real(z / denom) if np.ndim(denom) else np.real(z)
                    axes[0].plot(turns, value, label=label)
                    axes[0].set_ylabel("Re(combination / sum), uncalibrated")
                elif kind == "phase spectrum":
                    phase_spec = spectrum_pipeline(phase, self.app.cfg.sample_rate_hz, settings)
                    f, p = phase_spec["frequency_hz"], phase_spec["psd"]
                    axes[0].semilogy(f, np.maximum(p, 1e-30), label=label)
                    axes[0].set_xlabel("frequency [Hz]")
                    axes[0].set_ylabel("phase PSD [arb.]")
                    axes[0].set_xlim(0, self.app.cfg.sample_rate_hz / 2)
                elif kind == "magnitude spectrum":
                    axes[0].plot(turns, mag, label=label)
                    mag_spec = spectrum_pipeline(mag, self.app.cfg.sample_rate_hz, settings)
                    f, p = mag_spec["frequency_hz"], mag_spec["psd"]
                    axes[1].semilogy(f, np.maximum(p, 1e-30), label=label)
                    axes[0].set_ylabel("|phasor|")
                    axes[1].set_xlabel("frequency [Hz]")
                    axes[1].set_ylabel("magnitude PSD [arb.]")
                    axes[1].set_xlim(0, self.app.cfg.sample_rate_hz / 2)
                elif kind == "spectra":
                    phase_spec = spectrum_pipeline(phase, self.app.cfg.sample_rate_hz, settings)
                    mag_spec = spectrum_pipeline(mag, self.app.cfg.sample_rate_hz, settings)
                    f_phase, p_phase = phase_spec["frequency_hz"], phase_spec["psd"]
                    f_mag, p_mag = mag_spec["frequency_hz"], mag_spec["psd"]
                    axes[0].semilogy(f_phase, np.maximum(p_phase, 1e-30), label=label)
                    axes[1].semilogy(f_mag, np.maximum(p_mag, 1e-30), label=label)
                    axes[0].set_ylabel("phase PSD [arb.]")
                    axes[1].set_ylabel("magnitude PSD [arb.]")
                    axes[1].set_xlabel("frequency [Hz]")
                    axes[0].set_xlim(0, self.app.cfg.sample_rate_hz / 2)
                    axes[1].set_xlim(0, self.app.cfg.sample_rate_hz / 2)
                elif kind == "phase debug":
                    phase_spec = spectrum_pipeline(phase, self.app.cfg.sample_rate_hz, settings)
                    axes[0].plot(turns, phase_steps["raw_phase"], label=label)
                    axes[1].plot(turns, phase, label=label)
                    axes[2].plot(turns, phase_spec["detrended"], label=label)
                    axes[2].plot(turns, phase_spec["windowed"], label=f"{label} windowed", alpha=0.65, linestyle="--")
                    axes[3].semilogy(phase_spec["frequency_hz"], np.maximum(phase_spec["psd"], 1e-30), label=label)
                    axes[0].set_ylabel("angle(z) [rad]")
                    axes[1].set_ylabel("phase [rad]")
                    axes[2].set_ylabel("detrended/windowed")
                    axes[3].set_ylabel("PSD")
                    axes[3].set_xlabel("frequency [Hz]")
                    axes[3].set_xlim(0, self.app.cfg.sample_rate_hz / 2)
                else:  # all
                    axes[0].plot(turns, z.real, label=label)
                    axes[1].plot(turns, z.imag, label=label)
                    axes[2].plot(turns, phase, label=label)
                    phase_spec = spectrum_pipeline(phase, self.app.cfg.sample_rate_hz, settings)
                    f, p = phase_spec["frequency_hz"], phase_spec["psd"]
                    axes[3].semilogy(f, np.maximum(p, 1e-30), label=label)
                    axes[0].set_title("I")
                    axes[1].set_title("Q")
                    axes[2].set_title("phase")
                    axes[3].set_title("phase spectrum")

        if active_bpms and not self.last_data:
            axes[0].text(
                0.5,
                0.5,
                "No valid BPM data.\nCheck PV names, .SCAN state, and network.",
                ha="center",
                va="center",
                transform=axes[0].transAxes,
            )
        elif self.last_errors:
            axes[0].text(
                0.02,
                0.98,
                f"{len(self.last_errors)} BPM(s) had PV errors; see logs.",
                ha="left",
                va="top",
                transform=axes[0].transAxes,
                fontsize=9,
            )

        for index, ax in enumerate(axes):
            ax.grid(True, alpha=0.3)
            is_spectrum_axis = (
                kind == "phase spectrum"
                or (kind == "magnitude spectrum" and index == 1)
                or kind == "spectra"
                or (kind == "phase debug" and index == 3)
                or (kind == "all" and index == len(axes) - 1)
            )
            if tune_markers and is_spectrum_axis:
                self._draw_tune_markers(ax, tune_markers)
            handles, _labels = ax.get_legend_handles_labels()
            if handles:
                ax.legend(loc="best")
        self.figure.tight_layout()
        self.canvas.draw_idle()
        suffix = f"; {len(self.last_errors)} error(s)" if self.last_errors else ""
        tune_suffix = f"; {len(tune_markers)} tune marker(s)" if tune_markers else ""
        self.status.set(f"Updated {time.strftime('%H:%M:%S')} - {len(active_bpms)} BPM(s), expression {self.expr.get()}{tune_suffix}{suffix}")

    def _draw_tune_markers(self, ax, markers: Sequence[Tuple[float, str, str]]) -> None:
        ymin, ymax = ax.get_ylim()
        for freq, label, color in markers:
            ax.axvline(freq, color=color, alpha=0.45, linestyle="--", linewidth=1.0)
            ax.text(freq, ymax, label, rotation=90, va="top", ha="right", color=color, fontsize=8)
        ax.set_ylim(ymin, ymax)


class LatticeWindow(tk.Toplevel):
    def __init__(self, app: "BPMViewer"):
        super().__init__(app.root)
        self.app = app
        self.title("Clickable BPM lattice overview")
        self.geometry("1100x520")
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=6, pady=4)
        ttk.Label(top, text="Optics mode:").pack(side=tk.LEFT)
        modes = sorted({mode for bpm in app.cfg.bpms for mode in bpm.modes}) or ["low_emittance"]
        self.mode = tk.StringVar(value=modes[0])
        ttk.Combobox(top, textvariable=self.mode, values=modes, state="readonly", width=14).pack(side=tk.LEFT, padx=4)
        self.show_labels = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="Labels", variable=self.show_labels, command=self.draw).pack(side=tk.LEFT, padx=4)
        ttk.Label(top, text="Click a BPM marker to select/open raw I/Q. Positions/PVs come from bpm_config.json.").pack(side=tk.LEFT, padx=12)

        self.fig = Figure(figsize=(10, 4), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.canvas.mpl_connect("pick_event", self.on_pick)
        self.draw()

    def draw(self) -> None:
        self.ax.clear()
        bpms = sorted(self.app.cfg.bpms, key=lambda b: b.s_m)
        s = np.array([b.s_m for b in bpms])
        d = np.array([b.dispersion_x_m for b in bpms])
        bx = np.array([b.beta_x_m for b in bpms], dtype=float)
        by = np.array([b.beta_y_m for b in bpms], dtype=float)
        has_dispersion = np.any(np.isfinite(d) & (np.abs(d) > 0))
        has_beta_x = np.any(np.isfinite(bx) & (np.abs(bx) > 0))
        has_beta_y = np.any(np.isfinite(by) & (np.abs(by) > 0))
        marker_y = d if has_dispersion else np.zeros_like(s)
        if has_dispersion:
            self.ax.plot(s, d, "-", alpha=0.6, label="Dx [m]")
        if has_beta_x:
            self.ax.plot(s, bx, "-", alpha=0.45, label="beta_x [m]")
        if has_beta_y:
            self.ax.plot(s, by, "-", alpha=0.45, label="beta_y [m]")
        points = self.ax.scatter(s, marker_y, picker=True, pickradius=8, label="BPM")
        points._bpm_names = [b.name for b in bpms]  # type: ignore[attr-defined]
        points._bpm_pvs = [(b.x_pv, b.y_pv) for b in bpms]  # type: ignore[attr-defined]
        if self.show_labels.get():
            for bpm, y in zip(bpms, marker_y):
                label = f"{bpm.name}\nX:{bpm.x_pv}\nY:{bpm.y_pv}" if bpm.x_pv or bpm.y_pv else bpm.name
                self.ax.annotate(label, (bpm.s_m, y), fontsize=6, rotation=45)
        self.ax.set_xlabel("s [m]")
        self.ax.set_ylabel("lattice function [m]" if has_dispersion or has_beta_x or has_beta_y else "BPM markers")
        if not (has_dispersion or has_beta_x or has_beta_y):
            self.ax.set_ylim(-1.0, 1.0)
            self.ax.text(0.02, 0.95, "Only BPM positions/PVs are configured; import optics later for beta/Dx.", transform=self.ax.transAxes, va="top")
        self.ax.grid(True, alpha=0.3)
        self.ax.legend()
        self.fig.tight_layout()
        self.canvas.draw_idle()

    def on_pick(self, event) -> None:
        artist = event.artist
        names = getattr(artist, "_bpm_names", None)
        if not names or not event.ind:
            return
        bpm = names[event.ind[0]]
        self.app.select_bpm(bpm)
        pvs = getattr(artist, "_bpm_pvs", [("", "")])
        x_pv, y_pv = pvs[event.ind[0]]
        self.app.session.event("lattice_bpm_selected", bpm=bpm, x_pv=x_pv, y_pv=y_pv)
        PlotWindow(self.app, [bpm])


class PVProbeWindow(tk.Toplevel):
    def __init__(self, app: "BPMViewer"):
        super().__init__(app.root)
        self.app = app
        self.title("Read-only PV probe / config helper")
        self.geometry("1000x650")

        top = ttk.Frame(self, padding=8)
        top.pack(fill=tk.X)
        ttk.Label(top, text="Paste or generate PVs, then probe them with short read-only timeouts.").pack(side=tk.LEFT)
        ttk.Button(top, text="Load selected BPM PVs", command=self.load_selected_bpm_pvs).pack(side=tk.RIGHT, padx=3)
        ttk.Button(top, text="Load tune/status PVs", command=self.load_status_pvs).pack(side=tk.RIGHT, padx=3)

        split = ttk.PanedWindow(self, orient=tk.VERTICAL)
        split.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        input_frame = ttk.LabelFrame(split, text="PV names to query", padding=6)
        self.input_text = tk.Text(input_frame, height=12)
        self.input_text.pack(fill=tk.BOTH, expand=True)
        split.add(input_frame, weight=1)

        actions = ttk.Frame(self, padding=(8, 0, 8, 8))
        actions.pack(fill=tk.X)
        ttk.Button(actions, text="caget probe", command=self.probe_caget).pack(side=tk.LEFT, padx=3)
        ttk.Button(actions, text="cainfo probe", command=self.probe_cainfo).pack(side=tk.LEFT, padx=3)
        ttk.Button(actions, text="Save current config", command=self.app.save_config).pack(side=tk.RIGHT, padx=3)

        output_frame = ttk.LabelFrame(split, text="Probe results", padding=6)
        self.output_text = tk.Text(output_frame, height=16)
        self.output_text.pack(fill=tk.BOTH, expand=True)
        split.add(output_frame, weight=2)

        self.load_selected_bpm_pvs()

    def _input_pvs(self) -> List[str]:
        pvs = []
        for line in self.input_text.get("1.0", tk.END).splitlines():
            pv = line.strip()
            if pv and not pv.startswith("#"):
                pvs.append(pv)
        return pvs

    def _replace_input(self, pvs: Sequence[str]) -> None:
        self.input_text.delete("1.0", tk.END)
        self.input_text.insert("1.0", "\n".join(dict.fromkeys(pvs)))

    def _append_output(self, text: str) -> None:
        self.output_text.insert(tk.END, text + "\n")
        self.output_text.see(tk.END)

    def load_selected_bpm_pvs(self) -> None:
        names = self.app.selected_names() or [bpm.name for bpm in self.app.known_bpms()]
        pvs: List[str] = []
        for bpm in names:
            pvs.append(pv_for(self.app.cfg, bpm, "scan"))
            for button in BUTTONS:
                pvs.append(pv_for(self.app.cfg, bpm, "i", button))
                pvs.append(pv_for(self.app.cfg, bpm, "q", button))
            info = self.app.bpm_by_name.get(bpm)
            if info:
                pvs.extend([pv for pv in (info.x_pv, info.y_pv) if pv])
        self._replace_input(pvs)

    def load_status_pvs(self) -> None:
        self.app.sync_runtime_config()
        pvs = [item.pv for item in self.app.cfg.tune_pvs if item.pv]
        pvs.extend(item.pv for item in self.app.cfg.status_pvs if item.pv)
        self._replace_input(pvs)

    def probe_caget(self) -> None:
        self.app.sync_runtime_config()
        pvs = self._input_pvs()
        self._append_output(f"\n# caget probe {time.strftime('%H:%M:%S')} ({len(pvs)} PVs)")
        for pv in pvs:
            try:
                value = self.app.backend.get_value(pv)
                text = str(value)
                if len(text) > 180:
                    text = text[:177] + "..."
                self._append_output(f"OK   {pv} = {text}")
                self.app.session.event("pv_probe_ok", method="caget", pv=pv, value=text)
            except Exception as exc:
                message = str(exc)
                self._append_output(f"ERR  {pv}: {message}")
                self.app.session.event("pv_probe_error", method="caget", pv=pv, error=message)

    def probe_cainfo(self) -> None:
        pvs = self._input_pvs()
        timeout = max(self.app.cfg.epics_scalar_timeout_s + 0.5, 0.75)
        self._append_output(f"\n# cainfo probe {time.strftime('%H:%M:%S')} ({len(pvs)} PVs)")
        for pv in pvs:
            try:
                result = subprocess.run(
                    ["cainfo", pv],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                )
                output = (result.stdout or result.stderr).strip().replace("\n", " | ")
                if len(output) > 260:
                    output = output[:257] + "..."
                prefix = "OK" if result.returncode == 0 else f"ERR({result.returncode})"
                self._append_output(f"{prefix:<8} {pv}: {output}")
                self.app.session.event("pv_probe_cainfo", pv=pv, returncode=result.returncode, output=output)
            except FileNotFoundError:
                self._append_output("ERR      cainfo command not found in PATH")
                break
            except Exception as exc:
                message = str(exc)
                self._append_output(f"ERR      {pv}: {message}")
                self.app.session.event("pv_probe_error", method="cainfo", pv=pv, error=message)


class BPMViewer:
    def __init__(
        self,
        root: tk.Tk,
        cfg: AppConfig,
        backend: Backend,
        mode_label: str,
        can_write_machine: bool,
        session: SessionLogger,
    ):
        self.root = root
        self.cfg = cfg
        self.backend = backend
        self.mode_label = mode_label
        self.can_write_machine = can_write_machine
        self.session = session
        self.root.title("MLS BPM I/Q Viewer — prototype")
        self.root.geometry("980x760")
        self.selected: List[str] = []
        self.status_after_id: Optional[str] = None
        self._last_status_values: Dict[str, str] = {}
        self._tune_values: Dict[str, Dict[str, object]] = {}
        self._last_tune_values: Dict[str, str] = {}
        self.bpm_by_name = {bpm.name: bpm for bpm in self.cfg.bpms}
        self.displayed_bpm_names: List[str] = []

        main = ttk.Frame(root, padding=8)
        main.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main, text="BPM overview", font=("TkDefaultFont", 12, "bold")).grid(row=0, column=0, sticky="w")
        self.search = tk.StringVar()
        ttk.Label(main, text="Filter BPM name or section:").grid(row=1, column=0, sticky="w")
        search_entry = ttk.Entry(main, textvariable=self.search, width=28)
        search_entry.grid(row=2, column=0, sticky="ew", pady=(2, 4))
        search_entry.bind("<KeyRelease>", lambda _e: self.populate_bpms())

        self.listbox = tk.Listbox(main, selectmode=tk.EXTENDED, exportselection=False)
        self.listbox.grid(row=3, column=0, rowspan=8, sticky="nsew")
        self.listbox.bind("<Double-Button-1>", lambda _e: self.open_selected())
        self.populate_bpms()

        buttons = ttk.Frame(main)
        buttons.grid(row=3, column=1, sticky="new", padx=(10, 0))
        ttk.Button(buttons, text="Open selected plot", command=self.open_selected).pack(fill=tk.X, pady=2)
        ttk.Button(buttons, text="Select all BPMs", command=self.select_all_bpms).pack(fill=tk.X, pady=2)
        ttk.Button(buttons, text="Select visible/filter", command=self.select_visible_bpms).pack(fill=tk.X, pady=2)
        ttk.Button(buttons, text="Select known BPMs", command=self.select_known_bpms).pack(fill=tk.X, pady=2)
        ttk.Button(buttons, text="Clear selection", command=self.clear_bpm_selection).pack(fill=tk.X, pady=2)
        ttk.Button(buttons, text="Open lattice viewer", command=lambda: LatticeWindow(self)).pack(fill=tk.X, pady=2)
        ttk.Button(buttons, text="PV probe / edit IDs", command=lambda: PVProbeWindow(self)).pack(fill=tk.X, pady=2)
        ttk.Separator(buttons).pack(fill=tk.X, pady=8)
        ttk.Button(buttons, text="Start TBT selected…", command=self.start_tbt_selected).pack(fill=tk.X, pady=2)
        ttk.Button(buttons, text="Stop TBT selected…", command=self.stop_tbt_selected).pack(fill=tk.X, pady=2)
        ttk.Button(buttons, text="Check TBT status", command=self.check_tbt_status).pack(fill=tk.X, pady=2)
        ttk.Separator(buttons).pack(fill=tk.X, pady=8)
        ttk.Button(buttons, text="Show planned TBT commands", command=self.preview_selected).pack(fill=tk.X, pady=2)
        ttk.Button(buttons, text="Refresh status PVs", command=self.refresh_status_pvs).pack(fill=tk.X, pady=2)
        ttk.Button(buttons, text="Save config", command=self.save_config).pack(fill=tk.X, pady=2)
        ttk.Button(buttons, text="Help / guide", command=self.show_help).pack(fill=tk.X, pady=2)
        ttk.Button(buttons, text="Quit", command=root.destroy).pack(fill=tk.X, pady=2)

        pv_box = ttk.LabelFrame(main, text="Editable PV templates", padding=8)
        pv_box.grid(row=11, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.pv_template_vars: Dict[str, tk.StringVar] = {}
        for row, key in enumerate(("scan", "synth_scan", "i", "q")):
            ttk.Label(pv_box, text=key).grid(row=row, column=0, sticky="w")
            var = tk.StringVar(value=self.cfg.pv_templates.get(key, ""))
            self.pv_template_vars[key] = var
            ttk.Entry(pv_box, textvariable=var).grid(row=row, column=1, sticky="ew", padx=6, pady=1)
        ttk.Button(pv_box, text="Apply templates", command=self.apply_pv_templates).grid(row=0, column=2, rowspan=4, sticky="ns")
        pv_box.columnconfigure(1, weight=1)

        self.tune_frame = ttk.LabelFrame(main, text="Read-only tune PVs for spectrum markers", padding=8)
        self.tune_frame.grid(row=12, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.tune_rows: List[Tuple[TunePV, tk.StringVar, tk.Label, tk.BooleanVar, tk.StringVar]] = []
        self.build_tune_rows()

        self.status_pv_frame = ttk.LabelFrame(main, text="Read-only excitation / status PVs", padding=8)
        self.status_pv_frame.grid(row=13, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.status_pv_rows: List[Tuple[StatusPV, tk.StringVar, tk.Label, tk.BooleanVar, tk.StringVar]] = []
        self.build_status_pv_rows()

        info = ttk.LabelFrame(main, text="Combination examples", padding=8)
        info.grid(row=14, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Label(
            info,
            justify=tk.LEFT,
            text=(
                "A, B, C, D: one button phasor\n"
                "A+B+C+D: common-mode sum → charge / arrival phase\n"
                "(A+B)-(C+D): example difference; adapt signs to actual button geometry\n"
                "mean(A,B,C,D): mean phasor\n"
                "Position-like plot shows Re(combination/sum), still uncalibrated"
            ),
        ).pack(anchor="w")

        self.status = tk.StringVar(value=mode_label)
        ttk.Label(main, textvariable=self.status).grid(row=15, column=0, columnspan=2, sticky="w", pady=8)

        main.rowconfigure(3, weight=1)
        main.columnconfigure(0, weight=1)
        self.status.set(f"{mode_label}. Optional tune/status PVs are not read on startup; click Refresh or open a spectrum.")
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def populate_bpms(self) -> None:
        q = self.search.get().strip().lower()
        self.listbox.delete(0, tk.END)
        self.displayed_bpm_names = []
        for bpm in self.cfg.bpms:
            haystack = f"{bpm.name} {bpm.section}".lower()
            if not q or q in haystack:
                marker = "*" if bpm.known_orbit_pvs else " "
                orbit = " orbit-ok" if bpm.known_orbit_pvs else ""
                display = f"{marker} {bpm.name:<10} {bpm.section:<3}{orbit}"
                self.listbox.insert(tk.END, display)
                self.displayed_bpm_names.append(bpm.name)

    def select_bpm(self, bpm: str) -> None:
        for i, name in enumerate(self.displayed_bpm_names):
            if name == bpm:
                self.listbox.selection_clear(0, tk.END)
                self.listbox.selection_set(i)
                self.listbox.see(i)
                break

    def selected_names(self) -> List[str]:
        return [self.displayed_bpm_names[i] for i in self.listbox.curselection()]

    def select_visible_bpms(self) -> None:
        self.listbox.selection_clear(0, tk.END)
        if self.displayed_bpm_names:
            self.listbox.selection_set(0, len(self.displayed_bpm_names) - 1)
        self.status.set(f"Selected {len(self.displayed_bpm_names)} visible BPM(s).")

    def select_all_bpms(self) -> None:
        self.search.set("")
        self.populate_bpms()
        self.select_visible_bpms()

    def clear_bpm_selection(self) -> None:
        self.listbox.selection_clear(0, tk.END)
        self.status.set("Cleared BPM selection.")

    def known_bpms(self) -> List[BPMInfo]:
        known = [bpm for bpm in self.cfg.bpms if bpm.known_orbit_pvs]
        return known or self.cfg.bpms[:4]

    def select_known_bpms(self) -> None:
        targets = {bpm.name for bpm in self.known_bpms()}
        self.listbox.selection_clear(0, tk.END)
        for index, name in enumerate(self.displayed_bpm_names):
            if name in targets:
                self.listbox.selection_set(index)
        self.status.set(f"Selected {len(targets)} known BPM candidate(s). Starred BPMs have orbit PVs seen in betagui/CS-Studio material.")

    def open_startup_plot(self, expression: str = "A; B; C; D; A+B+C+D") -> None:
        self.select_known_bpms()
        names = self.selected_names()[:2] or [bpm.name for bpm in self.known_bpms()[:2]]
        if not names:
            self.status.set("No BPMs configured; check bpm_config.json.")
            return
        self.session.event("startup_plot_opened", bpms=names, expression=expression, plot_kind="raw buttons")
        PlotWindow(self, names, expression=expression, plot_kind="raw buttons", show_tunes=False)

    def open_selected(self) -> None:
        names = self.selected_names()
        if not names:
            messagebox.showinfo("Select BPM", "Select one or more BPMs first.", parent=self.root)
            return
        PlotWindow(self, names)

    def apply_pv_templates(self) -> None:
        candidate = {key: var.get().strip() for key, var in self.pv_template_vars.items()}
        missing = [key for key, value in candidate.items() if not value]
        if missing:
            messagebox.showerror("PV template error", f"Empty template(s): {', '.join(missing)}", parent=self.root)
            return
        try:
            test_bpm = self.cfg.bpms[0].name if self.cfg.bpms else "BPM"
            for key in ("scan", "synth_scan", "i", "q"):
                candidate[key].format(bpm=test_bpm, button="a", BUTTON="A")
        except Exception as exc:
            messagebox.showerror("PV template error", f"Template formatting failed: {exc}", parent=self.root)
            return
        self.cfg.pv_templates.update(candidate)
        self.session.event("pv_templates_updated", templates=candidate)
        self.status.set("PV templates updated for newly refreshed/opened plots.")

    def sync_runtime_config(self) -> None:
        self.cfg.pv_templates.update({key: var.get().strip() for key, var in self.pv_template_vars.items()})
        for item, _value_var, _lamp, enabled_var, pv_var in self.tune_rows:
            item.enabled = bool(enabled_var.get())
            item.pv = pv_var.get().strip()
        for item, _value_var, _lamp, enabled_var, pv_var in self.status_pv_rows:
            item.enabled = bool(enabled_var.get())
            item.pv = pv_var.get().strip()

    def save_config(self) -> None:
        try:
            self.sync_runtime_config()
            path = self.cfg.save()
            self.session.event("config_saved", path=str(path))
            self.status.set(f"Saved config: {path}")
            messagebox.showinfo("Config saved", f"Saved editable PV IDs to:\n{path}", parent=self.root)
        except Exception as exc:
            message = str(exc)
            self.session.event("config_save_error", error=message)
            messagebox.showerror("Config save failed", message, parent=self.root)

    def show_help(self) -> None:
        text = (
            "Quick control-room flow\n\n"
            "1. Start safe: python3 bpm_iq_viewer.py --safe\n"
            "2. Select one or more BPMs. Starred BPMs are known from local betagui / CS-Studio material.\n"
            "3. Click Open selected plot. Use semicolon-separated expressions to overlay traces, e.g. A; B; C; D; A+B+C+D.\n"
            "4. For spectra, enable tune markers in the plot window. Tune PVs are read only when requested.\n"
            "5. If a PV is wrong, edit it in the table or PV probe, then Save config.\n"
            "6. Enable BPM logging only after reviewing Show planned enable commands. In --safe mode writes are blocked.\n\n"
            "Useful raw PV pattern\n"
            "{bpm}:signals:ddc_raw.SCAN = enable/scan control\n"
            "{bpm}:signals:ddc_raw.Ia/Qa ... Id/Qd = raw complex button turns\n\n"
            "Math hints\n"
            "A+B+C+D is common mode / charge / arrival phase candidate.\n"
            "(A+B)-(C+D) and (A+D)-(B+C) are uncalibrated transverse-like differences; adapt signs to real button geometry.\n"
            "Magnitude spectra use |phasor|; phase spectra use unwrap(angle(phasor))."
        )
        win = tk.Toplevel(self.root)
        win.title("BPM I/Q viewer help")
        win.geometry("760x560")
        box = tk.Text(win, wrap="word")
        box.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        box.insert("1.0", text)
        box.configure(state=tk.DISABLED)

    def build_status_pv_rows(self) -> None:
        for child in self.status_pv_frame.winfo_children():
            child.destroy()
        self.status_pv_rows = []
        if not self.cfg.status_pvs:
            ttk.Label(self.status_pv_frame, text="No status PVs configured yet. Add status_pvs entries in bpm_config.json.").grid(row=0, column=0, sticky="w")
            return
        headers = ("Use", "Status", "Label", "PV", "Direction", "Excitation", "Value")
        for col, text in enumerate(headers):
            ttk.Label(self.status_pv_frame, text=text).grid(row=0, column=col, sticky="w", padx=3)
        for row, item in enumerate(self.cfg.status_pvs, start=1):
            enabled_var = tk.BooleanVar(value=item.enabled)
            ttk.Checkbutton(self.status_pv_frame, variable=enabled_var).grid(row=row, column=0, sticky="w", padx=3)
            lamp = tk.Label(self.status_pv_frame, text="?", width=3, relief=tk.GROOVE, bg="#d9d9d9")
            lamp.grid(row=row, column=1, sticky="w", padx=3, pady=1)
            value_var = tk.StringVar(value="not read" if item.enabled else "disabled")
            pv_var = tk.StringVar(value=item.pv)
            ttk.Label(self.status_pv_frame, text=item.label).grid(row=row, column=2, sticky="w", padx=3)
            entry = ttk.Entry(self.status_pv_frame, textvariable=pv_var, width=34)
            entry.grid(row=row, column=3, sticky="ew", padx=3)
            entry.bind("<FocusOut>", lambda _e, cfg=item, var=pv_var: setattr(cfg, "pv", var.get().strip()))
            ttk.Label(self.status_pv_frame, text=item.direction).grid(row=row, column=4, sticky="w", padx=3)
            ttk.Label(self.status_pv_frame, text=item.excitation).grid(row=row, column=5, sticky="w", padx=3)
            ttk.Label(self.status_pv_frame, textvariable=value_var).grid(row=row, column=6, sticky="w", padx=3)
            self.status_pv_rows.append((item, value_var, lamp, enabled_var, pv_var))
        self.status_pv_frame.columnconfigure(3, weight=1)

    def build_tune_rows(self) -> None:
        for child in self.tune_frame.winfo_children():
            child.destroy()
        self.tune_rows = []
        if not self.cfg.tune_pvs:
            ttk.Label(self.tune_frame, text="No tune PVs configured.").grid(row=0, column=0, sticky="w")
            return
        headers = ("Use", "Status", "Label", "PV", "Unit", "Value")
        for col, text in enumerate(headers):
            ttk.Label(self.tune_frame, text=text).grid(row=0, column=col, sticky="w", padx=3)
        for row, item in enumerate(self.cfg.tune_pvs, start=1):
            enabled_var = tk.BooleanVar(value=item.enabled)
            ttk.Checkbutton(self.tune_frame, variable=enabled_var).grid(row=row, column=0, sticky="w", padx=3)
            lamp = tk.Label(self.tune_frame, text="?", width=3, relief=tk.GROOVE, bg="#d9d9d9")
            lamp.grid(row=row, column=1, sticky="w", padx=3, pady=1)
            value_var = tk.StringVar(value="not read" if item.enabled else "disabled")
            pv_var = tk.StringVar(value=item.pv)
            ttk.Label(self.tune_frame, text=item.label).grid(row=row, column=2, sticky="w", padx=3)
            entry = ttk.Entry(self.tune_frame, textvariable=pv_var, width=34)
            entry.grid(row=row, column=3, sticky="ew", padx=3)
            entry.bind("<FocusOut>", lambda _e, cfg=item, var=pv_var: setattr(cfg, "pv", var.get().strip()))
            ttk.Label(self.tune_frame, text=item.unit).grid(row=row, column=4, sticky="w", padx=3)
            ttk.Label(self.tune_frame, textvariable=value_var).grid(row=row, column=5, sticky="w", padx=3)
            self.tune_rows.append((item, value_var, lamp, enabled_var, pv_var))
        self.tune_frame.columnconfigure(3, weight=1)

    def refresh_tunes(self) -> None:
        self.sync_runtime_config()
        for item, value_var, lamp, enabled_var, _pv_var in self.tune_rows:
            if not enabled_var.get():
                value_var.set("disabled")
                lamp.configure(text="SKIP", bg="#c9c9c9")
                self._tune_values.pop(item.label, None)
                continue
            try:
                value = self.backend.get_value(item.pv)
                converted = tune_value_to_frequency(value, self.cfg.sample_rate_hz, item.unit)
                if converted is None:
                    raise RuntimeError(f"Cannot convert tune value {value!r}")
                freq, tune = converted
                text = f"{value} -> {freq:.3g} Hz, Q={tune:.5g}"
                value_var.set(text)
                lamp.configure(text="OK", bg=item.color)
                self._tune_values[item.label] = {
                    "value": value,
                    "unit": item.unit,
                    "color": item.color,
                    "harmonics": item.harmonics,
                }
                if self._last_tune_values.get(item.pv) != text:
                    self.session.event("tune_pv_read", label=item.label, pv=item.pv, value=str(value), frequency_hz=freq, tune=tune)
                    self._last_tune_values[item.pv] = text
            except Exception as exc:
                message = str(exc)
                value_var.set(message)
                lamp.configure(text="ERR", bg="#d65f5f")
                self._tune_values.pop(item.label, None)
                error_marker = f"ERROR:{message}"
                if self._last_tune_values.get(item.pv) != error_marker:
                    self.session.event("tune_pv_error", label=item.label, pv=item.pv, error=message)
                    self._last_tune_values[item.pv] = error_marker

    def current_tune_markers(self, include_harmonics: bool) -> List[Tuple[float, str, str]]:
        self.refresh_tunes()
        return tune_markers_from_values(self._tune_values, self.cfg.sample_rate_hz, include_harmonics)

    def refresh_status_pvs(self) -> None:
        self.refresh_tunes()
        for item, value_var, lamp, enabled_var, _pv_var in self.status_pv_rows:
            if not enabled_var.get():
                value_var.set("disabled")
                lamp.configure(text="SKIP", bg="#c9c9c9")
                continue
            try:
                value = self.backend.get_value(item.pv)
                text = str(value)
                is_on = text in item.on_values
                lamp.configure(text="ON" if is_on else "OFF", bg="#44aa66" if is_on else "#c9c9c9")
                value_var.set(text)
                if self._last_status_values.get(item.pv) != text:
                    self.session.event("status_pv_read", label=item.label, pv=item.pv, value=text, is_on=is_on)
                    self._last_status_values[item.pv] = text
            except Exception as exc:
                lamp.configure(text="ERR", bg="#d65f5f")
                message = str(exc)
                value_var.set(message)
                error_marker = f"ERROR:{message}"
                if self._last_status_values.get(item.pv) != error_marker:
                    self.session.event("status_pv_error", label=item.label, pv=item.pv, error=message)
                    self._last_status_values[item.pv] = error_marker
        self.status.set("Status/tune PV refresh finished. Disabled rows were skipped.")

    def close(self) -> None:
        if self.status_after_id:
            self.root.after_cancel(self.status_after_id)
        self.root.destroy()

    def tbt_commands(self, names: Sequence[str], enabled: bool) -> List[Tuple[str, object]]:
        return tbt_scan_commands(self.cfg, names, enabled)

    def selected_or_all_names(self) -> List[str]:
        names = self.selected_names()
        return names or [b.name for b in self.cfg.bpms]

    def preview_selected(self) -> None:
        names = self.selected_or_all_names()
        commands = self.tbt_commands(names, enabled=True)
        self.session.event("preview_enable_commands", commands=[{"pv": pv, "value": value} for pv, value in commands])
        text = "\n".join(f"caput {pv!r} {value!r}" for pv, value in commands)
        win = tk.Toplevel(self.root)
        win.title("Planned EPICS writes")
        box = tk.Text(win, width=100, height=min(30, len(commands) + 3))
        box.pack(fill=tk.BOTH, expand=True)
        box.insert("1.0", text)
        box.configure(state=tk.DISABLED)

    def start_tbt_selected(self) -> None:
        names = self.selected_names()
        if not names:
            messagebox.showinfo("Select BPM", "Select one or more BPMs first.", parent=self.root)
            return
        self.confirm_and_write(self.tbt_commands(names, enabled=True), action="start TBT raw logging")

    def stop_tbt_selected(self) -> None:
        names = self.selected_names()
        if not names:
            messagebox.showinfo("Select BPM", "Select one or more BPMs first.", parent=self.root)
            return
        self.confirm_and_write(self.tbt_commands(names, enabled=False), action="stop TBT raw logging")

    def check_tbt_status(self) -> None:
        names = self.selected_or_all_names()
        lines: List[str] = []
        self.sync_runtime_config()
        for bpm in names:
            for key in ("scan", "synth_scan"):
                if key not in self.cfg.pv_templates:
                    continue
                pv = pv_for(self.cfg, bpm, key)
                try:
                    value = self.backend.get_value(pv)
                    lines.append(f"{pv}: {value}")
                    self.session.event("tbt_status_read", bpm=bpm, pv=pv, value=str(value))
                except Exception as exc:
                    lines.append(f"{pv}: ERROR {exc}")
                    self.session.event("tbt_status_error", bpm=bpm, pv=pv, error=str(exc))
        win = tk.Toplevel(self.root)
        win.title("TBT raw logging status")
        box = tk.Text(win, width=110, height=min(34, max(8, len(lines) + 2)))
        box.pack(fill=tk.BOTH, expand=True)
        box.insert("1.0", "\n".join(lines))
        box.configure(state=tk.DISABLED)
        self.status.set(f"Checked TBT status for {len(names)} BPM(s).")

    def confirm_and_write(self, commands: Sequence[Tuple[str, object]], action: str = "write") -> None:
        preview = "\n".join(f"{pv} <- {value!r}" for pv, value in commands[:12])
        if len(commands) > 12:
            preview += f"\n… and {len(commands)-12} more"
        if not self.can_write_machine:
            self.session.event("blocked_write_attempt", commands=[{"pv": pv, "value": value} for pv, value in commands])
            messagebox.showwarning("Writes blocked", "Machine writes are blocked in this mode.\n\nPlanned writes:\n" + preview, parent=self.root)
            return
        ok = messagebox.askyesno(
            "Confirm EPICS writes",
            f"This will {action} on the machine. Review the exact commands:\n\n" + preview + "\n\nProceed?",
            icon="warning",
            parent=self.root,
        )
        if not ok:
            self.session.event("write_cancelled", commands=[{"pv": pv, "value": value} for pv, value in commands])
            self.status.set("Write cancelled")
            return
        errors = []
        for pv, value in commands:
            try:
                self.backend.put(pv, value)
                self.session.event("caput_success", pv=pv, value=value)
            except Exception as exc:
                message = str(exc)
                errors.append(f"{pv}: {message}")
                self.session.event("caput_error", pv=pv, value=value, error=message)
        if errors:
            messagebox.showerror("Some writes failed", "\n".join(errors[:20]), parent=self.root)
            self.status.set(f"Completed with {len(errors)} error(s)")
        else:
            self.status.set(f"Completed {len(commands)} EPICS write(s)")


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Minimal live BPM I/Q viewer")
    p.add_argument("--config", type=Path, default=Path(__file__).with_name("bpm_config.json"))
    p.add_argument("--safe", action="store_true", help="use live EPICS reads but block all machine writes")
    p.add_argument("--demo", action="store_true", help="use synthetic waveforms; this is the default unless --live or --safe is given")
    p.add_argument("--live", action="store_true", help="use live EPICS reads")
    p.add_argument("--allow-writes", action="store_true", help="allow confirmed EPICS writes; requires --live and is blocked by --safe")
    p.add_argument("--bpm", action="append", default=[], help="open plot for BPM at startup; repeatable")
    p.add_argument("--combination", default="A+B+C+D", help="startup combination expression")
    p.add_argument("--no-startup-plot", action="store_true", help="do not auto-select known BPMs or open the initial raw-button plot")
    p.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_ROOT, help="directory for session logs")
    p.add_argument("--log-level", default="INFO")
    return p


def configure_logging(log_root: Path, log_level: str) -> SessionLogger:
    timestamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir = log_root.expanduser().resolve() / f"session_{timestamp}"
    session_dir.mkdir(parents=True, exist_ok=True)
    level = getattr(logging, log_level.upper(), logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    file_handler = logging.FileHandler(session_dir / "session.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)
    root_logger.addHandler(file_handler)
    logging.info("Session log directory: %s", session_dir)
    return SessionLogger(session_dir)


def main() -> int:
    args = build_arg_parser().parse_args()
    session = configure_logging(args.log_dir, args.log_level)
    cfg = AppConfig.load(args.config)
    if args.allow_writes and (args.safe or args.demo or not args.live):
        raise SystemExit("--allow-writes requires --live and cannot be combined with --safe or --demo")
    use_live = args.live or args.safe
    use_demo = args.demo or not use_live
    backend: Backend = (
        EpicsBackend(array_timeout=cfg.epics_array_timeout_s, scalar_timeout=cfg.epics_scalar_timeout_s)
        if use_live
        else DemoBackend(fs=cfg.sample_rate_hz)
    )
    can_write_machine = bool(args.allow_writes and use_live)
    if use_demo:
        mode_label = "DEMO: synthetic data, no machine access"
    elif can_write_machine:
        mode_label = "LIVE WRITE-CAPABLE: every machine write asks for confirmation"
    else:
        mode_label = "LIVE SAFE: EPICS reads allowed, machine writes blocked"
    session.event(
        "startup",
        mode=mode_label,
        config=str(args.config),
        sample_rate_hz=cfg.sample_rate_hz,
        bpm_count=len(cfg.bpms),
        log_dir=str(session.session_dir),
    )
    root = tk.Tk()
    app = BPMViewer(root, cfg, backend, mode_label=mode_label, can_write_machine=can_write_machine, session=session)
    if args.bpm:
        root.after(150, lambda: PlotWindow(app, args.bpm, expression=args.combination, show_tunes=False))
    elif not args.no_startup_plot:
        root.after(150, lambda: app.open_startup_plot())
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
