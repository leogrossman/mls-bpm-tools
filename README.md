# MLS BPM I/Q Viewer

Control-room safe viewer for MLS BPM turn-by-turn raw DDC data. It reads each BPM as four complex button signals `A`, `B`, `C`, and `D`, then lets you inspect raw traces, phase/amplitude, spectra, tune markers, and BPM overlays.

The first workflow is read-only and safe by default. Write-capable TBT start/stop buttons exist only behind explicit `--live --allow-writes` confirmation.

## What To Do First

1. Pull the newest version in the control-room checkout:

```bash
git pull
```

2. Start the GUI safely:

```bash
python3 bpm_iq_viewer.py --safe
```

3. The app opens a raw A/B/C/D plot for known BPMs. If it is blank, click `Check TBT status`; if the selected BPMs are `Passive`, ask whether it is OK to start TBT logging.
4. To inspect spectra, switch the plot mode to `phase debug` first. This shows `angle`, `unwrap`, `detrend/window`, and PSD separately.
5. If PV names are wrong, use `PV probe / edit IDs`, edit the ID, then `Save config`.

## Control-Room Start

Use this command for normal exploration:

```bash
python3 bpm_iq_viewer.py --safe
```

`--safe` means:

- live EPICS reads are allowed
- machine writes are blocked
- known BPMs are preselected and an initial raw-button plot opens automatically
- the Start/Stop TBT buttons only preview/block writes
- optional tune/noise/status PVs are not read during GUI startup
- missing/broken PVs should not crash the GUI
- scalar tune/noise/status PVs use a short timeout so bad candidates fail fast
- logs are written for later debugging

The write-capable command exists, but do not use it until the read-only test is understood and an operator agrees:

```bash
python3 bpm_iq_viewer.py --live --allow-writes
```

Even in write-capable mode, the GUI shows the exact PV/value list and asks for confirmation before writing.

The TBT start/stop buttons use the same meaning as the old control-room scripts:

```text
start: {bpm}:signals:ddc_raw.SCAN   <- "1 second"
start: {bpm}:signals:ddc_synth.SCAN <- "1 second"
stop:  {bpm}:signals:ddc_raw.SCAN   <- "Passive"
stop:  {bpm}:signals:ddc_synth.SCAN <- "Passive"
```

## Local Demo

Away from the control room, this uses synthetic data and no EPICS connection:

```bash
python3 bpm_iq_viewer.py
```

This is equivalent to:

```bash
python3 bpm_iq_viewer.py --demo
```

## Files

- `bpm_iq_viewer.py`: Tkinter/Matplotlib GUI and command-line entry point.
- `bpm_config.json`: BPM list, PV templates, sample rate, lattice positions, tune PVs, status PVs.
- `scripts/starttbt`, `scripts/stoptbt`: copies of the old control-room TBT start/stop scripts.
- `tests/fixtures/control_room_BPMZ1L2RP_sum_2048.npz`: compact real raw snapshot used by regression tests.
- `requirements.txt`: Python dependencies.
- `test_bpm_iq_viewer.py`: offline unit tests.
- `README_BPM_IQ_VIEWER.md`: older detailed prototype notes; this `README.md` is the current entry point.

## Install Check

The control-room Python should have:

```bash
python3 -c "import epics, numpy, matplotlib, tkinter"
```

Runtime packages:

- Python 3.9 or compatible
- `numpy`
- `matplotlib`
- `pyepics`
- `tkinter`

The default config uses a 2.0 s timeout for raw waveform reads and a 0.25 s timeout for scalar tune/status/noise readbacks. Optional status rows are skipped until you click `Refresh status PVs`, so a bad candidate like an unconfirmed `BBQRP:*:DRIVEO` ID should not stop the main window from opening.

## Logs

Every run creates a session directory:

```text
.mls_bpm_local/logs/session_YYYYMMDD_HHMMSS/
```

Files inside:

