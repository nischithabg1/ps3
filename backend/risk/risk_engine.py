"""
Risk Engine: VaR, CVaR, Sharpe, Sortino, Beta, Max Drawdown, Stress Testing
"""
import numpy as np
import pandas as pd
from scipy import stats
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class RiskEngine:
    """
    Comprehensive portfolio risk calculations:
    - Historical VaR / CVaR
    - Parametric VaR
    - Monte Carlo VaR
    - Portfolio-level metrics (Sharpe, Sortino, Calmar, Beta, Alpha)
    - Correlation & Covariance matrix
    - Max Drawdown analysis
    - Stress testing scenarios
    """

    RISK_FREE_RATE = 0.05  # 5% annual

    # ─────────────────────────────────────────────────────────────────
    # VaR Methods
    # ─────────────────────────────────────────────────────────────────

    def historical_var(self, returns: pd.Series, confidence: float = 0.95) -> float:
        """Historical simulation VaR (negative number = loss)."""
        if returns.empty:
            return 0.0
        return float(np.percentile(returns.dropna(), (1 - confidence) * 100))

    def parametric_var(self, returns: pd.Series, confidence: float = 0.95) -> float:
        """Parametric (normal) VaR."""
        if returns.empty:
            return 0.0
        mu = returns.mean()
        sigma = returns.std()
        z = stats.norm.ppf(1 - confidence)
        return float(mu + z * sigma)

    def monte_carlo_var(
        self,
        returns: pd.Series,
        confidence: float = 0.95,
        simulations: int = 10000,
        horizon: int = 1,
    ) -> float:
        """Monte Carlo VaR using bootstrapped return distribution."""
        if returns.empty:
            return 0.0
        mu = returns.mean() * horizon
        sigma = returns.std() * np.sqrt(horizon)
        simulated = np.random.normal(mu, sigma, simulations)
        return float(np.percentile(simulated, (1 - confidence) * 100))

    def cvar(self, returns: pd.Series, confidence: float = 0.95) -> float:
        """Conditional VaR (Expected Shortfall) — average of losses beyond VaR."""
        if returns.empty:
            return 0.0
        var = self.historical_var(returns, confidence)
        tail = returns[returns <= var]
        return float(tail.mean()) if not tail.empty else var

    def portfolio_var(
        self,
        returns_df: pd.DataFrame,
        weights: Dict[str, float],
        confidence: float = 0.95,
        method: str = "historical",
        nav: float = 1_000_000,
    ) -> dict:
        """Full portfolio VaR decomposition."""
        symbols = [s for s in weights if s in returns_df.columns]
        if not symbols:
            return {}
        w = np.array([weights[s] for s in symbols])
        w = w / w.sum()
        port_returns = returns_df[symbols].dot(w)

        var_map = {
            "historical": self.historical_var,
            "parametric": self.parametric_var,
            "monte_carlo": self.monte_carlo_var,
        }
        fn = var_map.get(method, self.historical_var)
        var_pct = fn(port_returns, confidence)
        cvar_pct = self.cvar(port_returns, confidence)

        return {
            "method": method,
            "confidence": confidence,
            "var_pct": round(var_pct * 100, 4),
            "cvar_pct": round(cvar_pct * 100, 4),
            "var_dollar": round(var_pct * nav, 2),
            "cvar_dollar": round(cvar_pct * nav, 2),
            "nav": nav,
        }

    # ─────────────────────────────────────────────────────────────────
    # Performance Metrics
    # ─────────────────────────────────────────────────────────────────

    def sharpe_ratio(self, returns: pd.Series, periods: int = 252) -> float:
        if returns.empty or returns.std() == 0:
            return 0.0
        excess = returns - self.RISK_FREE_RATE / periods
        return float((excess.mean() / excess.std()) * np.sqrt(periods))

    def sortino_ratio(self, returns: pd.Series, periods: int = 252) -> float:
        if returns.empty:
            return 0.0
        excess = returns - self.RISK_FREE_RATE / periods
        downside = returns[returns < 0].std()
        if downside == 0:
            return 0.0
        return float((excess.mean() / downside) * np.sqrt(periods))

    def calmar_ratio(self, returns: pd.Series, periods: int = 252) -> float:
        annual_return = self.annualized_return(returns, periods)
        mdd = abs(self.max_drawdown(returns))
        return float(annual_return / mdd) if mdd != 0 else 0.0

    def annualized_return(self, returns: pd.Series, periods: int = 252) -> float:
        if returns.empty:
            return 0.0
        total = (1 + returns).prod()
        n = len(returns)
        return float(total ** (periods / n) - 1) if n > 0 else 0.0

    def annualized_volatility(self, returns: pd.Series, periods: int = 252) -> float:
        if returns.empty:
            return 0.0
        return float(returns.std() * np.sqrt(periods))

    def max_drawdown(self, returns: pd.Series) -> float:
        if returns.empty:
            return 0.0
        cumulative = (1 + returns).cumprod()
        peak = cumulative.cummax()
        drawdown = (cumulative - peak) / peak
        return float(drawdown.min())

    def drawdown_series(self, returns: pd.Series) -> pd.Series:
        cumulative = (1 + returns).cumprod()
        peak = cumulative.cummax()
        return ((cumulative - peak) / peak) * 100

    def beta(self, returns: pd.Series, benchmark_returns: pd.Series) -> float:
        aligned = pd.concat([returns, benchmark_returns], axis=1).dropna()
        if len(aligned) < 2:
            return 1.0
        cov = np.cov(aligned.iloc[:, 0], aligned.iloc[:, 1])
        bench_var = np.var(aligned.iloc[:, 1])
        return float(cov[0, 1] / bench_var) if bench_var != 0 else 1.0

    def alpha(self, returns: pd.Series, benchmark_returns: pd.Series, periods: int = 252) -> float:
        b = self.beta(returns, benchmark_returns)
        port_ann = self.annualized_return(returns, periods)
        bench_ann = self.annualized_return(benchmark_returns, periods)
        return float(port_ann - (self.RISK_FREE_RATE + b * (bench_ann - self.RISK_FREE_RATE)))

    def information_ratio(self, returns: pd.Series, benchmark_returns: pd.Series, periods: int = 252) -> float:
        active = returns - benchmark_returns
        te = active.std() * np.sqrt(periods)
        return float(active.mean() * periods / te) if te != 0 else 0.0

    # ─────────────────────────────────────────────────────────────────
    # Portfolio-Level Analysis
    # ─────────────────────────────────────────────────────────────────

    def correlation_matrix(self, returns_df: pd.DataFrame) -> pd.DataFrame:
        return returns_df.corr()

    def covariance_matrix(self, returns_df: pd.DataFrame, annualize: bool = True) -> pd.DataFrame:
        cov = returns_df.cov()
        return cov * 252 if annualize else cov

    def portfolio_volatility(self, returns_df: pd.DataFrame, weights: Dict[str, float]) -> float:
        symbols = [s for s in weights if s in returns_df.columns]
        if not symbols:
            return 0.0
        w = np.array([weights[s] for s in symbols])
        w = w / w.sum()
        cov = returns_df[symbols].cov().values * 252
        variance = w @ cov @ w
        return float(np.sqrt(variance))

    def marginal_var(self, returns_df: pd.DataFrame, weights: Dict[str, float], confidence: float = 0.95) -> Dict[str, float]:
        """Marginal contribution to VaR for each position."""
        symbols = [s for s in weights if s in returns_df.columns]
        result = {}
        for sym in symbols:
            delta = 0.001
            w1 = dict(weights)
            w1[sym] = weights[sym] + delta
            w2 = dict(weights)
            w2[sym] = max(weights[sym] - delta, 0)
            v1 = self.portfolio_var(returns_df, w1, confidence)
            v2 = self.portfolio_var(returns_df, w2, confidence)
            if v1 and v2:
                result[sym] = round((v1.get("var_pct", 0) - v2.get("var_pct", 0)) / (2 * delta), 6)
        return result

    def full_risk_report(
        self,
        returns_df: pd.DataFrame,
        weights: Dict[str, float],
        benchmark_returns: Optional[pd.Series] = None,
        nav: float = 1_000_000,
    ) -> dict:
        """Generate a comprehensive risk report for the portfolio."""
        symbols = [s for s in weights if s in returns_df.columns]
        if not symbols:
            return {}
        w = np.array([weights.get(s, 0) for s in symbols])
        w = w / w.sum()
        port_returns = returns_df[symbols].dot(w)

        report = {
            "portfolio_metrics": {
                "annualized_return": round(self.annualized_return(port_returns) * 100, 2),
                "annualized_volatility": round(self.annualized_volatility(port_returns) * 100, 2),
                "sharpe_ratio": round(self.sharpe_ratio(port_returns), 4),
                "sortino_ratio": round(self.sortino_ratio(port_returns), 4),
                "calmar_ratio": round(self.calmar_ratio(port_returns), 4),
                "max_drawdown": round(self.max_drawdown(port_returns) * 100, 2),
            },
            "var_analysis": {
                "historical_95": self.portfolio_var(returns_df, weights, 0.95, "historical", nav),
                "historical_99": self.portfolio_var(returns_df, weights, 0.99, "historical", nav),
                "parametric_95": self.portfolio_var(returns_df, weights, 0.95, "parametric", nav),
                "monte_carlo_95": self.portfolio_var(returns_df, weights, 0.95, "monte_carlo", nav),
            },
            "correlation_matrix": self.correlation_matrix(returns_df[symbols]).round(4).to_dict(),
        }

        if benchmark_returns is not None:
            report["vs_benchmark"] = {
                "beta": round(self.beta(port_returns, benchmark_returns), 4),
                "alpha": round(self.alpha(port_returns, benchmark_returns) * 100, 2),
                "information_ratio": round(self.information_ratio(port_returns, benchmark_returns), 4),
            }

        return report

    # ─────────────────────────────────────────────────────────────────
    # Stress Testing
    # ─────────────────────────────────────────────────────────────────

    STRESS_SCENARIOS = {
        "2008 Financial Crisis": {"equity_shock": -0.50, "vol_shock": 2.5, "credit_spread": 0.05},
        "COVID-19 Crash (Mar 2020)": {"equity_shock": -0.35, "vol_shock": 3.0, "credit_spread": 0.03},
        "Dot-com Bust (2000-2002)": {"equity_shock": -0.45, "vol_shock": 1.8, "credit_spread": 0.02},
        "Rate Hike Shock (+200bps)": {"equity_shock": -0.15, "vol_shock": 1.2, "credit_spread": 0.01},
        "Flash Crash (-10% intraday)": {"equity_shock": -0.10, "vol_shock": 2.0, "credit_spread": 0.00},
        "Stagflation Scenario": {"equity_shock": -0.20, "vol_shock": 1.5, "credit_spread": 0.02},
    }

    def stress_test(self, weights: Dict[str, float], nav: float = 1_000_000) -> List[dict]:
        results = []
        for scenario, shocks in self.STRESS_SCENARIOS.items():
            equity_shock = shocks["equity_shock"]
            pnl = nav * equity_shock
            results.append({
                "scenario": scenario,
                "equity_shock_pct": round(equity_shock * 100, 1),
                "estimated_pnl": round(pnl, 2),
                "estimated_pnl_pct": round(equity_shock * 100, 2),
                "nav_after": round(nav + pnl, 2),
            })
        return results
