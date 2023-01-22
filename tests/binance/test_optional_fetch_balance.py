import backtrader
import datetime
import inspect
import json
import os
import threading
import time
import traceback
import unittest

from backtrader import Strategy, Cerebro, TimeFrame
from datetime import datetime
from pprint import pprint
from time import time as timer
from unittest.mock import patch

from ccxtbt.bt_ccxt__specifications import MAX_LIVE_EXCHANGE_RETRIES, VALUE_DIGITS
from ccxtbt.bt_ccxt_account_or_store__classes import BT_CCXT_Account_or_Store
from ccxtbt.bt_ccxt_feed__classes import BT_CCXT_Feed
from ccxtbt.bt_ccxt_instrument__classes import BT_CCXT_Instrument
from ccxtbt.bt_ccxt_order__classes import BT_CCXT_Order
from ccxtbt.utils import get_time_diff, legality_check_not_none_obj, truncate, get_digits, get_wallet_currency


class TestFeedInitialFetchBalance(unittest.TestCase):
    """
    At least at Binance and probably on other exchanges too fetching ohlcv data doesn't need authentication
    while obviously fetching the balance of ones account does need authentication.
    Usually the BT_CCXT_Account_or_Store fetches the balance when it is initialized which is not a problem during live trading
    operation.
    But the store is also initialized when the BT_CCXT_Feed is created and used during unit testing and backtesting.
    For this case it is beneficial to turn off the initial fetching of the balance as it is not really needed and
    it avoids needing to have api keys.
    This makes it possible for users that don't have a Binance api key to run backtesting and unit tests with real
    ohlcv data to try out this lib.
    """

    def setUp(self):
        """
        The initial balance is fetched in the context of the initialization of the BT_CCXT_Account_or_Store.
        But as the BT_CCXT_Account_or_Store is a singleton it's normally initialized only once and the instance is reused
        causing side effects.
        If the  first test run initializes the store without fetching the balance a subsequent test run
        would not try to fetch the balance again as the initialization won't happen again.
        Resetting the singleton to None here causes the initialization of the store to happen in every test method.
        """
        BT_CCXT_Account_or_Store._singleton = None

        self.enable_rate_limit = True
        self.account_alias__dropdown_value = "Main"
        self.account_type = "CONTRACT"

    @patch('ccxt.binance.fetch_balance')
    def test_fetch_balance_throws_error(self, fetch_balance_mock):
        """
        If API keys are provided the store is expected to fetch the balance.
        """
        exchange_specific_config = {
            'api': None,
            'secret': None,
            'nonce': lambda: str(int(time.time() * 1000)),
            'enableRateLimit': self.enable_rate_limit,
            'account_alias': self.account_alias__dropdown_value,
            'account_type': self.account_type,
        }
        backtesting(exchange_specific_config)

        fetch_balance_mock.assert_called_once()

    def test_default_fetch_balance_param(self):
        """
        If API keys are provided the store is expected to
        not fetch the balance and load the ohlcv data without them.
        """
        exchange_specific_config = {
            # 'api': None,
            # 'secret': None,
            'nonce': lambda: str(int(time.time() * 1000)),
            'enableRateLimit': self.enable_rate_limit,
            'account_alias': self.account_alias__dropdown_value,
            'account_type': self.account_type,
        }
        finished_strategies = backtesting(exchange_specific_config)
        self.assertEqual(finished_strategies[0].next_runs, 2)


class TestStrategy(Strategy):

    def __init__(self):
        self.next_runs = 0

    def next(self, dt=None):
        dt = dt or self.datafeeds[0].datetime.datetime(0)
        print('%s closing price: %s' %
              (dt.isoformat(), self.datafeeds[0].close[0]))
        self.next_runs += 1


def backtesting(exchange_specific_config):
    cerebro = Cerebro()

    cerebro.add_strategy(TestStrategy)

    main_net_toggle_switch_value = True
    exchange_dropdown_value = 'binance'
    isolated_toggle_switch_value = False
    symbol_name = 'BNB/USDT'
    symbol_id = symbol_name.replace("/", "")

    initial__capital_reservation__value = 0.0
    is_ohlcv_provider = False
    account__thread__connectivity__lock = threading.Lock()
    symbols_id = [symbol_id]
    wallet_currency = "BNB"

    account_or_store__dict = dict(
        main_net_toggle_switch_value=main_net_toggle_switch_value,
        config=exchange_specific_config,
        initial__capital_reservation__value=initial__capital_reservation__value,
        is_ohlcv_provider=is_ohlcv_provider,
    )

    # INFO: Live-specific Params
    account_or_store__dict.update(dict(
        exchange_dropdown_value=exchange_dropdown_value,
        wallet_currency=wallet_currency.upper(),
        retries=MAX_LIVE_EXCHANGE_RETRIES,
        symbols_id=symbols_id,
        account__thread__connectivity__lock=account__thread__connectivity__lock,

        # # TODO: Debug Use
        # debug=True,
    ))

    bt_ccxt_account_or_store = BT_CCXT_Account_or_Store(
        **account_or_store__dict)

    bt_ccxt_instrument__dict = dict(
        symbol_id=symbol_id,
    )
    instrument = BT_CCXT_Instrument(**bt_ccxt_instrument__dict)
    instrument.set__parent(bt_ccxt_account_or_store)
    bt_ccxt_account_or_store.add__instrument(instrument)

    datafeed = BT_CCXT_Feed(exchange=exchange_dropdown_value,
                            dataname=symbol_name,
                            timeframe=TimeFrame.Minutes,
                            fromdate=datetime(2023, 1, 1, 0, 0),
                            todate=datetime(2023, 1, 1, 0, 2),
                            compression=1,
                            ohlcv_limit=2,
                            currency=wallet_currency,
                            config=exchange_specific_config,
                            retries=MAX_LIVE_EXCHANGE_RETRIES,
                            historical=True)
    datafeed.set__parent(instrument)

    cerebro.add_datafeed(datafeed)

    finished_strategies = cerebro.run()
    return finished_strategies


if __name__ == '__main__':
    unittest.main()
