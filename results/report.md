# Cleaning results (synthetic IoT network, 8 motes x 7 days x 4 channels)

## Detection: method comparison (mean over channels)

| method                   |   precision |   recall |    f1 |
|:-------------------------|------------:|---------:|------:|
| rules only (range+stuck) |       1     |    0.224 | 0.34  |
| Hampel only              |       0.971 |    0.019 | 0.037 |
| Spatial only             |       0.988 |    0.848 | 0.911 |
| Isolation Forest only    |       0.857 |    0.257 | 0.395 |
| HYBRID (all layers)      |       0.937 |    0.943 | 0.939 |

## Hybrid detection per channel

| channel     |   precision |   recall |    f1 |   tp |   fp |   fn |
|:------------|------------:|---------:|------:|-----:|-----:|-----:|
| temperature |       0.959 |    0.961 | 0.96  | 1412 |   61 |   58 |
| humidity    |       0.955 |    0.921 | 0.938 | 1513 |   72 |  129 |
| light       |       0.888 |    0.952 | 0.919 | 1375 |  173 |   70 |
| voltage     |       0.946 |    0.937 | 0.942 | 1731 |   98 |  117 |

## Recall by fault type (all channels)

|          |   rules only (range+stuck) |   Hampel only |   Spatial only |   Isolation Forest only |   HYBRID (all layers) |
|:---------|---------------------------:|--------------:|---------------:|------------------------:|----------------------:|
| spike    |                      0.247 |         0.989 |          0     |                   0.753 |                 1     |
| stuck    |                      0.918 |         0     |          0.26  |                   0     |                 0.918 |
| bias     |                      0.255 |         0     |          1     |                   0.411 |                 1     |
| drift    |                      0.036 |         0     |          0.913 |                   0.21  |                 0.912 |
| sentinel |                      1     |         1     |          0     |                   0     |                 1     |

## Value accuracy vs hidden truth

| channel     |   raw_rmse |   cleaned_rmse |   raw_mae |   cleaned_mae |   improvement_% |
|:------------|-----------:|---------------:|----------:|--------------:|----------------:|
| temperature |     2.8242 |         0.0593 |    0.5037 |        0.0149 |         97.8993 |
| humidity    |     3.3513 |         0.1654 |    0.7789 |        0.0431 |         95.0632 |
| light       |  1068.57   |        14.906  |   72.3689 |        1.984  |         98.6051 |
| voltage     |     0.0461 |         0.0017 |    0.0056 |        0.0005 |         96.3651 |
