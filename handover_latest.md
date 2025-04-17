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