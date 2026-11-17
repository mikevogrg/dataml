# 15-minute talk plan and live-demo script

Timing (matches the speaker notes): cover 0:30 | problem 1:00 | question 0:30 | approach 1:30 | key idea 1:00 | **DEMO 4:00** | results 0:30 | ablation 1:00 | ML findings 1:00 | online 0:30 | ethics 1:00 | limits 1:00 | close + questions 1:30.

## Before you present (do this the day before)
1. `pip install -r requirements.txt`, then `python -m pytest -q tests` (9 pass).
2. `python demo.py` once so `results/` already holds the plots and report (this is your backup).
3. Open a terminal in the project folder, font size large. Close notifications.

## Live steps (about 4 minutes)
| Step | Command | What to say |
|---|---|---|
| 1 | `python main.py simulate --out data/demo.csv` | "A simulated network of 8 sensors with six kinds of injected faults; we know the truth, so we can score ourselves." |
| 2 | `python main.py clean --input data/demo.csv --mode batch` | "About 10% of points were faulty; this table is how many readings it flagged per channel." |
| 3 | `python main.py explain --mote 3 --channel humidity` | "Every change has a reason. Raw values are never deleted." |
| 4 | `python demo.py --stream` | "Online mode: fault, repair, and the hidden true value side by side." |
| 5 | open `results/before_after_humidity.png` | "A drift and a frozen stretch, caught and repaired." |

## If something breaks
Open `results/before_after_humidity.png` and `results/report.md` (already generated) and say: "Here is the output from our last run." Do not debug live.

## Likely questions
- *Why not deep learning?* We named an autoencoder as future work; a supervised Random Forest already ties our unsupervised system (E5), so extra complexity was not justified yet.
- *Why synthetic data?* Real Intel Lab data has no fault labels, so it cannot be scored; we use it for qualitative inspection (`python demo.py --intel data.txt.gz`).
- *Is 0.94 realistic?* On real data expect lower; the simulator is smoother and more correlated than reality (limits slide).
- *How would you deploy it?* Online cleaner on the gateway, offline cleaner nightly, audit database for review.
