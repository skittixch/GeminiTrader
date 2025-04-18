**Project Handover Document: GeminiTrader (BTCUSDT Rainbow Rebalancing)**

**Generated:** 2025-04-11 (Reflecting status after Plot v3.0 / Backtest v13.7.4)

**1. Project Overview & Goal** 🎯

*   **Project Name:** GeminiTrader
*   **Core Objective:** Develop a profitable, adaptive cryptocurrency trading bot using `python-binance` for the Binance.US exchange (`tld='us'`).
*   **Current Focus:** Backtesting and refining an automated "Rainbow Weighted Rebalancing" strategy for BTCUSDT using historical hourly data (Jan 2023 - Jan 2024).
*   **Language/Environment:** Python 3.10+ in Jupyter Notebook (`05-Analysis-SR-Trendlines.ipynb`).
*   **Key Vision:** Treat the backtester as a **parameterizable engine** suitable for automated parameter sweeps, optimization, and eventual integration with Machine Learning models incorporating external data (news, sentiment, etc.).

**2. Project Phases & Current Status** 📊

*   **Phase 1: Setup & Data Acquisition (✅ COMPLETE)**
    *   **Status:** Environment set up (`venv`, `requirements.txt`). API key handling via `.env` implemented. Binance client initialization for US exchange (`tld='us'`) established. Historical multi-timeframe (1D, 4H, 1H) kline data fetching implemented and functional (Cell 3). Exchange filters (tick size, step size, min notional) fetched/defined (Cell 2). Helper functions for price/qty adjustments created (Cell 2). Core configuration (symbol, logging, pandas display) established (Cell 1). Long-term data fetching (`yfinance`) for Power Law established (Cell 5).
    *   **Key Files/Cells:** Cell 1 (Setup), Cell 2 (Filters/Helpers), Cell 3 (Data Fetch), Cell 5 (PL Data Fetch).

*   **Phase 2: Core Strategy Development & Initial Backtesting (🔄 ACTIVE / ITERATING)**
    *   **Status:** Multiple strategy concepts explored:
        *   *Attempted:* Dynamic S/R Zone entries + Scaled TP (v7-v9). Encountered issues with reliable S/R zone generation (`calculate_dynamic_zones`).
        *   *Attempted:* Pure Power Law / BBM Grids (v10-v12). Encountered issues with level placement and basic performance.
        *   *Current:* **Rainbow Weighted Rebalancing (v13.x)**. Implemented Power Law channel calculation (Cell 5), Rainbow Band subdivision (Cell 5.1), target allocation logic (`target_crypto_allocation_pct`), and band-crossing trigger mechanism. Backtesting engine (Cell 6) simulates trades, fees, and portfolio value based on this logic.
    *   **Current Backtest Version:** v13.7.4 (Quiet Fills)
    *   **Key Files/Cells:** Cell 5 (Power Law), Cell 5.1 (Rainbow Bands), Cell 6 (Backtester).
    *   **Challenges:** Current parameters underperform HODL; band-crossing trigger might be too sensitive.

*   **Phase 3: Analysis & Visualization (🔄 ACTIVE / ITERATING)**
    *   **Status:** Plotting implemented (Cell 7) showing price, PL lines, rainbow boundaries, and trade markers. Iterations focused on improving clarity, including axis flipping and scaling adjustments to focus on price action. Basic performance metrics (PnL %, vs HODL %, trade counts, fees) are calculated and printed (Cell 6). Logging refined to separate INFO (screen) and DEBUG (file) output.
    *   **Key Files/Cells:** Cell 6 (Metrics Output), Cell 7 (Plotting - v3.0).
    *   **Observations:** Visualizations reveal high trade frequency near band boundaries with current parameters.

