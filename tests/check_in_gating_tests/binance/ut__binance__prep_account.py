import inspect
import json
import threading
import time
import traceback
import unittest

from time import time as timer

from ccxtbt.bt_ccxt__specifications import CCXT__MARKET_TYPES, CCXT__MARKET_TYPE__FUTURES, MAX_LIVE_EXCHANGE_RETRIES
from ccxtbt.bt_ccxt_account_or_store__classes import BT_CCXT_Account_or_Store
from ccxtbt.bt_ccxt_instrument__classes import BT_CCXT_Instrument
from ccxtbt.exchange.binance.binance__exchange__helper import get_binance_commission_rate
from ccxtbt.exchange.binance.binance__exchange__specifications import BINANCE_EXCHANGE_ID
from ccxtbt.exchange.bybit.bybit__exchange__helper import get_wallet_currency
from ccxtbt.exchange.exchange__helper import get_api_and_secret_file_path
from ccxtbt.utils import get_time_diff, legality_check_not_none_obj

from check_in_gating_tests.common.test__classes import FAKE_EXCHANGE
from check_in_gating_tests.common.test__helper import get_commission_info


class Binance__bt_ccxt_account_or_store__Prepare_Account__TestCases(unittest.TestCase):
    def setUp(self):
        try:
            self.exchange_dropdown_value = BINANCE_EXCHANGE_ID
            self.market_types = [CCXT__MARKET_TYPE__FUTURES]

            self.main_net_toggle_switch_value = False
            # self.main_net_toggle_switch_value = True

            self.isolated_toggle_switch_value = False

            self.leverage_in_percent = 50.0
            self.initial__capital_reservation__value = 0.0

            self.is_ohlcv_provider = False
            self.enable_rate_limit = True

            self.account__thread__connectivity__lock = threading.Lock()
            self.exchange_account__lock = threading.Lock()
            self.symbols_id = ["ETHUSDT", ]
            pass
        except Exception:
            traceback.print_exc()

    def tearDown(self):
        try:
            pass
        except Exception:
            traceback.print_exc()

    @unittest.skip("Only run if required")
    def test_01__(self):
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
            symbols_id = self.symbols_id
            market_types = self.market_types
            enable_rate_limit = self.enable_rate_limit
            initial__capital_reservation__value = self.initial__capital_reservation__value
            is_ohlcv_provider = self.is_ohlcv_provider
            account__thread__connectivity__lock = self.account__thread__connectivity__lock
            leverage_in_percent = self.leverage_in_percent

            for market_type in market_types:
                for symbol_id in symbols_id:
                    api_and_secret_file_path__dict = dict(
                        exchange_dropdown_value=self.exchange_dropdown_value,
                        market_type=market_type,
                        main_net_toggle_switch_value=self.main_net_toggle_switch_value,
                    )
                    api_key_and_secret_full_path = get_api_and_secret_file_path(
                        **api_and_secret_file_path__dict)

                    bt_ccxt_account_or_store = None
                    with open(api_key_and_secret_full_path, "r") as file_to_read:
                        json_data = json.load(file_to_read)
                        api_key = json_data['key']
                        api_secret = json_data['secret']
                        account_alias__dropdown_value = json_data['account_alias__dropdown_value']

                        if market_type == CCXT__MARKET_TYPE__FUTURES:
                            # WARNING: The "future" entry is NOT a typo error. It is a fixed requirement by Binance
                            #          exchange. The following code is workaround to remove the extra "s".
                            ccxt_market_type_name = CCXT__MARKET_TYPES[market_type][:-1]
                        else:
                            ccxt_market_type_name = CCXT__MARKET_TYPES[market_type]

                        exchange_specific_config = {
                            'apiKey': api_key,
                            'secret': api_secret,
                            'nonce': lambda: str(int(time.time() * 1000)),
                            'enableRateLimit': enable_rate_limit,
                            'type': ccxt_market_type_name,

                            'account_alias': account_alias__dropdown_value,
                            'account_type': market_type,
                        }

                        account_or_store__dict = dict(
                            main_net_toggle_switch_value=self.main_net_toggle_switch_value,
                            config=exchange_specific_config,
                            initial__capital_reservation__value=initial__capital_reservation__value,
                            is_ohlcv_provider=is_ohlcv_provider,
                            leverage_in_percent=leverage_in_percent,
                        )

                        wallet_currency = get_wallet_currency(symbol_id)
                        # INFO: Live-specific Params
                        account_or_store__dict.update(dict(
                            exchange_dropdown_value=self.exchange_dropdown_value,
                            wallet_currency=wallet_currency.upper(),
                            retries=MAX_LIVE_EXCHANGE_RETRIES,
                            symbols_id=symbols_id,
                            account__thread__connectivity__lock=account__thread__connectivity__lock,
                            # debug=True,
                        ))

                        bt_ccxt_account_or_store = BT_CCXT_Account_or_Store(
                            **account_or_store__dict)
                    legality_check_not_none_obj(
                        bt_ccxt_account_or_store, "bt_ccxt_account_or_store")

                    commission_rate__dict = dict(
                        bt_ccxt_account_or_store=bt_ccxt_account_or_store,
                        market_type=market_type,
                        symbol_id=symbol_id,
                    )
                    commission = get_binance_commission_rate(
                        params=commission_rate__dict)

                    get_commission_info__dict = dict(
                        symbol_id=symbol_id,
                        isolated_toggle_switch_value=self.isolated_toggle_switch_value,
                        leverage_in_percent=leverage_in_percent,
                        commission=commission,
                    )
                    commission_info = get_commission_info(
                        params=get_commission_info__dict)

                    fake_exchange = FAKE_EXCHANGE(
                        owner=bt_ccxt_account_or_store)
                    fake_exchange.add_commission_info(commission_info)
                    bt_ccxt_account_or_store.set__parent(fake_exchange)

                    bt_ccxt_instrument__dict = dict(
                        symbol_id=symbol_id,
                    )
                    instrument = BT_CCXT_Instrument(**bt_ccxt_instrument__dict)
                    instrument.set__parent(bt_ccxt_account_or_store)
                    bt_ccxt_account_or_store.add__instrument(instrument)

                    stepping_up__leverages_in_percent = [
                        i for i in range(0, 51, 10)]
                    for leverage_in_percent in stepping_up__leverages_in_percent:
                        success = bt_ccxt_account_or_store.set_leverage_in_percent(
                            leverage_in_percent)

                        # Test Assertion
                        self.assertTrue(success)

                    stepping_down__leverages_in_percent = [
                        i for i in range(40, -1, -10)]
                    for leverage_in_percent in stepping_down__leverages_in_percent:
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
