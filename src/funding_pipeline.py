# src/funding_pipeline.py

import logging
import time
from decimal import Decimal
from typing import Dict, Optional

# --- Add project root to sys.path FIRST ---
import os
import sys
from pathlib import Path
_project_root_for_path = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
if str(_project_root_for_path) not in sys.path:
    sys.path.insert(0, str(_project_root_for_path))
# --- End sys.path modification ---

# --- Project Imports ---
try:
    from config.settings import load_config
    from src.connectors.coinbase import CoinbaseConnector
    from src.connectors.binance_us import BinanceUSConnector
    from src.db.manager import DBManager  # If logging pipeline steps to DB
    from src.utils.logging_setup import setup_logging  # For test block
    from src.utils.formatting import to_decimal
except ImportError as e:
    print(f"ERROR: Could not import project modules for FundingPipeline: {e}")
    raise ImportError(
        "Failed to import required project modules for FundingPipeline.") from e

logger = logging.getLogger(__name__)

# Define states for the pipeline state machine (intermediate asset flow)


class PipelineState:
    IDLE = "IDLE"
    BUYING_INTERMEDIATE_ASSET = "BUYING_INTERMEDIATE_ASSET"
    CONFIRMING_INTERMEDIATE_BUY = "CONFIRMING_INTERMEDIATE_BUY"
    CHECKING_INTERMEDIATE_BALANCE = "CHECKING_INTERMEDIATE_BALANCE"
    WITHDRAWING_INTERMEDIATE_ASSET = "WITHDRAWING_INTERMEDIATE_ASSET"
    CONFIRMING_INTERMEDIATE_WITHDRAWAL = "CONFIRMING_INTERMEDIATE_WITHDRAWAL"
    AWAITING_BINANCE_INTERMEDIATE_DEPOSIT = "AWAITING_BINANCE_INTERMEDIATE_DEPOSIT"
    SELLING_INTERMEDIATE_ON_BINANCE = "SELLING_INTERMEDIATE_ON_BINANCE"
    CONFIRMING_BINANCE_SELL = "CONFIRMING_BINANCE_SELL"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"
    MANUAL_INTERVENTION_REQUIRED = "MANUAL_INTERVENTION_REQUIRED"