- `session.log`: readable runtime diagnostics.
- `events.jsonl`: structured JSON lines for startup, PV status reads/errors, plot refresh errors, write previews, blocked writes, cancelled writes, and `caput` success/failure.

If a PV is missing, disconnected, empty, or malformed:

- status PV rows turn red
- plot windows skip the affected BPM for that refresh
- the window shows an error count
- the exact error is logged in `session.log` and `events.jsonl`

Use another log location if needed:

```bash
python3 bpm_iq_viewer.py --safe --log-dir /path/to/logs
```

## PV Probe And Editable IDs

Use `PV probe / edit IDs` in the GUI to generate likely PV names for the selected BPMs and run read-only checks. It can probe raw waveform names, tune/status names, and orbit readback candidates. Results are also written to `events.jsonl`.

Equivalent shell checks on the control-room machine are:

```bash
cainfo BPMZ1L2RP:signals:ddc_raw.Ia
caget -t BPMZ1L2RP:signals:ddc_raw.Ia
cainfo TUNEZRP:measX
caget -t WFGEN2C1CP:stOut
```

If an ID is wrong, edit it in the GUI table or in `bpm_config.json`, then click `Save config`. The GUI stores the corrected names back to the config file used by the one-command startup.

## EPICS PV Manual

The default raw BPM templates in `bpm_config.json` are:

```text
scan: {bpm}:signals:ddc_raw.SCAN
synth_scan: {bpm}:signals:ddc_synth.SCAN
i:    {bpm}:signals:ddc_raw.I{button}
q:    {bpm}:signals:ddc_raw.Q{button}
```

For BPM `BPMZ1L2RP`, the four complex button channels are built from:

```text
BPMZ1L2RP:signals:ddc_raw.Ia
BPMZ1L2RP:signals:ddc_raw.Qa
BPMZ1L2RP:signals:ddc_raw.Ib
BPMZ1L2RP:signals:ddc_raw.Qb
BPMZ1L2RP:signals:ddc_raw.Ic
BPMZ1L2RP:signals:ddc_raw.Qc
BPMZ1L2RP:signals:ddc_raw.Id
BPMZ1L2RP:signals:ddc_raw.Qd
```

The raw logging control PVs are:

```text
PV:       {bpm}:signals:ddc_raw.SCAN
PV:       {bpm}:signals:ddc_synth.SCAN
start:    1 second
stop:     Passive
```

This follows the old MATLAB pattern:

```text
LcaPut('BPMZ1L2RP:signals:ddc_raw.SCAN', 'I/O Intr')
iq = [1 1] * LcaGet({'BPMZ1L2RP:signals:ddc_raw.Ia', 'BPMZ1L2RP:signals:ddc_raw.Qa'})
pspectrum(detrend(unwrap(angle(iq))), 6250e3, 'FrequencyResolution', 1000)
```

Before any write-capable run, verify:

- whether `1 second` and `Passive` are still the intended enum strings
- whether both `ddc_raw` and `ddc_synth` should be changed for the current study
- whether live reads can happen without changing `.SCAN`

The GUI has editable PV template fields, so if the capitalization or namespace is wrong you can test another template at runtime. Commit confirmed names back to `bpm_config.json`.

The BPM list and positions were copied from the local `betagui` low-emittance lattice export. Each BPM entry includes orbit readback candidates:

```text
{bpm}:rdX
{bpm}:rdY
```

The raw I/Q PV namespace is still template-based and must be verified on the control-room machine.

The current implementation uses `pyepics` Channel Access. If the BPM EPICS7/PVA waveform endpoints become available with richer structured data, the next clean step is a second backend next to `EpicsBackend`, not rewriting the analysis. The tested core expects complex arrays after readout, so CA and PVA can share the same plotting/spectrum pipeline.

## Status PVs

`bpm_config.json` currently contains these read-only tune PVs for spectrum markers:

