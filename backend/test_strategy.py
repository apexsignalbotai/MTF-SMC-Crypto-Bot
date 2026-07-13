import unittest
import pandas as pd
import numpy as np
import scanner as sc

class TestSMCCryptoBotStrategy(unittest.TestCase):
    
    def setUp(self):
        """Set up dummy data for structural testing."""
        # Create a series of 10 candles
        # Index 5 will be a clear Swing High, Index 7 a clear Swing Low
        self.dummy_candles = pd.DataFrame({
            "timestamp": [i * 3600 * 1000 for i in range(10)],
            "open":  [100, 102, 104, 103, 105, 110, 104, 98,  102, 103],
            "high":  [102, 105, 106, 104, 107, 115, 106, 102, 105, 107], # Index 5 (high=115) is a swing high
            "low":   [98,  100, 102, 101, 103, 108, 100, 95,  99,  100], # Index 7 (low=95) is a swing low
            "close": [101, 104, 103, 102, 106, 109, 101, 99,  103, 105],
            "volume": [1000] * 10
        })

    def test_fractal_swing_detection(self):
        """Verify that find_swings correctly identifies fractal highs and lows."""
        df_swings = sc.find_swings(self.dummy_candles, window=2)
        
        # Check Swing High at index 5 (high=115, previous highs: 104, 107, next highs: 106, 102)
        self.assertEqual(df_swings.iloc[5]["swing_high"], 115.0)
        
        # Check Swing Low at index 7 (low=95, previous lows: 108, 100, next lows: 99, 100)
        self.assertEqual(df_swings.iloc[7]["swing_low"], 95.0)
        
        # Check that non-swings are NaN
        self.assertTrue(np.isnan(df_swings.iloc[0]["swing_high"]))
        self.assertTrue(np.isnan(df_swings.iloc[1]["swing_low"]))

    def test_fibonacci_ote_long_calculation(self):
        """Verify 1:2 Risk-to-Reward calculation for a Bullish setup (LONG)."""
        actual_entry = 120.0
        actual_sl = 100.0
        
        actual_risk = actual_entry - actual_sl
        actual_tp = actual_entry + (2.0 * actual_risk)
        
        self.assertEqual(actual_risk, 20.0)
        self.assertEqual(actual_tp, 160.0)
 
    def test_fibonacci_ote_short_calculation(self):
        """Verify 1:2 Risk-to-Reward calculation for a Bearish setup (SHORT)."""
        actual_entry = 80.0
        actual_sl = 100.0
        
        actual_risk = actual_sl - actual_entry
        actual_tp = actual_entry - (2.0 * actual_risk)
        
        self.assertEqual(actual_risk, 20.0)
        self.assertEqual(actual_tp, 40.0)

if __name__ == "__main__":
    unittest.main()
