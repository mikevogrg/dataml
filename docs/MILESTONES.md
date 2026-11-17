# Milestone map: what exists for M1-M5

| Milestone | Requirement | Where it is | Status |
|---|---|---|---|
| **M1 Proposal** | Problem statement, objectives, methodology, team roles, initial literature review | `docs/M1_PROPOSAL_DRAFT.md`, `docs/LITERATURE_REVIEW.md`, `docs/DATASETS.md` | Done. **Team roles for members 2 and 3 are suggestions: confirm in the group** |
| **M2 Design** | System architecture, data pipeline design, algorithm selection, ethical analysis | `docs/M2_DESIGN.md`, `docs/img/architecture.png` (+ source `.mmd`) | Done |
| **M3 Prototype** | Working core AI component, initial training results, evaluation metrics | `src/cleaning.py` (Isolation Forest + detectors), `experiments.py`, `experiments_novel.py` -> `results/experiments.md` (E1-E7) | Done on synthetic data; real data not yet scored |
| **M4 Integration** | Full integration, testing, documentation, GitHub repo with README | `main.py` (CLI), `src/stream.py`, `src/store.py`, `tests/` (9 tests), `README.md`, `ERROR_LOG.md` | Done. **Push to GitHub is yours to do** (see below) |
| **M5 Final** | Final code, report (<= 20 pages), slides, 15-min live demo | Report and deck are online documents (see `docs/M5_DELIVERABLES.md`); demo script `docs/DEMO_SCRIPT.md` | Drafted. **Rehearse the demo; check report page count after export** |

## Pushing to GitHub
```bash
git init && git add . && git commit -m "AI data cleaning for IoT sensor streams"
git branch -M main && git remote add origin <your-repo-url> && git push -u origin main
```
