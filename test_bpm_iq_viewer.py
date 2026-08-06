import tempfile
import unittest
import json
from pathlib import Path

import numpy as np

from bpm_iq_viewer import (
    AppConfig,
    DemoBackend,
    SessionLogger,
    combination_expression,
    normalize_button_tokens,
    pv_for,
    read_button_phasors,
    spectrum,
    tune_markers_from_values,
    tune_value_to_frequency,
)


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
        self.assertEqual([item.pv for item in cfg.tune_pvs], ["TUNEZRP:measX", "TUNEZRP:measY", "TUNEZRP:measZ"])
        self.assertLessEqual(cfg.epics_scalar_timeout_s, 0.5)

    def test_spectrum_peak_near_known_signal(self):
        fs = 1000.0
        n = np.arange(2048)
        x = np.sin(2 * np.pi * 125.0 * n / fs)

        freq, power = spectrum(x, fs)

        self.assertAlmostEqual(freq[np.argmax(power)], 125.0, delta=fs / x.size)

    def test_tune_value_conversion_and_harmonic_markers(self):
        freq, tune = tune_value_to_frequency(0.2, 1000.0, "auto")
        self.assertEqual(freq, 200.0)
        self.assertEqual(tune, 0.2)

        markers = tune_markers_from_values(
            {"Qx": {"value": 0.2, "unit": "auto", "color": "blue", "harmonics": 3}},
            fs=1000.0,
            include_harmonics=True,
        )

        self.assertEqual([item[0] for item in markers], [200.0, 400.0])

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
