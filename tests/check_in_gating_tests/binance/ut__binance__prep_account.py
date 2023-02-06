import inspect
import threading
import traceback
import unittest

from time import time as timer

from ccxtbt.bt_ccxt__specifications import CCXT__MARKET_TYPE__FUTURE, CCXT__MARKET_TYPE__SPOT, \
    DEFAULT__INITIAL__CAPITAL_RESERVATION__VALUE, DEFAULT__LEVERAGE_IN_PERCENT
from ccxtbt.exchange_or_broker.binance.binance__exchange__specifications import BINANCE_EXCHANGE_ID
from ccxtbt.exchange_or_broker.bybit.bybit__exchange__helper import get_wallet_currency
from ccxtbt.expansion.bt_ccxt_expansion__helper import construct_standalone_account_or_store, \
    construct_standalone_instrument
from ccxtbt.utils import get_time_diff


class Binance__bt_ccxt_account_or_store__Prepare_Account__TestCases(unittest.TestCase):
    def setUp(self):
        try:
            self.exchange_dropdown_value = BINANCE_EXCHANGE_ID
            self.market_types = \
                [CCXT__MARKET_TYPE__FUTURE, CCXT__MARKET_TYPE__SPOT]
            # self.market_types = [CCXT__MARKET_TYPE__SPOT]

            self.main_net_toggle_switch_value = False
            # self.main_net_toggle_switch_value = True

            self.isolated_toggle_switch_value = False

            self.leverage_in_percent = DEFAULT__LEVERAGE_IN_PERCENT
            self.initial__capital_reservation__value = DEFAULT__INITIAL__CAPITAL_RESERVATION__VALUE

            self.is_ohlcv_provider = False
            self.enable_rate_limit = True

            self.account__thread__connectivity__lock = threading.Lock()
            self.exchange_account__lock = threading.Lock()
            self.symbols_id = ["ETHUSDT", ]
            self.wallet_currency = get_wallet_currency(self.symbols_id[0])

            self.bt_ccxt_account_or_stores = []

            symbols_id = self.symbols_id
            market_types = self.market_types
            enable_rate_limit = self.enable_rate_limit
            initial__capital_reservation__value = self.initial__capital_reservation__value
            is_ohlcv_provider = self.is_ohlcv_provider
            account__thread__connectivity__lock = self.account__thread__connectivity__lock
            leverage_in_percent = self.leverage_in_percent
            main_net_toggle_switch_value = self.main_net_toggle_switch_value
            exchange_dropdown_value = self.exchange_dropdown_value
            isolated_toggle_switch_value = self.isolated_toggle_switch_value
            wallet_currency = self.wallet_currency

            # Construct the components
            for market_type in market_types:
                construct_standalone_account_or_store__dict = dict(
                    exchange_dropdown_value=exchange_dropdown_value,
                    main_net_toggle_switch_value=main_net_toggle_switch_value,
                    isolated_toggle_switch_value=isolated_toggle_switch_value,
                    leverage_in_percent=leverage_in_percent,
                    market_type=market_type,
                    symbols_id=symbols_id,
                    enable_rate_limit=enable_rate_limit,
                    initial__capital_reservation__value=initial__capital_reservation__value,
                    is_ohlcv_provider=is_ohlcv_provider,
                    account__thread__connectivity__lock=account__thread__connectivity__lock,
                    wallet_currency=wallet_currency,
                )
                (bt_ccxt_account_or_store, _, ) = \
                    construct_standalone_account_or_store(
                        params=construct_standalone_account_or_store__dict)

                for symbol_id in symbols_id:
                    construct_standalone_instrument__dict = dict(
                        bt_ccxt_account_or_store=bt_ccxt_account_or_store,
                        market_type=market_type,
                        symbol_id=symbol_id,
                    )
                    construct_standalone_instrument(
                        params=construct_standalone_instrument__dict)
                self.bt_ccxt_account_or_stores.append(bt_ccxt_account_or_store)
            pass
        except Exception:
            traceback.print_exc()

    def tearDown(self):
        try:
            pass
        except Exception:
            traceback.print_exc()

    @unittest.skip("Only run if required")
    def test_01__Dry_Run(self):
        start = timer()
        try:
            pass
        except Exception:
            traceback.print_exc()

        _, minutes, seconds = get_time_diff(start)
        frameinfo = inspect.getframeinfo(inspect.currentframe())
        print("{} Line: {}: Took {}m:{:.2f}s".format(frameinfo.function, frameinfo.lineno,
                                                     int(minutes), seconds))

    # @unittest.skip("To be enabled")
    # @unittest.skip("Ready for regression")
    def test_10__Change_Leverage_During_Init_and_Dynamically_Assigned(self):
        start = timer()
        try:
            bt_ccxt_account_or_stores = self.bt_ccxt_account_or_stores

            # Run the tests
            for bt_ccxt_account_or_store in bt_ccxt_account_or_stores:
                stepping_down__leverages_in_percent = [
                    i for i in range(40, -1, -10)]
                for leverage_in_percent in stepping_down__leverages_in_percent:
                    success = bt_ccxt_account_or_store.set_leverage_in_percent(
                        leverage_in_percent)

                    # Test Assertion
                    self.assertTrue(success)

                stepping_up__leverages_in_percent = [
                    i for i in range(10, 51, 10)]
                for leverage_in_percent in stepping_up__leverages_in_percent:
                    success = bt_ccxt_account_or_store.set_leverage_in_percent(
                        leverage_in_percent)

                    # Test Assertion
                    self.assertTrue(success)
            pass
        except Exception:
            traceback.print_exc()

        _, minutes, seconds = get_time_diff(start)
        frameinfo = inspect.getframeinfo(inspect.currentframe())
        print("{} Line: {}: Took {}m:{:.2f}s".format(frameinfo.function, frameinfo.lineno,
                                                     int(minutes), seconds))


if __name__ == '__main__':
    unittest.main()
