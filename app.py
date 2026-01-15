import streamlit as st
import yfinance as yf
import requests
from bs4 import BeautifulSoup
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, date, timedelta

# Function to fetch current BTC price from CoinGecko API
def get_btc_price():
    url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
    try:
        response = requests.get(url)
        data = response.json()
        return data['bitcoin']['usd']
    except Exception as e:
        st.error(f"Error fetching BTC price: {e}")
        return None

# Function to scrape MicroStrategy's BTC holdings from bitcointreasuries.net
def get_btc_holdings():
    url = "https://bitcointreasuries.net/"
    try:
        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        rows = soup.find_all('tr')
        for row in rows:
            cells = row.find_all('td')
            if cells and ('MicroStrategy' in cells[0].text or 'Strategy' in cells[0].text):
                holdings_str = cells[1].text.strip().replace(',', '')
                return int(holdings_str)
        st.warning("Could not find MicroStrategy entry; using fallback value.")
        return 687410
    except Exception as e:
        st.error(f"Error scraping holdings: {e}")
        return 687410

# Fetch MSTR and STRC stock data using yfinance
def get_stock_data(ticker):
    stock = yf.Ticker(ticker)
    try:
        info = stock.info
        hist = stock.history(period="1d")
        if not hist.empty:
            daily_volume = hist['Volume'].iloc[-1]
            close_price = hist['Close'].iloc[-1]
            high_price = hist['High'].iloc[-1]
            low_price = hist['Low'].iloc[-1]
        else:
            daily_volume = 0
            close_price = info.get('regularMarketPrice', 0)
            high_price = close_price
            low_price = close_price
        return {
            'market_cap': info.get('marketCap', 0),
            'shares_outstanding': info.get('sharesOutstanding', 0),
            'last_price': close_price,
            'daily_volume': daily_volume,
            'high': high_price,
            'low': low_price
        }
    except Exception as e:
        st.error(f"Error fetching {ticker} data: {e}")
        return {'market_cap': 0, 'shares_outstanding': 0, 'last_price': 0, 'daily_volume': 0, 'high': 0, 'low': 0}

# New: Scrape historical purchases from strategy.com/purchases
def get_historical_purchases():
    url = "https://www.strategy.com/purchases"
    try:
        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        table = soup.find('table')
        if table:
            df = pd.read_html(str(table))[0]
            df['Reported'] = pd.to_datetime(df['Reported'], errors='coerce')
            df = df.dropna(subset=['Reported']).sort_values('Reported')
            df['BTC Acq'] = df['BTC Acq'].str.replace('₿ ', '').str.replace(',', '').astype(float)
            df['Cumulative BTC'] = df['BTC'].str.replace('₿ ', '').str.replace(',', '').astype(float)  # Use total holdings column
            return df
        else:
            st.warning("Could not find purchases table; using sample data.")
            # Fallback sample DF based on known history
            data = {
                'Reported': ['2020-08-11', '2021-02-24', '2024-03-11', '2025-12-15', '2026-01-12'],
                'BTC Acq': [21454, 19452, 12000, 10645, 13627],
                'Cumulative BTC': [21454, 90000, 300000, 671268, 687410]  # Approximate
            }
            return pd.DataFrame(data)
    except Exception as e:
        st.error(f"Error scraping purchases: {e}")
        return pd.DataFrame()

# New: Assign approximate funding sources based on periods (from filings/analysis)
def assign_funding_sources(df):
    sources = ['Common Stock', 'Convertible Debt', 'STRC', 'STRK', 'STRD', 'STRF', 'STRE']
    df[sources] = 0.0
    for idx, row in df.iterrows():
        year = row['Reported'].year
        acq = row['BTC Acq']
        if year <= 2022:
            # Early: Mostly convertible debt
            df.at[idx, 'Convertible Debt'] = acq * 0.8
            df.at[idx, 'Common Stock'] = acq * 0.2
        elif year == 2023 or year == 2024:
            # Mid: Common ATM dominant
            df.at[idx, 'Common Stock'] = acq * 0.7
            df.at[idx, 'Convertible Debt'] = acq * 0.3
        else:
            # Recent/Future: Preferred heavy
            df.at[idx, 'Common Stock'] = acq * 0.5
            df.at[idx, 'STRC'] = acq * 0.1
            df.at[idx, 'STRK'] = acq * 0.1
            df.at[idx, 'STRD'] = acq * 0.1
            df.at[idx, 'STRF'] = acq * 0.1
            df.at[idx, 'STRE'] = acq * 0.1
    for source in sources:
        df[f'Cum {source}'] = df[source].cumsum()
    return df, sources

