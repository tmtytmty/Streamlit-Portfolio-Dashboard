# Portfolio Dashboard

This is a personal project for better management of my portfolios across multiple brokers.

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

```


Example:

```text
Ticker    Currency    Category      Broker      Position    Max allocation    Don't add above
VTV       USD         Broad ETF     Firstrade   15          20.0%             15.0%
Cash      USD         Cash          IBKR        4210        Free              Free
NG.L      GBP         Non-cyclical  IBKR        175         7.5%              5.0%
```

## Google Sheet Sharing

The Google Sheet must be shared as:

```text
Anyone with the link can view
```

The app reads the sheet using Google Sheets CSV export. It does not require Google Cloud Platform, Google API credentials, or a service account.

## Installation

Clone the repository:

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
cd YOUR_REPO_NAME
```

Create and activate a Conda environment:

```bash
conda create -n portfolio-dashboard python=3.11 -y
conda activate portfolio-dashboard
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## Requirements

`requirements.txt` should contain:

```txt
streamlit
pandas
numpy
yfinance
plotly
```

## Run Locally

Start the Streamlit app:

```bash
streamlit run app.py
```

Then open the local URL shown in the terminal, usually:

```text
http://localhost:8501
```

Paste your Google Sheet link into the app to load the dashboard.

## Deployment

This app can be deployed on Streamlit Community Cloud.

1. Push the repo to GitHub.
2. Go to Streamlit Community Cloud.
3. Create a new app from the GitHub repo.
4. Set the main file path to:

```text
app.py
```

5. Deploy.

No Streamlit secrets are required for the current version because users paste their own Google Sheet link directly into the app.

## Privacy Notes

This app does not store Google Sheet links, passwords, or API keys.

However, the Google Sheet must be shared as **Anyone with the link can view** for the app to read it. Anyone with the sheet link may be able to view the data.

If you deploy the Streamlit app publicly, anyone with the app URL may be able to use the dashboard. Do not paste sensitive portfolio data into a public app unless you are comfortable with that risk.

## Historical Simulation Notes

The historical simulation is not a true record of your actual historical portfolio performance.

It applies your current holdings backward through historical price data. This answers:

```text
How would today's portfolio have performed historically?
```

It does not answer:

```text
What was my actual portfolio performance over time?
```

To calculate actual historical performance, you would need transaction history, deposits, withdrawals, dividends, taxes, fees, slippage, and historical position sizes.

## Limitations

- Market data comes from Yahoo Finance through `yfinance`
- Price data may occasionally be missing or delayed
- Foreign exchange conversion uses Yahoo Finance FX tickers
- Cash is treated as constant during historical simulation
- The dashboard assumes current holdings are representative for historical simulation
- Google Sheets must be publicly readable by link

## License

This project is for personal portfolio tracking and educational use.