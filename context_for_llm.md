```markdown
**(Rolling SSoT Prompt Block - Last Updated: 2025-04-14 ~18:40 UTC)**

**Based on: v6.5 (2025-04-12 - Integrates Prompt Engineering Best Practices)**
**Session Summary Appended: 2025-04-14 ~18:40 UTC**

**Preamble:** This document constitutes the complete and authoritative specification for the GeminiTrader project as of the base version date. It incorporates key findings from strategic research (v6.4) and **integrates best practices from modern Prompt Engineering methodologies** to enhance user-LLM collaboration and internal LLM usage (v6.5). It is designed to be self-contained and serve as the Single Source of Truth (SSoT) for development. **This specific text block also includes the handover summary from the most recent development session and instructions for continuing this rolling update process.** All previous versions or fragmented discussions are superseded by this plan. Future iterations will produce a new, complete version of this prompt block.

**0. Instructions for Assisting LLM (Meta-Guidance - Enhanced with Prompt Engineering Principles & Rolling SSoT Update)**

**(Note to LLM Assistant: This document serves as the primary specification and roadmap for the GeminiTrader project. Your assistance must strictly adhere to the guidelines below and the phased implementation plan detailed herein. This prompt block is the primary source of truth for requirements, phasing, and recent progress. It incorporates strategic refinements (v6.4), explicit prompt engineering best practices (v6.5), and the latest session handover summary. Your effectiveness is directly tied to how well you interpret and apply these instructions, paying close attention to the user interaction notes highlighted in the handover summaries.)**

A.  **Primary Goal:** Your central task is to assist the user in implementing all phases and modules of the GeminiTrader project. The core strategy is a hybrid approach combining intelligent DCA, adaptive geometric dip-buying, and a sophisticated confidence/adaptive decision-making layer. All operations use a hybrid risk management philosophy. **Achieving this requires effective communication and prompt interpretation.**
B.  **Code Generation (Python & python-binance for Binance.US):**
    *   Provide accurate, complete, modular, and efficient Python code (version 3.10+).
    *   Code must be tailored specifically for interacting with the Binance.US exchange using the `python-binance` library (`tld='us'`).
    *   Follow Python best practices and `python-binance` library conventions.
    *   **Formatting is CRITICAL (Strict Adherence Required):**
        *   **Self-Contained Runnable Code Blocks:** Generate complete, copy-pasteable code suitable for direct execution in the appropriate context (usually a `.py` module file within the `src/` directory, or occasionally a Jupyter cell for testing/analysis). Ensure all necessary imports and variable definitions (or explicit prerequisites) are included within each block. **Absolutely NO ellipses (`...`), omissions (`# rest of code`), or placeholder comments (`# implementation detail`, `# TODO`) within the code logic.** Provide the *full* code for the requested file or function. **(User Directive: User strongly prefers full code blocks - "full code only please").**
        *   **Imports Included:** Place ALL necessary import statements at the beginning of each code block/file.
        *   **Variable Definitions:** Define all variables within the block OR explicitly state which variables are prerequisites from specific prior steps/modules defined within this document.
        *   **Explanatory Comments Only:** Use comments (`#`) solely for clarifying complex logic, algorithmic choices, or intent, not as instructions to the user within the code. Avoid commented-out functional code unless it represents a clear, alternative path explicitly discussed and chosen as optional.
        *   **Proper Try/Except:** NEVER use single-line `try...except`. Ensure `try:`, `except Exception as e:`, and `finally:` (if used) start on separate, correctly indented lines. Include meaningful logging (using the configured logger) within `except` blocks to capture error details. Raise exceptions appropriately to signal failure when necessary.
        *   **Modular Structure:** Generate code organized into functions and classes within the appropriate `.py` files in the `src/` directory structure (outlined in Section 3). Promote reusability, testability, and separation of concerns. Adhere to the specified module structure for each phase.
        *   **Logging Verbosity:** Adhere to the logging strategy defined in Phase 0. Default to `logging.debug()` for high-frequency internal operations. Use `logging.info()` for significant milestones. Use `logging.warning()` for recoverable issues. Use `logging.error()` or `logging.exception()` for unrecoverable errors. Minimize INFO logs within tight loops.
    *   **Prompting for Code:**
        *   **Specificity:** Interpret user requests precisely. If a request is ambiguous, ask for clarification before generating code.
        *   **Context is Key:** Leverage this entire prompt block (SSoT + Handover) as the primary context. Understand the current phase and module requested (refer to the appended Handover Summary for the latest stopping point).
        *   **Use Examples (Few-Shot Principle):** If the user provides examples, use them as a strong guide.
        *   **Chain of Thought (Internal):** Use internal CoT for complex code generation.
        *   **Output Structure:** Adhere to user-requested structures.
C.  **Interaction & Assistance (Applying Prompting Techniques):**
    *   **Clarification is Key:** Proactively ask questions if requirements, intentions, technical details, or prompts are unclear based on *this entire prompt block*. **Do not guess.**
    *   **Proactive Guidance:** Identify potential challenges, edge cases, or improvements based on project goals and current phase. **Proactively request necessary context (existing files) before generating dependent code (See Section 0.G).**
    *   **Adherence to Plan:** Follow the phased implementation order (0-9). Guide the user back if requests deviate significantly. Refer to the appended Handover Summary for the next steps.
    *   **Emphasize Automation & Resilience:** Frame suggestions accordingly.
    *   **Leverage Prompting Techniques:** Use Contextual Prompting, System/Role Prompting awareness, Chain of Thought (for reasoning), Step-Back Prompting, and focus on Instructions over Constraints.
    *   **Iterative Process:** Expect and learn from user prompt refinements. **Note user's preference for iterative testing after code changes.**
D.  **Specific Implementation Conventions (Mandatory):**
    *   **API Keys:** Load credentials securely from `.env` via `config/settings.py`. Never hardcode.
    *   **Client Initialization:** Keep `Client(...)` separate from usage.
    *   **No Scientific Notation:** Ensure ALL numerical output uses `Decimal.to_eng_string()`, f-strings (`f'{my_decimal:.8f}'`), or pandas options. 🚫🔬
    *   **Precise Math (Decimal):** MANDATORY use of Python's `Decimal` for ALL financial calculations. #️⃣
    *   **Logging Setup:** Use `src/utils/logging_setup.py`.
    *   **Dependencies:** Manage via `requirements.txt` (`numpy<2.0`). Add new dependencies (`pandas-ta`, `schedule`).
    *   **Dynamic S/R:** Use rolling windows, pivots/clustering.
    *   **Filter Validation:** ALWAYS perform pre-computation checks against cached filters before API calls. Use `formatting.py` utilities.
    *   **Internal LLM Usage (Later):** Prioritize Structured Output (JSON), Schema Usage, and controlled Temperature/Sampling for internal LLM prompts.