*   **Phase 4: Optimization & Refinement (⏳ UPCOMING / PLANNING)**
    *   **Status:** Primarily manual adjustments and observations so far. Identified `NUM_RAINBOW_BANDS` and `ALLOCATION_EXPONENT` as key tuning parameters. Identified trigger sensitivity/profitability as a major area for refinement.
    *   **Immediate Next Steps:**
        *   Systematically test different `NUM_RAINBOW_BANDS` values.
        *   Test different `ALLOCATION_EXPONENT` values.
        *   Explore and test refined trigger mechanisms (e.g., requiring candle close, minimum price move).
        *   Prototype "TA Confirmation Multiplier / Dynamic TP" logic.
    *   **Future Vision:** Parameterize the backtester (Cell 6) for automated sweeps.

*   **Phase 5: Advanced Features & Future Development (📅 FUTURE)**
    *   **Status:** Conceptual / Planning stage.
    *   **Roadmap Items:**
        *   Parameterize backtester & build automated sweep framework.
        *   ML Integration: Use sweep results/market data to predict optimal parameters or directly inform trading decisions.
        *   External Data: Incorporate news, sentiment, on-chain data.
        *   UI Development: Visual adjustment of allocation curve, results dashboard.
        *   Multi-Asset Expansion.
        *   Live Trading Preparation: Broker integration, real-time data handling, risk management overlays, error handling.

**3. Current Core Strategy Details (v13.7.x - "Rainbow Weighted Rebalancing")** 🌈⚖️

*   *(This section remains the same as the previous handover document, detailing the PL Channel, Rainbow Bands, Target Allocation, Trigger, Execution, and Risk Management)*

**4. Strategy & Code Evolution History** 💡

*   *(This section remains the same as the previous handover document, detailing the evolution through v7-v9, v10-v12, v13.x, and Plotting iterations)*

**5. Current Status Summary (End of Session - 2025-04-11)** ✅

*   *(This section remains the same, summarizing Backtester/Plotter versions, key results, observations, and logging status)*

**6. Key Files & Variables** 💾

*   *(This section remains the same, listing Notebook, Log File, DataFrames, Key Parameters, and Key Functions)*

**7. Development Environment & Conventions** ⚙️

*   *(This section remains the same, listing Python version, venv, packages, Binance.US target, code rules, and API key handling)*

**8. Known Issues / Challenges** 🚧

*   *(This section remains the same, listing Performance, Trigger Sensitivity/Profitability, and Small Capital Simulation challenges)*

**9. Refined Roadmap & Future Goals (Mapped to Phases)** 🔭

*   **Phase 4: Optimization & Refinement:**
    *   **Immediate:** Tune `NUM_RAINBOW_BANDS`, `ALLOCATION_EXPONENT`.
    *   **Near-Term:** Refine trigger mechanism (alternatives to simple cross).
    *   **Near-Term:** Prototype & Test "TA Confirmation Multiplier / Dynamic TP" concept.
*   **Phase 5: Advanced Features & Future Development:**
    *   **Mid-Term:** Parameterize backtester, build automated sweep framework.
    *   **Mid-Long Term:** ML Integration (parameter prediction, potentially decision making).
    *   **Long-Term:** Integrate external data sources.
    *   **Long-Term:** Develop UI.
    *   **Long-Term:** Expand to multi-asset.
    *   **Long-Term:** Prepare for live trading (if desired).

**10. Immediate Next Steps for LLM** 🎯

1.  **Assist with Parameter Sweeps (Phase 4):** Help user set up code to run Cell 6 multiple times with different `NUM_RAINBOW_BANDS` and `ALLOCATION_EXPONENT`. Collect and compare results.
2.  **Code Trigger Refinements (Phase 4):** Help implement and test alternative trigger conditions (e.g., close basis, min move).
3.  **Conceptualize/Outline Dynamic TP (Phase 4):** Help structure the logic for the "TA Confirmation Multiplier / Dynamic TP" feature.
4.  **Parameterize Backtester (Phase 5 Prep):** Discuss and outline how to refactor Cell 6 into a callable function for automated testing.