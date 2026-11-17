import unittest

from src.core import regularise
from src import config as C


class RegulariseTests(unittest.TestCase):
    def row(self, timestamp, temperature):
        result = {"timestamp": timestamp, "mote_id": 1}
        for channel in C.CHANNELS:
            result[channel] = temperature if channel == "temperature" else 10.0
        return result

    def test_aggregates_31_second_samples_into_five_minute_bins(self):
        rows = [
            self.row("2004-02-28 00:00:00", 20.0),
            self.row("2004-02-28 00:00:31", 22.0),
            self.row("2004-02-28 00:04:58", 24.0),
            self.row("2004-02-28 00:05:29", 26.0),
        ]
        result = regularise(rows)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["timestamp"], "2004-02-28 00:00:00")
        self.assertEqual(result[0]["temperature"], 22.0)
        self.assertEqual(result[1]["timestamp"], "2004-02-28 00:05:00")
        self.assertEqual(result[1]["temperature"], 25.0)

    def test_inserts_missing_five_minute_bins(self):
        rows = [
            self.row("2004-02-28 00:00:00", 20.0),
            self.row("2004-02-28 00:10:00", 24.0),
        ]
        result = regularise(rows)
        self.assertEqual(len(result), 3)
        self.assertIsNone(result[1]["temperature"])


if __name__ == "__main__":
    unittest.main()
