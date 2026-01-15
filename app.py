import streamlit as st
import yfinance as yf
import requests
from bs4 import BeautifulSoup

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

# Function to scrape Strategy's BTC holdings from bitcointreasuries.net
def get_btc_holdings():
    url = "https://bitcointreasuries.net/"
    try:
        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        # Assume table rows; search for 'Strategy' or 'MicroStrategy' row
        # Adjust selectors based on site structure (inspect HTML if needed)
        rows = soup.find_all('tr')
        for row in rows:
            cells = row.find_all('td')
            if cells and ('Strategy' in cells[0].text or 'MicroStrategy' in cells[0].text):
                holdings_str = cells[1].text.strip().replace(',', '')  # e.g., '687410'
                return int(holdings_str)
        st.warning("Could not find Strategy entry; using fallback value.")
        return 687410  # Fallback to latest known (Jan 12, 2026)
    except Exception as e:
        st.error(f"Error scraping holdings: {e}")
        return 687410  # Fallback

# Fetch MSTR stock data using yfinance
def get_mstr_data():
    ticker = yf.Ticker("MSTR")
    try:
        info = ticker.info
        return {
            'market_cap': info.get('marketCap', 0),
            'shares_outstanding': info.get('sharesOutstanding', 0),
            'last_price': info.get('regularMarketPrice', 0)
        }
    except Exception as e:
        st.error(f"Error fetching MSTR data: {e}")
        return {'market_cap': 0, 'shares_outstanding': 0, 'last_price': 0}

# Main Streamlit app
st.title("Strategy Inc. (MSTR) Analysis Dashboard")
st.markdown("""
This dashboard provides real-time insights into Strategy's valuation, Bitcoin treasury, and amplification strategy via preferred stocks. Data is fetched live where possible.
""")

# Fetch data
btc_holdings = get_btc_holdings()
btc_price = get_btc_price()
mstr_data = get_mstr_data()

if btc_price and mstr_data['market_cap'] > 0:
    treasury_value = btc_holdings * btc_price
    btc_per_share = btc_holdings / mstr_data['shares_outstanding'] if mstr_data['shares_outstanding'] > 0 else 0
    
    # Approximate net liabilities from recent filings (update as needed)
    approx_debt = 8000000000  # ~$8B convertible debt
    approx_preferred_notional = 8000000000  # ~$8B preferred stock obligations
    approx_cash = 2190000000  # ~$2.19B reserves
    net_liabilities = approx_debt + approx_preferred_notional - approx_cash
    
    # Enterprise Value approximation
    ev = mstr_data['market_cap'] + net_liabilities
    
    # Amplification metrics
    leverage_amplification = treasury_value / mstr_data['market_cap'] if mstr_data['market_cap'] > 0 else 0
    nav = treasury_value - net_liabilities  # Simplified NAV for common equity
    premium_to_nav = mstr_data['market_cap'] / nav if nav > 0 else 0

    # Display metrics in a table for clarity
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
            "Premium to NAV"
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
    Strategy's preferred stock issuances (e.g., STRC at 11% dividend, STRD at 10%) enable low-cost capital raises to acquire more BTC, amplifying returns for common shareholders. This increases BTC per share over time (currently ~{:.6f} BTC/share) while dividends are supported by a ~$2.25B USD reserve. The leverage factor ({:.2f}x) shows how financing magnifies BTC upside, with the premium to NAV ({:.2f}x) reflecting market confidence in this strategy. If BTC appreciates, common equity benefits disproportionately after covering preferred dividends (~$640M annually).
    """.format(btc_per_share, leverage_amplification, premium_to_nav))

else:
    st.error("Failed to fetch required data. Check API availability or try again later.")
