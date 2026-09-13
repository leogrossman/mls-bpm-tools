# Reference

## CLI

```bash
python3 bpm_iq_viewer.py
python3 bpm_iq_viewer.py --demo
python3 bpm_iq_viewer.py --bpm BPMZ1L2RP
python3 bpm_iq_viewer.py --live --allow-writes
```

Default mode is live read-only: EPICS reads enabled, writes blocked. The normal way to unlock writes is the large green/red button in the main window; `--allow-writes` is retained only as a legacy shortcut to start already unlocked.

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

The copied legacy scripts are intentionally broad:

```text
scripts/starttbt: caput_many signals:ddc_raw.SCAN "1 second"; caput_many signals:ddc_synth.SCAN "1 second"
scripts/stoptbt:  caput_many signals:ddc_raw.SCAN "Passive";  caput_many signals:ddc_synth.SCAN "Passive"
```

The GUI `Raw TBT on/off + capture...` / `TBT raw logging control...` window is narrower by design. It limits the reviewed BPM list, reads the current `.SCAN` status first, previews exact PV writes, estimates capture storage, and can schedule an auto-stop back to `Passive`. Default mode blocks all writes until the main write button is unlocked; the TBT window has its own arm switch and every write still gets a confirmation dialog.

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
- `raw_bpm_logs/*.npz`

Raw snapshots are bounded and intended for regression/debugging, not long-term archiving. Files in `raw_bpm_logs` are explicit operator-requested read-only captures from the TBT raw logging control window. They include complex button arrays, separate I/Q arrays, sum phasors, and `metadata_json`. Manual saves and raw captures are written via temporary files and atomic rename.

## CSR / THz Bursting Analysis

The GUI `Bursting analysis...` window reads saved `raw_bpm_logs/*.npz` captures and performs no machine writes. It can compute:

- turn-by-turn common-mode phase and magnitude
- uncalibrated horizontal/vertical difference-over-sum proxies
- Welch PSD
- short-time spectrogram
- band-limited power versus time
- cross spectrum, phase, and magnitude-squared coherence between two BPM observables
- a guide-only correlation of horizontal-like band power with built-in `|Dx|`

The analysis uses `f_sample = f_rev` from capture metadata/config for frequency and tune axes. It does not assume a DDC carrier frequency or convert phase into arrival time.

Live plot windows also provide a `bursting` plot mode for immediate feedback on selected live BPMs/signals. It shows phase trace, phase PSD, a phase spectrogram for the first enabled trace, and 1-200 kHz band power.

## Plot Window Controls

- `all`: default view; shows raw magnitude, unwrapped phase, phase spectrum, and magnitude spectrum.
- `bursting`: shows live phase trace, phase PSD, phase spectrogram, and 1-200 kHz band power for selected signals.
- `phase`: shows unwrapped phase plus phase spectrum.
- `magnitude`: shows raw magnitude plus magnitude spectrum.
- `spectra`: shows phase spectrum and magnitude spectrum together.
- `phase debug`: shows wrapped phase, unwrapped phase, detrended/windowed phase, and PSD.
- `Freq`: displays spectra, tune markers, and peak listings as `kHz`, `Hz`, or fractional tune `Q=f/f_rev`.
- `Refresh s`: live plot refresh interval. The default is 3 seconds because a few BPMs already mean many large waveform PVs.
- `Normalize spectra`: scales each plotted spectrum to its own maximum.
- `Stack spectra`: applies a small visual offset so overlaid spectra do not hide each other.
- Spectrum display controls: `alpha`, `line width`, and `auto offset decades` tune how strongly overlaid spectra are drawn. Drag a spectrum curve up/down to add a manual per-trace log-scale offset inside that plot window.
- `Tunes` / `Harmonics`: reads configured tune PVs and draws only valid in-range markers. Harmonics are capped by the plot-window `max harmonics` value and default to base tune only.
- Sidebands: optional guide markers for `Qx +/- m Qz` and `Qy +/- m Qz`, capped by `sideband order`.
- Auto tune units treat values `0..1` as fractional tune, values `1..1000` as milli-tune, explicit `kHz` as kilohertz, and larger auto values as Hz.
- `Tune status / spectrum peaks`: lists tune PV status plus automatically detected spectrum peaks.
- `max time points`: display-only decimation for raw time traces. Spectra still use the full waveform block.

## Lattice Viewer

The lattice viewer shows clickable BPM markers at configured BPM positions and overlays basic optics-model curves:

- beta x
- beta y
- horizontal dispersion `Dx`
- vertical dispersion `Dy`

The main BPM picker includes a compact clickable lattice overlay with the same optics mode selector. The larger lattice viewer has separate beta/Dx/Dy toggles and a clearer two-axis plot.

The mode selector includes `standard user`, `low alpha`, and `SSMB`. These are smooth built-in model overlays for orientation and BPM selection; they are not yet a replacement for imported, machine-approved optics tables. Use them to quickly find high-dispersion or beta-relevant BPM regions, then replace them with real optics exports when available.

## FFT And Phase Settings

FFT settings apply to the whole plot window, not to each BPM separately. That is intentional: if Sum, A, and two BPMs are overlaid, the spectra should use the same detrending, window, NFFT, and frequency axis so peak heights and widths are comparable.

- `unwrap(angle)`: use continuous phase before detrending and FFT. This matches the old MATLAB workflow `unwrap(angle(iq))`.
- `unwrap jump rad`: phase jump threshold. `pi` is the normal choice unless the raw phase is exceptionally noisy.
- `detrend`: `linear` removes a slope and DC offset before the FFT. This is usually best for turn-by-turn phase because slow drift otherwise leaks into low-frequency bins.
- `window`: `hann` is the default compromise for live spectra. `rectangular` preserves amplitude for exactly bin-centered tones but leaks more for off-bin lines.
- `NFFT`: leave empty for automatic FFT length from `df Hz`; set manually only when testing a specific binning.
- `df Hz`: requested frequency-bin spacing. The code uses `nfft = ceil(fs / df)` and never less than the waveform length, so the actual spacing is `fs / nfft` and can be finer than requested. Smaller values increase FFT work and can make the plot slower. `500 Hz` is a good starting point for the 6.25 MHz sample rate.
- `max time points`: reduces only the number of raw points drawn. It does not change the FFT or peak-finding data.

The FFT/perf tab also shows the calculation equations and a tiny angle/windowed/PSD schematic. Change FFT settings per plot window when comparing different analysis assumptions. Keep them identical inside one plot window when comparing BPMs or Sum versus A.

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
