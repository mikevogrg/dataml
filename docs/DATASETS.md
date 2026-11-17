# Datasets for the AI Data Cleaning project

| # | Dataset | What it is | Labels? | Link | Verified |
|---|---------|-----------|---------|------|----------|
| 1 | **Intel Berkeley Research Lab** | 54 Mica2Dot motes, 28 Feb - 5 Apr 2004, reading every ~31 s, ~2.3 M rows. Fields: date, time, epoch, moteid, temperature, humidity, light, voltage. Known real faults (e.g. temperature 122.153 C, negative humidity, voltage drops). Free to use; acknowledge Bodik, Hong, Guestrin, Madden, Paskin, Thibaux. | No (qualitative only) | https://db.csail.mit.edu/labdata/labdata.html  (data: https://db.csail.mit.edu/labdata//data.txt.gz, 34 MB) | Yes, page read |
| 2 | **de Bruijn et al. fault benchmarks** | Intel Lab (280 subsets, temp+light, 10 sensors), SensorScope (140 outdoor temperature subsets), Smart Santander (224 subsets, 16 sensors). 5.78 M points with *labelled injected faults*: random, malfunction, bias, drift, polynomial drift, combos. | **Yes** | Paper: https://scitepress.org/Documents/2016/56379/ (check paper for the data/tool link) | Paper read; data link not checked |
| 3 | **Numenta Anomaly Benchmark (NAB)** | 58 labelled time series (365,551 points), real + artificial, single scalar per row | **Yes** (windows) | https://github.com/numenta/NAB | Yes, paper read |
| 4 | **Our synthetic generator** (`src/simulator.py`) | Multi-mote, 4 channels, 6 fault types, exact ground truth and the true clean signal | **Yes, plus true values** | in this repo | Yes |

## Recommendation
- **Method scoring (precision/recall/RMSE):** synthetic generator + dataset 2.
- **"It works on real data" demo:** Intel Lab, `python demo.py --intel data.txt.gz` (not yet run on the real file - the build environment could not download it; the loader was tested only on a 2-row file in the real format).
- Why both: real data convinces markers; labelled data lets you *measure*. Dataset 2 combines both (real signals, injected labelled faults) - best candidate to add for M3.