class FundingPipeline:
    """
    Manages the semi-automated process of funding the Binance account via Coinbase,
    using a configurable low-fee intermediate asset (e.g., XLM).
    Designed to be driven by an external script that handles user confirmations.
    """

    def __init__(
        self,
        config: Dict,
        coinbase_connector: CoinbaseConnector,
        binance_connector: BinanceUSConnector,
        db_manager: Optional[DBManager] = None
    ):
        """
        Initializes the Funding Pipeline.

        Args:
            config (Dict): Full application configuration.
            coinbase_connector (CoinbaseConnector): Initialized Coinbase connector.
            binance_connector (BinanceUSConnector): Initialized Binance.US connector.
            db_manager (Optional[DBManager]): DB manager for logging.
        """
        self.config = config
        self.coinbase_connector = coinbase_connector
        self.binance_connector = binance_connector
        self.db_manager = db_manager

        self.state = PipelineState.IDLE
        self.current_step_data = {}
        self.error_message = None

        # --- Extract relevant config details ---
        self.funding_config = config.get('funding_pipeline', {})
        self.dca_config = config.get('strategies', {}).get('dca', {})
        self.quote_currency = 'USD'  # Funding source on Coinbase

        self.intermediate_asset = self.funding_config.get('intermediate_asset')
        if not self.intermediate_asset:
            raise ValueError(
                "Missing 'funding_pipeline.intermediate_asset' in configuration.")
        self.intermediate_asset = self.intermediate_asset.upper()

        # e.g., XLM-USD
        self.coinbase_pair = f"{self.intermediate_asset}-{self.quote_currency}"

        self.binance_deposit_address = self.funding_config.get(
            'binance_deposit_address', {}).get(self.intermediate_asset)
        if not self.binance_deposit_address:
            raise ValueError(
                f"Missing Binance deposit address for {self.intermediate_asset} in config")

        self.binance_deposit_memo = self.funding_config.get(
            'binance_deposit_memo', {}).get(self.intermediate_asset)
        # Check if memo is required for this asset (can expand list)
        if self.intermediate_asset in ['XLM', 'EOS', 'ATOM', 'HBAR'] and not self.binance_deposit_memo:
            logger.warning(
                f"Intermediate asset {self.intermediate_asset} typically requires a MEMO, but none found in config. Withdrawal might fail.")
            # Allowing it to proceed but with a warning. Could raise ValueError if stricter control desired.

        self.binance_quote_asset = config.get(
            'portfolio', {}).get('quote_asset', 'USD')
        # e.g., XLMUSD
        self.binance_sell_pair = f"{self.intermediate_asset}{self.binance_quote_asset}"

        logger.info(
            "Funding Pipeline initialized (Intermediate Asset Strategy).")
        logger.info(f"  Intermediate Asset: {self.intermediate_asset}")
        logger.info(f"  Coinbase Buy Pair: {self.coinbase_pair}")
        logger.info(f"  Binance Sell Pair: {self.binance_sell_pair}")
        logger.info(
            f"  Target Deposit Address (Binance): {self.binance_deposit_address[:5]}...{self.binance_deposit_address[-4:]}")
        if self.binance_deposit_memo:
            logger.info(
                f"  Target Deposit Memo (Binance): {self.binance_deposit_memo}")

    def _set_state(self, new_state: str, data: Optional[Dict] = None, error: Optional[str] = None):
        """Updates the pipeline state and logs it."""
        old_state = self.state
        self.state = new_state
        if data is not None:
            self.current_step_data.update(data)
        if error is not None:
            self.error_message = error
        elif new_state != PipelineState.ERROR:
            self.error_message = None

        logger.info(f"Pipeline State Transition: {old_state} -> {new_state}")
        logger.debug(f"  Current State Data: {self.current_step_data}")
        if self.error_message:
            logger.error(f"  Error Message: {self.error_message}")
        # TODO: Log state transition to DB (PipelineHistory table)

    def execute_buy_intermediate(self, amount_usd: Decimal) -> bool:
        """Initiates the buy order for the intermediate asset on Coinbase."""
        if self.state != PipelineState.IDLE:
            self._set_state(
                PipelineState.ERROR, error=f"Cannot start buy, pipeline busy in state: {self.state}. Reset first.")
            return False

        self._set_state(PipelineState.BUYING_INTERMEDIATE_ASSET,
                        data={'buy_amount_usd': amount_usd})

        if not self.coinbase_connector:
            self._set_state(PipelineState.ERROR,
                            error="Coinbase connector not available.")
            return False

        # Use the corrected connector method
        buy_result = self.coinbase_connector.buy_crypto(
            amount_quote=amount_usd,
            currency_pair=self.coinbase_pair
        )

        if buy_result and buy_result.get('id'):
            # Store relevant details from the buy result if needed later
            buy_data = {'buy_tx_id': buy_result.get('id')}
            # Attempt to parse received amount if structure allows
            bought_amount_data = buy_result.get('amount')
            if isinstance(bought_amount_data, dict):
                buy_data['estimated_bought_amount'] = to_decimal(
                    bought_amount_data.get('amount'))

            self._set_state(
                PipelineState.CONFIRMING_INTERMEDIATE_BUY, data=buy_data)
            logger.info(
                f"Coinbase buy for {self.intermediate_asset} initiated successfully. TX ID: {buy_result.get('id')}")
            return True
        else:
            error_msg = f"Failed to initiate buy for {self.intermediate_asset} on Coinbase. Result: {buy_result}"
            self._set_state(PipelineState.ERROR, error=error_msg)
            return False

    def check_intermediate_balance(self) -> Optional[Decimal]:
        """Checks the balance of the intermediate asset on Coinbase."""
        # Allow checking balance from various states, but log current state
        logger.info(f"Checking balance while in state: {self.state}")
        # Indicate checking is happening
        self._set_state(PipelineState.CHECKING_INTERMEDIATE_BALANCE)

        if not self.coinbase_connector:
            self._set_state(PipelineState.ERROR,
                            error="Coinbase connector not available.")
            return None

        balance = self.coinbase_connector.get_asset_balance(
            self.intermediate_asset)

        if balance is not None:
            logger.info(
                f"Checked Coinbase {self.intermediate_asset} balance: {balance}")
            self._set_state(self.state, data={
                            'coinbase_intermediate_balance': balance})  # Update data
            # Stay in CHECKING state until next action is triggered externally
        else:
            self._set_state(
                PipelineState.ERROR, error=f"Failed to check Coinbase {self.intermediate_asset} balance.")

        return balance

    def execute_intermediate_withdrawal(self, amount: Decimal) -> bool:
        """Initiates the withdrawal of the intermediate asset from Coinbase."""
        # Example pre-condition check (can be adapted)
        # if self.state != PipelineState.CHECKING_INTERMEDIATE_BALANCE:
        #     self._set_state(PipelineState.ERROR, error=f"Invalid state ({self.state}) for withdrawal.")
        #     return False

        self._set_state(PipelineState.WITHDRAWING_INTERMEDIATE_ASSET, data={
                        'withdraw_amount': amount})

        if not self.coinbase_connector:
            self._set_state(PipelineState.ERROR,
                            error="Coinbase connector not available.")
            return False
        if not self.binance_deposit_address:
            self._set_state(PipelineState.ERROR,
                            error="Binance deposit address is not configured.")
            return False

        # Use the corrected connector method with memo handling
        withdraw_result = self.coinbase_connector.withdraw_crypto(
            amount=amount,
            currency=self.intermediate_asset,
            crypto_address=self.binance_deposit_address,
            crypto_memo=self.binance_deposit_memo  # Pass memo (could be None)
        )

        if withdraw_result and withdraw_result.get('id'):
            self._set_state(PipelineState.CONFIRMING_INTERMEDIATE_WITHDRAWAL, data={
                            'withdraw_tx': withdraw_result})
            logger.info(
                f"Coinbase withdrawal for {self.intermediate_asset} initiated successfully. TX ID: {withdraw_result.get('id')}")
            self._set_state(
                PipelineState.AWAITING_BINANCE_INTERMEDIATE_DEPOSIT, data=self.current_step_data)
            return True
        else:
            error_msg = f"Failed to initiate withdrawal of {self.intermediate_asset} from Coinbase. Result: {withdraw_result}"
            self._set_state(PipelineState.ERROR, error=error_msg)
            return False

    def check_binance_intermediate_deposit(self, expected_amount: Optional[Decimal] = None) -> bool:
        """(Placeholder) Checks Binance for the intermediate asset deposit."""
        if self.state != PipelineState.AWAITING_BINANCE_INTERMEDIATE_DEPOSIT:
            self._set_state(PipelineState.ERROR,
                            error="Not currently awaiting Binance deposit.")
            return False

        logger.info(
            f"Checking for {self.intermediate_asset} deposit on Binance (logic placeholder)...")
        # --- Placeholder Logic ---
        # Requires BinanceUSConnector method like:
        # deposit = self.binance_connector.find_recent_deposit(asset=self.intermediate_asset, ...)
        deposit_found_and_confirmed = False
        simulated_received_amount = self.current_step_data.get(
            'withdraw_amount')  # Assume full amount received for now
        # --- End Placeholder ---

        if deposit_found_and_confirmed:
            logger.info(
                f"Confirmed {self.intermediate_asset} deposit on Binance.")
            self._set_state(PipelineState.SELLING_INTERMEDIATE_ON_BINANCE, data={
                            'confirmed_deposit_amount': simulated_received_amount})
            return True
        else:
            logger.info(
                f"Deposit for {self.intermediate_asset} not yet confirmed on Binance.")
            # Remain in AWAITING state
            return False

    def execute_sell_intermediate_on_binance(self, amount: Decimal) -> bool:
        """(Placeholder) Sells the received intermediate asset on Binance.US."""
        if self.state != PipelineState.SELLING_INTERMEDIATE_ON_BINANCE:
            self._set_state(
                PipelineState.ERROR, error="Not in the correct state to sell intermediate asset.")
            return False

        self._set_state(PipelineState.SELLING_INTERMEDIATE_ON_BINANCE, data={
                        'sell_amount': amount})

        if not self.binance_connector:
            self._set_state(PipelineState.ERROR,
                            error="Binance connector not available.")
            return False

        logger.info(
            f"Attempting to SELL {amount} {self.intermediate_asset} for {self.binance_quote_asset} on Binance.US ({self.binance_sell_pair})...")

        # --- Placeholder Logic ---
        # 1. Need method like binance_connector.create_market_order(symbol=self.binance_sell_pair, side='SELL', quantity=amount)
        # 2. Ensure quantity formatting matches Binance filters for the pair.
        # 3. Handle potential errors (insufficient balance, invalid pair, etc.)
        sell_result_simulated = {'symbol': self.binance_sell_pair,
                                 'orderId': f'mock_bn_sell_{int(time.time())}', 'status': 'FILLED', 'executedQty': str(amount)}
        # --- End Placeholder ---

        if sell_result_simulated and sell_result_simulated.get('status') == 'FILLED':
            logger.info(
                f"Simulated successful sale of {self.intermediate_asset} on Binance.US.")
            # Store sell details and mark pipeline as complete
            self._set_state(PipelineState.COMPLETED, data={
                            'sell_tx': sell_result_simulated})
            return True
        else:
            error_msg = f"Failed to execute or confirm sale of {self.intermediate_asset} on Binance.US."
            self._set_state(PipelineState.ERROR, error=error_msg)
            return False

    def reset_pipeline(self):
        """Resets the pipeline state to IDLE and clears data."""
        logger.info("Resetting funding pipeline state.")
        self._set_state(PipelineState.IDLE, data={})  # Clear data