```text
TUNEZRP:measX
TUNEZRP:measY
TUNEZRP:measZ
```

The code treats values between 0 and 1 as tune fractions, converting to frequency with:

```text
f_marker = Q * f_sample
```

Larger values are treated as Hz unless the config says `unit: "khz"`.

The status/noise candidates are:

```text
WFGEN1C1CP:setVolt
WFGEN1C1CP:stOut
WFGEN2C1CP:setVolt
WFGEN2C1CP:stOut
WFGENC1CP:rdVolt
WFGENC1CP:stOut
BBQRP:X:DRIVEO
BBQRP:Y:DRIVEO
BBQRP:Z:DRIVEO
```

`WFGEN2C1CP:setVolt`, `WFGEN2C1CP:stOut`, `WFGENC1CP:rdVolt`, and the `TUNEZRP:*` tune PVs appear in the local `betagui`/CS-Studio material. `WFGEN1C1CP:*`, `WFGENC1CP:stOut`, and `BBQRP:*:DRIVEO` are editable candidates based on the requested control-room names and are disabled by default until confirmed live.

Use these rows for read-only indication of:

- longitudinal phase/noise generator enable
- horizontal excitation enable
- vertical excitation enable
- excitation type readback, for example phase, amplitude, chirp, kick, noise

For now these are read-only. Later, write controls can be added behind explicit `--live --allow-writes` confirmation.

## GUI Use

1. Start with `python3 bpm_iq_viewer.py --safe`.
2. The GUI preselects known BPMs and opens an initial raw-button plot for the first two known BPMs. Use `--no-startup-plot` if you want an empty workspace.
3. Select another BPM, for example `BPMZ1L2RP`, or click `Select known BPMs`. Starred BPMs have orbit PV names seen in local `betagui`/CS-Studio material.
4. Use `Select all BPMs` for the full configured ring list or type in the search box and use `Select visible/filter`.
5. First inspect individual buttons with expressions `A`, `B`, `C`, `D`.
6. Use `raw buttons` plot mode to compare all I/Q traces.
7. Use `A+B+C+D` for common mode.
8. Try `phase debug` before trusting a spectrum; it shows every step in the phase-spectrum calculation.
9. Try `spectra` to see phase and magnitude spectra together.
10. Toggle `Tunes` and `Harmonics` in plot windows to overlay live tune marker lines.
11. Use the `BPM overlays` panel in each plot window to add BPMs, add the main-window selection, and toggle individual BPM traces on/off without closing the viewer.
12. Use the Matplotlib toolbar under the plot to pan, zoom, and move around spectra or turn-by-turn traces.
13. Enter multiple expressions separated by semicolons, for example `A+B+C+D; A-B; (A+B)-(C+D)`.
14. Try difference expressions only as uncalibrated diagnostics until button geometry is confirmed.
15. Open the lattice view to select BPMs by ring position and candidate `rdX`/`rdY` PV names.
16. Use `PV probe / edit IDs` when a PV looks wrong, then click `Save config`.
17. Check logs after any red PV status or plot error.

Useful expressions:

```text
A
B
C
D
A+B+C+D
(A+B)-(C+D)
(A+D)-(B+C)
A-B
mean(A,B,C,D)
sum(A,B,C,D)
abs(A)
real(A)
imag(A)
conj(A)
```

Available plot modes:

- `I/Q`: Zeiger/phasor trajectory in the complex plane.
- `raw buttons`: raw I and Q arrays for A, B, C, D.
- `magnitude`: `abs(expression)` versus turn.
- `phase`: `unwrap(angle(expression))` versus turn.
- `phase spectrum`: FFT power spectrum of unwrapped phase.
- `magnitude spectrum`: magnitude versus turn plus FFT power spectrum of magnitude.
- `spectra`: phase and magnitude spectra together.
- `phase debug`: wrapped phase, unwrapped phase, detrended/windowed phase, and PSD.
- `position-like`: `Re(expression / (A+B+C+D))`, uncalibrated.
- `all`: compact overview of I, Q, phase, and phase spectrum.

