import unittest

import numpy as np
import pandas as pd

from scripts.analysis.robustness import (
    factor_alpha,
    hac_mean,
    moving_block_bootstrap_mean,
    two_sample_block_bootstrap_difference,
)


class RobustnessTests(unittest.TestCase):
    def test_hac_mean_returns_sample_mean(self):
        values = np.linspace(-0.01, 0.02, 40)
        result = hac_mean(values, maxlags=3)
        self.assertAlmostEqual(result["estimate"], values.mean())
        self.assertEqual(result["n_days"], 40)

    def test_block_bootstrap_is_deterministic(self):
        values = np.arange(30, dtype=float)
        first = moving_block_bootstrap_mean(values, repetitions=100, seed=7)
        second = moving_block_bootstrap_mean(values, repetitions=100, seed=7)
        self.assertEqual(first, second)

    def test_factor_alpha_recovers_intercept(self):
        factor = np.linspace(-0.02, 0.02, 80)
        frame = pd.DataFrame({"return": 0.001 + 0.5 * factor, "mkt_rf": factor})
        result = factor_alpha(frame, "return", ["mkt_rf"], maxlags=3)
        self.assertAlmostEqual(result["alpha_daily"], 0.001, places=10)
        self.assertAlmostEqual(result["beta_mkt_rf"], 0.5, places=10)

    def test_two_sample_difference_uses_requested_order(self):
        result = two_sample_block_bootstrap_difference(
            np.full(20, 0.02), np.full(20, 0.01), repetitions=100
        )
        self.assertAlmostEqual(result["difference"], 0.01)


if __name__ == "__main__":
    unittest.main()
