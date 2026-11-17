# Experiments (all numbers reproducible: `python experiments.py`)

## E1. Method comparison and leave-one-layer-out ablation (5 seeds, mean +- std)

|                      | precision    | recall       | F1           | RMSE improvement %   |
|:---------------------|:-------------|:-------------|:-------------|:---------------------|
| rules (range+stuck)  | 1.000+-0.000 | 0.238+-0.013 | 0.356+-0.016 | 47.8+-4.1            |
| Hampel               | 0.954+-0.014 | 0.015+-0.002 | 0.029+-0.004 | 50.1+-3.9            |
| Spatial              | 0.986+-0.011 | 0.827+-0.013 | 0.898+-0.011 | 19.0+-7.1            |
| Isolation Forest     | 0.887+-0.009 | 0.254+-0.003 | 0.394+-0.005 | 10.4+-1.7            |
| HYBRID (all)         | 0.950+-0.015 | 0.936+-0.009 | 0.942+-0.010 | 96.5+-0.3            |
| hybrid minus range   | 0.955+-0.010 | 0.935+-0.009 | 0.945+-0.008 | 96.4+-0.4            |
| hybrid minus hampel  | 0.950+-0.015 | 0.936+-0.009 | 0.943+-0.010 | 96.5+-0.3            |
| hybrid minus stuck   | 0.945+-0.015 | 0.842+-0.013 | 0.889+-0.012 | 96.2+-0.4            |
| hybrid minus spatial | 0.929+-0.006 | 0.471+-0.007 | 0.616+-0.008 | 63.0+-3.8            |
| hybrid minus iforest | 0.980+-0.016 | 0.936+-0.009 | 0.957+-0.011 | 96.3+-0.6            |


## E2. Isolation Forest `contamination` sweep (seed 11)

|   contamination |   IF_precision |   IF_recall |   IF_F1 |   hybrid_precision |   hybrid_recall |   hybrid_F1 |
|----------------:|---------------:|------------:|--------:|-------------------:|----------------:|------------:|
|            0.01 |          0.907 |       0.084 |   0.153 |              0.962 |           0.92  |       0.941 |
|            0.02 |          0.903 |       0.17  |   0.287 |              0.953 |           0.92  |       0.936 |
|            0.03 |          0.89  |       0.252 |   0.393 |              0.941 |           0.92  |       0.93  |
|            0.05 |          0.804 |       0.381 |   0.517 |              0.889 |           0.921 |       0.904 |
|            0.08 |          0.713 |       0.542 |   0.615 |              0.799 |           0.922 |       0.854 |
|            0.12 |          0.567 |       0.647 |   0.604 |              0.65  |           0.924 |       0.762 |


## E3. Robustness to fault rate (hybrid, seed 21)

|   fault_rate |   precision |   recall |    F1 |   RMSE_impr_% |
|-------------:|------------:|---------:|------:|--------------:|
|         0.02 |       0.856 |    0.964 | 0.904 |        96.036 |
|         0.05 |       0.862 |    0.933 | 0.89  |        95.289 |
|         0.08 |       0.96  |    0.926 | 0.942 |        96.028 |
|         0.15 |       0.96  |    0.928 | 0.943 |        95.045 |
|         0.25 |       0.945 |    0.88  | 0.911 |        90.296 |


## E4. Sensitivity to number of sensors (spatial layer needs neighbours)

|   motes |   spatial_F1 |   hybrid_F1 |
|--------:|-------------:|------------:|
|       2 |        0.687 |       0.722 |
|       3 |        0.728 |       0.793 |
|       4 |        0.864 |       0.892 |
|       8 |        0.917 |       0.955 |
|      16 |        0.917 |       0.946 |


## E5. Unsupervised hybrid vs supervised Random Forest (test seeds 14, 15)

|                                                       |   precision |   recall |    F1 |
|:------------------------------------------------------|------------:|---------:|------:|
| supervised RandomForest (trained on 3 labelled seeds) |       0.932 |    0.953 | 0.942 |
| our unsupervised hybrid (no labels)                   |       0.942 |    0.943 | 0.942 |

The supervised model needs thousands of labelled faults, which real deployments do not have; the hybrid needs none.

## E6. Online (causal, no Isolation Forest) vs offline batch (seed 11)

| channel     |   online_precision |   online_recall |   online_F1 |   batch_precision |   batch_recall |   batch_F1 |
|:------------|-------------------:|----------------:|------------:|------------------:|---------------:|-----------:|
| temperature |              0.856 |           0.842 |       0.849 |             0.957 |          0.938 |      0.948 |
| humidity    |              0.76  |           0.646 |       0.698 |             0.943 |          0.885 |      0.913 |
| light       |              0.858 |           0.878 |       0.868 |             0.897 |          0.92  |      0.908 |
| voltage     |              0.927 |           0.895 |       0.911 |             0.967 |          0.938 |      0.952 |

## E7. Role of the ML layer: novel (unanticipated) fault type, 3 seeds

| scenario                  | method                          |    F1 |   precision |   recall |   burst_recall |
|:--------------------------|:--------------------------------|------:|------------:|---------:|---------------:|
| known + novel burst fault | full hybrid (+Isolation Forest) | 0.899 |       0.992 |    0.825 |          0.709 |
| known + novel burst fault | rules+Hampel+spatial (no ML)    | 0.872 |       0.993 |    0.783 |          0.614 |
| known faults only         | full hybrid (+Isolation Forest) | 0.943 |       0.955 |    0.932 |        nan     |
| known faults only         | rules+Hampel+spatial (no ML)    | 0.958 |       0.986 |    0.932 |        nan     |

Reading: on faults we wrote rules for, the ML layer costs a little precision; when a NEW fault type appears it adds recall that no hand-written rule provides.
