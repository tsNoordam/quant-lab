# Quant Research Lab

## Mission

This repository is used to convert academic quantitative finance research
papers into reproducible, testable trading strategies.

The goal is NOT to maximize historical returns.

Priority:

1. Research fidelity
2. Reproducibility
3. No look-ahead bias
4. Realistic execution
5. Statistical validity
6. Robustness
7. Performance

## Research rules

Every strategy rule must be classified as:

[PAPER-DERIVED]
[MATHEMATICALLY-DERIVED]
[IMPLEMENTATION-ASSUMPTION]
[EXTERNAL-RESEARCH]
[PROPOSED-EXTENSION]

Never silently introduce a trading rule.

Never convert an empirical observation into a trading rule
without explicitly identifying that transformation.

Never optimize solely for historical performance.

Never use future information.

Never use the out-of-sample period for strategy development.

## Backtesting

All backtests must document:

- dataset
- date range
- timeframe
- parameters
- costs
- slippage
- execution model
- position sizing
- leverage
- number of trades
A failed backtest is a research result.

Do not modify the strategy merely because the result is bad.
Never use the out-of-sample period to decide what to change.
## Statistical standards

Investigate:

- look-ahead bias
- survivorship bias
- data snooping
- multiple testing
- overfitting
- parameter sensitivity
- walk-forward stability
- out-of-sample performance
- transaction costs
- liquidity
- regime dependence

## Coding standards

Use:

- Python 3.12
- uv
- pytest
- ruff
- pandas
- numpy
- scipy
- statsmodels

Run tests before declaring a task complete.

Run linting before committing.

## Git

Never delete or rewrite research history without explicit permission.

Use descriptive commits.

Never commit:

- API keys
- credentials
- .env files
- private tokens
