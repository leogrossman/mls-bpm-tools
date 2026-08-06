# Quickstart

## Read-Only Control-Room Use

```bash
git pull
python3 bpm_iq_viewer.py
```

The main window is a BPM picker:

1. Click a BPM marker in the top lattice strip, or double-click a BPM row.
2. A plot window opens and paints before the first EPICS read starts.
3. Use `Refresh now` to force a fresh read.
4. Use `Live` to keep reading periodically.
5. Use `BPM overlays` to add or toggle BPMs in that plot.

## First Plot To Trust

Use `phase debug` first. It shows:

1. `angle(z)`
2. unwrapped phase
3. detrended/windowed phase
4. PSD

Only move to `phase spectrum` or `spectra` after these intermediate traces look reasonable.

## Signals

The default signals are:

- `A`
- `A+B+C+D`

Use the `Signals to plot` panel to add B/C/D, difference candidates, mean, or a custom expression.

## TBT Raw Logging

In normal mode, TBT write buttons are blocked. Use `Check TBT status` to read:

```text
{bpm}:signals:ddc_raw.SCAN
{bpm}:signals:ddc_synth.SCAN
```

Only with explicit operator agreement:

```bash
python3 bpm_iq_viewer.py --live --allow-writes
```

Start writes `"1 second"` and stop writes `"Passive"` to both raw and synth `.SCAN` PVs.

## If It Looks Blank

1. Select one known BPM, for example `BPMZ1L2RP`.
2. Click `Check TBT status`.
3. If `.SCAN` is `Passive`, raw arrays may not be updating.
4. Open `PV probe / edit IDs` and probe `BPMZ1L2RP:signals:ddc_raw.Ia`.
5. Check `.mls_bpm_local/logs/session_.../events.jsonl`.
