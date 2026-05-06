System Architecture Summary

The system operates across five layers: *Data, Risk*, *Strategy*,Execution, and Reporting

Data: ingests multi-asset market, macro, and sentiment feeds concurrently. Missing values are imputed backward-only to avoid lookahead bias; outliers are winsorized and flagged.

Risk Modeling: runs continuously. Historical-simulation VaR and maximum drawdown are recalculated on every rebalancing cycle and act as hard gates — breaching thresholds suppresses new buy signals entirely.

Signal Generation: scores each asset using volatility and momentum features plus aligned macro/sentiment inputs, emitting typed BUY/SELL/HOLD signals. It is fully decoupled from execution.

Execution: applies volatility-scaled position sizing with absolute concentration caps, simulates slippage and commissions on every trade, and rejects orders that exceed available capital — logging each rejection without crashing the simulation.

Reporting: aggregates daily NAV, Sharpe Ratio, Alpha/Beta, and drawdown into structured snapshots. Every trade is paired with a strategy log capturing the exact indicator values and risk metrics that drove the decision, creating a full audit trail.

Risk is not a reporting afterthought — it is embedded at ingestion, signal approval, and execution, making the entire pipeline risk-aware by design.

