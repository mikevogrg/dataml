"""SQLite audit store. WHY: cleaning must be reversible and explainable - we never delete raw data;
every flag keeps its reason so a human (or an auditor) can see why a value was changed."""
import sqlite3
import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
  timestamp TEXT, mote_id INTEGER, channel TEXT,
  raw REAL, cleaned REAL, flagged INTEGER, missing INTEGER, reasons TEXT,
  PRIMARY KEY (timestamp, mote_id, channel));
CREATE VIEW IF NOT EXISTS summary AS
  SELECT channel, COUNT(*) n, SUM(flagged) flagged, SUM(missing) missing,
         ROUND(100.0*SUM(flagged)/COUNT(*),2) pct_flagged FROM readings GROUP BY channel;
"""


def open_db(path=":memory:"):
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    return con


def save_results(con, results_df):
    d = results_df.copy()
    d["timestamp"] = d["timestamp"].astype(str)
    d["reasons"] = d["reasons"].apply(lambda r: ",".join(r))
    d["flagged"] = d["flagged"].astype(int); d["missing"] = d["missing"].astype(int)
    d[["timestamp", "mote_id", "channel", "raw", "cleaned", "flagged", "missing", "reasons"]].to_sql(
        "readings", con, if_exists="append", index=False)
    con.commit()


def summary(con):
    return pd.read_sql("SELECT * FROM summary", con)


def explain(con, mote_id, channel, limit=10):
    """Why was this mote/channel changed? Most recent flagged readings with reasons."""
    return pd.read_sql("SELECT timestamp, raw, cleaned, reasons FROM readings WHERE mote_id=? AND channel=? "
                       "AND flagged=1 ORDER BY timestamp DESC LIMIT ?", con, params=(mote_id, channel, limit))