# New: Forecast future acquisitions using BTC power law
def forecast_acquisitions(last_date, last_cum_btc, sources):
    genesis = date(2009, 1, 3)
    annual_raise = 10000000000  # $10B/year assumption
    future_years = range(last_date.year + 1, last_date.year + 11)
    future_df = pd.DataFrame({'Reported': [datetime(year, 12, 31) for year in future_years]})
    future_df['BTC Acq'] = 0.0
    future_df[sources] = 0.0
    cum_btc = last_cum_btc
    for idx, row in future_df.iterrows():
        days = (row['Reported'].date() - genesis).days
        years = days / 365.25
        proj_price = 10 ** -1.847796462 * years ** 5.616314045
        btc_added = annual_raise / proj_price
        future_df.at[idx, 'BTC Acq'] = btc_added
        cum_btc += btc_added
        future_df.at[idx, 'Cumulative BTC'] = cum_btc
        # Assume future split: 60% preferred (even), 30% common, 10% convertible
        future_df.at[idx, 'Common Stock'] = btc_added * 0.3
        future_df.at[idx, 'Convertible Debt'] = btc_added * 0.1
        for pref in ['STRC', 'STRK', 'STRD', 'STRF', 'STRE']:
            future_df.at[idx, pref] = btc_added * 0.12
    for source in sources:
        future_df[f'Cum {source}'] = future_df[source].cumsum() + df[f'Cum {source}'].iloc[-1]
    return future_df

# Main Streamlit app
st.title("Strategy Inc. (MSTR) Bitcoin Treasury Analysis Dashboard")
st.markdown("""
This dashboard provides real-time insights into Strategy's valuation, Bitcoin treasury, amplification via preferred stocks, estimated daily BTC acquisitions from STRC issuances, and common stock ATM estimates. Now includes historical/forecasted acquisitions chart with source attribution. Data is fetched live where possible.
""")

# Fetch data
btc_holdings = get_btc_holdings()
btc_price = get_btc_price()
mstr_data = get_stock_data("MSTR")
strc_data = get_stock_data("STRC")

