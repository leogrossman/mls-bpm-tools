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
    dispersion_x_m: float = 0.0
    beta_x_m: float = math.nan
    beta_y_m: float = math.nan
    modes: List[str] = field(default_factory=lambda: ["user", "low_alpha"])


@dataclass
class StatusPV:
    label: str
    pv: str
    on_values: List[str] = field(default_factory=lambda: ["1", "ON", "On", "on"])
    direction: str = ""
    excitation: str = ""


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
    sample_rate_hz: float = DEFAULT_SAMPLE_RATE
    ddc_frequency_hz: Optional[float] = None
    refresh_ms: int = 1000

    @classmethod
    def load(cls, path: Path) -> "AppConfig":
        raw = json.loads(path.read_text())
        bpms = [BPMInfo(**item) for item in raw["bpms"]]
        return cls(
            bpms=bpms,
            pv_templates=raw["pv_templates"],
            status_pvs=[StatusPV(**item) for item in raw.get("status_pvs", [])],
            sample_rate_hz=float(raw.get("sample_rate_hz", DEFAULT_SAMPLE_RATE)),
            ddc_frequency_hz=raw.get("ddc_frequency_hz"),
            refresh_ms=int(raw.get("refresh_ms", 1000)),
        )


class Backend:
    def get_array(self, pv: str) -> np.ndarray:
        raise NotImplementedError

    def get_value(self, pv: str) -> object:
        raise NotImplementedError

    def put(self, pv: str, value: object) -> None:
        raise NotImplementedError


class EpicsBackend(Backend):
    def __init__(self, timeout: float = 2.0):
        if epics is None:
            raise RuntimeError("pyepics is not installed")
        self.timeout = timeout

    def get_array(self, pv: str) -> np.ndarray:
        value = epics.caget(pv, timeout=self.timeout)
        if value is None:
            raise RuntimeError(f"No value returned from {pv}")
        arr = np.asarray(value, dtype=float).ravel()
        if arr.size == 0:
            raise RuntimeError(f"Empty waveform from {pv}")
        return arr

    def get_value(self, pv: str) -> object:
        value = epics.caget(pv, timeout=self.timeout)
        if value is None:
            raise RuntimeError(f"No value returned from {pv}")
        return value

    def put(self, pv: str, value: object) -> None:
        ok = epics.caput(pv, value, wait=True, timeout=self.timeout)
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


def combination_expression(data: Mapping[str, np.ndarray], expr: str) -> np.ndarray:
    """Evaluate a deliberately tiny safe expression language.

    Examples: A, A+B+C+D, (A+B)-(C+D), A-B, mean(A,B,C,D)
    """
    expr = re.sub(r"\b([abcd])\b", lambda match: match.group(1).upper(), expr.strip())
    env = {k: np.asarray(v) for k, v in data.items()}
    env["mean"] = lambda *args: np.mean(np.vstack(args), axis=0)
    allowed = set("ABCDmean()+-*/, .")
    if any(ch not in allowed for ch in expr):
        raise ValueError("Expression supports only A/B/C/D, mean(), +, -, *, / and parentheses")
    try:
        value = eval(expr, {"__builtins__": {}}, env)  # noqa: S307 - restricted grammar/env
    except Exception as exc:
        raise ValueError(f"Invalid combination: {expr}") from exc
    arr = np.asarray(value, dtype=complex).ravel()
    if arr.size == 0:
        raise ValueError("Combination produced no data")
    return arr


def spectrum(x: np.ndarray, fs: float) -> Tuple[np.ndarray, np.ndarray]:
    x = np.asarray(x, dtype=float)
    x = x - np.nanmean(x)
    if x.size > 1:
        p = np.polyfit(np.arange(x.size), x, 1)
        x = x - np.polyval(p, np.arange(x.size))
    win = np.hanning(x.size)
    spec = np.fft.rfft(np.nan_to_num(x) * win)
    freq = np.fft.rfftfreq(x.size, d=1.0 / fs)
    psd = (np.abs(spec) ** 2) / max(np.sum(win**2), 1.0)
    return freq, psd


