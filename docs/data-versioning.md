# Data versioning

## Purpose

Backtests and training must be reproducible. Data versioning lets you record which dataset was used for each run.

## How to version data

1. **Path-based:** Store data under `data/<version>/` or `data/<symbol>_<version>.csv`. Set `data_version` in config.
2. **DVC (optional):** Use DVC to track large files. Tag a run with the DVC commit or data artifact hash.
3. **Run logs:** Log git_commit, config_file, data_version, model_version in your report or MLflow.
