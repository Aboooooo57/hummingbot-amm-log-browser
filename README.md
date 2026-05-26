# Hummingbot AMM Log Browser

A production-ready Streamlit application to browse and analyze Hummingbot Avellaneda Market Making (AMM) logs.

## Features
- **Trade Fills Analysis:** View total fills, volume, notional, and price trends.
- **Order Tracking:** Monitor order statuses, levels, and distributions.
- **Avellaneda Parameters:** Visualize inventory skew (q), risk aversion (γ), volatility, and reservation prices.
- **Dynamic Configuration:** Easily point to your Hummingbot data directory.

## Setup

### Prerequisites
- Python 3.9+
- SQLite log files from Hummingbot

### Local Installation

1. **Clone the repository:**
   ```bash
   git clone <repo-url>
   cd humm_sqlite_browser
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **(Optional) Configure Environment:**
   Create a `.env` file in the root directory:
   ```env
   SQLITE_DB_DIR=/path/to/your/hummingbot/data
   ```

5. **Run the app:**
   ```bash
   streamlit run app.py
   ```

## Docker Deployment

1. **Build the image:**
   ```bash
   docker build -t humm-browser .
   ```

2. **Run the container:**
   ```bash
   docker run -p 8501:8501 -v /path/to/hummingbot/data:/data -e SQLITE_DB_DIR=/data humm-browser
   ```

## Usage
- Use the sidebar to set the **SQLite Directory** where your `.sqlite` files are located.
- Select a specific log file from the dropdown.
- Alternatively, upload a `.sqlite` file directly.
- Navigate through the tabs to analyze fills, orders, and strategy parameters.

## Interpreting Avellaneda Metrics
- **q (Inventory Skew):** Values > 0 indicate a long position, < 0 indicate a short position. The strategy adjusts reservation prices to bring `q` back to 0.
- **Reservation Price:** The price at which the bot is indifferent between holding inventory and trading.
- **Optimal Spread:** The calculated spread to maximize utility given risk aversion and volatility.
