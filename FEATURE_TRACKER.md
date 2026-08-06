# MLS BPM Tool Feature Tracker

This file tracks requested control-room BPM viewer work so implementation status is visible in the repo.

## Implemented

- Default `python3 bpm_iq_viewer.py` runs live safe control-room mode.
- `--demo` is explicit synthetic-data mode.
- No startup plot opens unless `--bpm` is passed.
- Main window has a clickable BPM lattice strip and a BPM list.
- BPM list can filter by BPM name or section, select all, select visible/filter, select known, and clear.
- Plot windows can add/remove/toggle BPM overlays.
- Plot windows have signal-combination checkboxes; standard default is `A` and `A+B+C+D`.
- Optional custom expression still exists for advanced combinations.
- Legend can be toggled off.
- Tune and harmonic markers can be toggled.
- Phase debug plot shows wrapped phase, unwrapped phase, detrended/windowed phase, and PSD.
- FFT settings are editable: unwrap threshold, detrend, window, NFFT, and frequency resolution.
- TBT start/stop/check controls use the control-room `ddc_raw` and `ddc_synth` `.SCAN` PVs.
- Safe mode blocks all writes and logs blocked attempts.
- Real control-room BPM snapshot is included as a regression fixture.
- Unit tests cover phase unwrap, MATLAB-style phase spectrum, FFT settings, TBT commands, and snapshot spectrum regression.
- Session logs include events and bounded raw snapshots for debugging.

## Partially Implemented

- Lattice viewer: BPM positions are clickable; true beta/dispersion overlays still need trustworthy optics imports.
- Status PVs: tune/noise/status readbacks are configurable and editable; unconfirmed drive PV names remain disabled by default.
- EPICS7/PVA: architecture can support a new backend, but only Channel Access via `pyepics` is implemented today.

## Not Yet Implemented

- Full optics mode import for standard user, low-alpha, and SSMB lattice functions.
- Calibrated transverse x/y formulas using confirmed button geometry and BPM calibration constants.
- Calibrated longitudinal phase-to-time conversion using confirmed DDC/RF reference frequency.
- Multi-BPM dispersion/phase-space reconstruction.
- Persistent user layout/workspace presets.
- Operator-reviewed production safety certification.
