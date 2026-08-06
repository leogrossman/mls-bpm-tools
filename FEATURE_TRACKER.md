# MLS BPM Tool Feature Tracker

This file tracks requested control-room BPM viewer work so implementation status is visible in the repo.

## Implemented

- Default `python3 bpm_iq_viewer.py` runs live safe control-room mode.
- `--demo` is explicit synthetic-data mode.
- No startup plot opens unless `--bpm` is passed.
- Main window has a clickable BPM lattice strip with compact beta-x/beta-y and Dx/Dy overlays, plus a BPM list.
- BPM list can filter by BPM name or section, select all, select visible/filter, select known, and clear.
- Plot windows can add/remove/toggle BPM overlays.
- Plot windows can pull active BPM overlays from other open plot windows.
- Plot windows have signal-combination checkboxes; standard default is `A+B+C+D` and `A`.
- Plot windows open on the signal tab by default.
- Plot windows combine raw phase/magnitude traces with their spectra in the common phase, magnitude, and all views.
- Optional custom expression still exists for advanced combinations.
- Legend can be toggled off.
- Tune and harmonic markers can be toggled; invalid tune PV values are reported but not drawn.
- Tune auto-scaling treats 1..1000 readbacks as milli-tune; explicit kHz remains available.
- Optional Qx/Qy +/- m Qz synchrotron sideband guide markers can be toggled.
- Spectrum frequency axes can be shown as kHz, Hz, or fractional tune.
- Plot windows list detected spectrum peaks and tune marker status in a side pane.
- Spectrum overlays can be normalized and visually stacked so multiple BPMs/signals stay visible.
- Spectrum overlays have editable alpha, line width, auto offset, and manual drag offsets.
- Plot and main windows show live performance/load indicators for PV count, sample count, bytes, elapsed time, cache hits, and lagging refreshes.
- Default live plot refresh is 3 seconds and can be changed per plot window.
- Plot-window settings are grouped into tabs so controls fit on shorter screens.
- Raw time traces are display-decimated and repeated cached refreshes reuse derived analysis results where possible.
- Lattice viewer overlays basic beta-x, beta-y, horizontal-dispersion, and vertical-dispersion model curves for standard user, low-alpha, and SSMB modes.
- Phase debug plot shows wrapped phase, unwrapped phase, detrended/windowed phase, and PSD.
- FFT settings are editable: unwrap threshold, detrend, window, NFFT, and frequency resolution.
- FFT/performance tab explains the raw-complex to spectrum pipeline with equations, a mini schematic, and notes on `df Hz`, `max time points`, and per-window settings.
- TBT start/stop/check controls use the control-room `ddc_raw` and `ddc_synth` `.SCAN` PVs.
- Safe mode blocks all writes and logs blocked attempts.
- Real control-room BPM snapshot is included as a regression fixture.
- Unit tests cover phase unwrap, MATLAB-style phase spectrum, FFT settings, TBT commands, and snapshot spectrum regression.
- Session logs include events and bounded raw snapshots for debugging.
- Core math/config/PV helpers are split into `bpm_core.py`; Tk/EPICS app code remains in `bpm_iq_viewer.py`.
- Plot windows cache recent raw phasor reads briefly so UI-only redraws do not immediately re-read EPICS.
- Documentation is split into README, quickstart, theory, and reference docs.

## Partially Implemented

- Lattice viewer: BPM positions are clickable and basic optics overlays exist in the main picker and large viewer; true beta/dispersion overlays still need trustworthy optics imports.
- Status PVs: tune/noise/status readbacks are configurable and editable; unconfirmed drive PV names remain disabled by default.
- EPICS7/PVA: architecture can support a new backend, but only Channel Access via `pyepics` is implemented today.

## Not Yet Implemented

- Full measured optics table import for standard user, low-alpha, and SSMB lattice functions.
- Calibrated transverse x/y formulas using confirmed button geometry and BPM calibration constants.
- Calibrated longitudinal phase-to-time conversion using confirmed DDC/RF reference frequency.
- Multi-BPM dispersion/phase-space reconstruction.
- Persistent user layout/workspace presets.
- Full GUI integration tests on a working Tk display.
- Operator-reviewed production safety certification.
