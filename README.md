# GeminiTrader ♊📈

**A personal project exploring the development of an LLM-enhanced cryptocurrency trading application.**

This project aims to create a dynamic and adaptable trading strategy, initially focusing on the Binance.US exchange. The core goal is to maximize capital accumulation over a very long time horizon (conceptualized as reaching "age 100"), taking into account trading fees, market dynamics, and risk management. This is purely an experimental endeavor for personal learning and use, **not financial advice**.

## Core Philosophy & Inspiration

- **Brachistochrone Principle Applied:** Inspired by the physics problem of finding the path of fastest descent, this project seeks the trading strategy that optimizes the _rate_ of capital growth. This involves not just picking profitable trades, but also considering the velocity of capital – how quickly it can be deployed, generate returns, and be redeployed, factoring in trading costs.
- **LLM Enhancement:** Leverage Large Language Models (LLMs) for tasks beyond simple analysis, including:
  - **Dynamic Strategy Generation:** Adapting trading rules based on real-time market conditions, sentiment, and news.
  - **Advanced Sentiment/Narrative Analysis:** Interpreting news, social media, and other text sources to gauge market mood and identify emerging trends.
  - **Complex Event Interpretation:** Understanding the potential impact of traditional finance events (Fed meetings, options expiry) on crypto markets.
  - **Adaptive Risk Management:** Dynamically adjusting exposure based on perceived market risk and LLM analysis.
- **High-Probability Entries:** Focus on identifying trading setups with a confluence of supporting factors (technical, quantitative, on-chain, sentiment) rather than relying on single indicators.
- **Fee-Aware Trading:** Acknowledging that trading fees (even relatively low ones on Binance.US) impact profitability, especially for higher-frequency strategies. Strategies must generate sufficient profit _after_ fees.
- **Long-Term Perspective & Survival:** Incorporating considerations for the long-term viability ("survival probability") of traded assets, essential for a multi-decade goal.

## Current Architecture & Setup (Initial Phase)

This project is currently set up for **exploratory development** using:

1.  **VS Code + Dev Containers:** The primary development environment is managed through VS Code's Dev Containers feature. This ensures a consistent, reproducible environment using Docker.
2.  **Docker:** Underpins the Dev Container, making the entire development environment portable and isolated.
3.  **Jupyter Notebooks:** The initial interface for interacting with APIs, testing strategy components, visualizing data, and prototyping LLM integrations. Notebooks are run _within_ the dev container.
4.  **Python:** The core programming language.
    - Key libraries: `jupyterlab`, `pandas`, `numpy`, `requests`, `python-binance` (or the appropriate Binance.US API library).

**Eventual Goal:** The long-term vision is to evolve this from an exploratory Jupyter setup into a more robust, potentially headless application running within a simple Docker container for automated execution.

## Getting Started

Follow these steps to set up and run the development environment:

1.  **Prerequisites:**
    - Install [Docker Desktop](https://www.docker.com/products/docker-desktop/).
    - Install [Visual Studio Code](https://code.visualstudio.com/).
    - Install the "Dev Containers" extension in VS Code (ID: `ms-vscode-remote.remote-containers`).
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
    - Open the `GeminiTrader` folder in VS Code (`File` > `Open Folder...`).
4.  **Reopen in Container:**
    - VS Code should detect the `.devcontainer` configuration and prompt you: "Folder contains a Dev Container configuration file. Reopen folder to develop in a container?"
    - Click **"Reopen in Container"**.
    - If you don't see the prompt, open the Command Palette (`Ctrl+Shift+P` or `Cmd+Shift+P`), type `Dev Containers: Rebuild and Reopen in Container`, and select it.
    - VS Code will build the Docker image (takes time on the first run) and connect.
5.  **Install Dependencies (If needed):**
    - The dev container should automatically install packages listed in `requirements.txt` (if configured in `devcontainer.json` or `Dockerfile`).
    - If not, open a Terminal in VS Code (`Terminal` > `New Terminal` - this runs _inside_ the container) and run: `pip install -r requirements.txt`
6.  **Launch JupyterLab:**
    - In the VS Code Terminal, run:
      ```bash
      jupyter lab --ip=0.0.0.0 --port=8888 --no-browser --allow-root --NotebookApp.token=''
      ```
7.  **Access JupyterLab:**
    - VS Code might automatically forward the port and allow you to connect via its Jupyter extension.
    - Alternatively, open your web browser and navigate to `http://127.0.0.1:8888` or `http://localhost:8888`.
8.  **API Keys SECURITY:**
    - **NEVER** commit your API keys or hardcode them directly into notebooks or scripts.
    - Use environment variables (configurable via `.devcontainer/devcontainer.json`'s `remoteEnv` property or a `.env` file loaded by Python) or another secure method to manage your Binance.US API Key and Secret Key.

## Usage (Initial Phase)

- Use the Jupyter notebooks within the running dev container to:
  - Connect to the Binance.US API.
  - Fetch market data (prices, volume, order books).
  - Experiment with technical indicators.
  - Prototype strategy logic (entry/exit signals).
  - Test order placement and management functions.
  - Begin integrating LLM functionalities (e.g., pulling news, basic sentiment analysis).

## Roadmap / Future Goals

- [ ] Develop core trading logic modules.
- [ ] Integrate robust API interaction (error handling, rate limits).
- [ ] Implement initial LLM-driven sentiment analysis pipeline.
- [ ] Design and test basic strategy backtesting framework.
- [ ] Explore LLM for dynamic parameter tuning or rule generation.
- [ ] Implement risk management rules (stop-loss, position sizing).
- [ ] Develop basic monitoring/logging.
- [ ] Refactor core logic from notebooks into Python modules (`.py` files).
- [ ] Package as a standalone Docker image for background execution.
- [ ] Consider adding a simple UI (potentially revisiting Svelte?) for monitoring _after_ core logic is stable.

## License

Proprietary - For Personal Educational and Experimental Use Only. Not for redistribution or commercial use.
