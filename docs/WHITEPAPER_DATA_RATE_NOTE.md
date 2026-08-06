# Whitepaper Data-Rate Note

The whitepaper estimate:

```text
28 BPMs * 4 complex electrodes * 6.25 MHz * 8 bytes ~= 5.6 GB/s ~= 44.8 Gbit/s
```

is correct as a first-order design-bound estimate for continuous full-rate complex64 streaming from all BPM buttons.

Important caveats:

- It assumes each electrode is already one complex64 value per turn.
- It does not include protocol, timestamp, packet, archive, metadata, or replication overhead.
- It is not the same as the current Tk GUI read path.

The current GUI reads finite waveform blocks through separate Channel Access I and Q PVs. Its per-refresh raw payload estimate is:

```text
BPM_count * button_count * 2 I/Q PVs * waveform_samples * 8 bytes
```

Example:

```text
2 BPMs * 4 buttons * 2 PVs * 8192 samples * 8 bytes = 1.0 MiB per fresh refresh
```

That is the raw I/Q array payload after pyepics converts the waveform values to `float64`. Plotting, FFTs, copies, and Matplotlib rendering add CPU and memory traffic. The GUI `Load:` line reports the measured per-refresh version of this number.
