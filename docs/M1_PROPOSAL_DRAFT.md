# M1 Proposal - AI Data Cleaning for IoT Sensor Streams (draft for group edit)

**Problem statement.** IoT sensor networks produce streams riddled with missing values, impossible readings, spikes, stuck sensors, bias and drift. Feeding this to analytics or control systems produces wrong decisions. Manual cleaning does not scale and single-technique cleaners miss whole fault classes.

**Objectives.**
1. Build an end-to-end pipeline: ingest -> validate -> detect faults -> repair -> report.
2. Detect six fault types (spike, stuck, bias, drift, out-of-range, missing) with F1 >= 0.90 on labelled data.
3. Reduce error versus the hidden true signal by >= 90% (RMSE).
4. Demonstrate on real data (Intel Lab) and measure on labelled data (synthetic + benchmark).

**Methodology.** Layered hybrid: range rules -> Hampel filter -> stuck-at rule -> spatial-consistency test -> Isolation Forest -> imputation (linear / neighbour-based). Evaluate each layer alone vs hybrid (ablation). See README for current prototype results.

**Team roles (suggested - confirm in the group).**
- Lt: pipeline + cleaning model + demo (built), dataset/literature search.
- Member 2: literature review write-up, ethics section, report.
- Member 3: dataset 2 (labelled benchmarks) integration, evaluation, slides.

**Literature review.** See `docs/LITERATURE_REVIEW.md`.

**Timeline.** M1 proposal -> M2 design (architecture diagram, ethics) -> M3 prototype (this repo already has one) -> M4 GitHub/README/tests -> M5 report (<=20 pages), slides, 15-min live demo.
