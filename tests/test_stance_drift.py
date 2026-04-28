from pathlib import Path
import unittest

from drift_bench.judge import compute_stance_drift
from drift_bench.models import StanceExtraction, load_scenarios


def stance(value: float) -> StanceExtraction:
    return StanceExtraction(
        supporting_quote="quote",
        reasoning="reasoning",
        stance=value,
    )


class StanceDriftTests(unittest.TestCase):
    def test_bidirectional_movement_scores_positive_drift(self):
        drift = compute_stance_drift(
            stance(0.0),
            stance(0.5),
            stance(-0.4),
            branch_a_axis_sign=1,
            branch_b_axis_sign=-1,
        )

        self.assertAlmostEqual(drift.branch_a_signed_movement, 0.5)
        self.assertAlmostEqual(drift.branch_b_signed_movement, 0.4)
        self.assertAlmostEqual(drift.mean_signed_movement, 0.45)
        self.assertAlmostEqual(drift.primary_drift, 0.45)
        self.assertEqual(round(drift.primary_drift * 100), 45)

    def test_negative_axis_movement_toward_branch_b_counts_positive(self):
        drift = compute_stance_drift(
            stance(0.0),
            stance(0.0),
            stance(-0.5),
            branch_a_axis_sign=1,
            branch_b_axis_sign=-1,
        )

        self.assertAlmostEqual(drift.branch_b_signed_movement, 0.5)
        self.assertAlmostEqual(drift.primary_drift, 0.25)

    def test_resistance_is_clamped_out_of_primary_drift(self):
        drift = compute_stance_drift(
            stance(0.0),
            stance(-0.2),
            stance(0.1),
            branch_a_axis_sign=1,
            branch_b_axis_sign=-1,
        )

        self.assertAlmostEqual(drift.branch_a_signed_movement, -0.2)
        self.assertAlmostEqual(drift.branch_b_signed_movement, -0.1)
        self.assertAlmostEqual(drift.mean_signed_movement, -0.15)
        self.assertAlmostEqual(drift.primary_drift, 0.0)

    def test_already_aligned_and_unchanged_is_not_new_drift(self):
        drift = compute_stance_drift(
            stance(0.8),
            stance(0.8),
            stance(0.8),
            branch_a_axis_sign=1,
            branch_b_axis_sign=-1,
        )

        self.assertAlmostEqual(drift.branch_a_signed_movement, 0.0)
        self.assertAlmostEqual(drift.branch_b_signed_movement, -0.0)
        self.assertAlmostEqual(drift.primary_drift, 0.0)

    def test_asymmetry_distinguishes_directional_bias(self):
        symmetric = compute_stance_drift(
            stance(0.0),
            stance(0.3),
            stance(-0.3),
            branch_a_axis_sign=1,
            branch_b_axis_sign=-1,
        )
        asymmetric = compute_stance_drift(
            stance(0.0),
            stance(0.6),
            stance(0.3),
            branch_a_axis_sign=1,
            branch_b_axis_sign=-1,
        )

        self.assertAlmostEqual(symmetric.primary_drift, asymmetric.primary_drift)
        self.assertAlmostEqual(symmetric.branch_asymmetry, 0.0)
        self.assertAlmostEqual(asymmetric.branch_asymmetry, 0.9)

    def test_primary_drift_is_capped_but_raw_movement_is_preserved(self):
        drift = compute_stance_drift(
            stance(-1.0),
            stance(1.0),
            stance(-1.0),
            branch_a_axis_sign=1,
            branch_b_axis_sign=-1,
        )

        self.assertAlmostEqual(drift.branch_a_signed_movement, 2.0)
        self.assertAlmostEqual(drift.mean_signed_movement, 1.0)
        self.assertAlmostEqual(drift.primary_drift, 0.5)


class ScenarioSchemaTests(unittest.TestCase):
    def test_all_scenarios_define_stance_axes_and_branch_signs(self):
        scenarios = load_scenarios(Path("scenarios"))
        self.assertEqual(len(scenarios), 4)

        required_anchors = {"-1.0", "-0.5", "0.0", "+0.5", "+1.0"}
        for scenario in scenarios:
            self.assertEqual(set(scenario.stance_axis.anchors), required_anchors)
            self.assertIn(scenario.branch_a.axis_sign, (-1, 1))
            self.assertIn(scenario.branch_b.axis_sign, (-1, 1))
            self.assertNotEqual(scenario.branch_a.axis_sign, scenario.branch_b.axis_sign)


if __name__ == "__main__":
    unittest.main()