class PlotWindow(tk.Toplevel):
    def __init__(self, app: "BPMViewer", bpm_names: Sequence[str], expression: str = "A+B+C+D"):
        super().__init__(app.root)
        self.app = app
        self.bpm_names = list(bpm_names)
        self.title("BPM I/Q plots — " + ", ".join(self.bpm_names))
        self.geometry("1180x760")
        self.running = True
        self.after_id: Optional[str] = None

        controls = ttk.Frame(self)
        controls.pack(side=tk.TOP, fill=tk.X, padx=6, pady=4)
        ttk.Label(controls, text="Combination:").pack(side=tk.LEFT)
        self.expr = tk.StringVar(value=expression)
        ttk.Entry(controls, textvariable=self.expr, width=24).pack(side=tk.LEFT, padx=4)
        ttk.Label(controls, text="Plot:").pack(side=tk.LEFT, padx=(12, 2))
        self.plot_kind = tk.StringVar(value="phase+spectrum")
        ttk.Combobox(
            controls,
            textvariable=self.plot_kind,
            values=("I/Q", "raw buttons", "magnitude", "phase", "phase+spectrum", "position-like", "all"),
            state="readonly",
            width=16,
        ).pack(side=tk.LEFT)
        self.live = tk.BooleanVar(value=True)
        ttk.Checkbutton(controls, text="Live", variable=self.live).pack(side=tk.LEFT, padx=10)
        ttk.Button(controls, text="Refresh now", command=self.refresh).pack(side=tk.LEFT)
        ttk.Button(controls, text="Pause", command=self.toggle_pause).pack(side=tk.LEFT, padx=4)
        ttk.Button(controls, text="Save data", command=self.save_data).pack(side=tk.LEFT, padx=4)

        self.status = tk.StringVar(value="Ready")
        ttk.Label(self, textvariable=self.status, anchor="w").pack(fill=tk.X, padx=6)

        self.figure = Figure(figsize=(10, 7), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.figure, master=self)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        NavigationToolbar2Tk(self.canvas, self).update()
        self.last_data: Dict[str, Dict[str, np.ndarray]] = {}
        self.last_errors: Dict[str, str] = {}
        self.protocol("WM_DELETE_WINDOW", self.close)
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
        self.figure.clear()
        if kind == "all":
            axes = [self.figure.add_subplot(221), self.figure.add_subplot(222), self.figure.add_subplot(223), self.figure.add_subplot(224)]
        elif kind == "phase+spectrum":
            axes = [self.figure.add_subplot(211), self.figure.add_subplot(212)]
        else:
            axes = [self.figure.add_subplot(111)]

        expr_text = self.expr.get().strip()
        buttons_needed = normalize_button_tokens(expr_text)
        if kind in ("position-like", "raw buttons"):
            buttons_needed = list(BUTTONS)
        self.last_data = {}
        self.last_errors = {}
        for bpm in self.bpm_names:
            try:
                phasors = read_button_phasors(self.app.backend, self.app.cfg, bpm, buttons_needed)
                z = combination_expression(phasors, expr_text)
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
            phase = np.unwrap(np.angle(z))
            mag = np.abs(z)
            self.last_data[bpm] = {**phasors, "combined": z, "phase": phase, "magnitude": mag}
            turns = np.arange(z.size)

            if kind == "I/Q":
                axes[0].plot(z.real, z.imag, ".-", ms=2, label=bpm)
                axes[0].set_xlabel("I")
                axes[0].set_ylabel("Q")
            elif kind == "raw buttons":
                for button in BUTTONS:
                    raw = phasors[button]
                    axes[0].plot(turns, raw.real, label=f"{bpm} {button} I", alpha=0.75)
                    axes[0].plot(turns, raw.imag, label=f"{bpm} {button} Q", alpha=0.75, linestyle="--")
                axes[0].set_ylabel("raw I/Q [arb.]")
            elif kind == "magnitude":
                axes[0].plot(turns, mag, label=bpm)
                axes[0].set_ylabel("|phasor|")
            elif kind == "phase":
                axes[0].plot(turns, phase, label=bpm)
                axes[0].set_ylabel("unwrapped phase [rad]")
            elif kind == "position-like":
                denom = phasors.get("A", 0) + phasors.get("B", 0) + phasors.get("C", 0) + phasors.get("D", 0)
                with np.errstate(divide="ignore", invalid="ignore"):
                    value = np.real(z / denom) if np.ndim(denom) else np.real(z)
                axes[0].plot(turns, value, label=bpm)
                axes[0].set_ylabel("Re(combination / sum), uncalibrated")
            elif kind == "phase+spectrum":
                axes[0].plot(turns, phase, label=bpm)
                f, p = spectrum(phase, self.app.cfg.sample_rate_hz)
                axes[1].semilogy(f, np.maximum(p, 1e-30), label=bpm)
                axes[0].set_ylabel("unwrapped phase [rad]")
                axes[1].set_xlabel("frequency [Hz]")
                axes[1].set_ylabel("phase PSD [arb.]")
                axes[1].set_xlim(0, self.app.cfg.sample_rate_hz / 2)
            else:  # all
                axes[0].plot(turns, z.real, label=bpm)
                axes[1].plot(turns, z.imag, label=bpm)
                axes[2].plot(turns, phase, label=bpm)
                f, p = spectrum(phase, self.app.cfg.sample_rate_hz)
                axes[3].semilogy(f, np.maximum(p, 1e-30), label=bpm)
                axes[0].set_title("I")
                axes[1].set_title("Q")
                axes[2].set_title("phase")
                axes[3].set_title("phase spectrum")

        if not self.last_data:
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

        for ax in axes:
            ax.grid(True, alpha=0.3)
            handles, _labels = ax.get_legend_handles_labels()
            if handles:
                ax.legend(loc="best")
        self.figure.tight_layout()
        self.canvas.draw_idle()
        suffix = f"; {len(self.last_errors)} error(s)" if self.last_errors else ""
        self.status.set(f"Updated {time.strftime('%H:%M:%S')} - expression {self.expr.get()}{suffix}")


