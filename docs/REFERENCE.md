# Reference

## CLI

```bash
python3 bpm_iq_viewer.py
python3 bpm_iq_viewer.py --demo
python3 bpm_iq_viewer.py --bpm BPMZ1L2RP
python3 bpm_iq_viewer.py --live --allow-writes
```

Default mode is live safe: EPICS reads enabled, writes blocked.

## Important PV Templates

```text
scan:       {bpm}:signals:ddc_raw.SCAN
synth_scan: {bpm}:signals:ddc_synth.SCAN
i:          {bpm}:signals:ddc_raw.I{button}
q:          {bpm}:signals:ddc_raw.Q{button}
```

TBT start/stop:

```text
start: 1 second
stop:  Passive
```

## Read-Only Probe Commands

```bash
cainfo BPMZ1L2RP:signals:ddc_raw.Ia
caget -t BPMZ1L2RP:signals:ddc_raw.Ia
caget -t TUNEZRP:measX
```

The GUI `PV probe / edit IDs` window logs all OK/error results to `events.jsonl`.

## Logs

Each run creates:

```text
.mls_bpm_local/logs/session_YYYYMMDD_HHMMSS/
```

Important files:

- `session.log`
- `events.jsonl`
- `raw_snapshots/*.npz`

Raw snapshots are bounded and intended for regression/debugging, not long-term archiving.

## Plot Window Controls

- `all`: default view; shows I, Q, unwrapped phase, and phase spectrum.
- `spectra`: shows phase spectrum and magnitude spectrum together.
- `phase debug`: shows wrapped phase, unwrapped phase, detrended/windowed phase, and PSD.
- `Normalize spectra`: scales each plotted spectrum to its own maximum.
- `Stack spectra`: applies a small visual offset so overlaid spectra do not hide each other.
- `Tunes` / `Harmonics`: reads configured tune PVs and draws only valid in-range markers.
- `Tune status / spectrum peaks`: lists tune PV status plus automatically detected spectrum peaks.

## Code Layout

- `bpm_core.py`: testable, GUI-free analysis and PV helpers.
- `bpm_iq_viewer.py`: Tk GUI and pyepics Channel Access backend.
- Future EPICS7/PVA support should be a new backend that produces the same arrays consumed by `bpm_core.py`.

## Tests

```bash
python3 -m py_compile bpm_core.py bpm_iq_viewer.py test_bpm_iq_viewer.py
MPLCONFIGDIR=/tmp/mls-bpm-tools-mpl python3 -m unittest discover -v -p 'test_*.py'
MPLCONFIGDIR=/tmp/mls-bpm-tools-mpl python3 bpm_iq_viewer.py --help
```
