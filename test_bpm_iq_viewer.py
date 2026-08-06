import tempfile
import unittest
import json
from pathlib import Path

import numpy as np

from bpm_core import (
    AppConfig,
    DemoBackend,
    SpectrumSettings,
    COMBINATION_PRESETS,
    combine_selected_expressions,
    combination_expression,
    decimation_stride,
    estimate_iq_payload,
    find_spectrum_peaks,
    human_bytes,
    nearest_bpm_marker,
    normalize_button_tokens,
    normalize_power,
    phase_pipeline,
    pv_for,
    read_button_phasors,
    spectrum,
    spectrum_pipeline,
    tbt_scan_commands,
    tune_markers_from_values,
    tune_value_to_frequency,
)
from bpm_iq_viewer import SessionLogger, build_arg_parser, runtime_mode_from_args


class BPMIQViewerTest(unittest.TestCase):
    def test_combination_expression_sum_and_mean(self):
        data = {
            "A": np.array([1 + 1j, 2 + 2j]),
            "B": np.array([3 + 0j, 4 + 0j]),
            "C": np.array([0 + 1j, 0 + 2j]),
            "D": np.array([1 + 0j, 1 + 0j]),
        }

        np.testing.assert_allclose(combination_expression(data, "A+B"), data["A"] + data["B"])
        np.testing.assert_allclose(
            combination_expression(data, "mean(A,B,C,D)"),
            np.mean(np.vstack([data["A"], data["B"], data["C"], data["D"]]), axis=0),
        )
        np.testing.assert_allclose(combination_expression(data, "conj(A)"), np.conjugate(data["A"]))
        np.testing.assert_allclose(combination_expression(data, "abs(A)"), np.abs(data["A"]))

    def test_combination_expression_blocks_unknown_names(self):
        data = {"A": np.array([1 + 0j])}

        with self.assertRaises(ValueError):
            combination_expression(data, "__import__('os').system('caput BAD 1')")

    def test_button_token_detection(self):
        self.assertEqual(normalize_button_tokens("(A+B)-(C+D)"), ["A", "B", "C", "D"])
        self.assertEqual(normalize_button_tokens("mean(A,A,b)"), ["A", "B"])

    def test_expression_preset_builder_defaults_and_custom(self):
        self.assertEqual(COMBINATION_PRESETS[0][1], "A+B+C+D")
        self.assertEqual(combine_selected_expressions([], "", False), "A+B+C+D; A")
        self.assertEqual(
            combine_selected_expressions(["A", "A+B+C+D", "A"], "B; C", True),
            "A; A+B+C+D; B; C",
        )

    def test_nearest_bpm_marker_requires_close_click(self):
        markers = {"BPMZ1L2RP": (10.0, 20.0), "BPMZ3L2RP": (40.0, 20.0)}

        self.assertEqual(nearest_bpm_marker(13.0, 21.0, markers, max_distance=8.0), "BPMZ1L2RP")
        self.assertIsNone(nearest_bpm_marker(25.0, 60.0, markers, max_distance=8.0))

    def test_default_runtime_is_live_safe_not_demo(self):
        parser = build_arg_parser()

        use_live, can_write, label = runtime_mode_from_args(parser.parse_args([]))

        self.assertTrue(use_live)
        self.assertFalse(can_write)
        self.assertIn("LIVE SAFE", label)

    def test_demo_runtime_is_explicit(self):
        parser = build_arg_parser()

        use_live, can_write, label = runtime_mode_from_args(parser.parse_args(["--demo"]))

        self.assertFalse(use_live)
        self.assertFalse(can_write)
        self.assertIn("DEMO", label)

    def test_pv_templates_and_status_config_load(self):
        config_text = """
        {
          "sample_rate_hz": 6250000.0,
          "pv_templates": {
            "scan": "{bpm}:signals:ddc_raw.SCAN",
            "i": "{bpm}:signals:ddc_raw.I{button}",
            "q": "{bpm}:signals:ddc_raw.Q{button}"
          },
          "status_pvs": [
            {
              "label": "Phase noise",
              "pv": "TEST:PHASE:ENABLE",
              "on_values": ["1"],
              "direction": "longitudinal",
              "excitation": "phase noise"
            }
          ],
          "bpms": [{"name": "BPMZ1L2RP"}]
        }
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(config_text)
            cfg = AppConfig.load(path)

        self.assertEqual(pv_for(cfg, "BPMZ1L2RP", "i", "A"), "BPMZ1L2RP:signals:ddc_raw.Ia")
        self.assertEqual(cfg.status_pvs[0].pv, "TEST:PHASE:ENABLE")

    def test_demo_backend_reads_four_complex_buttons_same_length(self):
        cfg = AppConfig.load(Path(__file__).with_name("bpm_config.json"))
        backend = DemoBackend(n=128, fs=cfg.sample_rate_hz)

        phasors = read_button_phasors(backend, cfg, "BPMZ1L2RP", ["A", "B", "C", "D"])

        self.assertEqual(set(phasors), {"A", "B", "C", "D"})
        self.assertTrue(all(value.shape == (128,) for value in phasors.values()))
        self.assertTrue(all(np.iscomplexobj(value) for value in phasors.values()))

    def test_default_config_has_ring_bpms_tunes_and_fast_scalar_timeout(self):
        cfg = AppConfig.load(Path(__file__).with_name("bpm_config.json"))

        self.assertGreaterEqual(len(cfg.bpms), 28)
        self.assertTrue(any(bpm.name == "BPMZ1L2RP" and bpm.x_pv == "BPMZ1L2RP:rdX" for bpm in cfg.bpms))
        self.assertTrue(any(bpm.name == "BPMZ3L2RP" and bpm.known_orbit_pvs for bpm in cfg.bpms))
        self.assertEqual(cfg.pv_templates["synth_scan"], "{bpm}:signals:ddc_synth.SCAN")
        self.assertEqual(cfg.raw_scan_on_value, "1 second")
        self.assertEqual(cfg.raw_scan_off_value, "Passive")
        self.assertEqual([item.pv for item in cfg.tune_pvs], ["TUNEZRP:measX", "TUNEZRP:measY", "TUNEZRP:measZ"])
        self.assertGreaterEqual(cfg.refresh_ms, 3000)
        self.assertFalse(next(item for item in cfg.status_pvs if item.pv == "BBQRP:X:DRIVEO").enabled)
        self.assertTrue(next(item for item in cfg.status_pvs if item.pv == "WFGEN2C1CP:stOut").enabled)
        self.assertLessEqual(cfg.epics_scalar_timeout_s, 0.5)

    def test_iq_payload_estimate_matches_iq_waveform_count(self):
        payload = estimate_iq_payload(n_bpms=2, n_buttons=4, n_samples=8192)

        self.assertEqual(payload["pv_count"], 16.0)
        self.assertEqual(payload["samples"], 131072.0)
        self.assertEqual(payload["bytes"], 1048576.0)
        self.assertEqual(human_bytes(payload["bytes"]), "1.0 MiB")

    def test_decimation_stride_limits_display_points(self):
        self.assertEqual(decimation_stride(1000, 2500), 1)
        self.assertEqual(decimation_stride(8192, 2500), 4)
        self.assertEqual(decimation_stride(8192, 0), 1)

    def test_config_save_roundtrip_keeps_runtime_pv_edits(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(__file__).with_name("bpm_config.json")
            path = Path(tmp) / "config.json"
            path.write_text(src.read_text())
            cfg = AppConfig.load(path)
            cfg.status_pvs[0].pv = "TEST:EDITED"
            cfg.status_pvs[0].enabled = False
            cfg.bpms[0].known_orbit_pvs = True
            cfg.save()

            reloaded = AppConfig.load(path)

        self.assertEqual(reloaded.status_pvs[0].pv, "TEST:EDITED")
        self.assertFalse(reloaded.status_pvs[0].enabled)
        self.assertTrue(reloaded.bpms[0].known_orbit_pvs)

    def test_tbt_scan_commands_match_control_room_scripts(self):
        cfg = AppConfig.load(Path(__file__).with_name("bpm_config.json"))

        on = tbt_scan_commands(cfg, ["BPMZ1L2RP"], enabled=True)
        off = tbt_scan_commands(cfg, ["BPMZ1L2RP"], enabled=False)

        self.assertEqual(
            on,
            [
                ("BPMZ1L2RP:signals:ddc_raw.SCAN", "1 second"),
                ("BPMZ1L2RP:signals:ddc_synth.SCAN", "1 second"),
            ],
        )
        self.assertEqual(
            off,
            [
                ("BPMZ1L2RP:signals:ddc_raw.SCAN", "Passive"),
                ("BPMZ1L2RP:signals:ddc_synth.SCAN", "Passive"),
            ],
        )

    def test_spectrum_peak_near_known_signal(self):
        fs = 1000.0
        n = np.arange(2048)
        x = np.sin(2 * np.pi * 125.0 * n / fs)

        freq, power = spectrum(x, fs)

        self.assertAlmostEqual(freq[np.argmax(power)], 125.0, delta=fs / x.size)

    def test_phase_unwrap_recovers_continuous_ramp(self):
        n = np.arange(128)
        true_phase = 0.35 * n - 4.0
        z = np.exp(1j * true_phase)

        steps = phase_pipeline(z, SpectrumSettings(unwrap_phase=True))

        offset = steps["phase"][0] - true_phase[0]
        np.testing.assert_allclose(steps["phase"] - offset, true_phase, atol=1e-12)
        self.assertGreater(np.max(np.abs(np.diff(steps["raw_phase"]))), np.pi)

    def test_phase_spectrum_matches_matlab_style_unwrap_detrend(self):
        fs = 6250.0
        n = np.arange(4096)
        modulation_hz = 312.5
        slow_phase_ramp = 0.02 * n
        modulation = 0.08 * np.sin(2 * np.pi * modulation_hz * n / fs)
        iq = np.exp(1j * (slow_phase_ramp + modulation))
        settings = SpectrumSettings(
            unwrap_phase=True,
            detrend="linear",
            window="hann",
            frequency_resolution_hz=10.0,
        )

        phase = phase_pipeline(iq, settings)["phase"]
        spec = spectrum_pipeline(phase, fs, settings)
        peak = spec["frequency_hz"][np.argmax(spec["psd"][1:]) + 1]

        self.assertAlmostEqual(peak, modulation_hz, delta=10.0)
        self.assertLess(abs(np.mean(spec["detrended"])), 1e-10)

    def test_spectrum_pipeline_window_and_nfft_settings(self):
        fs = 1000.0
        x = np.ones(16)
        settings = SpectrumSettings(detrend="none", window="rectangular", nfft=64)

        spec = spectrum_pipeline(x, fs, settings)

        self.assertEqual(len(spec["frequency_hz"]), 33)
        np.testing.assert_allclose(spec["window"], np.ones(16))
        np.testing.assert_allclose(spec["windowed"], x)

    def test_normalize_power_and_peak_finder(self):
        freq = np.arange(0, 10, dtype=float)
        power = np.array([0, 1, 5, 1, 0, 2, 9, 2, 0, 1], dtype=float)

        norm = normalize_power(power)
        peaks = find_spectrum_peaks(freq, norm, max_peaks=2, min_frequency_hz=1.0, min_relative_height=0.1)

        self.assertEqual(norm.max(), 1.0)
        self.assertEqual([item[0] for item in peaks], [6.0, 2.0])

    def test_control_room_snapshot_phase_spectrum_regression(self):
        fixture = Path(__file__).parent / "tests" / "fixtures" / "control_room_BPMZ1L2RP_sum_2048.npz"
        data = np.load(fixture)
        settings = SpectrumSettings(
            unwrap_phase=True,
            detrend="linear",
            window="hann",
            frequency_resolution_hz=500.0,
        )

        phase = phase_pipeline(data["combined"], settings)["phase"]
        spec = spectrum_pipeline(phase, 6250e3, settings)
        power = spec["psd"].copy()
        power[0] = 0.0
        peak = spec["frequency_hz"][np.argmax(power)]

        self.assertAlmostEqual(peak, 13500.0, delta=500.0)
        self.assertLess(np.max(np.abs(np.diff(np.angle(data["combined"])))), np.pi)

    def test_tune_value_conversion_and_harmonic_markers(self):
        freq, tune = tune_value_to_frequency(0.2, 1000.0, "auto")
        self.assertEqual(freq, 200.0)
        self.assertEqual(tune, 0.2)

        freq, tune = tune_value_to_frequency(13.5, 6250e3, "auto")
        self.assertEqual(freq, 13_500.0)
        self.assertAlmostEqual(tune, 13_500.0 / 6250e3)

        markers = tune_markers_from_values(
            {"Qx": {"value": 0.2, "unit": "auto", "color": "blue", "harmonics": 3}},
            fs=1000.0,
            include_harmonics=True,
        )

        self.assertEqual([item[0] for item in markers], [200.0, 400.0])

        bad_markers = tune_markers_from_values(
            {
                "nan": {"value": float("nan"), "unit": "auto"},
                "zero": {"value": 0, "unit": "auto"},
                "too_high": {"value": 900.0, "unit": "hz"},
            },
            fs=1000.0,
            include_harmonics=True,
        )
        self.assertEqual(bad_markers, [])

    def test_session_logger_writes_jsonl_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = SessionLogger(Path(tmp))
            logger.event("pv_error", pv="BROKEN:PV", error="timeout")
            lines = logger.events_path.read_text().splitlines()

        self.assertEqual(len(lines), 1)
        record = json.loads(lines[0])
        self.assertEqual(record["event"], "pv_error")
        self.assertEqual(record["pv"], "BROKEN:PV")


if __name__ == "__main__":
    unittest.main()
