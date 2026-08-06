# MLS BPM I/Q Viewer Prototype

A deliberately small, command-line-friendly Python/Tkinter prototype for inspecting the raw complex DDC waveforms of one or more MLS BPMs.

It follows the control-room conventions already used in `betagui`:

- Python 3.9
- Tkinter + Matplotlib
- `pyepics`
- `--safe` mode
- explicit confirmation before every write
- standalone files that can be copied to the control-room machine

This is **not yet an operator-certified application**. It now starts in synthetic demo mode unless you explicitly request live EPICS reads. Start in demo mode, then read-only safe mode, and only then test writes with an operator.

## Files

- `bpm_iq_viewer.py` — GUI and CLI entry point
- `bpm_config.json` — BPM list, PV templates, sample rate, placeholder lattice data
- `requirements.txt` — minimal Python dependencies

## Run

Outside the control room:

```bash
python3 bpm_iq_viewer.py
# equivalent:
python3 bpm_iq_viewer.py --demo
```

On the control-room machine, with live reads but all writes blocked:

```bash
python3 bpm_iq_viewer.py --safe
```

Open several BPMs immediately:

```bash
python3 bpm_iq_viewer.py --safe \
  --bpm BPMZ1L2RP \
  --bpm BPMZ2L2RP
```

Write-capable mode still asks for a confirmation dialog showing the exact PV/value pairs:

```bash
python3 bpm_iq_viewer.py --live --allow-writes
```

`--allow-writes` is rejected unless `--live` is also present. It is also rejected with `--safe` or `--demo`.

## Current functionality

The main window provides:

1. Searchable multi-select BPM list.
2. Open one plot window for one or many BPMs.
3. Enable selected BPM records or all BPM records.
4. Preview the exact write commands without executing them.
5. Open a simple clickable lattice view.
6. Edit the raw BPM PV templates from the GUI if the configured names are wrong.
7. Poll configured read-only excitation/status PVs with green/gray/red status lamps.
8. Overlay live tune markers and harmonics from `TUNEZRP:measX`, `TUNEZRP:measY`, and `TUNEZRP:measZ` on spectrum plots.
9. Enter multiple expressions separated by semicolons to compare several combinations at once.

Every plot window updates independently and allows an expression such as:

```text
A
A+B+C+D
(A+B)-(C+D)
A-B
mean(A,B,C,D)
sum(A,B,C,D)
abs(A)
real(A)
imag(A)
conj(A)
```

Available plots:

- I/Q trajectory in the complex plane
- raw I/Q traces for A, B, C, and D
- magnitude versus turn
- unwrapped phase versus turn
- phase spectrum
- magnitude spectrum
- phase and magnitude spectra together
- uncalibrated position-like ratio
- combined four-panel overview

Data can be saved as a compressed NumPy `.npz` archive.

## Logs

Every run creates a session directory under:

```text
.mls_bpm_local/logs/session_YYYYMMDD_HHMMSS/
```

It contains:

- `session.log` — human-readable startup, PV, plot, and write diagnostics.
- `events.jsonl` — structured JSON lines for startup, status PV reads/errors, plot refresh errors, write previews, blocked writes, cancelled writes, and successful/failed `caput` calls.

Use `--log-dir /path/to/logs` if the control-room copy should store logs somewhere else.

Broken or missing PVs should not crash the GUI. Plot windows skip the affected BPM for that refresh, show an error count, and write the failing BPM/expression/PV context to the logs. Status PVs turn red and record the exception in `events.jsonl`.

Scalar tune/status/noise PVs use the shorter `epics_scalar_timeout_s` from `bpm_config.json` (default `0.25 s`) so a bad noise-generator candidate does not stall safe-mode startup for long. Raw waveform arrays use `epics_array_timeout_s` (default `2.0 s`).

## EPICS mapping

The initial templates reproduce the MATLAB naming pattern:

```text
{bpm}:signals:ddc_raw.SCAN
{bpm}:signals:ddc_raw.Ia
{bpm}:signals:ddc_raw.Qa
...
```

The enable operation plans:

```text
PV: {bpm}:signals:ddc_raw.SCAN
value: I/O Intr
```

