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

- `all`: default view; shows raw magnitude, unwrapped phase, phase spectrum, and magnitude spectrum.
- `phase`: shows unwrapped phase plus phase spectrum.
- `magnitude`: shows raw magnitude plus magnitude spectrum.
- `spectra`: shows phase spectrum and magnitude spectrum together.
- `phase debug`: shows wrapped phase, unwrapped phase, detrended/windowed phase, and PSD.
- `Freq`: displays spectra, tune markers, and peak listings as `kHz`, `Hz`, or fractional tune `Q=f/f_rev`.
- `Refresh s`: live plot refresh interval. The default is 3 seconds because a few BPMs already mean many large waveform PVs.
- `Normalize spectra`: scales each plotted spectrum to its own maximum.
- `Stack spectra`: applies a small visual offset so overlaid spectra do not hide each other.
- `Tunes` / `Harmonics`: reads configured tune PVs and draws only valid in-range markers. Auto tune units treat values `0..1` as tune fraction, values `1..1000` as kHz, and larger values as Hz.
- `Tune status / spectrum peaks`: lists tune PV status plus automatically detected spectrum peaks.
- `max time points`: display-only decimation for raw time traces. Spectra still use the full waveform block.

## Lattice Viewer

The lattice viewer shows clickable BPM markers at configured BPM positions and overlays basic optics-model curves:

- beta x
- beta y
- horizontal dispersion `Dx`

The mode selector includes `standard user`, `low alpha`, and `SSMB`. These are smooth built-in model overlays for orientation and BPM selection; they are not yet a replacement for imported, machine-approved optics tables. Use them to quickly find high-dispersion or beta-relevant BPM regions, then replace them with real optics exports when available.

## FFT And Phase Settings

FFT settings apply to the whole plot window, not to each BPM separately. That is intentional: if Sum, A, and two BPMs are overlaid, the spectra should use the same detrending, window, NFFT, and frequency axis so peak heights and widths are comparable.

- `unwrap(angle)`: use continuous phase before detrending and FFT. This matches the old MATLAB workflow `unwrap(angle(iq))`.
- `unwrap jump rad`: phase jump threshold. `pi` is the normal choice unless the raw phase is exceptionally noisy.
- `detrend`: `linear` removes a slope and DC offset before the FFT. This is usually best for turn-by-turn phase because slow drift otherwise leaks into low-frequency bins.
- `window`: `hann` is the default compromise for live spectra. `rectangular` preserves amplitude for exactly bin-centered tones but leaks more for off-bin lines.
- `NFFT`: leave empty for automatic FFT length from `df Hz`; set manually only when testing a specific binning.
- `df Hz`: desired frequency-bin spacing. Smaller values give finer bins but increase FFT work and can make the plot slower. `500 Hz` is a good starting point for the 6.25 MHz sample rate.
- `max time points`: reduces only the number of raw points drawn. It does not change the FFT or peak-finding data.

Change FFT settings per plot window when comparing different analysis assumptions. Keep them identical inside one plot window when comparing BPMs or Sum versus A.

## Data Rate And Performance

For every selected BPM and every required button, the tool reads two waveform PVs:

```text
I_button and Q_button
```

The current EPICS backend converts each waveform to `float64`, so a practical per-refresh payload estimate is:

```text
bytes ~= BPM_count * button_count * 2 * waveform_samples * 8
```

Example: 2 BPMs, 4 buttons, and 8192 samples per waveform is:

```text
2 * 4 * 2 * 8192 * 8 = 1.0 MiB
```

That is only the raw I/Q payload for one fresh read. Plotting and FFTs add CPU work. Each plot window therefore shows a `Load:` line with planned array PVs, fresh reads, cache hits, scalar samples, processed bytes, elapsed time, and a `LAGGING` marker if the refresh takes longer than the selected interval. The main window repeats the latest performance line globally.

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
