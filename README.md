# GeminiTrader ♊📈

**A personal project exploring the development of an LLM-enhanced cryptocurrency portfolio management application.**

This project aims to create a dynamic and adaptable portfolio strategy, initially focusing on the Binance.US exchange. The core goal is to maximize capital accumulation over a very long time horizon (conceptualized as reaching "age 100") by intelligently managing allocations across established cryptocurrencies and stablecoins, rather than relying solely on traditional trading signals or stop-losses. This is purely an experimental endeavor for personal learning and use, **not financial advice**.

## Core Philosophy & Strategy

*   **Dynamic Portfolio Allocation:** The primary strategic lever is the **ratio of capital allocated** across different assets within the portfolio. Success is driven by adjusting these allocations effectively based on market conditions.
*   **Accumulation & Rebalancing (No Stop-Loss):** Instead of using stop-losses on individual positions, risk is managed through diversification across **established coins (e.g., BTC, ETH)** and by maintaining a **significant reserve in stablecoins**. Market dips are viewed as opportunities to strategically deploy stablecoin reserves ("buy the dip") to rebalance towards target asset allocations or accumulate favoured assets at lower prices.
*   **LLM for Allocation Decisions:** Leverage Large Language Models (LLMs) to assist with higher-level strategic decisions:
    *   Analyze market sentiment, news, and historical context to gauge overall market conditions (e.g., fear vs. greed, potential bottoms).
    *   Inform decisions on *how much* stablecoin reserve to deploy during dips.
    *   Potentially help adjust long-term target asset ratios based on evolving market narratives or perceived asset strengths.
*   **Focus on Established Coins:** Limit exposure primarily to cryptocurrencies with higher market capitalization, longer track records, and higher perceived probability of long-term survival.
*   **Stablecoin Management:** Select and utilize stablecoins (e.g., USDT, USDC) based on their stability, availability, and transaction/trading fee implications on Binance.US.
*   **Data-Driven History:** Collect and store historical market data (klines) to provide context for LLM analysis and strategy evaluation.

## Current Architecture & Setup (Initial Phase)

This project is currently set up for **exploratory development** using:

1.  **VS Code + Dev Containers:** Consistent, portable development environment via Docker.
2.  **Docker:** Underpins the Dev Container.
3.  **Jupyter Notebooks:** Initial interface for API interaction, data fetching/storage testing, strategy prototyping, and LLM experiments. Run *within* the dev container.
4.  **Python:** Core programming language.
    *   Key libraries: `jupyterlab`, `pandas`, `numpy`, `requests`, `python-binance` (or appropriate API library), `python-dotenv`.

**Eventual Goal:** Evolve from Jupyter exploration into a more automated system (likely running in a Docker container) that monitors the portfolio, fetches market data, interacts with an LLM (potentially), and executes rebalancing trades based on the defined allocation strategy.

## Getting Started

1.  **Prerequisites:**
    *   Install [Docker Desktop](https://www.docker.com/products/docker-desktop/).
    *   Install [Visual Studio Code](https://code.visualstudio.com/).
    *   Install the "Dev Containers" extension in VS Code (ID: `ms-vscode-remote.remote-containers`).
2.  **Clone the Repository:**
    ```bash
    # If you haven't initialized git yet:
    # git init
    # git add .
    # git commit -m "Initial commit with README and .devcontainer setup"
    # git remote add origin <your-repo-url>
    # git push -u origin main

    # If already pushed, just clone:
    git clone <your-repo-url>
    cd GeminiTrader
    ```
3.  **Open in VS Code:**
    *   Open the `GeminiTrader` folder in VS Code (`File` > `Open Folder...`).
4.  **Reopen in Container:**
    *   VS Code should detect the `.devcontainer` configuration and prompt you: "Folder contains a Dev Container configuration file. Reopen folder to develop in a container?"
    *   Click **"Reopen in Container"**.
    *   If you don't see the prompt, open the Command Palette (`Ctrl+Shift+P` or `Cmd+Shift+P`), type `Dev Containers: Rebuild and Reopen in Container`, and select it.
    *   VS Code will build the Docker image (takes time on the first run) and connect.
5.  **Install Dependencies (If needed):**
    *   The dev container should automatically install packages listed in `requirements.txt` (if configured in `devcontainer.json` or `Dockerfile`).
    *   If not, open a Terminal in VS Code (`Terminal` > `New Terminal` - this runs *inside* the container) and run: `pip install -r requirements.txt`
6.  **Launch JupyterLab:**
    *   In the VS Code Terminal, run:
        ```bash
        jupyter lab --ip=0.0.0.0 --port=8888 --no-browser --allow-root
        # Note: Remove --NotebookApp.token='' if you prefer token auth
        ```
7.  **Access JupyterLab:**
    *   VS Code might automatically forward the port and allow you to connect via its Jupyter extension (check the notifications or the Jupyter tab in the side panel).
    *   Alternatively, look for a URL in the terminal output like `http://127.0.0.1:8888/lab?token=...` and open it in your web browser.
8.  **API Keys SECURITY:**
    *   Create a `.env` file in the project root (e.g., `GeminiTrader/.env`).
    *   Add your keys like this:
        ```dotenv
        BINANCE_API_KEY=YOUR_BINANCE_US_API_KEY_HERE
        BINANCE_API_SECRET=YOUR_BINANCE_US_SECRET_KEY_HERE
        ```
    *   **Add `.env` to your `.gitignore` file** to prevent accidentally committing secrets.
    *   The provided Python code examples use `python-dotenv` to load these keys.

## Usage (Initial Phase)

*   Use the Jupyter notebooks within the running dev container to:
    *   Connect to the Binance.US API.
    *   Fetch and **store historical market data (klines)**.
    *   Track current portfolio balances.
    *   Prototype logic for calculating portfolio allocations.
    *   Experiment with rules for deploying stablecoin reserves.
    *   Begin integrating LLM functionalities for market context analysis.

## Roadmap / Future Goals (Revised)

*   [ ] Implement robust historical data fetching and storage (e.g., to CSV files or database).
*   [ ] Develop functions to accurately track current portfolio composition and value.
*   [ ] Define and implement logic for calculating target asset allocation ratios.
*   [ ] Develop rules/triggers for rebalancing trades (e.g., deviation thresholds, dip detection).
*   [ ] Research and select optimal stablecoin(s) on Binance.US.
*   [ ] Prototype LLM integration for market sentiment/context analysis to inform dip-buying decisions.
*   [ ] Implement safe order execution logic for rebalancing trades.
*   [ ] Develop basic monitoring/logging for portfolio changes and trades.
*   [ ] Refactor core logic from notebooks into Python modules (`.py` files).
*   [ ] Package as a standalone Docker image for potential automated execution.

## License

Proprietary - For Personal Educational and Experimental Use Only. Not for redistribution or commercial use.