The write is never silently executed. In demo and `--safe` modes it is impossible. In `--live --allow-writes` mode the GUI displays the exact list and asks for confirmation.

Before live use, verify whether the actual Python EPICS client accepts the enum string `I/O Intr`. Some installations may require an enum index or another exact spelling.

Configured tune marker PVs:

```text
TUNEZRP:measX
TUNEZRP:measY
TUNEZRP:measZ
```

Values between 0 and 1 are treated as tune fractions and converted to marker frequency with `f = Q f_sample`. Larger values are treated as Hz unless a config entry says `unit: "khz"`.

Configured read-only noise/status candidates:

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

Some of these are confirmed from local `betagui`/CS-Studio material (`WFGEN2C1CP:*`, `WFGENC1CP:rdVolt`, `TUNEZRP:*`); the rest are editable candidates that should be confirmed on the machine.

## Physics: what one complex BPM value means

For button `A`, the raw digital downconverter gives one pair per turn:

\[
I_A[n],\qquad Q_A[n].
\]

The program forms the phasor

\[
A[n] = I_A[n] + iQ_A[n]
     = |A[n]|e^{i\phi_A[n]}.
\]

It is not itself a frequency. It is the complex amplitude of a selected RF/DDC component during turn `n`.

- `abs(A[n])` is the component amplitude.
- `angle(A[n])` is its phase relative to the DDC reference.
- variation over many turns contains synchrotron, betatron, RF-noise and other modulation frequencies.

The waveform sampling frequency is one sample per bunch passage. For the MLS single-bunch case used here:

\[
f_{\mathrm{sample}} = f_{\mathrm{rev}} \approx 6.25\,\mathrm{MHz}.
\]

A peak in the turn-by-turn spectrum at frequency `f` corresponds to tune

\[
Q = \frac{f}{f_{\mathrm{rev}}}.
\]

The DDC carrier frequency is a separate quantity. It is needed to convert phase to arrival time:

\[
\Delta t[n] = -\frac{\Delta\phi[n]}{2\pi f_{\mathrm{DDC}}}.
\]

Do not use `6.25 MHz` for this conversion unless the DDC actually operates at that harmonic.

## Button combinations

After per-channel complex gain and phase calibration, the approximate common-mode signal is

\[
S[n] = A[n]+B[n]+C[n]+D[n].
\]

Its magnitude is mainly related to bunch signal strength and its phase is a candidate arrival-phase observable.

A transverse difference-over-sum observable has the form

\[
x_{\mathrm{raw}}[n]
\propto
\Re\left(\frac{X[n]}{S[n]}\right),
\]

where `X` is a geometry-dependent signed combination of the four buttons. The prototype intentionally does not hard-code the signs because the actual A/B/C/D physical orientation must be confirmed for the MLS BPM electronics.

Examples only:

\[
X=(A+B)-(C+D),
\]

or

\[
X=(A+D)-(B+C).
\]

The right formula depends on the button labels around the chamber.

## Longitudinal centroid phase space

The intended later workflow is:

1. Build a calibrated common-mode phasor `S[n]`.
2. Convert its unwrapped phase to arrival coordinate `z[n]`.
3. Reconstruct momentum error from horizontal orbit at dispersive BPMs:

\[
x_i[n] = x_{\beta,i}[n] + D_{x,i}\delta[n] + \cdots.
\]

4. Use many BPMs and a lattice model to separate betatron coordinates from momentum error by weighted least squares.
5. Plot

\[
(z[n],\delta[n])
\]

for the bunch centroid after a longitudinal kick.

This maps the **centroid trajectory**, not the full particle density `rho(z, delta)`.

## Multi-BPM optics fit to add later

For one turn, collect all horizontal BPM readings:

\[
\mathbf{x}[n] = H
\begin{pmatrix}
x_0[n]\\
x'_0[n]\\
\delta[n]
\end{pmatrix}
+ \mathbf{x}_{\mathrm{co}},
\]

with

\[
H_i = \begin{pmatrix}R_{11}^{(i)} & R_{12}^{(i)} & D_i\end{pmatrix}.
\]

Then solve

