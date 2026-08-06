# Theory Notes

## Complex Button Signal

For button `A`, the raw DDC waveforms are one I/Q pair per turn:

```text
A[n] = I_A[n] + i Q_A[n]
     = |A[n]| exp(i phi_A[n])
```

This is a complex turn-by-turn amplitude relative to the DDC reference. It is not itself a frequency.

## Standard Combinations

Common mode:

```text
S[n] = A[n] + B[n] + C[n] + D[n]
```

The phase of `S[n]` is the first longitudinal arrival-phase candidate. The magnitude is a charge/signal-strength candidate.

Example uncalibrated transverse-like differences:

```text
(A+B)-(C+D)
(A+D)-(B+C)
```

These are deliberately marked as candidates until button geometry and calibration constants are confirmed.

## Phase Spectrum Pipeline

The MATLAB sketch was:

```text
pspectrum(detrend(unwrap(angle(iq))), 6250e3, 'FrequencyResolution', 1000)
```

The implemented pipeline is:

```text
z[n] = expression over A/B/C/D
raw_phase[n] = angle(z[n])
phase[n] = unwrap(raw_phase[n])
detrended[n] = detrend(phase[n])
windowed[n] = window[n] * detrended[n]
PSD = abs(rfft(windowed, nfft))^2 / sum(window^2)
```

`phase debug` plots every step. The default frequency resolution is 500 Hz because the real snapshot regression resolves the dominant line near 13.5 kHz better than 1000 Hz bins.

## Tune Markers

Tune PVs:

```text
TUNEZRP:measX
TUNEZRP:measY
TUNEZRP:measZ
```

Values between 0 and 1 are treated as tune fractions:

```text
f_marker = Q * f_sample
```

Larger values are treated as Hz unless configured otherwise.

## Later Phase-Space Work

A future calibrated workflow should:

1. Build calibrated common-mode phasor `S[n]`.
2. Convert phase to arrival time with the confirmed DDC/RF reference frequency.
3. Use dispersive BPMs and lattice functions to estimate momentum error.
4. Fit multi-BPM transverse and longitudinal centroid coordinates.