Spectrum modes can overlay tune markers and harmonics. Markers are based on live read-only tune PVs. If a tune PV is broken or out of range, the marker is skipped and the error is logged.

Each plot window has editable FFT/phase settings:

- `unwrap(angle)`: matches the MATLAB `unwrap(angle(iq))` step.
- `unwrap jump rad`: phase jump threshold, default `pi`.
- `detrend`: `linear` matches MATLAB `detrend(...)`; `constant` removes only the mean; `none` leaves the signal as-is.
- `window`: `hann`, `hamming`, `blackman`, or `rectangular`.
- `NFFT`: explicit FFT length, blank means use the waveform length unless `df Hz` is set.
- `df Hz`: requested frequency bin spacing, for example `1000` approximates the old `FrequencyResolution`, by choosing `NFFT = ceil(sample_rate / df)`.
- `log first raw snapshot`: stores a bounded `.npz` file in the session log directory for the first successful BPM/expression read.

The phase spectrum path is now:

```text
z[n] = expression over A/B/C/D
raw_phase[n] = angle(z[n])
phase[n] = unwrap(raw_phase[n])
detrended[n] = detrend(phase[n])
windowed[n] = window[n] * detrended[n]
PSD = abs(rfft(windowed, nfft))^2 / sum(window^2)
```

## Theory

For button `A`, the raw DDC waveforms are one I/Q pair per turn:

```text
I_A[n], Q_A[n]
```

The code forms a complex phasor:

```text
A[n] = I_A[n] + i Q_A[n]
     = |A[n]| exp(i phi_A[n])
```

Interpretation:

- `abs(A[n])` is the raw component amplitude.
- `angle(A[n])` is phase relative to the DDC reference.
- turn-by-turn variation contains synchrotron, betatron, RF-noise, excitation, and electronics effects.

For all buttons:

```text
A[n] = I_A[n] + i Q_A[n]
B[n] = I_B[n] + i Q_B[n]
C[n] = I_C[n] + i Q_C[n]
D[n] = I_D[n] + i Q_D[n]
```

The current sample rate is configured as:

```text
f_sample = f_rev ~= 6.25 MHz
```

A spectral peak at frequency `f` corresponds approximately to tune:

```text
Q = f / f_rev
```

This is for turn-by-turn modulation spectra. The DDC carrier/reference frequency is separate. To convert phase to arrival time, use:

```text
Delta t[n] = - Delta phi[n] / (2 pi f_DDC)
```

Do not use `6.25 MHz` for this conversion unless the DDC carrier/reference is actually at that frequency.

## Button Sums And Differences

After complex gain/phase calibration, the common-mode sum is:

```text
S[n] = A[n] + B[n] + C[n] + D[n]
```

Possible use:

- `abs(S[n])`: bunch signal strength / charge-like observable
- `unwrap(angle(S[n]))`: arrival phase candidate
- spectrum of `angle(S[n])`: synchrotron/excitation/noise content

Transverse observables are difference-over-sum style:

```text
x_raw[n] proportional to Re(X[n] / S[n])
y_raw[n] proportional to Re(Y[n] / S[n])
```

where `X` and `Y` are signed button combinations. Examples only:

```text
X = (A+B) - (C+D)
X = (A+D) - (B+C)
Y = (A+C) - (B+D)
Y = (A+B) - (C+D)
```

The correct signs depend on actual A/B/C/D physical button orientation around the chamber. Do not interpret transverse coordinates quantitatively until this is confirmed.

## Longitudinal Phase-Space Idea

The near-term goal is a high-detail centroid playground:

1. Read all four complex raw button channels for selected BPMs.
2. Calibrate fixed complex gains:

```text
A_cal = G_A A
B_cal = G_B B
C_cal = G_C C
D_cal = G_D D
```

