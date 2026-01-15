import streamlit as st
import yfinance as yf
import requests
from bs4 import BeautifulSoup
import pandas as pd  # Added for data handling

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
        return 687410  # Fallback to known value
    except Exception as e:
        st.error(f"Error scraping holdings: {e}")
        return 687410

# Fetch MSTR and STRC stock data using yfinance
def get_stock_data(ticker):
    stock = yf.Ticker(ticker)
    try:
        info = stock.info
        hist = stock.history(period="1d")  # For daily volume/price
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

# Main Streamlit app
st.title("MicroStrategy (MSTR) Bitcoin Treasury Analysis Dashboard")
st.markdown("""
This dashboard provides real-time insights into MicroStrategy's valuation, Bitcoin treasury, amplification via preferred stocks, estimated daily BTC acquisitions from STRC issuances, and common stock ATM estimates. Data is fetched live where possible.
""")

# Fetch data
btc_holdings = get_btc_holdings()
btc_price = get_btc_price()
mstr_data = get_stock_data("MSTR")
strc_data = get_stock_data("STRC")  # Added for STRC

if btc_price and mstr_data['market_cap'] > 0:
    treasury_value = btc_holdings * btc_price
    btc_per_share = btc_holdings / mstr_data['shares_outstanding'] if mstr_data['shares_outstanding'] > 0 else 0
    
    # Approximate net liabilities (update as needed from filings)
    approx_debt = 8000000000
    approx_preferred_notional = 8000000000
    approx_cash = 2190000000
    net_liabilities = approx_debt + approx_preferred_notional - approx_cash
    
    # Enterprise Value
    ev = mstr_data['market_cap'] + net_liabilities
    
    # Amplification metrics
    leverage_amplification = treasury_value / mstr_data['market_cap'] if mstr_data['market_cap'] > 0 else 0
    nav = treasury_value - net_liabilities
    premium_to_nav = mstr_data['market_cap'] / nav if nav > 0 else 0  # mNAV

    # Display key metrics
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
    MicroStrategy's preferred stock issuances (e.g., STRC at 11% dividend) enable low-cost capital raises to acquire more BTC, amplifying returns for common shareholders. This increases BTC per share over time while dividends are supported by reserves. The leverage factor shows magnified BTC upside, with mNAV reflecting market confidence.
    """)

    # New: Estimated Daily BTC from STRC (based on strc.live model)
    st.subheader("Estimated Daily BTC Acquisition from STRC Issuances")
    atm_threshold = 100.05  # User's believed threshold
    atm_pct = 0.40  # 40%
    commission = 0.025  # 2.5%
    
    # Approximate volume above threshold: If high >= threshold, assume fraction of daily volume
    # (For simplicity; full intraday needs advanced API. Here: if low >= threshold, 100%; elif high >=, (high - threshold)/(high - low); else 0)
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

    # New: Estimated Daily MSTR Common Issuance
    st.subheader("Estimated Daily MSTR Common Stock Issuance")
    # Pct function: Low at mNAV<=1 (0.1%), ramps to 5% at mNAV>=3
    if premium_to_nav <= 1.0:
        issuance_pct = 0.001  # 0.1%, miniscule
    elif premium_to_nav >= 3.0:
        issuance_pct = 0.05  # 5%
    else:
        issuance_pct = 0.001 + 0.049 * ((premium_to_nav - 1.0) / 2.0)  # Linear ramp from 0.1% to 5%
    
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

else:
    st.error("Failed to fetch required data. Check API availability or try again later.")
