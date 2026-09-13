# CSR / THz Bursting BPM Analysis

## Purpose

The BPM tool can now analyze saved turn-by-turn raw BPM captures as exploratory evidence for beam dynamics that may accompany CSR microbunching / THz bursting.

This is a centroid/moment diagnostic. It does not directly reconstruct the microscopic longitudinal phase-space density `f(z, delta)`. A quiet BPM result does not prove that the bunch is not microbunching.

## Control-Room Workflow

1. Start normally in read-only mode:

```bash
python3 bpm_iq_viewer.py
```

2. Open `TBT raw logging control...`.
3. Choose a small BPM set manually or use `Suggest burst BPMs`.
4. Click `Check selected status`.
5. Save data with `Capture raw arrays now` or `Start capture series`.
6. Open `Bursting analysis...`.
7. Load the latest capture or choose a `.npz` file.
8. Compare observables, BPMs, spectra, spectrograms, band power, and coherence.

Raw captures are saved under:

```text
.mls_bpm_local/logs/session_YYYYMMDD_HHMMSS/raw_bpm_logs/
```

## Observables

For each BPM, the analysis window can build:

- `sum_phase_rad`: unwrapped phase of `A+B+C+D`, a relative common-mode arrival-phase-like centroid observable.
- `sum_mag`: magnitude of `A+B+C+D`, a common-mode/intensity-like observable.
- `x_diff_over_sum_uncal`: real part of `((A+B)-(C+D))/(A+B+C+D)`, an uncalibrated horizontal-like proxy.
- `y_diff_over_sum_uncal`: real part of `((A+D)-(B+C))/(A+B+C+D)`, an uncalibrated vertical-like proxy.

These depend on button orientation, electronics phase/gain, and calibration. They are deliberately labeled uncalibrated where appropriate.

## Analysis Views

The burst analysis window shows:

- time trace versus turn
- Welch PSD
- short-time spectrogram
- band-limited power versus time
- cross-BPM magnitude-squared coherence and phase when two BPMs are selected
- saved tune readback markers, harmonics, and first synchrotron sidebands when the capture contains valid tune metadata
- for horizontal-like motion, a simple correlation between band power and the built-in SSMB `|Dx|` guide

The default search band is `1 kHz` to `200 kHz`, motivated by historical MLS CSR-power fluctuation measurements. The full turn-by-turn bandwidth remains available by changing the settings.

## Interpretation Checklist

Use the plots to separate possibilities rather than automatically labeling a peak as bursting:

- Transverse motion: features follow transverse tune markers or beta-like behavior.
- Longitudinal centroid motion: common-mode phase and high-dispersion horizontal-like BPMs share a coherent feature.
- CSR bursting with weak centroid signature: THz signal may burst while BPM centroid observables stay quiet.
- Coupled transverse-longitudinal dynamics: features appear in both dispersive and transverse-like observables.
- Instrument artifact: a feature appears identically in unrelated channels or does not follow beam optics.

## Calibration Gaps

Before quantitative physics claims, confirm:

- physical A/B/C/D orientation
- one-sample-per-turn semantics
- DDC carrier/reference information
- fixed complex button gain/phase calibration
- timing coherence between BPM electronics
- real low-alpha/SSMB lattice and dispersion data
- synchronized THz detector timing if correlating with external THz data

The current built-in optics curves are orientation guides only.
