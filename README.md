# Portfolio Dashboard

A Streamlit dashboard for visualizing a personal investment portfolio from a Google Sheet.

The app lets users paste a Google Sheets link, then automatically loads portfolio holdings, fetches live market prices, converts non-USD holdings into USD, shows allocation and exposure breakdowns, flags allocation limits, and runs a historical simulation against a benchmark like SPY.

## Disclaimer

This project is for personal portfolio tracking, visualization, and educational use only. It is not financial advice, investment advice, tax advice, legal advice, or a recommendation to buy, sell, or hold any security.

Market prices, foreign exchange rates, and historical data are pulled from third-party sources such as Yahoo Finance through `yfinance`. Data may be delayed, incomplete, inaccurate, or unavailable. Always verify important figures with your broker, custodian, or official data source before making decisions.

The historical simulation is hypothetical. It applies current holdings backward through historical prices and does not represent actual historical portfolio performance. It does not account for past trades, deposits, withdrawals, dividends, taxes, fees, slippage, or changes in position size.

Use this dashboard at your own risk.

## Features

- Load portfolio data directly from Google Sheets
- Fetch latest prices using Yahoo Finance
- Convert foreign-currency holdings into USD
- Combine cash positions into one portfolio-level cash row
- Show portfolio overview, holdings, risk flags, and exposure charts
- Break down exposure by category, broker, and currency
- Compare current allocation against max allocation and don't-add thresholds
- Run historical simulation using current holdings
- Compare portfolio performance against a benchmark
- Display risk metrics such as Sharpe ratio, alpha, beta, correlation, VaR, and drawdown

## App Structure

The dashboard has three main tabs:

### Portfolio Overview

Shows total portfolio value, filtered value, number of holdings, cash exposure, risk flags, top holdings, allocation by category, and a holdings table.

### Exposure

Shows detailed exposure breakdowns by holding, category, broker, currency, and broker/category mix. It also separates true risk flags from don't-add warnings.

### Historical Simulation

Simulates how the current portfolio would have performed historically, assuming the portfolio starts at 100 on the selected start date. The simulation compares performance against a benchmark such as SPY.

## Google Sheet Format

Your Google Sheet should have the following columns:

```text
Ticker
Currency
Category
Broker
Position
Max allocation
Don't add above
Thesis / catalysts
Notes