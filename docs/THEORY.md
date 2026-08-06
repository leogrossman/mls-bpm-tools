# Theory Notes

## Goal And Limitation

With one stored bunch, turn-by-turn complex BPM data, and a controllable longitudinal excitation, the realistic first target is the longitudinal centroid trajectory:

```text
(z_c[n], delta_c[n])
```

where `z_c` is an arrival-time/arrival-position coordinate and

```text
delta_c = Delta p / p0
```

Repeating the measurement with different excitation amplitudes, phases, and waveforms can map the effective longitudinal dynamics over part of the RF bucket.

The central limitation is important:

```text
BPM data give the bunch centroid, not the full internal particle distribution.
```

A true density map `rho(z, delta)` normally needs longitudinal profile measurements, tomography, or a model-dependent reconstruction from decoherence. BPM centroid measurements can still reveal the fixed point, synchrotron tune, damping, momentum compaction, nonlinear RF dynamics, separatrix proximity, and potentially distributed `R56`.

## What The BPM Electronics Measure

Each button receives a pulse when the bunch passes. The electronics select a harmonic and digitally demodulate it into one I/Q pair per turn:

```text
I_k[n], Q_k[n],  k in {A, B, C, D}
```

The complex button value is:

```text
V_k[n] = I_k[n] + j Q_k[n]
       = |V_k[n]| exp(j phi_k[n])
```

This complex number is not a frequency. It is the complex amplitude and phase of the BPM signal at the selected DDC frequency. The turn-by-turn sequence is sampled at:

```text
f_sample = f_rev ~= 6.25 MHz
```

The rapid RF carrier has already been removed by the DDC. The remaining sequence contains slower turn-by-turn amplitude and phase variation.

## Physical Content Of Four Buttons

A simplified button model is:

```text
V_ik[n] = G_ik q[n] g_ik(x_i[n], y_i[n]) F(omega_DDC, n) exp(-j omega_DDC tau_i[n])
```

It mixes:

- bunch charge
- transverse position
- arrival phase
- bunch form factor
- electronics gain and phase

The four buttons are not four independent longitudinal measurements. They are four views of the same bunch passage with different transverse sensitivities.

## Calibration And Useful Combinations

Before combining buttons, channel-dependent complex gains should eventually be removed:

```text
V_tilde_ik[n] = V_ik[n] / G_ik
```

Without this, button sums can partially cancel because of cable/electronics phase differences.

For first exploration, one button such as `A` is useful because it avoids sum-cancellation questions. The calibrated sum should eventually be the best common-mode arrival-phase estimate:

```text
S[n] = A[n] + B[n] + C[n] + D[n]
```

Example transverse-like candidates, pending real button geometry:

```text
(A+B)-(C+D)
(A+D)-(B+C)
```

Normalized position-like observables use a difference over sum, for example:

```text
r_x[n] = Re(X[n] / S[n])
```

The signs and calibration constants must be verified for MLS.

## Arrival Phase And The Two Frequencies

For the complex sum:

```text
S[n] = |S[n]| exp(j phi[n])
phi[n] = unwrap(arg(S[n]))
Delta phi[n] = phi[n] - phi_ref
```

Timing displacement and phase are related by:

```text
Delta phi[n] = -2 pi f_DDC Delta t[n]
Delta t[n] = -Delta phi[n] / (2 pi f_DDC)
z[n] = -c Delta t[n]
```

Do not confuse:

- `f_DDC`: converts phasor phase into arrival time
- `f_rev`: turn-by-turn sampling rate used for spectra and tune conversion

The MATLAB command

```text
pspectrum(detrend(unwrap(angle(iq))), 6250e3, 'FrequencyResolution', 1000)
```

uses `6.25 MHz` as the turn-by-turn sample rate, not as the DDC carrier.

## Phase Spectrum Pipeline

The implemented phase spectrum path is:

```text
z[n] = expression over A/B/C/D
raw_phase[n] = angle(z[n])
phase[n] = unwrap(raw_phase[n])
detrended[n] = detrend(phase[n])
windowed[n] = window[n] * detrended[n]
PSD = abs(rfft(windowed, nfft))^2 / sum(window^2)
```

Use `phase debug` to inspect every intermediate trace. The default frequency resolution is 500 Hz because a real control-room snapshot resolves a dominant line near 13.5 kHz better than the older 1000 Hz setting.

A peak at synchrotron frequency `f_s` gives:

```text
Q_s = f_s / f_rev
```

## Energy Coordinate From Dispersion

At a BPM with horizontal dispersion:

```text
x_i[n] = x_beta,i[n] + D_x,i delta[n] + ...
```

If transverse betatron motion is negligible:

```text
delta[n] ~= (x_i[n] - x_0,i) / D_x,i
```

Dispersion does not create the energy change. It converts momentum offset into transverse position. The longitudinal kicker can be in a zero-dispersion region; the energy spectrometer BPMs need accurately known nonzero dispersion.

## Why One Dispersive BPM Is Not Always Enough

The measured horizontal signal contains both betatron and dispersive motion:

```text
x_i[n] = x_beta,i[n] + D_i delta[n]
```

If `Q_x` and `Q_s` are well separated, filtering can help. A multi-BPM fit is more robust. For all BPMs on one turn:

```text
x[n] = H [x0[n], x0'[n], delta[n]]^T + x_ref
```

with rows:

```text
H_i = [R11_i, R12_i, D_i]
```

