# scripts/run_dca_pipeline.py

import argparse
import logging
import os
import sys
import time
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from pathlib import Path

# --- Add project root to sys.path ---
try:
    project_root = Path(__file__).parent.parent.resolve()
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    print(f"Project Root added to sys.path: {project_root}")
except NameError:
    project_root = Path('.').resolve()
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    print(
        f"Could not detect script path, assuming running from project root: {project_root}")

# --- Project Imports ---
try:
    from config.settings import load_config
    from src.connectors.coinbase import CoinbaseConnector
    from src.connectors.binance_us import BinanceUSConnector
    from src.funding_pipeline import FundingPipeline, PipelineState
    from src.strategies.dca import calculate_dca_amount_v1
    from src.utils.logging_setup import setup_logging
    from src.utils.formatting import to_decimal
    # from src.db.manager import DBManager
except ImportError as e:
    print(f"ERROR: Failed to import project modules: {e}")
    sys.exit(1)

# --- Setup Logging ---
# (Logging setup remains the same as before)
log_dir = project_root / "data" / "logs"
log_filename = "run_dca_pipeline.log"
try:
    log_dir.mkdir(parents=True, exist_ok=True)
    setup_logging(log_file=(log_dir / log_filename),
                  log_level=logging.INFO, console_logging=True)
    logger = logging.getLogger(__name__)
    logger.info("Logging setup complete for run_dca_pipeline.")
except Exception as log_setup_e:
    print(
        f"ERROR setting up logging: {log_setup_e}. Continuing without file logging.")
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        handlers=[logging.StreamHandler()])
    logger = logging.getLogger(__name__)


# --- Constants ---
# TODO: Get minimums dynamically
MIN_COINBASE_USD_ORDER_SIZE = Decimal('5.00')
# Example minimum XLM withdrawal (check Coinbase actuals)
MIN_INTERMEDIATE_WITHDRAWAL_SIZE = Decimal('1.0')
MIN_ORDER_BUFFER_FACTOR = Decimal('1.01')
AVAILABLE_BALANCE_USAGE_FACTOR = Decimal('0.99')

# --- Utility Functions (remain the same) ---


def get_user_confirmation(prompt: str) -> bool:
    # ... (function code) ...
    while True:
        response = input(f"{prompt} [y/N]: ").strip().lower()
        if response == 'y':
            return True
        elif response == 'n' or response == '':
            return False
        else:
            print("Invalid input. Please enter 'y' or 'n'.")


def display_step(step_num: int, description: str):
    # ... (function code) ...
    print("\n" + "="*60)
    print(f" STEP {step_num}: {description}")
    print("="*60)

# --- Main Script Logic ---