if btc_price and mstr_data['market_cap'] > 0:
    treasury_value = btc_holdings * btc_price
    btc_per_share = btc_holdings / mstr_data['shares_outstanding'] if mstr_data['shares_outstanding'] > 0 else 0
    
    # Approximate net liabilities
    approx_debt = 8000000000
    approx_preferred_notional = 8000000000
    approx_cash = 2190000000
    net_liabilities = approx_debt + approx_preferred_notional - approx_cash
    
    ev = mstr_data['market_cap'] + net_liabilities
    leverage_amplification = treasury_value / mstr_data['market_cap'] if mstr_data['market_cap'] > 0 else 0
    nav = treasury_value - net_liabilities
    premium_to_nav = mstr_data['market_cap'] / nav if nav > 0 else 0

    # Key Metrics table
    st.subheader("Key Metrics")
    data = {
        "Metric": [
            "Bitcoin Hold Amount",
            "Current Bitcoin Price (USD)",
            "Bitcoin Treasury Value (USD)",
            "MSTR Market Cap (USD)",
            "MSTR Shares Outstanding",
            "BTC per Share",
            "Approximate Enterprise Value (USD)",
            "Leverage Amplification Factor (BTC Value / Market Cap)",
            "Premium to NAV (mNAV)"
        ],
        "Value": [
            f"{btc_holdings:,} BTC",
            f"${btc_price:,.2f}",
            f"${treasury_value:,.0f}",
            f"${mstr_data['market_cap']:,.0f}",
            f"{mstr_data['shares_outstanding']:,}",
            f"{btc_per_share:.6f} BTC/share",
            f"${ev:,.0f}",
            f"{leverage_amplification:.2f}x",
            f"{premium_to_nav:.2f}x"
        ]
    }
    st.table(data)

    st.subheader("Amplification Analysis Using Preferred Stocks")
    st.markdown("""
    Strategy's preferred stock issuances (e.g., STRC at 11% dividend) enable low-cost capital raises to acquire more BTC, amplifying returns for common shareholders. This increases BTC per share over time while dividends are supported by reserves. The leverage factor shows magnified BTC upside, with mNAV reflecting market confidence.
    """)

    # Estimated Daily BTC from STRC
    st.subheader("Estimated Daily BTC Acquisition from STRC Issuances")
    atm_threshold = 100.05
    atm_pct = 0.40
    commission = 0.025
    
    if strc_data['high'] >= atm_threshold:
        if strc_data['low'] >= atm_threshold:
            volume_above = strc_data['daily_volume']
        else:
            frac_above = (strc_data['high'] - atm_threshold) / (strc_data['high'] - strc_data['low'])
            volume_above = strc_data['daily_volume'] * max(0, min(1, frac_above))
    else:
        volume_above = 0
    
    est_shares_issued = volume_above * atm_pct
    gross_proceeds = est_shares_issued * strc_data['last_price']
    net_proceeds = gross_proceeds * (1 - commission)
    est_btc_from_strc = net_proceeds / btc_price if btc_price > 0 else 0
    
    st.markdown(f"""
    Using threshold ${atm_threshold:.2f} and {atm_pct*100:.0f}% ATM assumption:  
    - STRC Daily Volume: {strc_data['daily_volume']:,} shares  
    - Est. Volume ≥ Threshold: {volume_above:,.0f} shares  
    - Est. New STRC Shares Issued: {est_shares_issued:,.0f}  
    - Est. Net Proceeds: ${net_proceeds:,.0f}  
    - Est. BTC Acquired: {est_btc_from_strc:,.2f} BTC  
    *Note: Approximation; validate with weekly 8-K filings.*
    """)

    # Estimated Daily MSTR Common Issuance
    st.subheader("Estimated Daily MSTR Common Stock Issuance")
    if premium_to_nav <= 1.0:
        issuance_pct = 0.001
    elif premium_to_nav >= 3.0:
        issuance_pct = 0.05
    else:
        issuance_pct = 0.001 + 0.049 * ((premium_to_nav - 1.0) / 2.0)
    
    est_new_common_shares = mstr_data['daily_volume'] * issuance_pct
    est_proceeds_common = est_new_common_shares * mstr_data['last_price']
    est_btc_from_common = est_proceeds_common / btc_price if btc_price > 0 else 0
    
    st.markdown(f"""
    Based on mNAV {premium_to_nav:.2f}x and daily volume {mstr_data['daily_volume']:,} shares:  
    - Est. Issuance % of Volume: {issuance_pct*100:.2f}%  
    - Est. New Common Shares: {est_new_common_shares:,.0f}  
    - Est. Proceeds: ${est_proceeds_common:,.0f}  
    - Est. BTC Acquired: {est_btc_from_common:,.2f} BTC  
    *Note: Model assumes higher issuances at premiums; actual depends on ATM execution.*
    """)

    # New: Historical and Forecasted Acquisitions Chart
    st.subheader("Historical and Forecasted Bitcoin Acquisitions")
    df_hist = get_historical_purchases()
    if not df_hist.empty:
        df_hist, sources = assign_funding_sources(df_hist)
        last_date = df_hist['Reported'].max()
        last_cum_btc = df_hist['Cumulative BTC'].max()
        df_future = forecast_acquisitions(last_date, last_cum_btc, sources)
        df_all = pd.concat([df_hist, df_future]).reset_index(drop=True)

        # Stacked area chart
        fig, ax = plt.subplots(figsize=(12, 6))
        cum_cols = [f'Cum {source}' for source in sources]
        ax.stackplot(df_all['Reported'], df_all[cum_cols].T, labels=sources, alpha=0.8)
        ax.set_title('Cumulative BTC Holdings by Funding Source (Historical + 10-Year Forecast)')
        ax.set_xlabel('Date')
        ax.set_ylabel('Cumulative BTC')
        ax.legend(loc='upper left')
        ax.grid(True)
        st.pyplot(fig)

        st.markdown("""
        *Historical data scraped from strategy.com/purchases. Sources approximated by period (e.g., early convertible-heavy). Forecast assumes $10B annual raises at power law prices, split 60% preferred/30% common/10% convertible. Actuals may vary based on market conditions and Strategy's execution.*
        """)
    else:
        st.error("Failed to load historical data for chart.")

else:
    st.error("Failed to fetch required data. Check API availability or try again later.")
