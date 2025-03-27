# GeminiTrader (Prototype)

A web-based, interactive candlestick chart displaying cryptocurrency data (initially BTC-USD) fetched from a local backend proxying the Coinbase API, with live updates via WebSocket. Built with plain HTML, CSS, and vanilla JavaScript modules.

## Features

*   **Interactive Chart:**
    *   Displays historical candlestick data (OHLCV).
    *   Pan the chart by clicking and dragging the main chart area.
    *   Zoom in/out using the mouse scroll wheel.
    *   Scale the Y-axis (price) by clicking and dragging the price scale vertically.
    *   Scale the X-axis (time) by clicking and dragging the time scale horizontally.
    *   Double-click anywhere on the chart to reset the view to a default zoom level centered on the clicked time.
*   **Live Data:**
    *   Connects to Coinbase WebSocket feed for real-time price updates.
    *   Displays the current ticker price as a line and label on the chart.
    *   Updates the closing price and high/low of the *latest* candle in real-time.
*   **Customization & UI:**
    *   Selectable Candlestick Granularity (5m, 15m, 1h, 6h, 1d).
    *   Logarithmic / Linear Y-axis scale toggle.
    *   Dark / Light theme toggle (respects system preference, saves choice).
    *   12-hour (AM/PM) / 24-hour time format toggle.
    *   Date rollover labels and vertical separator lines on the X-axis.
    *   Clean, minimal dashboard-like styling.
*   **Backend Proxy:**
    *   Simple Python Flask server (`server.py`) fetches historical data from the official Coinbase API, decoupling the frontend from direct API calls.

## Project Goals (Future)

*   [ ] Integrate basic trading features (e.g., placing market/limit orders - **requires authentication and careful security considerations**).
*   [ ] integrate LLM interface to determine trading opportunities and general strategy management.
*   [ ] Display additional data (e.g., volume bars, technical indicators).
*   [ ] Allow selection of different trading pairs (product IDs).


## Tech Stack

*   **Frontend:** HTML5, CSS3, Vanilla JavaScript (ES Modules)
*   **Backend:** Python, Flask, Flask-CORS, Requests
*   **Data Source:** Coinbase Exchange API (REST for historical, WebSocket for live ticker)

## Setup and Running

**Prerequisites:**

*   [Git](https://git-scm.com/)
*   [Python 3](https://www.python.org/) (including `pip`)
*   A modern web browser

**Instructions:**

1.  **Clone the Repository (if applicable):**
    ```bash
    git clone https://github.com/skittixch/GeminiTrader/tree/main.git
    cd GeminiTrader
    ```
    *(If you haven't cloned it yet)*

2.  **Navigate to Project Directory:**
    Open your terminal or command prompt and `cd` into the project's root folder (the one containing `index.html`, `server.py`, etc.).

3.  **Install Python Dependencies:**
    ```bash
    pip install Flask Flask-Cors requests
    ```
    *(Consider using a Python virtual environment: `python -m venv venv`, then activate it before installing)*

4.  **Run the Backend Server:**
    Open a terminal in the project directory and run:
    ```bash
    python server.py
    ```
    Leave this terminal running. You should see output indicating it's running on `http://0.0.0.0:5000/`.

5.  **Run the Frontend Server:**
    Open a *second* terminal in the *same* project directory and run Python's built-in HTTP server (or use VS Code's Live Server):
    ```bash
    python -m http.server 8000
    ```
    *(You can use a different port if 8000 is taken)*. Leave this terminal running.

6.  **Access the Chart:**
    Open your web browser and navigate to:
    ```
    http://localhost:8000
    ```
    *(Use the port number you specified for the frontend server)*.

The chart should load, fetch data from your local backend (which fetches from Coinbase), connect to the WebSocket, and display the live price.

## Code Structure