class LatticeWindow(tk.Toplevel):
    def __init__(self, app: "BPMViewer"):
        super().__init__(app.root)
        self.app = app
        self.title("Clickable BPM lattice overview")
        self.geometry("1100x520")
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=6, pady=4)
        ttk.Label(top, text="Optics mode:").pack(side=tk.LEFT)
        self.mode = tk.StringVar(value="user")
        ttk.Combobox(top, textvariable=self.mode, values=("user", "low_alpha"), state="readonly", width=14).pack(side=tk.LEFT, padx=4)
        ttk.Label(top, text="Prototype: positions/functions come from bpm_config.json; replace with exported lattice data.").pack(side=tk.LEFT, padx=12)

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
        self.ax.plot(s, d, "-", alpha=0.5, label="Dx [m]")
        points = self.ax.scatter(s, d, picker=True, pickradius=8, label="BPM")
        points._bpm_names = [b.name for b in bpms]  # type: ignore[attr-defined]
        for bpm in bpms:
            self.ax.annotate(bpm.name, (bpm.s_m, bpm.dispersion_x_m), fontsize=7, rotation=45)
        self.ax.set_xlabel("s [m]")
        self.ax.set_ylabel("horizontal dispersion [m]")
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
        PlotWindow(self.app, [bpm])


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

        main = ttk.Frame(root, padding=8)
        main.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main, text="BPMs", font=("TkDefaultFont", 12, "bold")).grid(row=0, column=0, sticky="w")
        self.search = tk.StringVar()
        search_entry = ttk.Entry(main, textvariable=self.search, width=28)
        search_entry.grid(row=1, column=0, sticky="ew", pady=(2, 4))
        search_entry.bind("<KeyRelease>", lambda _e: self.populate_bpms())

        self.listbox = tk.Listbox(main, selectmode=tk.EXTENDED, exportselection=False)
        self.listbox.grid(row=2, column=0, rowspan=8, sticky="nsew")
        self.listbox.bind("<Double-Button-1>", lambda _e: self.open_selected())
        self.populate_bpms()

        buttons = ttk.Frame(main)
        buttons.grid(row=2, column=1, sticky="new", padx=(10, 0))
        ttk.Button(buttons, text="Open selected plot", command=self.open_selected).pack(fill=tk.X, pady=2)
        ttk.Button(buttons, text="Open lattice viewer", command=lambda: LatticeWindow(self)).pack(fill=tk.X, pady=2)
        ttk.Separator(buttons).pack(fill=tk.X, pady=8)
        ttk.Button(buttons, text="Enable selected BPM(s)…", command=self.enable_selected).pack(fill=tk.X, pady=2)
        ttk.Button(buttons, text="Enable ALL BPMs…", command=self.enable_all).pack(fill=tk.X, pady=2)
        ttk.Separator(buttons).pack(fill=tk.X, pady=8)
        ttk.Button(buttons, text="Show planned enable commands", command=self.preview_selected).pack(fill=tk.X, pady=2)
        ttk.Button(buttons, text="Refresh status PVs", command=self.refresh_status_pvs).pack(fill=tk.X, pady=2)
        ttk.Button(buttons, text="Quit", command=root.destroy).pack(fill=tk.X, pady=2)

        pv_box = ttk.LabelFrame(main, text="Editable PV templates", padding=8)
        pv_box.grid(row=10, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.pv_template_vars: Dict[str, tk.StringVar] = {}
        for row, key in enumerate(("scan", "i", "q")):
            ttk.Label(pv_box, text=key).grid(row=row, column=0, sticky="w")
            var = tk.StringVar(value=self.cfg.pv_templates.get(key, ""))
            self.pv_template_vars[key] = var
            ttk.Entry(pv_box, textvariable=var).grid(row=row, column=1, sticky="ew", padx=6, pady=1)
        ttk.Button(pv_box, text="Apply templates", command=self.apply_pv_templates).grid(row=0, column=2, rowspan=3, sticky="ns")
        pv_box.columnconfigure(1, weight=1)

        self.status_pv_frame = ttk.LabelFrame(main, text="Read-only excitation / status PVs", padding=8)
        self.status_pv_frame.grid(row=11, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.status_pv_rows: List[Tuple[StatusPV, tk.StringVar, tk.Label]] = []
        self.build_status_pv_rows()

        info = ttk.LabelFrame(main, text="Combination examples", padding=8)
        info.grid(row=12, column=0, columnspan=2, sticky="ew", pady=(10, 0))
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
        ttk.Label(main, textvariable=self.status).grid(row=13, column=0, columnspan=2, sticky="w", pady=8)

        main.rowconfigure(2, weight=1)
        main.columnconfigure(0, weight=1)
        self.refresh_status_pvs()
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def populate_bpms(self) -> None:
        q = self.search.get().strip().lower()
        self.listbox.delete(0, tk.END)
        for bpm in self.cfg.bpms:
            if not q or q in bpm.name.lower():
                self.listbox.insert(tk.END, bpm.name)

    def select_bpm(self, bpm: str) -> None:
        for i in range(self.listbox.size()):
            if self.listbox.get(i) == bpm:
                self.listbox.selection_clear(0, tk.END)
                self.listbox.selection_set(i)
                self.listbox.see(i)
                break

    def selected_names(self) -> List[str]:
        return [self.listbox.get(i) for i in self.listbox.curselection()]

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
            for key in ("scan", "i", "q"):
                candidate[key].format(bpm=test_bpm, button="a", BUTTON="A")
        except Exception as exc:
            messagebox.showerror("PV template error", f"Template formatting failed: {exc}", parent=self.root)
            return
        self.cfg.pv_templates.update(candidate)
        self.session.event("pv_templates_updated", templates=candidate)
        self.status.set("PV templates updated for newly refreshed/opened plots.")

    def build_status_pv_rows(self) -> None:
        for child in self.status_pv_frame.winfo_children():
            child.destroy()
        self.status_pv_rows = []
        if not self.cfg.status_pvs:
            ttk.Label(self.status_pv_frame, text="No status PVs configured yet. Add status_pvs entries in bpm_config.json.").grid(row=0, column=0, sticky="w")
            return
        headers = ("Status", "Label", "PV", "Direction", "Excitation", "Value")
        for col, text in enumerate(headers):
            ttk.Label(self.status_pv_frame, text=text).grid(row=0, column=col, sticky="w", padx=3)
        for row, item in enumerate(self.cfg.status_pvs, start=1):
            lamp = tk.Label(self.status_pv_frame, text="?", width=3, relief=tk.GROOVE, bg="#d9d9d9")
            lamp.grid(row=row, column=0, sticky="w", padx=3, pady=1)
            value_var = tk.StringVar(value="not read")
            pv_var = tk.StringVar(value=item.pv)
            ttk.Label(self.status_pv_frame, text=item.label).grid(row=row, column=1, sticky="w", padx=3)
            entry = ttk.Entry(self.status_pv_frame, textvariable=pv_var, width=34)
            entry.grid(row=row, column=2, sticky="ew", padx=3)
            entry.bind("<FocusOut>", lambda _e, cfg=item, var=pv_var: setattr(cfg, "pv", var.get().strip()))
            ttk.Label(self.status_pv_frame, text=item.direction).grid(row=row, column=3, sticky="w", padx=3)
            ttk.Label(self.status_pv_frame, text=item.excitation).grid(row=row, column=4, sticky="w", padx=3)
            ttk.Label(self.status_pv_frame, textvariable=value_var).grid(row=row, column=5, sticky="w", padx=3)
            self.status_pv_rows.append((item, value_var, lamp))
        self.status_pv_frame.columnconfigure(2, weight=1)

    def refresh_status_pvs(self) -> None:
        for item, value_var, lamp in self.status_pv_rows:
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
        if self.status_after_id:
            self.root.after_cancel(self.status_after_id)
        self.status_after_id = self.root.after(max(self.cfg.refresh_ms, 1000), self.refresh_status_pvs)

    def close(self) -> None:
        if self.status_after_id:
            self.root.after_cancel(self.status_after_id)
        self.root.destroy()

    def enable_commands(self, names: Sequence[str]) -> List[Tuple[str, object]]:
        return [(pv_for(self.cfg, bpm, "scan"), "I/O Intr") for bpm in names]

    def preview_selected(self) -> None:
        names = self.selected_names()
        if not names:
            names = [b.name for b in self.cfg.bpms]
        commands = self.enable_commands(names)
        self.session.event("preview_enable_commands", commands=[{"pv": pv, "value": value} for pv, value in commands])
        text = "\n".join(f"caput {pv!r} {value!r}" for pv, value in commands)
        win = tk.Toplevel(self.root)
        win.title("Planned EPICS writes")
        box = tk.Text(win, width=100, height=min(30, len(commands) + 3))
        box.pack(fill=tk.BOTH, expand=True)
        box.insert("1.0", text)
        box.configure(state=tk.DISABLED)

    def enable_selected(self) -> None:
        names = self.selected_names()
        if not names:
            messagebox.showinfo("Select BPM", "Select one or more BPMs first.", parent=self.root)
            return
        self.confirm_and_write(self.enable_commands(names))

    def enable_all(self) -> None:
        self.confirm_and_write(self.enable_commands([b.name for b in self.cfg.bpms]))

    def confirm_and_write(self, commands: Sequence[Tuple[str, object]]) -> None:
        preview = "\n".join(f"{pv} <- {value!r}" for pv, value in commands[:12])
        if len(commands) > 12:
            preview += f"\n… and {len(commands)-12} more"
        if not self.can_write_machine:
            self.session.event("blocked_write_attempt", commands=[{"pv": pv, "value": value} for pv, value in commands])
            messagebox.showwarning("Writes blocked", "Machine writes are blocked in this mode.\n\nPlanned writes:\n" + preview, parent=self.root)
            return
        ok = messagebox.askyesno(
            "Confirm EPICS writes",
            "This will write to the machine. Review the exact commands:\n\n" + preview + "\n\nProceed?",
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
            self.status.set(f"Enabled {len(commands)} BPM record(s)")


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Minimal live BPM I/Q viewer")
    p.add_argument("--config", type=Path, default=Path(__file__).with_name("bpm_config.json"))
    p.add_argument("--safe", action="store_true", help="use live EPICS reads but block all machine writes")
    p.add_argument("--demo", action="store_true", help="use synthetic waveforms; this is the default unless --live or --safe is given")
    p.add_argument("--live", action="store_true", help="use live EPICS reads")
    p.add_argument("--allow-writes", action="store_true", help="allow confirmed EPICS writes; requires --live and is blocked by --safe")
    p.add_argument("--bpm", action="append", default=[], help="open plot for BPM at startup; repeatable")
    p.add_argument("--combination", default="A+B+C+D", help="startup combination expression")
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
    backend: Backend = EpicsBackend() if use_live else DemoBackend(fs=cfg.sample_rate_hz)
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
        root.after(150, lambda: PlotWindow(app, args.bpm, expression=args.combination))
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