# --- Example Usage / Testing Block ---
if __name__ == '__main__':
    # Setup basic logging for testing
    project_root_fp = Path(_project_root_for_path)
    log_file_path_fp = project_root_fp / "data" / \
        "logs" / "test_funding_pipeline.log"
    log_file_path_fp.parent.mkdir(parents=True, exist_ok=True)
    try:
        setup_logging(log_file=log_file_path_fp,
                      console_logging=True, log_level=logging.INFO)
    except Exception as log_e:
        print(f"ERROR setting up logging: {log_e}. Using basicConfig.")
        logging.basicConfig(
            level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    logger.info(
        "--- Starting Funding Pipeline Test (Intermediate Asset Strategy) ---")

    # Load config
    test_config_fp = load_config()
    if not test_config_fp:
        logger.error("Failed to load config for test. Exiting.")
        sys.exit(1)

    # --- Use Mock Connectors ---
    logger.info("Initializing Mock Connectors...")
    # Define Mock Classes within the test block or import if separated

    class MockCoinbaseConnector:
        def __init__(self, *args, **kwargs): self.log = logging.getLogger(
            'MockCB'); self.log.info("Initialized.")

        def buy_crypto(self, amount_quote, currency_pair, **kwargs): self.log.info(f"buy_crypto called: {amount_quote} {currency_pair.split('-')[1]} for {currency_pair.split('-')[0]}"); return {
            # Simulate getting some crypto
            'id': f'mock_buy_{int(time.time()*10)}', 'amount': {'amount': str(amount_quote / Decimal('0.1') if 'XLM' in currency_pair else amount_quote / Decimal('60000')), 'currency': currency_pair.split('-')[0]}}

        def get_asset_balance(self, asset): self.log.info(f"get_asset_balance called for {asset}."); return Decimal(
            # Example XLM balance
            '100.0') if asset == 'XLM' else Decimal('0.1')
        def withdraw_crypto(self, amount, currency, crypto_address, crypto_memo=None): self.log.info(
            f"withdraw_crypto called: {amount} {currency} to {crypto_address[:5]}.. Memo: {crypto_memo}"); return {'id': f'mock_wd_{int(time.time()*10)}'}

        def get_client(self): return True

    class MockBinanceConnector:
        def __init__(self, *args, **kwargs): self.log = logging.getLogger(
            'MockBN'); self.log.info("Initialized.")

        def create_market_sell_order(self, symbol, quantity): self.log.info(f"create_market_sell called: {quantity} {symbol}"); return {
            'symbol': symbol, 'orderId': f'mock_sell_{int(time.time()*10)}', 'status': 'FILLED', 'executedQty': str(quantity)}
        # Add other methods if pipeline uses them (like checking deposit)

        def find_recent_deposit(self, asset, **kwargs): self.log.info(
            # Simulate deposit not found initially
            f"find_recent_deposit called for {asset}. Simulating NOT FOUND."); return None

        def get_client(self): return True

    mock_cb_connector = MockCoinbaseConnector()
    mock_bn_connector = MockBinanceConnector()

    logger.info("Initializing FundingPipeline with mocks...")
    pipeline = None  # Define before try block
    try:
        pipeline = FundingPipeline(
            config=test_config_fp,
            coinbase_connector=mock_cb_connector,
            binance_connector=mock_bn_connector,
            db_manager=None
        )
        logger.info(f"Initial State: {pipeline.state}")
        intermediate_asset = pipeline.intermediate_asset  # Get configured asset

        # --- Test State Transitions (Conceptual using Mocks) ---
        test_dca_amount = pipeline.dca_config.get(
            'base_amount_usd', Decimal('25.00'))
        logger.info(
            f"\n--- Testing Buy Step ({test_dca_amount} USD for {intermediate_asset}) ---")
        success_buy = pipeline.execute_buy_intermediate(test_dca_amount)
        logger.info(
            f"Buy Step Success: {success_buy}, State: {pipeline.state}")

        if success_buy:
            # Simulate confirming buy
            logger.info(
                "--- Simulating User/Process Confirmation: Buy Completed ---")
            pipeline._set_state(PipelineState.CHECKING_INTERMEDIATE_BALANCE)

            logger.info("\n--- Testing Balance Check Step ---")
            balance = pipeline.check_intermediate_balance()
            logger.info(
                f"Balance Check Result: {balance}, State: {pipeline.state}")

            if balance is not None and balance > 0:
                withdraw_amount = balance
                logger.info(
                    f"\n--- Testing Withdraw Step ({withdraw_amount} {intermediate_asset}) ---")
                success_wd = pipeline.execute_intermediate_withdrawal(
                    withdraw_amount)
                logger.info(
                    f"Withdraw Step Success: {success_wd}, State: {pipeline.state}")

                if success_wd:
                    logger.info(
                        "--- Simulating User/Process Confirmation: Withdrawal Sent ---")
                    # State should be AWAITING_BINANCE_INTERMEDIATE_DEPOSIT

                    logger.info(
                        "\n--- Testing Deposit Check Step (Simulated Success) ---")
                    # Manually set state as if deposit was confirmed
                    pipeline._set_state(PipelineState.SELLING_INTERMEDIATE_ON_BINANCE, data={
                                        'confirmed_deposit_amount': withdraw_amount})
                    deposit_confirmed = True
                    logger.info(
                        f"Simulated Deposit Check Result: {deposit_confirmed}, State: {pipeline.state}")

                    logger.info(
                        "\n--- Testing Sell Step on Binance (Simulated) ---")
                    sell_amount = pipeline.current_step_data.get(
                        'confirmed_deposit_amount', withdraw_amount)
                    # Need to implement the sell method in the mock/real connector first
                    # success_sell = pipeline.execute_sell_intermediate_on_binance(sell_amount)
                    # logger.info(f"Sell Step Success: {success_sell}, State: {pipeline.state}")
                    # For now, just simulate the final state transition
                    pipeline._set_state(PipelineState.COMPLETED, data={
                                        'sell_tx': {'id': 'sim_sell_final'}})
                    logger.info(
                        f"Simulated Sell Step Success, Final State: {pipeline.state}")

        logger.info("\n--- Testing Reset ---")
        pipeline.reset_pipeline()
        logger.info(f"State after reset: {pipeline.state}")

    except ValueError as ve:
        logger.error(f"ValueError during test setup/run: {ve}")
    except Exception as e:
        logger.exception(
            f"An unexpected error occurred during the Funding Pipeline test: {e}")
    finally:
        pass  # No connections to close for mocks

    logger.info("\n--- Funding Pipeline Test Complete ---")


# File path: src/funding_pipeline.py
