# Initial literature review (M1 draft)

> **Citation status.** [V] = I opened the source and checked title/abstract. [B] = from background knowledge, NOT opened - check the exact authors/year/venue before it goes in the report.

## 1. Why IoT data needs cleaning
Sensor streams contain missing values, outliers, bias, drift and stuck readings caused by hardware, battery and communication faults. A systematic review of 57 sensor-data-quality papers (screened from 6,970 records) found missing data and faults such as outliers, bias and drift to be the most common errors; PCA and artificial neural networks accounted for ~40% of detection methods, and Bayesian networks and association-rule mining were common for correction/imputation. Crucially, methods could not be compared directly because evaluation protocols differ and many studies use private datasets. **[V]** *Sensor data quality: a systematic review*, Journal of Big Data, 2020, DOI 10.1186/s40537-020-0285-1 (authors: Teh, Kempa-Liehr, Wang - confirm on the paper page).
**Gap we address:** reproducible, labelled, open evaluation.

A second survey, **[title only]** *IoT data cleaning techniques: a survey* (found via HIT repository; authors/venue not verified) - read before citing.

## 2. Benchmarks and datasets
- **[V]** de Bruijn, Nguyen, Bucur, Tei (2016), *Benchmark Datasets for Fault Detection and Classification in Sensor Data*, SENSORNETS (SciTePress), pp. 185-195. Argues benchmarks need real raw data, natural or injected faults, and ground-truth labels per point; releases Intel Lab / SensorScope / Smart Santander subsets with injected random, malfunction, bias, drift and polynomial-drift faults. **Our fault taxonomy follows this paper.**
- **[V]** Lavin & Ahmad (2015), *Evaluating Real-time Anomaly Detection Algorithms - the Numenta Anomaly Benchmark*, IEEE ICMLA. 58 labelled streams; scoring rewards early detection and penalises false positives - relevant if we move to a streaming setting in M4.
- **[V]** Bodik et al. (2004), Intel Berkeley Research Lab dataset (see DATASETS.md).

## 3. Techniques (to expand in M2)
| Technique | Role in our design | Source |
|---|---|---|
| Physical range rules | catch impossible values (e.g. 122 C) | domain knowledge |
| Hampel filter (median + MAD) | robust spike detection | **[B]** Hampel (1974), JASA |
| Isolation Forest | unsupervised anomaly model, no labels needed | **[B]** Liu, Ting & Zhou (2008), IEEE ICDM |
| Spatial redundancy across neighbouring sensors | detects slow bias/drift that point-wise methods miss (our strongest single layer) | motivated by surveys above |
| Declarative / pipeline-style sensor cleaning (smoothing, arbitration) | architecture precedent for layered cleaning | **[B]** Jeffery et al. (2006), Pervasive/ESP |
| Imputation: linear for short gaps, neighbour-based for long gaps | repair, not just flag | surveys above |

## 4. Positioning
Existing work often uses one technique on a private dataset. We (i) combine cheap explainable layers with an unsupervised ML model, (ii) evaluate per fault type against ground truth, and (iii) compare each layer alone vs the hybrid (ablation) on open data.

## 5. Ethics (needed for M2)
Sensor data can reveal occupancy/behaviour (light, temperature patterns in homes/offices); cleaning must not silently erase real events (e.g. a fire looks like a spike). Hence we **flag and log** rather than delete, and keep raw data.