def main():
    parser = argparse.ArgumentParser(
        description="Run semi-automated DCA funding pipeline.")
    args = parser.parse_args()
    logger.info("--- Starting Semi-Automated DCA Funding Pipeline ---")

    # --- Init Steps (Config, Connectors, Pipeline) ---
    display_step(1, "Load Configuration & Initialize Connectors/Pipeline")
    config = load_config()
    if not config:
        logger.error("Failed config load.")
        return
    try:
        cb_conf = config.get('coinbase', {})
        cb_key = cb_conf.get('api_key')
        cb_pk = cb_conf.get('private_key')
        if not cb_key or not cb_pk or 'YOUR_ACTUAL' in cb_key or '-----BEGIN' not in cb_pk:
            raise ValueError("Coinbase keys missing/invalid.")
        cb_connector = CoinbaseConnector(
            api_key=cb_key, private_key=cb_pk, config=config)
        logger.info("CB Connector Init OK.")

        bn_conf = config.get('binance_us', {})
        bn_key = bn_conf.get('api_key')
        bn_secret = bn_conf.get('api_secret')
        if not bn_key or not bn_secret or 'YOUR_ACTUAL' in bn_key:
            raise ValueError("Binance keys missing/invalid.")
        bn_connector = BinanceUSConnector(
            api_key=bn_key, api_secret=bn_secret, config=config)
        logger.info("BNB Connector Init OK.")

        pipeline = FundingPipeline(config, cb_connector, bn_connector, None)
        logger.info("Pipeline Init OK.")
    except (ValueError, ConnectionError) as e:
        logger.error(f"Init Error: {e}")
        return
    except Exception as e:
        logger.exception(f"Unexpected init error: {e}")
        return

    intermediate_asset = pipeline.intermediate_asset
    withdraw_amount = None  # Amount of intermediate asset to withdraw

    # === NEW STEP 4: Check Existing Intermediate Asset Balance ===
    display_step(4, f"Check Existing {intermediate_asset} Balance on Coinbase")
    try:
        intermediate_balance = cb_connector.get_asset_balance(
            intermediate_asset)
        if intermediate_balance is None:
            logger.error(
                f"Failed to retrieve Coinbase {intermediate_asset} balance.")
            return
        logger.info(
            f"Available Coinbase {intermediate_asset} Balance: {intermediate_balance}")

        if intermediate_balance >= MIN_INTERMEDIATE_WITHDRAWAL_SIZE:
            logger.warning(
                f"Found existing {intermediate_asset} balance ({intermediate_balance}) above minimum withdrawal size.")
            # TODO: Estimate USD value? Needs price fetch. For now just show asset amount.
            # price = cb_connector.get_market_price(f"{intermediate_asset}-USD") # Needs implementation
            # usd_value_estimate = intermediate_balance * price if price else Decimal('0.0')
            if get_user_confirmation(f"Use this existing {intermediate_balance} {intermediate_asset} for transfer instead of buying new?"):
                withdraw_amount = intermediate_balance  # Set withdraw amount
                logger.info(
                    f"Proceeding directly to withdrawal with existing {intermediate_asset}.")
                # Skip buy steps by jumping conditional block below
            else:
                logger.info(
                    "User chose not to use existing balance. Proceeding with standard DCA buy flow.")
                # withdraw_amount remains None, normal flow continues
        else:
            logger.info(
                f"Existing {intermediate_asset} balance ({intermediate_balance}) is below minimum withdrawal size ({MIN_INTERMEDIATE_WITHDRAWAL_SIZE}). Proceeding with standard DCA buy flow.")
            # withdraw_amount remains None, normal flow continues

    except Exception as e:
        logger.exception(
            f"An error occurred checking {intermediate_asset} balance: {e}")
        return  # Stop if balance check fails

    # === Standard Buy Flow (only if withdraw_amount wasn't set above) ===
    if withdraw_amount is None:
        display_step(5, "Calculate Target DCA Amount & Check USD Balance")
        target_dca_amount_usd = calculate_dca_amount_v1(pipeline.dca_config)
        if target_dca_amount_usd is None:
            logger.error("Could not calculate DCA amount.")
            return
        logger.info(f"Target DCA amount: ${target_dca_amount_usd:.2f} USD")

        try:
            usd_balance = cb_connector.get_asset_balance('USD')
            if usd_balance is None:
                logger.error("Failed USD balance check.")
                return
            logger.info(f"Available Coinbase USD Balance: ${usd_balance:.2f}")
            min_req = MIN_COINBASE_USD_ORDER_SIZE * MIN_ORDER_BUFFER_FACTOR

            actual_amount_to_buy = None
            if usd_balance >= target_dca_amount_usd:
                logger.info("Sufficient balance for target DCA.")
                actual_amount_to_buy = target_dca_amount_usd
            elif usd_balance >= min_req:
                logger.warning(
                    "Insufficient balance for target DCA, but above minimum.")
                proposed_buy = (usd_balance * AVAILABLE_BALANCE_USAGE_FACTOR).quantize(
                    Decimal('0.01'), rounding=ROUND_DOWN)
                if proposed_buy < MIN_COINBASE_USD_ORDER_SIZE:
                    logger.warning(
                        f"Adjusted amount ${proposed_buy:.2f} is too small. Aborting buy attempt.")
                    return
                if get_user_confirmation(f"Use adjusted balance of ${proposed_buy:.2f} for this DCA instead?"):
                    actual_amount_to_buy = proposed_buy
                else:
                    logger.info("User declined using available balance.")
                    return
            else:
                logger.error(
                    f"Insufficient USD balance (${usd_balance:.2f}). Min required (+buffer): ~${min_req:.2f}. Please deposit funds.")
                return

            if actual_amount_to_buy is None or actual_amount_to_buy < MIN_COINBASE_USD_ORDER_SIZE:
                logger.error(
                    f"Invalid buy amount determined: {actual_amount_to_buy}. Aborting.")
                return
            logger.info(
                f"===> Proposed Buy Amount: ${actual_amount_to_buy:.2f} USD <===")

        except Exception as e:
            logger.exception(f"Error checking USD balance: {e}")
            return

        # --- User Confirmation & Buy Execution ---
        if not get_user_confirmation(f"Proceed to buy ~${actual_amount_to_buy:.2f} worth of {intermediate_asset} on Coinbase?"):
            logger.warning("User aborted before buy.")
            return

        display_step(6, f"Execute Buy ({intermediate_asset} on Coinbase)")
        buy_success = pipeline.execute_buy_intermediate(actual_amount_to_buy)
        if not buy_success or pipeline.state == PipelineState.ERROR:
            logger.error(
                f"Buy step failed. State: {pipeline.state}, Error: {pipeline.error_message}")
            return
        buy_tx_id = pipeline.current_step_data.get(
            'buy_tx', {}).get('order_id', 'N/A')
        logger.info(
            f"Buy initiated (Order ID: {buy_tx_id}). Verify settlement on Coinbase.")

        # --- User Confirmation & Post-Buy Balance Check ---
        if not get_user_confirmation(f"Has the buy for {intermediate_asset} (ID: {buy_tx_id}) settled?"):
            logger.warning("Buy not settled. Aborting.")
            pipeline.reset_pipeline()
            return

        display_step(7, f"Check Post-Buy {intermediate_asset} Balance")
        balance = pipeline.check_intermediate_balance()
        if balance is None or pipeline.state == PipelineState.ERROR:
            logger.error(
                f"Failed post-buy balance check. Error: {pipeline.error_message}")
            return
        try:
            balance_decimal = to_decimal(balance)
            if balance_decimal is None or balance_decimal < MIN_INTERMEDIATE_WITHDRAWAL_SIZE:
                logger.error(
                    f"{intermediate_asset} balance ({balance}) is zero or below withdrawal minimum after buy. Check Coinbase.")
                pipeline.reset_pipeline()
                return
            withdraw_amount = balance_decimal  # Set withdraw amount from post-buy balance
            logger.info(
                f"Confirmed {intermediate_asset} balance post-buy: {withdraw_amount}")
        except (InvalidOperation, TypeError) as conv_e:
            logger.error(
                f"Could not convert post-buy balance '{balance}' to Decimal: {conv_e}")
            pipeline.reset_pipeline()
            return

    # === Withdrawal Flow (runs if withdraw_amount was set either from existing balance or post-buy) ===
    if withdraw_amount is None or withdraw_amount < MIN_INTERMEDIATE_WITHDRAWAL_SIZE:
        logger.error(
            f"Cannot proceed to withdrawal. Amount ({withdraw_amount}) is invalid or below minimum ({MIN_INTERMEDIATE_WITHDRAWAL_SIZE}).")
        pipeline.reset_pipeline()
        return

    # --- User Confirmation & Withdrawal ---
    if not get_user_confirmation(f"Proceed to withdraw {withdraw_amount} {intermediate_asset} from Coinbase to Binance.US?"):
        logger.warning("User aborted before withdrawal.")
        pipeline.reset_pipeline()
        return

    display_step(8, f"Execute Withdrawal ({intermediate_asset} from Coinbase)")
    logger.error(
        "!!! WITHDRAWAL FUNCTIONALITY REQUIRES VERIFICATION/IMPLEMENTATION in CoinbaseConnector !!!")
    logger.warning(
        "The actual withdrawal call is currently disabled in the connector.")
    withdraw_success = True  # Simulate success
    pipeline._set_state(PipelineState.AWAITING_BINANCE_INTERMEDIATE_DEPOSIT, data={
                        'withdraw_tx': {'id': 'simulated_wd_123'}, 'withdraw_amount': withdraw_amount})
    logger.info(
        f"(Simulated) Coinbase withdrawal for {withdraw_amount} {intermediate_asset} initiated.")

    if not withdraw_success:  # Check won't fail now, but keep structure
        logger.error(
            f"Withdrawal failed. State: {pipeline.state}, Error: {pipeline.error_message}")
        return

    logger.info(
        "Monitor Coinbase & Binance.US for withdrawal completion & deposit arrival.")
    logger.info(f"  Destination Address: {pipeline.binance_deposit_address}")
    if pipeline.binance_deposit_memo:
        logger.info(f"  Destination Memo: {pipeline.binance_deposit_memo}")

    # --- User Confirmation: Deposit Arrived ---
    if not get_user_confirmation(f"Has the {intermediate_asset} deposit arrived/credited on Binance.US?"):
        logger.warning(
            "Deposit not confirmed. Pipeline stopped before final conversion.")
        return

    # --- Manual Action Required ---
    display_step(
        9, f"Manual Action Required: Sell {intermediate_asset} on Binance.US")
    logger.info(
        f"User confirmed deposit arrived. Please manually sell {intermediate_asset} for {pipeline.binance_quote_asset} on Binance.US.")
    pipeline._set_state(PipelineState.COMPLETED, data={
                        'status': 'Transfer complete, manual sale pending'})
    logger.info("--- Semi-Automated DCA Funding Pipeline Finished ---")


if __name__ == "__main__":
    main()

# File path: scripts/run_dca_pipeline.py
