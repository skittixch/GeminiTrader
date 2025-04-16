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