3. Build calibrated common mode:

```text
S = A_cal + B_cal + C_cal + D_cal
```

4. Convert common-mode phase to arrival coordinate:

```text
z[n] proportional to -unwrap(angle(S[n])) / (2 pi f_DDC)
```

5. Use dispersive BPMs to estimate momentum error:

```text
x_i[n] = x_beta,i[n] + D_x,i delta[n] + ...
```

6. Plot centroid longitudinal phase space:

```text
(z[n], delta[n])
```

This reconstructs the bunch centroid trajectory, not the full particle density `rho(z, delta)`.

## Multi-BPM Optics Fit Idea

For one turn, collect horizontal readings at many BPMs:

```text
x[n] = H u[n] + x_co
```

with:

```text
u[n] = [x0[n], x0_prime[n], delta[n]]^T
H_i  = [R11_i, R12_i, D_i]
```

Weighted least squares:

```text
u_hat[n] = (H^T W H)^(-1) H^T W (x[n] - x_co)
```

This can separate betatron and dispersive components if:

- enough BPMs are included
- BPM calibration/noise weights are known
- lattice functions are reliable
- dispersive and non-dispersive BPMs are both available

## Lattice Viewer Idea

The current lattice view uses the BPM positions and `rdX`/`rdY` PV candidates imported from the low-emittance lattice export. It does not yet contain trustworthy beta or dispersion functions; those fields are zero until imported.

The intended import format is:

```text
name,s_m,beta_x_m,beta_y_m,dispersion_x_m,mode
```

Future useful workflow:

- import real user-mode and low-alpha optics
- plot `beta_x`, `beta_y`, and `D_x`
- click BPMs at high dispersion to open raw I/Q plots
- compare dispersive and non-dispersive BPMs
- overlay excitation status and selected BPMs

## Calibration Checklist

Before trusting quantitative phase/position:

- Confirm the real BPM inventory.
- Confirm all raw DDC PV names.
- Confirm `.SCAN` behavior and enum value.
- Confirm waveform length and update timing.
- Confirm arrays are one sample per turn.
- Confirm timing coherence between different BPM electronics.
- Confirm A/B/C/D physical button orientation.
- Measure complex channel gains `G_A`, `G_B`, `G_C`, `G_D`.
- Phase-align channels before summing.
- Confirm DDC carrier/reference frequency.
- Import real lattice functions.
- Identify dispersive and non-dispersive BPMs.
- Compare `phase+spectrum` with the old MATLAB `pspectrum` workflow.

## Offline Tests

Run these away from the machine:

```bash
python3 -m py_compile bpm_iq_viewer.py test_bpm_iq_viewer.py
MPLCONFIGDIR=/tmp/mls-bpm-tools-mpl python3 -m unittest discover -v -p 'test_*.py'
```

The tests cover:

- safe expression parsing
- PV template expansion
- synthetic four-button complex waveforms
- phase spectrum peak location
- structured event logging

## Current Limitations

- EPICS reads still happen in the Tkinter callback thread, so a slow PV can briefly freeze the GUI.
- Status PV names are placeholders.
- BPM inventory is incomplete.
- Lattice functions are placeholders.
- Tune marker conversion assumes tune-fraction values for `TUNEZRP:*` when values are between 0 and 1.
- Button geometry is not confirmed.
- Channel calibration is not implemented.
- DDC frequency is unknown, so phase-to-time conversion is not shown in the GUI.
- No automatic peak finder yet.
- No full longitudinal reconstruction yet.
- No excitation write controls yet.

## Golden Rule For Control-Room Use

Start with:

```bash
python3 bpm_iq_viewer.py --safe
```

If something is red or weird, inspect:

```text
.mls_bpm_local/logs/session_*/session.log
.mls_bpm_local/logs/session_*/events.jsonl
```

Do not move to `--live --allow-writes` until the read-only behavior and PV names are understood.