\[
\hat{u}[n] = (H^TWH)^{-1}H^TW(\mathbf{x}[n]-\mathbf{x}_{\mathrm{co}}).
\]

This should be a separate tested analysis module rather than added directly to the first prototype.

## Lattice viewer integration

The prototype includes a simple clickable plot of BPM position `s`. BPM names, positions, and `rdX`/`rdY` candidates come from the local `betagui` low-emittance lattice export. Beta and dispersion values remain zero until a trustworthy optics export is imported.

The preferred next implementation is an export/import bridge rather than tightly coupling this viewer to another GUI:

1. Export from the existing lattice viewer to CSV or JSON:

```text
name,s_m,beta_x_m,beta_y_m,dispersion_x_m,mode
```

2. Add `File -> Import lattice CSV`.
3. Store separate datasets for `user` and `low_alpha` optics.
4. Plot beta functions and dispersion.
5. Make each BPM marker clickable.
6. Clicking a marker selects the BPM and opens or focuses its plot window.

A later direct integration can expose a small callback/event API from the lattice viewer, for example:

```python
def on_bpm_selected(bpm_name: str) -> None:
    viewer.open_bpm(bpm_name)
```

Do not scrape pixel positions from the lattice-viewer window. Use machine/lattice data or an explicit export.

## Important calibration tasks

Before interpreting phase or position quantitatively:

- Confirm A/B/C/D physical button orientation.
- Confirm whether arrays really contain one sample per turn.
- Confirm the DDC frequency and reference phase.
- Measure fixed complex channel gains `G_A ... G_D`.
- Phase-align the four channels before summing.
- Confirm waveform length and update semantics.
- Confirm whether changing `.SCAN` is actually required for each BPM.
- Confirm whether live reads can occur without changing scan mode.
- Confirm the exact BPM inventory and PV names.
- Confirm timing coherence between different BPM electronics.
- Import real user-mode and low-alpha optics.

## Suggested next Codex tasks

Keep the next pass focused:

1. Read the real BPM inventory from a known EPICS list or exported file.
2. Add calibrated channel coefficients to the config.
3. Verify button geometry and provide named `SUM`, `X`, and `Y` combinations.
4. Move EPICS acquisition to one worker thread per plot window or a shared acquisition service so Tkinter never blocks.
5. Add a bounded history/ring buffer for scalar live data.
6. Add `scipy.signal.welch` or MATLAB-compatible spectrum settings if SciPy is available.
7. Add peak detection with frequency and tune readout.
8. Add a reference capture and kick-on minus kick-off subtraction.
9. Add separate safe snapshots and structured session logging like `betagui`.
10. Import real lattice functions for standard user and low-alpha modes.

Avoid initially adding automated kicker control, phase-space inversion, feedback tuning, or machine writes beyond the explicit `.SCAN` enable action.

## Operational test sequence

```bash
# 1. Local synthetic test
python3 bpm_iq_viewer.py

# 2. Control-room import/runtime check
python3 -c "import epics, numpy, matplotlib, tkinter"

# 3. Safe live reads
python3 bpm_iq_viewer.py --safe

# 4. Verify one BPM and one button
# expression: A

# 5. Verify all four buttons independently
# expressions: A, B, C, D

# 6. Verify the common sum
# expression: A+B+C+D

# 7. Preview the planned enable command
# Do not write yet.

# 8. With an operator, enable only one BPM and confirm the waveform updates.
python3 bpm_iq_viewer.py --live --allow-writes

# 9. Compare the phase spectrum with the existing MATLAB command.

# 10. Inspect logs if anything looked wrong
ls -lt .mls_bpm_local/logs
```

## Known prototype limitations

- EPICS reads currently happen on the Tkinter callback thread and can briefly freeze the GUI if a PV times out.
- The lattice data are placeholders.
- Excitation/status PVs are placeholders until imported from a real inventory.
- Channel calibration is not implemented.
- Difference signs are not fixed.
- No phase-to-time conversion is shown because `f_DDC` is unknown.
- No automatic peak finder or tune label exists yet.
- No full longitudinal reconstruction exists yet.
- It has not been tested against the MLS control system.