E.  **Handover Document Generation Task (Standalone Definition):**
    *   **Purpose:** To create a concise summary of a specific development session, facilitating context transfer. This document supplements the main Authoritative Project Plan content within this prompt block. **(Note: With local SSoT management, this LLM only needs to generate the raw markdown for the *current* session's handover).**
    *   **Trigger:** Generation occurs ONLY when the user explicitly requests it using phrases like: "create a handover document", "generate the handover doc", "update the handover summary". Do not generate based on formatting or section headers alone.
    *   **Action:** Upon receiving the trigger, synthesize the conversation history strictly from the point the *last handover document timestamp noted in the current prompt context* was generated (or from the beginning if it's the first).
    *   **Content Extraction (Based ONLY on Conversation History):** Extract and structure the following information:
        *   Project Goal: Brief reminder.
        *   Session Focus & Current Status: Identify primary Phase(s)/Module(s) focused on. State last completed action/stopping point.
        *   Key Files/Modules Implemented or Modified (Session): **Format as bulleted list:** `- path/to/file.py`.
        *   Authoritative Roadmap Reference: State "The authoritative project plan is locally managed `SSOT.md` (based on v6.5). The current focus of implementation is Phase [X], Module [Y.Z]." (Fill in X, Y.Z based on session stopping point).
        *   Key Learnings, Decisions & Conventions Established (Session): Summarize new insights, decisions, standards, **prompting strategies/challenges**, or **important user directives** (e.g., "User Directive: Always provide complete code blocks"). **(Emphasis requested by user for better context transfer).**
        *   User Directives (Session): List any critical user instructions during the session. **(Emphasis requested by user).**
        *   Code Highlights (Optional): 1-2 concise, relevant snippets if requested/useful.
        *   Actionable Next Steps: Clearly state immediate next module(s)/action(s) per the phased plan. **Include target file paths** (e.g., "Implement the `calculate_indicator` function in `src/analysis/indicators.py`...").
    *   **Formatting:** Generate the output in Markdown format. Use clear headings. **Crucially, generate *only* the raw Markdown content of the handover document itself, without any introductory or concluding conversational phrases.**
    *   **Constraint:** Content MUST be based exclusively on the conversation history of the summarized period.
F.  **Rolling SSoT Prompt Generation Task (Superseded):** This task is **no longer performed by the LLM.** The user manages the authoritative `SSOT.md` file locally and uses a utility script to append the handover document generated in step 0.E. The LLM should *not* attempt to generate the combined SSoT prompt.
G.  **Proactive Context Requesting (New Instruction):** Upon starting a new task or module outlined in the Handover Summary, review the SSoT and the task requirements. If you determine that accessing the content of existing project files (e.g., utility functions, connector classes, configuration settings, previously implemented modules) is necessary to accurately generate the requested code or provide guidance, explicitly ask the user to provide the content of those specific files. **State clearly which files you believe are needed and briefly explain why** (e.g., "To integrate the SMA calculation, please provide the content of `src/analysis/indicators.py` to see the `calculate_sma` function signature and `config/config.yaml` to check for default period settings."). Do not proceed with implementation requiring unknown dependencies without requesting them first. The user wants to know what you need to succeed.
**(End of Instructions for Assisting LLM)**

**1. Core Philosophy & Strategy Foundation**

*   **Overall Goal:** To engineer and continuously refine a fully autonomous cryptocurrency trading and accumulation system, GeminiTrader. Its primary directive is substantial, multi-decade capital growth (conceptual "rich by 100" target), achieved through intelligent navigation of market dynamics, inherent volatility, and potential future systemic disruptions, all while operating with minimal human intervention.
*   **Hybrid Strategy Engine - The Triad of Operation:**
    *   **Intelligent Accumulation (Automated DCA):** Forms the consistent capital injection mechanism. Implements a disciplined, automated Dollar-Cost Averaging strategy, decoupled from direct bank balance monitoring initially. Triggered by a pre-defined schedule aligned with estimated income patterns (e.g., semi-monthly using `schedule` library), deploying a configurable base USD amount. This baseline DCA reduces timing risk for core positions and ensures persistent market participation. Future phases enhance this with dynamic adjustments based on market conditions (confidence scores modulating amount/frequency) and fully automated bank funding integration. Aims to consistently build core positions.
    *   **Volatility Harvesting (Adaptive Geometric Dip-Buying):** The primary active trading mechanism. Employs a layered strategy across multiple, configurable timeframes (e.g., 1h, 4h, 1d). Strategically places LIMIT BUY orders at **volatility-adjusted geometrically spaced** price intervals below the current market price (informed by S/R, trendlines, ATR, and current price action), featuring geometrically increasing order sizes. **Crucially, dip-buying is filtered by higher-timeframe trend confirmation** (avoiding entries in strong downtrends). Aims to systematically profit from price oscillations while managing risk in trending markets. Maximum order counts or total position size limits act as pseudo-stop mechanisms.
    *   **Predictive & Contextual Intelligence Layer (Confidence & Adaptive Decision-Making):** GeminiTrader transcends simple reactive trading by incorporating predictive elements informed by a vast data ecosystem. It integrates: Technical Analysis (Indicators, Dynamic S/R Zones via pivots/clustering, Algorithmic Trendlines with reliability scoring), Market Microstructure (Order Book Dynamics), External Context (News Feeds - LLM Sentiment/Topic/Magnitude, Crypto Categories/Narratives, Macro Data), Social & Behavioral Signals (Influencer Tracking/Sentiment, Market Psychology Indicators), Long-Term Models & Cycles (Power Law, Rainbow, S2F, MVRV, Halving analysis), and insights from Academic Research. This data dynamically feeds a composite **Confidence Score**, quantifying conviction (potentially calibrated towards a probability via meta-labeling or ensemble weighting in later phases). This score directly modulates: **Adaptive Position Sizing** (using principles inspired by fractional Kelly Criterion - higher confidence justifies larger size allocations), Dynamic Profit Target calculations (adjusting targets based on confidence), DCA amount/frequency adjustments, and grid spacing/aggressiveness.
*   **Hybrid Risk Management (Avoiding Price-Based Stops):** Fundamentally rejects conventional price-based stop-losses for active trades to avoid whipsaws and stop-hunts, *but implements robust alternative risk controls*. Manages risk holistically through:
    *   **Adaptive Position Sizing:** Small initial entries, confidence-scaled allocations (primary risk control).
    *   **Capital Flow Management:** Consistent DCA, strategic stablecoin reserves.
    *   **Dynamic Profit Taking:** Proactive gain realization based on confidence, volatility, S/R, time-decay.
    *   **Confidence Modulation:** Reducing exposure/aggressiveness in low-conviction states.
    *   **Time-Based Position Evaluation & Exits:** Reassessing and potentially exiting stagnant or invalidated trades based on time elapsed (time stops).
    *   **Conditional Exits:** Potential exits triggered by volatility extremes or invalidation of the core trade thesis (indicator-based or logic-based stops).
    *   **Geometric Grid Limits:** Maximum number of grid levels or total position size caps per asset/strategy.
    *   **Higher-Timeframe Trend Filtering:** Preventing dip-buys during confirmed downtrends.
    *   **Strict Exchange Filter Compliance:** Preventing execution errors.
    *   **Long-Term Assumption Validation:** Monitoring model decay and market regime shifts.
    *   **Catastrophic Event Response Framework:** Portfolio-level maximum loss triggers or systemic risk responses (e.g., flatten to stables).
*   **Full Automation & Self-Sufficiency:** Designed for minimal intervention over extended periods. Aims for complete end-to-end automation (funding, trading, logging, state management) with minimal required user interaction. Includes self-monitoring and alerting. Intends to eventually self-fund operational costs.
*   **Data-Driven Evolution & Academic Grounding:** Incorporates mechanisms for continuous improvement via rigorous backtesting, live performance analysis, ML model retraining (later phases), integration of quantitative finance research, **documentation of prompt engineering strategies & attempts (see Section 2 & RESEARCH.md)**, and periodic optimization of external dependencies ("Composer Agent").
*   **Lean & Efficient Infrastructure:** Follows a local-first development model. Employs value-driven, adaptive data polling. Mindful of costs. Scalable architecture.
*   **Most Important Foundational Pillars (Implementation Order):**
    1.  Core Trading Engine (Volatility-Adjusted Geometric Dip-Buying + Basic Dynamic TP).
    2.  Robust Data Handling, Configuration & State Management.
    3.  Exchange Filter Compliance.
    4.  Backtesting Framework (Simulating adaptive sizing, time stops, grid limits).
    5.  DCA Logic & Semi-Automated Funding Pipeline.
    6.  Initial Confidence Layer & Adaptive Sizing Logic.
    7.  Alternative Risk Controls (Time Stops, Conditional Exits, Max Limits).

**2. Development Workflow Strategy (User & LLM Collaboration - Enhanced with Local SSoT Management)**

*   **Single Source of Truth (SSoT):** The **user manages** the authoritative `SSOT.md` file locally. The prompt provided to the LLM at the start of a session (containing this text) represents the SSoT *for that session*.
*   **Phased Implementation:** Development proceeds phase by phase (0 through 9), focusing on the modules and actions defined within each phase as outlined below. The user will direct the LLM assistant by requesting implementation of specific steps from the current phase, referencing the appended Handover Summary for the starting point.
*   **LLM Code Generation:** LLM assistant generates complete, modular, runnable Python code adhering strictly to the LLM Instructions (Section 0 above) and the specific requirements of the requested module/step. Code is generated for `.py` files within the `src/` directory structure or as test snippets. **Completeness is mandatory (no omissions).**
*   **User Testing & Debugging:** User integrates, runs, tests (unit, integration, backtests), and debugs code, collaborating with the LLM.
*   **Iterative Refinement & Prompt Engineering:** User and LLM refine code, config, strategy, and **user prompts** based on results. Significant deviations require updates to the local `SSOT.md` file (managed by the user).
*   **Prompt Documentation:** Maintain record of significant prompt attempts (e.g., in `RESEARCH.md` or `PROMPTS.md`), especially for internal LLM use or complex tasks.
*   **Handover Document Generation (Context Transfer - Step 1):** At session end, user prompts LLM assistant to "create a handover document". LLM generates session summary per Section 0.E, based only on session history, **outputting raw Markdown only**.
*   **Local SSoT Update (Context Transfer - Step 2):** **User** saves the generated handover markdown and uses a local utility (e.g., enhanced `scripts/context_manager.py`) to append it to the master `SSOT.md` file and generate the complete `context_for_llm.txt` file for the next session. **LLM does not perform this step.**
*   **Long-Term Goal (Agentic System):** The locally managed SSoT, modular code, documented prompts, and traceable history via Handover Docs facilitate potential future agentic integration.

**3. Project Directory Structure (Conceptual)**

```
geminitrader/
│
├── .venv/                  # Python virtual environment
├── config/                 # Configuration files
│   ├── __init__.py
│   ├── settings.py         # Loads config & environment vars
│   └── config.yaml         # Core parameters, API endpoints, feature flags, strategy params (grid spacing, ATR multiplier, max levels, sizing rules)
│   └── asset_categories.yaml # Asset -> Category mapping
│   └── influencers.yaml      # Curated influencer list & tiers
│
├── data/                   # Persistent data (!!! GITIGNORE THIS DIR !!!)
│   ├── cache/              # Cached API responses (exchange info, klines etc.)
│   │   └── exchange_info.json
│   ├── db/                 # Database files
│   │   └── geminitrader_log.db
│   ├── logs/               # Log files
│   │   └── trader.log
│   │   └── pipeline.log
│   ├── models/             # Saved ML models & scalers
│   │   ├── tp_model.pkl
│   │   └── confidence_scaler.pkl
│   └── backtests/          # Saved backtest results/reports
│   └── context_logs/       # Logs from context_manager.py
│   └── state/              # Persisted application state (Phase 7)
│       └── trader_state.json
│
├── notebooks/              # Jupyter notebooks
│   ├── 00_Setup_Check.ipynb
│   ├── 01_MVP_Backtest.ipynb
│   ├── 02_DCA_Pipeline_Test.ipynb
│   ├── 03_Live_Monitoring_Dashboard.ipynb
│   ├── 04_ML_Model_Training.ipynb
│   └── 05_Research_Analysis.ipynb
│
├── scripts/                # Standalone utility/operational scripts
│   ├── run_dca_pipeline.py # Manual trigger for funding steps
│   ├── flatten_positions.py # Utility to sell all non-quote assets (Catastrophic Stop action)
│   ├── optimize_pipeline.py # The Composer Agent (Phase 8)
│   ├── run_backtest.py      # CLI interface for backtester
│   └── db_manage.py         # Database migration/management script
│   └── context_manager.py   # Utility for handover generation and SSoT management
│
├── src/                    # Core source code (Python package)
│   ├── connectors/         # Interface with external APIs
│   │   ├── __init__.py
│   │   ├── base_connector.py # Abstract base class
│   │   ├── binance_us.py     # Binance.US specific implementation
│   │   ├── coinbase.py       # For DCA funding pipeline
│   │   └── plaid_connector.py  # Optional, for bank integration
│   ├── strategies/         # Core trading and DCA logic
│   │   ├── __init__.py
│   │   ├── geometric_grid.py # Volatility-adjusted dip-buying logic, sizing rules
│   │   ├── dca.py            # DCA calculation logic (confidence modulated)
│   │   ├── profit_taking.py  # Dynamic TP logic (confidence modulated)
│   │   └── risk_controls.py  # Time stops, conditional exits, grid limits
│   ├── data/               # Data fetching, processing, caching
│   │   ├── __init__.py
│   │   ├── kline_fetcher.py
│   │   ├── orderbook_fetcher.py
│   │   ├── news_fetcher.py
│   │   ├── influencer_tracker.py
│   │   └── long_term_model_fetcher.py # Fetches/calculates PL, Rainbow, etc.
│   ├── analysis/           # Data analysis and signal generation
│   │   ├── __init__.py
│   │   ├── indicators.py     # TA indicators (ATR, SMA, RSI, MACD, Pivots)
│   │   ├── support_resistance.py # Dynamic zone calculation (pivot clustering)
│   │   ├── trendlines.py       # Algorithmic trendline detection (scored reliability)
│   │   ├── confidence.py       # Confidence score calculation (multi-factor, calibrated)
│   │   ├── orderbook.py        # OB analysis (walls, spoofing, etc.)
│   │   ├── llm_analyzer.py     # News/Sentiment/Topic analysis via LLM
│   │   ├── risk_monitor.py     # Black swan event monitoring, systemic risk
│   │   ├── behavioral.py       # Basic psych modeling (Fear/Greed, time-of-day)
│   │   └── assumption_validator.py # Checks long-term models vs reality
│   ├── db/                 # Database interaction layer
│   │   ├── __init__.py
│   │   ├── manager.py        # Connection, execution methods
│   │   ├── models.py         # (Optional) SQLAlchemy models for ORM
│   │   └── schema.sql        # SQL schema definition
│   ├── ml/                 # Machine learning models
│   │   ├── __init__.py
│   │   ├── tp_model.py         # Profit target prediction model
│   │   └── confidence_model.py # Confidence scoring model (potential meta-labeling)
│   ├── utils/              # General utility functions
│   │   ├── __init__.py
│   │   ├── formatting.py     # Decimal formatting, filter adjustments
│   │   ├── logging_setup.py  # Logging configuration
│   │   ├── caching.py        # Caching decorators/functions
│   │   └── categorizer.py      # Asset category lookup
│   ├── backtester/         # Backtesting engine
│   │   ├── __init__.py
│   │   └── engine.py         # Must simulate adaptive sizing, risk controls accurately
│   ├── dashboard/          # Code for TUI or Web dashboard (Phase 9)
│   │   └── __init__.py
│   │   └── app.py            # (Example if using Flask/Dash/Streamlit)
│   ├── __init__.py         # Makes src a package
│   └── main_trader.py      # Main live trading loop script
│   └── state_manager.py    # Handles live state persistence/recovery (Phase 7)
│   └── scheduler.py        # Manages periodic task execution
│
├── tests/                  # Unit and integration tests
│   ├── __init__.py
│   ├── test_connectors.py
│   ├── test_strategies.py
│   ├── test_utils.py
│   └── test_db.py
│   └── test_risk_controls.py
│
├── .env                    # API keys and secrets (GITIGNORE!)
├── .gitignore
├── Dockerfile              # For containerizing the application (Phase 8+)
├── docker-compose.yml      # For managing multi-container setups (Phase 8+)
├── requirements.txt
├── README.md               # Project overview, setup, usage, research links
├── SSOT.md                 # <<< NEW: Authoritative Single Source of Truth file (managed by user)
├── RESEARCH.md             # Links strategies to academic/quant concepts (Kelly, Meta-labeling, Time Stops, SR Algo Refs)
└── PROMPTS.md              # (Optional but Recommended) Detailed documentation of key prompts used
```

**4. GeminiTrader Project Plan: Phased Modular Development (Detailed - v6.5)**

**(LLM Assistant: Implement steps referencing v6.5 guidelines and conventions stated in Section 0. Pay close attention to the User Directive regarding *complete code* generation. Check the appended Handover Summary for the current starting point.)**

**Phase 0: Setup & Foundational Tools (The Workbench) [COMPLETED]**
Goal: Create the project scaffolding, establish API connectivity, implement precise math/filter utilities, setup logging, define DB schema.

*   0.1. Module: Project Setup & Environment **[COMPLETED]**
*   0.2. Module: Configuration Management (`config/`) **[COMPLETED]**
*   0.3. Module: API Connectivity (`src/connectors/binance_us.py`) **[COMPLETED - Added order methods & caching]**
*   0.4. Module: Core Utilities (`src/utils/`) **[COMPLETED - Added filter logic]**
*   0.5. Module: Database Setup (`src/db/`) **[COMPLETED]**

**Phase 1: MVP - Core Trading Engine & Basic Backtesting (The First Run) 📈⚙️ [Partially Implemented]**
Goal: Implement and validate the core *volatility-adjusted* geometric dip-buying / fixed-TP logic via backtesting, including *basic adaptive sizing* and *grid limits*.

*   1.1. Module: Market Data Fetching (`src/data/kline_fetcher.py`) **[Step 1.1.1 Completed]**
    *   Action (1.1.1): Implement `fetch_and_prepare_klines`. **[COMPLETED]**
    *   Action (1.1.2): Generate `scripts/fetch_historical_data.py` CLI tool. **[DEFERRED/SKIPPED]**
*   1.2. Module: MVP Strategy Logic (`src/strategies/geometric_grid.py`, `src/strategies/profit_taking.py`, `src/analysis/indicators.py`)
    *   Action: `indicators.py`: Implement basic `calculate_atr` etc. (Now using `pandas-ta`). **[COMPLETED]**
    *   Action: `geometric_grid.py`: Implement `plan_buy_grid_v1` function (volatility-adjusted, geo spacing/sizing, confidence scaling, limits, filters). **[COMPLETED & Integrated into main_trader.py]**
    *   Action: `profit_taking.py`: Implement `calculate_dynamic_tp_price` (ATR/confidence modulated, filters). **[COMPLETED & Integrated into main_trader.py]** (Note: Was originally `simple_tp.py` in plan, evolved)
*   1.3. Module: Backtesting Engine (`src/backtester/engine.py`, `notebooks/01_MVP_Backtest.ipynb`) **[DEFERRED/SKIPPED]**
*   1.4. Module: Database Logging (Simulation) **[DEFERRED/SKIPPED]**

**Phase 2: DCA Logic & Semi-Automated Funding (Getting Capital In) 💰➡️ [Structurally Complete, Verification Needed]**
Goal: Define schedule-based DCA logic, set up initial semi-automated low-fee pipeline. *Confidence modulation introduced later.*

*   2.1. Module: DCA Calculation (`src/strategies/dca.py`) **[COMPLETED]**
*   2.2. Module: Funding Pipeline Components (`src/connectors/coinbase.py`, `src/funding_pipeline.py`) **[COMPLETED - Withdrawal needs live test]**
*   2.3. Module: Semi-Automated Pipeline Script (`scripts/run_dca_pipeline.py`) **[COMPLETED]**
*   2.4. Module: Live Engine DCA Trigger (`main_trader.py` placeholder) **[DEFERRED - Requires scheduler integration]**

**Phase 3: Intelligence Layer 1 (Live) - Dynamics, TA, Initial Confidence & Risk Controls 🤖📉▶️ [IN PROGRESS]**
Goal: Enhance live engine with core TA, dynamic rule-based TP (confidence-modulated), S/R (pivot/cluster based), trendlines (scored), initial confidence, **adaptive sizing**, and **basic risk controls (time stops)**. Validate live.

*   3.1. Module: Live Indicator Calculation (`src/analysis/indicators.py`, `main_trader.py`) **[COMPLETED]**
*   3.2. Module: Live Dynamic Profit Targets (`src/strategies/profit_taking.py`, `main_trader.py`) **[COMPLETED & Integrated]**
*   3.3. Module: Live S/R Detection (`src/analysis/support_resistance.py`, `main_trader.py`) **[Partially Complete - Pivot finding & clustering implemented & integrated; Scoring TBD]**
*   3.4. Module: Live S/R Integration (`src/strategies/geometric_grid.py`, `src/strategies/profit_taking.py`) **[DEFERRED]**
*   3.5. Module: Live Confidence Score V1 (`src/analysis/confidence.py`, `main_trader.py`) **[COMPLETED & Integrated]**
*   3.6. Module: Live Dynamic Trendline Detection & Adjustment (`src/analysis/trendlines.py`, `main_trader.py`) **[DEFERRED]**
*   3.7. Module: Live Time-Based Trade Evaluation & Exit (`src/strategies/risk_controls.py`, `main_trader.py`) **[COMPLETED & Integrated]**
*   3.8. Module: Live Execution Script (`main_trader.py`) & Validation **[IN PROGRESS - Simulation framework built, real execution TBD]**

**Phase 4: Intelligence Layer 2 - External Context & Sentiment 📰🤖💬**
Goal: Integrate external data sources (news, social media) using LLMs for sentiment/topic analysis to further refine the Confidence Score and potentially trigger state changes.

*   4.1. Module: News Fetching (`src/data/news_fetcher.py`)
    *   Action: Implement fetching from RSS feeds, news APIs (e.g., NewsAPI - may require key). Store fetched articles/metadata. Handle potential rate limits/costs. Add parsers for relevant crypto news sites.
*   4.2. Module: LLM Analyzer (`src/analysis/llm_analyzer.py`, `config.yaml`)
    *   Action: Define prompts for sentiment analysis, topic extraction (e.g., "Regulation", "Adoption", "Security Breach"), and magnitude scoring based on news headlines/summaries. Use structured output (JSON).
    *   Action: Implement function `analyze_news_item(text)` using a chosen LLM API (e.g., OpenAI, Google AI/Vertex AI). Handle API key management securely.
    *   Action: Add LLM endpoint/model config to `config.yaml`.
*   4.3. Module: Confidence Score V2 (`src/analysis/confidence.py`)
    *   Action: Modify `calculate_confidence` to incorporate weighted scores from LLM analysis (sentiment, topic magnitude). Adjust weights based on backtesting/heuristics.
*   4.4. Module: State Change Triggers (`main_trader.py`)
    *   Action: Implement logic to detect high-magnitude negative news (e.g., major exchange hack, regulatory crackdown) and potentially trigger a "panic sell" or "reduce exposure" state change (e.g., widen grids, lower size multipliers).

**Phase 5: Intelligence Layer 3 - Long-Term Models & Market Cycles 📈📉⏳**
Goal: Incorporate long-term cycle models and on-chain data to provide macro context, influencing strategy parameters and confidence over longer timeframes.

*   5.1. Module: Long-Term Model Data Fetcher (`src/data/long_term_model_fetcher.py`)
    *   Action: Implement fetching/calculating data for models like Power Law Corridor, Bitcoin Rainbow Chart, S2F(X), MVRV Z-Score. Use public APIs (e.g., Glassnode - may require key/paid tier, Blockchain.com) or calculate from historical price data where possible. Cache results.
*   5.2. Module: Assumption Validator (`src/analysis/assumption_validator.py`)
    *   Action: Implement logic to periodically compare current price action against these long-term models. Log deviations or potential invalidations.
*   5.3. Module: Macro Confidence Adjustment (`src/analysis/confidence.py`)
    *   Action: Modify `calculate_confidence` to slightly adjust the score based on position within long-term cycles (e.g., lower confidence near model tops, higher near bottoms). This acts as a macro filter.
*   5.4. Module: Dynamic Parameter Adjustment (`main_trader.py`, `config.yaml`)
    *   Action: Add logic where extreme readings from long-term models (e.g., MVRV Z-Score > 7) could trigger adjustments to strategy parameters (e.g., reduce max grid levels, increase profit target percentages, reduce DCA amounts) stored/accessed via config or state manager.

**Phase 6: Advanced Risk Management & Order Types 🛡️⚙️**
Goal: Implement more sophisticated risk controls and potentially utilize more advanced order types if beneficial and available.

*   6.1. Module: Conditional Exits (`src/strategies/risk_controls.py`, `main_trader.py`)
    *   Action: Implement logic for indicator-based stops (e.g., exit if price closes below a long-term MA AND MACD confirms bearish cross).
    *   Action: Implement volatility-based exits (e.g., exit if ATR spikes beyond an extreme threshold, potentially indicating panic).
*   6.2. Module: Portfolio-Level Risk (`src/analysis/risk_monitor.py`, `main_trader.py`)
    *   Action: Implement tracking of overall portfolio drawdown (requires consistent balance/valuation updates).
    *   Action: Define portfolio-level drawdown thresholds in config.
    *   Action: Implement logic in `main_trader` to trigger emergency actions (e.g., call `scripts/flatten_positions.py`, halt trading) if drawdown threshold breached.
*   6.3. Module: Advanced Order Types (Optional) (`src/connectors/binance_us.py`, strategy modules)
    *   Action: Research and potentially implement Trailing Stop orders or OCO (Order-Cancels-Order) for TP/SL if available and deemed beneficial over current logic. Requires careful integration with state management. (Note: Binance.US API support for advanced types might be limited compared to .com).

**Phase 7: State Management, Persistence & Resilience ��🔄💪**
Goal: Implement robust state persistence, error handling, and recovery mechanisms.

*   7.1. Module: State Manager (`src/state_manager.py`)
    *   Action: Implement `StateManager` class responsible for saving and loading the application state (`position`, `active_grid_orders`, `active_tp_order`, potentially recent indicators/klines needed for recovery) to/from a persistent format (e.g., JSON file, database table).
    *   Action: Integrate `StateManager.save_state()` calls periodically and on graceful shutdown in `main_trader.py`.
    *   Action: Integrate `StateManager.load_state()` call during `_initialize` in `main_trader.py`.
*   7.2. Module: Enhanced Error Handling (`main_trader.py`, connector, other modules)
    *   Action: Review all major functions and implement more specific exception handling (e.g., distinguishing API errors from connection errors from calculation errors).
    *   Action: Implement retry logic with backoff for potentially transient API errors in connector methods.
*   7.3. Module: Order Reconciliation (`main_trader.py`)
    *   Action: Implement robust logic in `_check_orders` (or a dedicated `_reconcile_orders` function) to fetch *all* open orders from the exchange at startup and compare against loaded state to handle discrepancies (e.g., orders filled while bot was offline).

**Phase 8: Optimization, Deployment & Composer Agent 🚀🔧🤖**
Goal: Optimize strategies, prepare for deployment, and create a "Composer Agent" for managing dependencies.

*   8.1. Module: Backtesting Enhancement (`src/backtester/`)
    *   Action: Ensure backtester accurately simulates confidence scores, dynamic TP/sizing, S/R interactions, time stops, and conditional exits. Implement parameter sweep capabilities.
*   8.2. Module: Performance Optimization (`All modules`)
    *   Action: Profile code execution. Optimize critical sections (e.g., indicator calculation, API calls) using techniques like vectorization (Pandas/NumPy), caching, asynchronous operations (if applicable later).
*   8.3. Module: Deployment Setup (`Dockerfile`, `docker-compose.yml`, `scripts/`)
    *   Action: Create `Dockerfile` to containerize the application and its dependencies.
    *   Action: Create `docker-compose.yml` (optional) if needing linked services (e.g., separate DB, monitoring tool).
    *   Action: Write deployment scripts/documentation for running on a server/cloud instance.
*   8.4. Module: Composer Agent (`scripts/optimize_pipeline.py`)
    *   Action: Conceptualize and implement a script (potentially using LLM assistance) that periodically analyzes external factors (market regime shifts identified by LT models, news sentiment trends, academic research feeds, dependency updates/deprecations) and suggests or **(carefully!)** makes updates to configuration, strategy parameters, or even code modules (via git patches or similar). Requires strict sandboxing and approval mechanisms initially.

**Phase 9: Monitoring, Dashboard & Advanced Features 📊🔔✨**
Goal: Implement monitoring, alerting, a user interface, and explore advanced strategy additions.

*   9.1. Module: Monitoring & Alerting (`main_trader.py`, external service)
    *   Action: Integrate with monitoring services (e.g., Healthchecks.io, UptimeRobot) via simple API calls within the main loop to ensure the bot is running.
    *   Action: Implement alerting (e.g., email, Telegram/Discord bot) for critical errors, large fills, or significant state changes.
*   9.2. Module: Dashboard (`src/dashboard/`, `notebooks/03_Live_Monitoring_Dashboard.ipynb`)
    *   Action: Develop a simple dashboard (e.g., using Streamlit, Dash, or a TUI like Textual) to visualize current state (position, PnL, active orders, confidence score, key indicators, logs).
    *   Action: Use the Jupyter notebook for more complex historical analysis plots.
*   9.3. Module: Advanced Strategy Features (Exploratory)
    *   Action: Research/Implement integration of Order Book analysis (`src/analysis/orderbook.py`) into confidence score.
    *   Action: Research/Implement ML models for TP prediction or confidence calibration (`src/ml/`).
    *   Action: Research/Implement multi-asset trading capabilities.

**5. Potential Pitfalls & Mitigation Strategies**

*   **API Rate Limits/Bans:** Excessive API calls. **Mitigation:** Implement rate limiting in connector, use caching (`exchange_info`, klines), employ WebSocket streams for real-time data where appropriate (later phase).
*   **Exchange Downtime/Errors:** API failures during critical operations. **Mitigation:** Robust `try/except` blocks, retry logic with exponential backoff, state persistence to recover gracefully, monitoring/alerting.
*   **Data Quality Issues:** Incorrect kline data, missing data points, inconsistent filter info. **Mitigation:** Data validation steps after fetching, sanity checks on indicator outputs, robust handling of `None`/`NaN` values, periodic refetching of exchange info.
*   **Strategy Failure/Overfitting:** Strategy performs poorly in live market conditions different from backtests. **Mitigation:** Rigorous backtesting across different regimes, walk-forward optimization, focus on robust parameters, incorporate macro context, avoid excessive complexity, use conservative risk management.
*   **Configuration Errors:** Incorrect parameters in `config.yaml` or `.env`. **Mitigation:** Schema validation for config, clear documentation, startup checks for essential parameters.
*   **State Management Failure:** Losing track of positions or orders after restarts. **Mitigation:** Robust state saving/loading mechanism (`StateManager`), reconciliation with exchange state on startup.
*   **Calculation Errors:** Bugs in indicator, strategy, or filter logic, especially with `Decimal`. **Mitigation:** Comprehensive unit tests, careful handling of `Decimal` precision and context, logging intermediate values for debugging.
*   **Connectivity Issues:** Network failures breaking the main loop or API calls. **Mitigation:** Connection check retries, heartbeat monitoring.
*   **Resource Exhaustion:** Memory leaks, excessive CPU usage. **Mitigation:** Code profiling, efficient data handling (e.g., avoid holding excessive klines in memory), appropriate data types.
*   **Security Risks:** Exposure of API keys. **Mitigation:** Load keys from `.env` (added to `.gitignore`), secure server environment, avoid logging sensitive data.

**6. Academic & Scientific Grounding Approach**

*   **Core Principle:** While the primary strategies (DCA, Geometric Grid) are heuristic, their parameters and the decision-making layer will be informed by established quantitative finance concepts.
*   **Adaptive Sizing (Confidence):** Inspired by **Kelly Criterion** principles (fractional Kelly) – position size should be proportional to perceived edge/confidence, adjusted for risk aversion. The Confidence Score serves as a proxy for this edge.
*   **Volatility Adjustment (ATR):** Using ATR for grid spacing and potentially TP targets acknowledges market volatility regimes, a common practice in quantitative strategy design.
*   **Profit Taking & Exits:** Dynamic TP based on volatility/confidence relates to concepts like adaptive exits. Time stops are a recognized alternative risk management technique, particularly in non-stationary markets where price-based stops can be easily triggered by noise. Conditional exits based on indicator regimes align with technical trading system design.
*   **Machine Learning (Future):** Potential use of ML for TP prediction or confidence calibration draws from supervised learning techniques. Feature engineering would rely on TA indicators and potentially market microstructure data. Model validation requires rigorous backtesting and walk-forward analysis to avoid overfitting (reference: Marcos Lopez de Prado's work on financial ML). Concepts like **Meta-Labeling** could be explored to build ML models on top of the primary strategy signals.
*   **External Data (LLMs):** Using LLMs for sentiment/topic analysis mirrors NLP applications in quantitative news analysis, attempting to capture alpha from unstructured data. Requires careful prompt engineering and validation of the LLM's output reliability.
*   **Long-Term Models:** Incorporating cycle models (Power Law, Rainbow, MVRV) grounds short-term decisions within a broader macro context, aiming to filter trades based on long-term market phases (overheated vs. undervalued).
*   **`RESEARCH.md`:** This file will explicitly link specific implementation choices (e.g., confidence calculation factors, time stop logic, S/R algorithm details) to relevant academic papers, articles, or established quantitative trading concepts and provide justifications.

**7. Conclusion**

GeminiTrader aims to be a sophisticated, autonomous trading system built on a hybrid strategy foundation. By combining disciplined accumulation (DCA) with volatility harvesting (Adaptive Geometric Grid) and overlaying an intelligence layer driven by technicals, external context, and long-term models, it seeks robust performance across diverse market conditions. The rejection of conventional stop-losses in favor of a holistic risk management approach (adaptive sizing, time stops, conditional exits) is a core design principle. Development follows a phased, modular approach, emphasizing rigorous testing, simulation, and eventual data-driven optimization. The ultimate goal is a self-sufficient system capable of significant long-term capital appreciation with minimal human intervention, grounded in sound quantitative principles.

------- SESSION HANDOVER APPENDED [2025-04-13 ~04:15 UTC] -------
# GeminiTrader - Handover Document (2025-04-13 ~04:15 UTC)

**Project Goal:** Develop GeminiTrader, an autonomous cryptocurrency trading system aiming for long-term capital growth via a hybrid strategy (DCA, adaptive geometric dip-buying, confidence layer) and robust risk management, emphasizing effective User-LLM collaboration using v6.5 standards.

**Session Focus & Current Status:**
*   Completed all modules of **Phase 0: Setup & Foundational Tools**. This included project structure, Git setup, configuration (YAML/env), core utilities (formatting, logging), database schema (`schema.sql`), and database manager (`manager.py`).
*   Began **Phase 1: MVP - Core Trading Engine & Basic Backtesting**.
*   Implemented **Module 1.1: Market Data Fetching**, specifically **Step 1.1.1: Implement `kline_fetcher.py`**.
*   Successfully created and tested the `fetch_and_prepare_klines` function within `kline_fetcher.py`. Verified it fetches recent data and correctly parses timestamps and numerical values to `Decimal`.
*   **Debugging:** Investigated why initial tests failed to fetch historical `BTCUSD` data for a specific 2024 window. Confirmed via testing `BTCUSDT` that the fetcher code is likely correct and the issue stems from data availability for the `BTCUSD` pair on Binance.US during that specific timeframe.
*   **Current Status:** Stopped development after successfully implementing and testing `src/data/kline_fetcher.py`.

**Key Files/Modules Implemented or Modified (Session):**
*   - .gitignore (updated)
*   - config/config.yaml (created)
*   - config/settings.py (created)
*   - .env (created/populated by user)
*   - src/connectors/binance_us.py (created/modified)
*   - src/utils/formatting.py (created)
*   - src/utils/logging_setup.py (created)
*   - src/db/schema.sql (created)
*   - src/db/manager.py (created/corrected test imports)
*   - src/data/kline_fetcher.py (created)
*   - scripts/context_manager.py (created/refined based on discussion)

**Authoritative Roadmap Reference:**
The authoritative project plan is Document Version 6.5 (Rolling SSoT Prompt Block). The current focus of implementation is Phase [1], Module [1.1]. Development stopped after completing Step 1.1.1.

**Key Learnings, Decisions & Conventions Established (Session):**
*   Established the Git backup strategy (`pre-v6.5-refactor` branch).
*   Adopted the v6.5 project directory structure.
*   Implemented the `context_manager.py` script (CMD version) for handover context generation and optional Git commits.
*   Confirmed `pyperclip` automatic clipboard copy does not work reliably in the user's DevContainer setup; the workaround is manual copy from the context log file. (Note: User uses Ctrl+D in Ubuntu DevContainer on Windows).
*   Confirmed `python -m <module.path>` is necessary for running module tests directly from the project root to resolve import path issues.
*   Identified potential data availability differences between `BTCUSD` and `BTCUSDT` for specific historical periods on Binance.US.
*   **User Directive:** Always provide complete code blocks. This is mandatory. No ellipses, omissions, or shorthand references. This directive was re-emphasized multiple times.

**User Directives (Session):**
*   Requested step-by-step Git guidance.
*   Proposed and iterated on the `context_manager.py` utility concept (settling on CMD version).
*   **Repeatedly requested COMPLETE code generation without omissions.**
*   Requested a 15-minute time limit reminder near the end of the session.
*   Requested that Handover docs contain only raw Markdown.
*   Requested that this rolling SSoT prompt block be generated.

**Actionable Next Steps:**
*   Implement **Phase 1, Step 1.1.2: `scripts/fetch_historical_data.py`** CLI tool. This script should utilize the `fetch_and_prepare_klines` function from `src/data/kline_fetcher.py` to allow downloading and saving historical data (e.g., to CSV or database cache) via command-line arguments (symbol, interval, start, end, output path).

------- SESSION HANDOVER APPENDED [2025-04-14 ~04:15 UTC] -------
# GeminiTrader - Handover Document (2025-04-14 ~04:15 UTC)

**Project Goal:** Develop GeminiTrader, an autonomous cryptocurrency trading system aiming for long-term capital growth via a hybrid strategy (DCA, adaptive geometric dip-buying, confidence layer) and robust risk management, using the v6.5 development plan and focusing on User-LLM collaboration best practices.

**Session Focus & Current Status:**
*   Focused on implementing **Phase 2: DCA Logic & Semi-Automated Funding**.
*   Implemented **Module 2.1: DCA Calculation** (`src/strategies/dca.py` - `calculate_dca_amount_v1`). Tested successfully.
*   Began **Module 2.2: Funding Pipeline Components**.
    *   Encountered significant challenges integrating with Coinbase due to API key/library mismatches.
    *   **Debugging Journey:** Resolved issues moving from `coinbase` to `coinbase-advanced-py`, including CDP key usage, venv activation, library method calls (`RESTClient`, `market_order_buy`, etc.), product ID formatting, and insufficient fund errors.
    *   Implemented `src/connectors/coinbase.py` using `coinbase-advanced-py`. Connection, balance checks, and market buy are functional. **Withdrawal (`withdraw_crypto`) uses direct V2 API call via `client.post` and requires further verification.**
    *   Implemented `src/funding_pipeline.py` structure using state machine logic, adapted for intermediate asset (XLM) transfer.
*   Implemented **Module 2.3: Semi-Automated Pipeline Script** (`scripts/run_dca_pipeline.py`). Tested flow up to withdrawal confirmation. Handles insufficient funds checks.
*   **Current Status:** Phase 2 structurally complete, pending withdrawal verification.

**Key Files/Modules Implemented or Modified (Session):**
*   - src/strategies/dca.py (Created & Tested)
*   - requirements.txt (Added `coinbase-advanced-py`, `tabulate`; Removed `coinbase`)
*   - src/connectors/coinbase.py (Created & Refactored multiple times for `coinbase-advanced-py`)
*   - src/funding_pipeline.py (Created & Refactored for intermediate asset)
*   - scripts/run_dca_pipeline.py (Created & Refined)
*   - config/config.yaml (Updated `funding_pipeline` section)
*   - .env (User updated with real Coinbase CDP Key Name & Private Key)
*   - src/db/manager.py (Corrected schema parsing)
*   - src/db/schema.sql (Verified `backtest_id` column)

**Authoritative Roadmap Reference:**
The authoritative project plan is Document Version 6.5 (Rolling SSoT Prompt Block with previous handover appended). The current focus of implementation is **Phase 2**, specifically completing Modules 2.1, 2.2, and 2.3.

**Key Learnings, Decisions & Conventions Established (Session):**
*   **Library Choice:** Confirmed necessity of official `coinbase-advanced-py` with CDP API Keys (Name + Private Key).
*   **Authentication:** `RESTClient` handles auth.
*   **Virtual Environments:** Confirmed necessity and correct procedure for `.venv` *inside* DevContainer.
*   **API Method Usage:** Determined correct methods for `coinbase-advanced-py`.
*   **V2 API Calls:** Confirmed `client.post()` can be used for V2 endpoints (like sends/withdrawals).
*   **Withdrawal Implementation:** Implemented using direct V2 API call; **needs live testing.**
*   **Funding Strategy:** Pivoted to using configurable low-fee intermediate asset (XLM) for transfers.
*   **Semi-Auto Script Logic:** Enhanced to check existing intermediate asset and available USD balances.
*   **Configuration:** Deposit addresses/intermediate asset in `config.yaml`, Private Keys in `.env`.

**User Directives (Session):**
*   Requested full code replacements.
*   Prioritize fixing blocking issues.
*   Use `pip freeze > requirements.txt`.
*   Add start/end markers to notebook cells.
*   Add note to re-test funding pipeline.
*   Pushed for verification of Coinbase library/withdrawal.

**Actionable Next Steps:**
1.  **(Verification Task):** Live test `scripts/run_dca_pipeline.py` focusing on `withdraw_crypto` step (requires funding Coinbase).
2.  Proceed to **Phase 3: Intelligence Layer 1 (Live)**, starting with **Module 3.1: Live Indicator Calculation**. Add functions for SMA, RSI, MACD, and Pivot Points to `src/analysis/indicators.py`.

------- SESSION HANDOVER APPENDED [2025-04-14 ~18:40 UTC] -------
# GeminiTrader - Handover Document (2025-04-14 ~18:40 UTC)

**Project Goal:** Develop GeminiTrader, an autonomous cryptocurrency trading system aiming for long-term capital growth via a hybrid strategy (DCA, adaptive geometric dip-buying, confidence layer) and robust risk management, using the v6.5 development plan and focusing on User-LLM collaboration best practices.

**Session Focus & Current Status:**
*   Focused primarily on **Phase 3** analysis components and integrating **Phase 1.2** (Grid Planning).
*   Implemented **Module 3.1 (Indicators):** Implemented `indicators.py` using `pandas-ta` for ATR, SMA, RSI, MACD; kept manual daily pivots. Resolved `pandas-ta` integration issues (`AttributeError`, `TypeError`). Integrated into `main_trader.py`.
*   Implemented **Module 3.2 (Dynamic TP):** Implemented `profit_taking.py` (`calculate_dynamic_tp_price`), including config methods (ATR, %, fixed), confidence modulation (using placeholder score), and **exchange filter integration** using new `formatting.py` functions. Integrated call into `main_trader.py`.
*   Implemented **Module 3.3 (S/R Zones - Partial):** Implemented `support_resistance.py` with `find_rolling_pivots` and `cluster_pivots_to_zones`. Integrated `calculate_dynamic_zones` call into `main_trader.py` (scoring TBD).
*   Implemented **Module 3.5 (Confidence):** Implemented `confidence.py` (`calculate_confidence_v1`) using basic rules (RSI, MACD, SMA trend). Integrated into `main_trader.py` and linked to TP calculation (via feature flag).
*   Implemented **Module 3.7 (Time Stops):** Implemented `risk_controls.py` (`check_time_stop`) based on duration and PnL threshold. Integrated into `main_trader.py`.
*   Implemented **Module 1.2 (Grid Planning):** Implemented `geometric_grid.py` (`plan_buy_grid_v1`) with volatility/geometric spacing/sizing, confidence scaling, limits, and filter checks. Integrated into `main_trader.py`.
*   Implemented **Exchange Filters (`formatting.py`):** Implemented core logic for Price, Lot Size, Min Notional filters and public wrapper functions (`apply_filter_rules_to_price`, `apply_filter_rules_to_qty`, `validate_order_filters`).
*   Implemented **Connector (`binance_us.py`):** Added exchange info caching (`get_exchange_info`, `get_exchange_info_cached`). Added order management methods (`create_limit_buy/sell`, `create_market_sell`, `cancel_order`, `get_order_status`, `get_open_orders`), ensuring filter usage.
*   Implemented **Main Trader (`main_trader.py`):** Heavily refactored to integrate all above modules. Implemented a **full simulation framework** (controlled by `SIMULATION_MODE` flag) including:
    *   State tracking for position, active orders (grid, TP).
    *   Balance fetching and checking (with simulation hack).
    *   Calling planning functions (`plan_buy_grid_v1`).
    *   **Simulating** order placement/cancellation (`_reconcile_and_place_grid`, `_place_or_update_tp_order`, `_execute_market_sell`).
    *   **Simulating** order status checks and fills (`_check_orders`), updating position state accordingly.
*   **Debugging:** Resolved various `pandas-ta` integration issues, `NameError` (missing imports), `pandas` DataFrame truthiness `ValueError`. Identified insufficient real USD balance preventing grid planning and implemented temporary simulation hacks (balance injection, lowered confidence threshold) to test the full loop. Fixed a minor bug in TP update simulation logic. Resolved `ImportError` and `NameError` related to filter function usage between `profit_taking.py`, `formatting.py`, and `main_trader.py`.
*   **Current Status:** The application (`main_trader.py`) successfully runs a **complete simulation loop**. It fetches live data, performs all calculations, simulates placing/managing grid & TP orders, and simulates position entry/exit based on fills or time stops. **Real API calls for order placement/cancellation/status are commented out.** The foundation for live execution is built but requires careful uncommenting and robust reconciliation logic.

**Key Files/Modules Implemented or Modified (Session):**
*   - src/analysis/indicators.py (Refactored for pandas-ta, fixed bugs)
*   - src/strategies/profit_taking.py (Created, integrated filters)
*   - src/analysis/support_resistance.py (Created, implemented pivot finding & clustering)
*   - src/analysis/confidence.py (Created V1 logic)
*   - src/strategies/risk_controls.py (Created time stop logic)
*   - src/strategies/geometric_grid.py (Created grid planning logic)
*   - src/utils/formatting.py (Added filter functions, helpers, corrected imports)
*   - src/connectors/binance_us.py (Added order methods, caching)
*   - src/main_trader.py (Major integration of all modules, simulation framework, fixed bugs)
*   - config/config.yaml (Added sections for trading params, profit taking, risk controls)
*   - requirements.txt (Added pandas-ta, schedule)

**Authoritative Roadmap Reference:**
The authoritative project plan is locally managed `SSOT.md` (based on v6.5). Development integrated modules from Phase 1 (1.2) and Phase 3 (3.1, 3.2, 3.3 partial, 3.5, 3.7).

**Key Learnings, Decisions & Conventions Established (Session):**
*   **Filter Logic:** Implemented and verified crucial exchange filter handling.
*   **Simulation Framework:** Built a comprehensive simulation mode within `main_trader.py` (controlled by `SIMULATION_MODE` flag and temporary hacks) to test state transitions and logic flow before enabling live API calls.
*   **Iterative Development:** Successfully integrated multiple analysis and strategy components (Indicators, S/R, Confidence, TP, Grid Planning, Time Stops) into the main application loop.
*   **Debugging:** Systematically identified and resolved various errors related to library usage (`pandas-ta`), imports (`NameError`), and framework logic (`ValueError`, DataFrame truthiness).
*   **USD vs USDT:** Confirmed bot operates based on configured `quote_asset` (currently USD) and requires the corresponding balance. User swapped USDT->USD to provide working capital.
*   **SSoT Management:** **Shifted SSoT management strategy.** User will maintain the master `SSOT.md` locally. LLM will only generate the *current session's* handover markdown. User will use a local utility to append handover to `SSOT.md` and generate the context file for the next LLM session. This guarantees SSoT completeness.
*   **(Meta) User Preferences (Reinforced):**
    *   User requires **full code blocks**. Omissions/placeholders within code logic are unacceptable.
    *   User requires **single-line Git commands** for staging, commit, and push.
    *   User values **iterative testing** after each significant code change.
    *   User wants **interaction patterns/directives emphasized** in handovers.
    *   LLM must **proactively request context files** when needed for accurate implementation.

**User Directives (Session):**
*   Consistently requested full code blocks.
*   Requested single-line Git command.
*   Requested summary emphasizing interaction patterns for handover.
*   Clarified USD vs USDT balance.
*   Approved simulation framework approach.
*   Approved iterative integration of S/R logic.
*   **Crucially, directed change in SSoT management to local file + utility script.**

**Actionable Next Steps:**
1.  **(Local SSoT Setup):** User to save this full text block as `SSOT.md` in the project root.
2.  **(Utility Enhancement):** Enhance `scripts/context_manager.py` to support appending a handover file to `SSOT.md` and outputting a combined `context_for_llm.txt`.
3.  **(Simulation Refinement):** Implement **robust order reconciliation logic** in `_reconcile_and_place_grid` (fetch open orders - simulated first, compare intelligently).
4.  **(Simulation Refinement):** Implement **realistic order status checking simulation** in `_check_orders` (beyond simple random chance).
5.  **(Refinement):** Implement S/R zone scoring (`score_zones` function in `src/analysis/support_resistance.py`).
6.  **(Refinement):** Implement more sophisticated entry conditions in `_plan_grid_buys` and remove temporary hacks.
7.  **(Towards Live):** Begin carefully uncommenting API calls, starting with read-only checks (`get_order_status`, `get_open_orders`) within simulation mode.
8.  **(Towards Live):** Implement state persistence (Phase 7 `StateManager`).

*(Recommendation: Focus on Step 2 (Utility) then Step 3 & 4 (Simulation Refinement) next).*

------- END OF ROLLING SSOT PROMPT BLOCK -------
```


------- SESSION HANDOVER APPENDED [2025-04-14 ~21:23 UTC] -------
# GeminiTrader - Handover Document (2025-04-14 ~21:25 UTC)

**Project Goal:** Develop GeminiTrader, an autonomous cryptocurrency trading system aiming for long-term capital growth via a hybrid strategy (DCA, adaptive geometric dip-buying, confidence layer) and robust risk management, using the v6.5 development plan and the local SSoT management workflow.

**Session Focus & Current Status:**
*   Focused on implementing **Actionable Next Step 2** from the previous handover (dated 2025-04-14 ~18:40 UTC): Enhancing the `scripts/context_manager.py` utility.
*   Successfully updated `context_manager.py` to support the new **local SSoT management workflow**.
*   Added command-line arguments (`--update-ssot`, `--handover-file`, `--ssot-file`, `--output-context-file`) and logic to:
    *   Read a user-saved handover markdown file.
    *   Append its content to the main `SSOT.md` file.
    *   Generate the full `context_for_llm.txt` file containing the entire updated `SSOT.md`.
    *   Optionally copy the full context to the clipboard.
    *   Generate a specific commit message (`chore(SSoT): ...`) when run in this mode.
*   Clarified the purpose and origin of the `handover_latest.md` file (user saves LLM output before running the script).
*   Tested the script's error handling for the case where the handover file doesn't exist.
*   **Current Status:** The `context_manager.py` script is updated and ready to process the handover file you are about to create using this text block.

**Key Files/Modules Implemented or Modified (Session):**
*   - scripts/context_manager.py

**Authoritative Roadmap Reference:**
The authoritative project plan is locally managed `SSOT.md` (based on v6.5). This session completed the utility enhancement step (Step 2 from the previous handover's "Actionable Next Steps") designed to support the local SSoT workflow itself.

**Key Learnings, Decisions & Conventions Established (Session):**
*   Solidified the new SSoT management workflow: LLM generates handover -> User saves to file (e.g., `handover_latest.md`) -> User runs `context_manager.py --update-ssot` -> Script appends to `SSOT.md` and generates `context_for_llm.txt`.
*   Implemented the `--update-ssot` workflow within `context_manager.py`.
*   Confirmed the script handles the missing handover file scenario correctly.

**User Directives (Session):**
*   Requested clarification on the `handover_latest.md` file.
*   Requested to proceed with generating this handover and testing the full script workflow.

**Actionable Next Steps:**
1.  **(User Action):** Save *this* Markdown block to a file named `handover_latest.md` in the project root directory.
2.  **(User Action):** Run the context manager script to process the handover file, update the SSoT, and generate the next context file. Recommended command: `python scripts/context_manager.py --update-ssot --handover-file handover_latest.md --commit` (add `--push` if desired).
3.  **(Development):** Proceed to the next development task outlined in the *previous* handover (2025-04-14 ~18:40 UTC), which was **Step 3: (Simulation Refinement)** Implement robust order reconciliation logic in `_reconcile_and_place_grid` within the `src/main_trader.py` file. (This involves fetching open orders - simulated first - and comparing intelligently against the bot's internal state).

------- SESSION HANDOVER APPENDED [2025-04-14 ~22:06 UTC] -------
# GeminiTrader - Handover Document (2025-04-14 ~21:25 UTC)

**Project Goal:** Develop GeminiTrader, an autonomous cryptocurrency trading system aiming for long-term capital growth via a hybrid strategy (DCA, adaptive geometric dip-buying, confidence layer) and robust risk management, using the v6.5 development plan and the local SSoT management workflow.

**Session Focus & Current Status:**
*   Focused on implementing **Actionable Next Step 2** from the previous handover (dated 2025-04-14 ~18:40 UTC): Enhancing the `scripts/context_manager.py` utility.
*   Successfully updated `context_manager.py` to support the new **local SSoT management workflow**.
*   Added command-line arguments (`--update-ssot`, `--handover-file`, `--ssot-file`, `--output-context-file`) and logic to:
    *   Read a user-saved handover markdown file.
    *   Append its content to the main `SSOT.md` file.
    *   Generate the full `context_for_llm.txt` file containing the entire updated `SSOT.md`.
    *   Optionally copy the full context to the clipboard.
    *   Generate a specific commit message (`chore(SSoT): ...`) when run in this mode.
*   Clarified the purpose and origin of the `handover_latest.md` file (user saves LLM output before running the script).
*   Tested the script's error handling for the case where the handover file doesn't exist.
*   **Current Status:** The `context_manager.py` script is updated and ready to process the handover file you are about to create using this text block.

**Key Files/Modules Implemented or Modified (Session):**
*   - scripts/context_manager.py

**Authoritative Roadmap Reference:**
The authoritative project plan is locally managed `SSOT.md` (based on v6.5). This session completed the utility enhancement step (Step 2 from the previous handover's "Actionable Next Steps") designed to support the local SSoT workflow itself.

**Key Learnings, Decisions & Conventions Established (Session):**
*   Solidified the new SSoT management workflow: LLM generates handover -> User saves to file (e.g., `handover_latest.md`) -> User runs `context_manager.py --update-ssot` -> Script appends to `SSOT.md` and generates `context_for_llm.txt`.
*   Implemented the `--update-ssot` workflow within `context_manager.py`.
*   Confirmed the script handles the missing handover file scenario correctly.

**User Directives (Session):**
*   Requested clarification on the `handover_latest.md` file.
*   Requested to proceed with generating this handover and testing the full script workflow.

**Actionable Next Steps:**
1.  **(User Action):** Save *this* Markdown block to a file named `handover_latest.md` in the project root directory.
2.  **(User Action):** Run the context manager script to process the handover file, update the SSoT, and generate the next context file. Recommended command: `python scripts/context_manager.py --update-ssot --handover-file handover_latest.md --commit` (add `--push` if desired).
3.  **(Development):** Proceed to the next development task outlined in the *previous* handover (2025-04-14 ~18:40 UTC), which was **Step 3: (Simulation Refinement)** Implement robust order reconciliation logic in `_reconcile_and_place_grid` within the `src/main_trader.py` file. (This involves fetching open orders - simulated first - and comparing intelligently against the bot's internal state).

------- SESSION HANDOVER APPENDED [2025-04-15 ~04:07 UTC] -------
# GeminiTrader - Handover Document (2025-04-15 ~04:00 UTC)

**Project Goal:** Develop GeminiTrader, an autonomous cryptocurrency trading system aiming for long-term capital growth via a hybrid strategy (DCA, adaptive geometric dip-buying, confidence layer) and robust risk management, using the v6.5 development plan and the local SSoT management workflow.

**Session Focus & Current Status:**
*   **Focus:** This session primarily focused on debugging, refining the simulation framework, implementing state persistence, refactoring core logic, and improving the development workflow/output.
*   **Key Activities & Status:**
    *   **Simulation Data:** Created a script (`scripts/download_sim_data.py`) to fetch historical data; identified `BTCUSD` data scarcity and switched to `BTCUSDT`; downloaded Q1 2024 data for `BTCUSDT` to `data/simulation/`.
    *   **Simulation Integration:** Modified `main_trader.py` (`_initialize`, `_update_market_data`, `run`) to load and step through the CSV simulation data when `SIMULATION_MODE = True`.
    *   **Debugging:** Resolved multiple errors encountered during simulation runs:
        *   `TypeError` in `_update_pivot_points` (incorrect arguments to `fetch_and_prepare_klines`).
        *   `AttributeError: 'numpy.ndarray' object has no attribute 'idxmax'` in `find_rolling_pivots` (fixed rolling apply logic).
        *   `ValueError: The truth value of a Series is ambiguous...` in `_calculate_indicators` (fixed MACD column retrieval logic).
        *   `NameError: name 'indices_set' is not defined` in `OrderManager.check_orders` (fixed variable scope issue after refactoring).
        *   `NameError: name 'Dict' is not defined` in `StateManager` (added typing import).
    *   **Refactoring (`OrderManager`):** Successfully created `src/core/order_manager.py` and moved order checking, reconciliation, placement, and market sell logic from `main_trader.py` into the new `OrderManager` class. `main_trader.py` now delegates these tasks.
    *   **State Persistence (`StateManager`):** Implemented `src/core/state_manager.py` with `save_state` and `load_state` methods using JSON. Added helper functions to handle `Decimal` and `Timestamp` conversion. Integrated state loading into `_initialize` and state saving periodically and on exit in `main_trader.py`. Confirmed persistence works across restarts during simulation.
    *   **S/R Zone Scoring:** Implemented basic scoring logic (`score_zones` v1) in `src/analysis/support_resistance.py`, calculating touches and determining type (support/resistance/range), removing the "not implemented" warning. Added recency and composite scores.
    *   **Entry Conditions:** Refined entry logic in `_plan_grid_buys` to use configurable thresholds (`entry_confidence_threshold`, `entry_rsi_threshold`) and added trend (SMA cross) and RSI filters. Removed the balance injection hack/warning.
    *   **Logging/Output:** Refined logging levels (moving many INFO to DEBUG), implemented `tqdm` progress bar with status postfix for simulations, added a dedicated `errors.log` file handler, and configured console level via `config.yaml` for cleaner output.
*   **Current Status:** The simulation runs successfully end-to-end using CSV data, state persists across restarts, confidence score is calculated correctly, entry conditions are applied, S/R zones are scored (v1), order logic is handled by `OrderManager`, and console output is clean via `tqdm`. The system is stable in simulation mode. We completed refactoring (Step 9), state management (Step 8), S/R scoring (Step 5), and entry condition refinement (Step 6).

**Key Files/Modules Implemented or Modified (Session):**
*   - src/main_trader.py (Major changes: Refactoring delegation, State integration, Sim data loading, Entry logic, tqdm, Logging calls)
*   - src/core/order_manager.py (Created: Moved order logic, Integrated state/config, Added counters)
*   - src/core/state_manager.py (Created: Save/Load logic, Type helpers, Atomic saves)
*   - src/analysis/support_resistance.py (Fixed pivot bug, Implemented score_zones v1)
*   - src/analysis/confidence.py (Fixed key issues, Adjusted logging)
*   - src/utils/logging_setup.py (Added error handler, console level param, color formatter, root level adjustment)
*   - config/config.yaml (Added state_manager section, trading entry params, updated logging section)
*   - requirements.txt (Added scikit-learn, tqdm)
*   - scripts/download_sim_data.py (Created)
*   - data/simulation/BTCUSDT_1h_2024-01-01_2024-03-31.csv (Created via script by user)

**Authoritative Roadmap Reference:**
The authoritative project plan is locally managed `SSOT.md` (based on v6.5). This session completed Steps 5, 6, 8, 9, and simulation framework refinements related to Steps 3 & 4.

**Key Learnings, Decisions & Conventions Established (Session):**
*   Confirmed refactoring `main_trader.py` significantly improves clarity and organization.
*   Established CSV-based simulation as the method for deterministic testing.
*   Switched primary trading pair to `BTCUSDT` due to data availability.
*   Adopted `tqdm` for cleaner simulation progress display on the console.
*   Implemented separate error logging for focused issue tracking.
*   Successfully debugged multiple integration issues across different modules.
*   Confirmed state persistence mechanism works as intended for simulation resumption.
*   **User Directives Review & Meta-Instructions:**
    *   **Full Code:** The directive for providing full code blocks remains critical and was reinforced. I will continue to strive for 100% adherence.
    *   **Handover Content:** User prefers explicit next steps, references to specific files/functions, and inclusion of meta-instructions/learnings like these in the handover.
    *   **Clarity > Brevity:** Clear, step-by-step instructions and explanations are preferred, even if slightly longer.
    *   **Proactive Guidance:** User values proactive suggestions for improvement (like refactoring, logging changes) aligned with project goals.

**User Directives (Session):**
*   Requested help creating simulation data CSV.
*   Requested fixes for noisy console output and implementation of `tqdm`.
*   Consistently **required full code blocks** for all file modifications.
*   Asked clarifying questions about state persistence and simulation restart behavior.
*   Approved refactoring approach (`OrderManager`) before S/R integration.
*   Approved implementing S/R scoring v1.
*   Approved implementing enhanced entry conditions (config thresholds, trend/RSI filters).
*   Requested session end and handover generation with Git command.

**Actionable Next Steps:**

1.  **(User Action):** Save this **entire Markdown block** to the file `handover_latest.md` in your project root directory.
2.  **(User Action):** Open your terminal in the project root, ensure your virtual environment is active, stage your changes, and commit using a message generated by the context manager. Then run the context manager script:
    ```bash
    # Stage ALL changes (including new core dir, scripts, data dir if needed, config, requirements etc.)
    git add .
    # Commit using a standard message for end-of-session SSoT update
    git commit -m "chore(SSoT): Update SSoT with handover [2025-04-15 ~04:00 UTC]"
    # Run the context manager to append handover and generate next context file
    python scripts/context_manager.py --update-ssot --handover-file handover_latest.md
    # (Optional: git push)
    ```
3.  **(User Action - Next Session):** Copy the *entire content* of the generated `context_for_llm.md` file and paste it as the first message in our next session.
4.  **(Development - Next Session):** Proceed with **Step 7: Uncomment Read-Only API Calls**.
    *   **File:** `src/core/order_manager.py`
    *   **Action:** Uncomment the `self.connector.get_order_status(...)` calls within the `else:` block of the `check_orders` method.
    *   **Action:** Uncomment the `fetched_orders = self.connector.get_open_orders(symbol)` line within the `else:` block of the `reconcile_and_place_grid` method.
    *   **Goal:** Run `python src/main_trader.py` (with `SIMULATION_MODE = True`) and verify in the logs (`trader.log`, `errors.log`) that the bot successfully connects to the Binance.US API, makes these read-only calls, and handles the responses (including potential errors for simulated order IDs) without crashing. The simulation's internal logic for fills/placements will still drive the state changes.

------- SESSION HANDOVER APPENDED [2025-04-15 ~04:09 UTC] -------
# GeminiTrader - Handover Document (2025-04-15 ~04:15 UTC)

**Project Goal:** Develop GeminiTrader, an autonomous cryptocurrency trading system aiming for long-term capital growth via a hybrid strategy (DCA, adaptive geometric dip-buying, confidence layer) and robust risk management, using the v6.5 development plan and the local SSoT management workflow.

**Session Focus & Current Status:**
*   **Focus:** This session primarily focused on debugging, refining the simulation framework, implementing state persistence, refactoring core logic, and improving the development workflow/output.
*   **Key Activities & Status:**
    *   **Simulation Data:** Created `scripts/download_sim_data.py`; identified `BTCUSD` data scarcity, switched to `BTCUSDT`; downloaded Q1 2024 data.
    *   **Simulation Integration:** Modified `main_trader.py` to load and step through CSV simulation data.
    *   **Debugging:** Resolved `TypeError` (pivot fetch), `AttributeError` (rolling pivots), `ValueError` (Series truthiness in indicator calc), `NameError` (OrderManager state update), `NameError` (StateManager typing import). Fixed simulation not terminating cleanly (`sys.exit`).
    *   **Refactoring (`OrderManager`):** Successfully created `src/core/order_manager.py` and moved order logic from `main_trader.py`.
    *   **State Persistence (`StateManager`):** Implemented `src/core/state_manager.py` (JSON save/load, type helpers, atomic saves). Integrated into `main_trader.py`. Confirmed persistence works across restarts.
    *   **S/R Zone Scoring:** Implemented basic scoring (`score_zones` v1) in `src/analysis/support_resistance.py` (touches, type, recency, composite).
    *   **Entry Conditions:** Refined `_plan_grid_buys` using configurable thresholds (confidence, RSI) and added trend filter (SMA cross). Removed balance hack warning.
    *   **Logging/Output:** Refined logging levels (more DEBUG), implemented `tqdm` progress bar with status postfix, added dedicated `errors.log` file, configured console level via `config.yaml`.
*   **Current Status:** The simulation runs successfully using CSV data, state persists, confidence score calculates, entry conditions are applied, S/R zones are scored (v1), order logic is handled by `OrderManager`, console output is clean via `tqdm`, and error logging is separate. The system is stable in simulation mode. Completed refactoring (Step 9), state management (Step 8), S/R scoring (Step 5), and entry condition refinement (Step 6).

**Key Files/Modules Implemented or Modified (Session):**
*   - src/main_trader.py (Major changes)
*   - src/core/order_manager.py (Created)
*   - src/core/state_manager.py (Created)
*   - src/analysis/support_resistance.py (Fixed pivot bug, Implemented score_zones v1, Fixed FutureWarning initialization)
*   - src/analysis/confidence.py (Fixed key issues, Adjusted logging)
*   - src/utils/logging_setup.py (Added error handler, console level param, color formatter, root level adjustment)
*   - config/config.yaml (Added state_manager, trading entry params, updated logging section, updated symbol/quote asset)
*   - requirements.txt (Added scikit-learn, tqdm)
*   - scripts/download_sim_data.py (Created)
*   - data/simulation/BTCUSDT_1h_2024-01-01_2024-03-31.csv (Created via script by user)

**Authoritative Roadmap Reference:**
The authoritative project plan is locally managed `SSOT.md` (based on v6.5). This session completed Steps 5, 6, 8, 9, and simulation framework refinements related to Steps 3 & 4.

**Key Learnings, Decisions & Conventions Established (Session):**
*   Confirmed refactoring `main_trader.py` improves clarity.
*   Established CSV-based simulation for deterministic testing.
*   Switched primary pair to `BTCUSDT`.
*   Adopted `tqdm` for cleaner simulation console output.
*   Implemented separate error logging.
*   Successfully debugged multiple integration issues (TypeError, AttributeError, ValueError, NameError).
*   Confirmed state persistence works for simulation resumption/completion recognition.
*   Confirmed log rotation (`trader.log.1`, etc.) is working as expected.
*   **User Directives Review & Meta-Instructions:**
    *   **Full Code:** The directive for providing full code blocks remains critical and was reinforced. I need to maintain 100% adherence. *Self-correction: Need to avoid providing only code snippets.*
    *   **Handover Content:** User prefers explicit next steps, references to specific files/functions, and inclusion of meta-instructions/learnings like these.
    *   **Clarity & Proactive Guidance:** User values clear explanations and proactive suggestions.
    *   **Git Commit Command:** **User explicitly requested that the handover document *always* include the version of the `context_manager.py` command that includes the `--commit` flag in the next steps section.**

**User Directives (Session):**
*   Consistently **required full code blocks** for all file modifications.
*   Requested help creating simulation data CSV.
*   Requested fixes for noisy console output and implementation of `tqdm`.
*   Asked clarifying questions about state persistence and simulation restart behavior.
*   Approved refactoring approach (`OrderManager`).
*   Approved implementing S/R scoring v1.
*   Approved implementing enhanced entry conditions.
*   Requested session end and handover generation with **specific inclusion of the commit command**.

**Actionable Next Steps:**

1.  **(User Action):** Save this **entire Markdown block** to the file `handover_latest.md` in the project root directory, overwriting the previous version.
2.  **(User Action):** Open your terminal in the project root, ensure your virtual environment is active, stage your changes (e.g., `git add .`), and then run the context manager script **using the commit option** to update the SSoT and commit changes simultaneously:
    ```bash
    python scripts/context_manager.py --update-ssot --handover-file handover_latest.md --commit
    ```
    *(Optional: If you prefer not to commit automatically, you can omit the `--commit` flag and commit manually afterwards.)*
3.  **(User Action - Next Session):** Copy the *entire content* of the generated `context_for_llm.md` file and paste it as the first message in our next session.
4.  **(Development - Next Session):** Proceed with **Step 7: Uncomment Read-Only API Calls**.
    *   **File:** `src/core/order_manager.py`
    *   **Action:** Uncomment the `self.connector.get_order_status(...)` calls within the `else:` block of the `check_orders` method.
    *   **Action:** Uncomment the `fetched_orders = self.connector.get_open_orders(symbol)` line within the `else:` block of the `reconcile_and_place_grid` method.
    *   **Goal:** Run `python src/main_trader.py` (with `SIMULATION_MODE = True`) and verify in the logs (`trader.log`, `errors.log`) that the bot successfully connects to the Binance.US API, makes these read-only calls, and handles the responses without crashing.

------- SESSION HANDOVER APPENDED [2025-04-16 ~03:26 UTC] -------
# GeminiTrader - Handover Document (2025-04-16 ~03:30 UTC)

**Project Goal:** Develop GeminiTrader, an autonomous cryptocurrency trading system using the v6.5 development plan and local SSoT management workflow. Focus on resolving integration and runtime errors.

**Session Focus & Current Status:**
*   Continued debugging the main trading loop (`src/main_trader.py`) after attempting merges of different code versions.
*   Encountered significant challenges with LLM providing truncated or incomplete code blocks, hindering direct replacement and requiring difficult manual integration attempts.
*   Successfully identified and understood the root cause of the `TypeError: '<=' not supported between instances of 'str' and 'int'` related to `position_size` type handling. Attempted fix by ensuring `to_decimal` conversions.
*   Successfully identified subsequent `TypeError` exceptions in function calls within `_apply_risk_controls` (calling `check_time_stop`) and `_plan_trades` (calling `calculate_dynamic_tp_price`). Determined these were due to mismatched keyword arguments being passed from `main_trader.py` compared to the function definitions in `src/strategies/risk_controls.py` and `src/strategies/profit_taking.py`.
*   **Current Status:** The simulation runs but consistently fails with the `TypeError` exceptions related to the incorrect arguments passed to `check_time_stop` and `calculate_dynamic_tp_price`. The immediate next step is to correct these function calls within `src/main_trader.py`.

**Key Files/Modules Implemented or Modified (Session):**
*   - src/main_trader.py (Multiple attempts to correct errors, latest version still contains TypeErrors)
*   - src/core/order_manager.py (Previous fix applied)
*   - src/strategies/risk_controls.py (Reviewed for function signature)
*   - src/strategies/profit_taking.py (Reviewed for function signature)

**Authoritative Roadmap Reference:**
The authoritative project plan is locally managed `SSOT.md` (based on v6.5). The current focus is debugging the main application loop within **Phase 3** context (integrating analysis, risk, and planning).

**Key Learnings, Decisions & Conventions Established (Session):**
*   **LLM Limitations:** Repeatedly struggled with receiving truncated/incomplete code modifications from the LLM, making debugging and integration very difficult. This highlights a need for alternative methods (e.g., code-aware tools, more precise prompting, manual editing based on diffs) for complex changes.
*   **TypeError Root Cause:** Confirmed that the latest errors stem from passing incorrect keyword arguments to imported strategy functions.
*   **SSoT Relevance:** Re-confirmed the importance of SSoT rules regarding `Decimal` usage to prevent type errors during comparisons and calculations.

**User Directives (Session):**
*   Provided multiple tracebacks for debugging `KeyError` and `TypeError`.
*   Expressed frustration with LLM code truncation/incompleteness.
*   Requested specific modification instructions and later full file replacements.
*   Requested handover generation, identification of relevant SSoT sections, and discussion of alternative approaches/tools.
*   Mentioned potential future enhancement for `context_manager.py` to include file contents.

**Actionable Next Steps (Next Session):**
1.  **(Correction):** **Modify `src/main_trader.py`**.
    *   In the `_apply_risk_controls` method: Correct the call to `check_time_stop` to pass arguments matching its definition (`position` dict, `current_klines` DataFrame, `config` dict, optional `confidence_score`).
    *   In the `_plan_trades` method: Correct the call to `calculate_dynamic_tp_price` to pass arguments matching its definition (`entry_price` Decimal, `current_atr` Decimal/None, `config` dict, `exchange_info` dict, `symbol` str, optional `confidence_score`).
2.  **(Testing):** Run `python -m src.main_trader` again to verify the `TypeError` exceptions are resolved.
3.  **(Debugging):** Address any subsequent errors that may arise after the `TypeError` fixes.

**Key Files Needed for Next Session:**
*   `src/main_trader.py` (The file to be corrected)
*   `src/strategies/risk_controls.py` (To confirm `check_time_stop` signature)
*   `src/strategies/profit_taking.py` (To confirm `calculate_dynamic_tp_price` signature)
*   `config/config.yaml` (For context on settings)

------- SESSION HANDOVER APPENDED [2025-04-17 ~04:45 UTC] -------
# GeminiTrader - Handover Document (2025-04-17 ~04:15 UTC - End of Session)

**Project Goal:** Develop GeminiTrader, an autonomous cryptocurrency trading system aiming for long-term capital growth via a hybrid strategy (DCA, adaptive geometric dip-buying, confidence layer) and robust risk management, using the v6.5 development plan and local SSoT management workflow.

**Session Focus & Current Status:**
*   **Focus:** Debugging the core simulation loop, focusing on state initialization, order placement validation, simulated fill detection, state persistence, and CSV report logging. Addressed multiple `TypeError` and `NameError` exceptions.
*   **Key Activities & Status:**
    *   Corrected state file loading logic in `StateManager` and `main_trader.__init__` to ensure proper handling of missing/empty state files and correct initialization of starting balance.
    *   Fixed multiple `TypeError` exceptions related to incorrect function calls (`check_time_stop`, `calculate_dynamic_tp_price`) or incorrect function definitions (`validate_order_filters`) involving keyword arguments and unpacking. Required manual code application by user to ensure fixes stuck.
    *   Added detailed debug logging to trace entry condition checks and simulated order fill checks.
    *   Confirmed simulation entry conditions (`*** ENTRY CONDITIONS MET ***`) are triggering correctly based on config/data.
    *   Confirmed simulated grid orders are being planned and added to the state (`Placing new grid BUY order...`).
    *   **SUCCESS:** Confirmed simulated grid fills *are* now being detected by `OrderManager.check_orders` (`Sim: Grid order ... filled ...`).
    *   **SUCCESS:** Confirmed fill processing logic in `main_trader._process_fills` updates position/balance state correctly.
    *   **SUCCESS:** Confirmed `GRID_ENTRY` events are being logged correctly to the `SimReport...csv` file.
    *   Confirmed Time Stop logic *is* triggering based on duration/PnL checks after a position is opened.
    *   Identified that the triggered Time Stop market sell attempts were failing due to the now-fixed `TypeError` in `execute_market_sell`'s validation call.
    *   Identified (and user prioritized) a need for a more sophisticated Time Stop exit mechanism than immediate market sell.
    *   **Decision (User Directive):** Implement **Option D - Cascading Time Stop Exit**. This involves trying a maker limit sell, then an aggressive taker limit sell, then a market sell fallback, with configurable timeouts. PnL reporting for TS_EXIT should still use the price that *triggered* the initial check.
    *   Identified minor warnings (duplicate CIDs, naive timestamps) to address later.
*   **Current Status:** The core simulation loop is stable and correctly simulates entries and logs them to the CSV report. The immediate next step is to implement the new Cascading Time Stop Exit mechanism.

**Key Files/Modules Modified (Session):**
*   - src/main_trader.py (Multiple fixes: init logic, state passing, function calls, reporting calls, debug logging)
*   - src/core/order_manager.py (Multiple fixes: state passing refactor, validation calls, fill check logic, import fix)
*   - src/core/state_manager.py (Fixed load_state return value, adjusted post-processing, silenced naive ts warning temporarily)
*   - src/utils/formatting.py (Added estimated_price param to validation functions, removed duplicate function definition)
*   - src/strategies/risk_controls.py (Corrected kline column check)
*   - src/strategies/profit_taking.py (Corrected imports)
*   - src/connectors/binance_us.py (Added get_ticker method)

**Authoritative Roadmap Reference:**
The authoritative project plan is locally managed `SSOT.md` (based on v6.5). This session focused on debugging and stabilizing the core simulation loop (related to Phase 3 integration). The next development step deviates slightly to implement the **Cascading Time Stop Exit** (related to Phase 6 Advanced Risk Controls) as prioritized by the user, before creating the simulation report generator script.

**Key Learnings, Decisions & Conventions Established (Session):**
*   Confirmed clean state initialization requires careful handling of `StateManager.load_state` return values.
*   File cache (`__pycache__`) or editor save issues can cause significant delays in applying code fixes; manual verification and cache clearing are sometimes necessary.
*   Refactoring `OrderManager` to accept state explicitly improved clarity and resolved potential timing issues.
*   Confirmed simulation fill detection (`check_orders`) logic is now functional.
*   CSV reporting mechanism for trade events is successfully implemented.
*   Identified Time Stop PnL reporting needs alignment with the triggering price.
*   **User Decision:** Prioritize implementing a more sophisticated, fee-conscious Cascading Time Stop Exit mechanism (Limit(Maker) -> Limit(Taker) -> Market) over immediate report generation or other refinements.
*   User requested a more comprehensive list of files for future LLM context.

**User Directives (Session):**
*   Manually applied code fixes when LLM updates seemed ineffective.
*   Requested clarification on "DUMMY" warnings.
*   Requested focus shift to implementing the Cascading Time Stop Exit (Option D).
*   Requested generous file list for next handover.
*   Requested specific Git command format.

**Actionable Next Steps:**
1.  **(Configuration):** Define new parameters in `config.yaml` under `risk_controls -> time_stop -> cascade:` for initial limit type (e.g., 'MAKER', 'TAKER', 'OFFSET'), initial limit offset ticks/percentage, initial timeout (seconds), aggressive timeout (seconds).
2.  **(State):** Modify `StateManager` and the default state in `main_trader.py` to include new keys for tracking the cascade: `ts_exit_active` (bool), `ts_exit_step` (int/str), `ts_exit_timer_start` (timestamp), `ts_exit_trigger_price` (Decimal), `ts_exit_active_order_id` (Optional[str]).
3.  **(Connector):** Ensure `binance_us.py` has methods to fetch necessary order book data (e.g., `get_order_book_ticker` to get best bid/ask) if needed for maker/aggressor limit placement. Add if missing.
4.  **(OrderManager):**
    *   Potentially add specific methods like `place_ts_exit_limit_maker`, `place_ts_exit_limit_taker`.
    *   Modify `execute_market_sell` to be the final fallback.
5.  **(Risk Controls):** Modify `main_trader._apply_risk_controls` - when `check_time_stop` returns `True`:
    *   Instead of calling `execute_market_sell`, set `ts_exit_active=True`, `ts_exit_step=1`, `ts_exit_timer_start=now`, store `ts_exit_trigger_price=current_price`, and call the *first* order placement method in `OrderManager` (e.g., `place_ts_exit_limit_maker`) storing the resulting order ID in `ts_exit_active_order_id`.
6.  **(Main Loop):** Add logic (likely near `_check_orders_and_update_state` or `_apply_risk_controls`) to:
    *   Check if `ts_exit_active` is True.
    *   Check the status of the `ts_exit_active_order_id`. If filled, log `TS_EXIT` (using trigger price for PnL), reset position, and clear TS exit state flags.
    *   If not filled, check `now - ts_exit_timer_start` against the relevant timeout (initial or aggressive based on `ts_exit_step`).
    *   If timeout exceeded, call `OrderManager.cancel_order` for the current exit order, increment `ts_exit_step`, reset `ts_exit_timer_start`, and call the *next* placement method (`place_ts_exit_limit_taker` or `execute_market_sell`), updating `ts_exit_active_order_id`.
7.  **(Reporting):** Modify `main_trader._write_report_row` call site for `TS_EXIT` events (likely within the new cascade management logic in `run` or `_check_orders`) to use the stored `ts_exit_trigger_price` for PnL calculation.

**Files Needed for Next LLM Session:**
*   `src/main_trader.py`
*   `src/core/order_manager.py`
*   `src/core/state_manager.py`
*   `src/strategies/risk_controls.py`
*   `src/utils/formatting.py`
*   `src/connectors/binance_us.py`
*   `config/config.yaml`
*   Latest `SimReport_...csv` from `data/sim_reports/`
*   Latest `app.log` (or `trader.log`) from `data/logs/`

**(End of Handover Document Markdown)**