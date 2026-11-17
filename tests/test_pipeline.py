"""Dependency-free regression tests for the repaired implementation."""
import tempfile,unittest
from pathlib import Path
from src.core import generate,CleaningPipeline,hampel_flags,stuck_flags,read_csv,write_csv,open_db,save_results,summary,to_long,stream_clean
from src import config as C

class PipelineTests(unittest.TestCase):
    def test_hampel_detects_spike(self):
        vals=[20.0+(i%3)*.02 for i in range(100)]; vals[50]=26
        self.assertTrue(hampel_flags(vals)[50])
    def test_stuck_and_night_light(self):
        self.assertTrue(all(stuck_flags([1.0]*12,"temperature")))
        self.assertFalse(any(stuck_flags([0.0]*50,"light")))
    def test_hybrid_pipeline_shapes_and_audit(self):
        raw=generate(n_motes=4,days=2)
        rows,cleaned,flags,report=CleaningPipeline().run(raw)
        self.assertEqual(len(rows),len(cleaned))
        self.assertTrue(any(flags["temperature"]))
        results=to_long(rows,cleaned,flags)
        con=open_db(); save_results(con,results)
        self.assertEqual({r[0] for r in summary(con)},set(C.CHANNELS))
        self.assertGreater(con.execute("SELECT COUNT(*) FROM readings WHERE raw IS NOT NULL").fetchone()[0],0)
    def test_csv_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"sample.csv"; rows=generate(n_motes=2,days=1)
            write_csv(str(p),rows); loaded=read_csv(str(p))
            self.assertEqual(len(rows),len(loaded))
    def test_stream_output(self):
        rows=generate(n_motes=3,days=1)
        result=stream_clean(rows)
        self.assertEqual(len(result),len(rows)*len(C.CHANNELS))
        self.assertTrue(all("reasons" in r for r in result))

if __name__=="__main__": unittest.main()