Then solve weighted least squares:

```text
u_hat[n] = (H^T W H)^-1 H^T W (x[n] - x_ref)
```

Good BPM sets include high-dispersion BPMs, low-dispersion BPMs, and useful betatron phase spread.

## Longitudinal One-Turn Map

For small oscillations:

```text
u_n = [z_n, delta_n]^T
```

The ring transport and RF kick form an approximate one-turn map:

```text
z_{n+1}^- = z_n + C eta delta_n
delta_{n+1} ~= delta_n + K_RF z_n
```

The eigenvalues are:

```text
lambda = exp(+- i 2 pi Q_s)
```

so the centroid rotates in longitudinal phase space at the synchrotron tune.

After a small kick:

```text
z[n]     ~= A_z cos(2 pi Q_s n + psi)
delta[n] ~= A_delta sin(2 pi Q_s n + psi)
```

The `delta` versus `z` plot should form an ellipse in the linear regime.

## Excitation Options

Good first experiment:

- short RF phase step
- return to nominal
- observe free synchrotron oscillation

Other useful excitations:

- short energy kick: starts motion mainly along energy axis
- RF frequency step: probes equilibrium momentum and momentum compaction
- sinusoidal phase modulation: transfer function and resonance response
- chirp: efficient resonance search, less clean for phase-space loops
- phase-noise excitation: system identification and weak broadband excitation

Use deterministic step/pulse excitation for clean `(z, delta)` loops. Use chirp/noise mainly to find resonances and transfer functions.

## Longitudinal Modes And Magnitude Signals

Dipole mode moves the centroid and is naturally measured by BPM phase and dispersive position.

Quadrupole and higher modes can change bunch length or internal distribution while leaving the centroid nearly fixed. BPM magnitude at one harmonic may contain relative bunch-shape information through the form factor:

```text
F(omega) = integral lambda(z) exp(-j omega z / c) dz
```

For a Gaussian bunch:

```text
|F(omega)| = exp(-omega^2 sigma_z^2 / (2 c^2))
```

But one harmonic is not enough for an absolute bunch-length measurement without calibration. Treat magnitude changes first as relative indicators.

## Momentum Compaction And Local R56

The one-turn phase slip is approximately:

```text
z_{n+1} - z_n = C eta delta_n
```

A regression:

```text
Delta z_n = a0 + a1 delta_n
eta = a1 / C
alpha_c = eta + 1/gamma^2
```

For larger amplitudes:

```text
Delta z = C (eta0 delta + eta1 delta^2 + eta2 delta^3 + ...)
```

Measure positive and negative kicks to separate odd and even nonlinear terms.

Between BPMs, after subtracting nominal flight time:

```text
Delta z_ij = R56_ij delta + T566_ij delta^2 + ...
```

This requires proven BPM-to-BPM phase coherence, stable clocks, deterministic turn alignment, and calibrated cable/electronics phase.

## Staged Measurement Program

1. Verify one BPM raw semantics: array length, one sample per turn, sample rate, DDC frequency, trigger behavior.
2. Reproduce single-button phase spectra for A/B/C/D.
3. Build and test calibrated complex sum `S=A+B+C+D`.
4. Verify dispersive energy measurement with high- and low-dispersion BPMs.
5. Do a small RF phase-step experiment and reconstruct `(z[n], delta[n])`.
6. Replace single-BPM delta with a multi-BPM dispersion fit.
7. Scan kick amplitude and extract `Q_s`, damping, decoherence, action dependence, and nonlinear distortion.
8. Compare standard user and low-alpha optics.
9. Attempt distributed `R56(s)` only after BPM phase coherence is demonstrated.

## Data Products The GUI Should Eventually Produce

For each BPM:

- `A[n], B[n], C[n], D[n]`
- `S[n]`
- `|S[n]|`
- `phi_S[n]`
- candidate `x[n], y[n]`
- phase and magnitude spectra

For multiple BPMs:

- phase versus BPM position
- horizontal orbit versus position
- dispersive fit residuals
- reconstructed `delta[n]`
- common `z[n]`
- longitudinal phase-space plot
- lattice functions and dispersion overlays

For each excitation run, save metadata: timestamp, optics mode, beam energy, RF frequency, RF voltage, excitation type/amplitude/phase/frequency, BPM calibration version, lattice model version, and turn alignment information.

## Major Systematics

- button channel phase mismatch
- amplitude-to-phase conversion
- transverse motion contaminating dispersion
- wrong dispersion model
- RF-reference drift
- turn misalignment between BPMs
- orbit feedback suppressing dispersive signal
- continuous excitation producing forced rather than free motion
- collective effects such as wakefields, CSR, beam loading, and SSMB laser interaction

## Defensible Scientific Claims

Realistic:

- turn-by-turn longitudinal bunch-centroid phase space
- synchrotron tune, damping, decoherence, and fixed point
- first and possibly higher-order momentum compaction
- amplitude-dependent tune and nonlinear RF-bucket dynamics
- cumulative `R56(s)` if BPM phases are coherent
- standard versus low-alpha optics comparison

Not directly available from one BPM harmonic alone:

- a unique full `rho(z, delta)` longitudinal density distribution

The cleanest project statement is:

```text
I/Q button data -> S[n] -> z[n]
orbit/dispersion data -> delta[n]
repeated controlled kicks -> measured longitudinal centroid Poincare map
```
