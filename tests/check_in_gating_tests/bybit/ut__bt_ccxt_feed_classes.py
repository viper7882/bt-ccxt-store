import backtrader
import datetime
import inspect
import json
import os
import pathlib
import threading
import time
import traceback
import unittest

from backtrader import TimeFrame
from pprint import pprint
from time import time as timer
from unittest.mock import patch

from ccxtbt.bt_ccxt__specifications import MAX_LIVE_EXCHANGE_RETRIES, VALUE_DIGITS
from ccxtbt.bt_ccxt_account_or_store__classes import BT_CCXT_Account_or_Store
from ccxtbt.bt_ccxt_feed__classes import BT_CCXT_Feed
from ccxtbt.bt_ccxt_instrument__classes import BT_CCXT_Instrument
from ccxtbt.bt_ccxt_order__classes import BT_CCXT_Order
from ccxtbt.bybit_exchange__specifications import BYBIT_EXCHANGE_ID, BYBIT_OHLCV_LIMIT, BYBIT_COMMISSION_PRECISION
from ccxtbt.utils import get_time_diff, legality_check_not_none_obj, truncate, get_digits, get_wallet_currency
from check_in_gating_tests.common.test__classes import FAKE_EXCHANGE
from check_in_gating_tests.common.test__helper import get_commission_info, handle_datafeed, reverse_engineer__ccxt_order
from check_in_gating_tests.common.test__specifications import API_KEY_AND_SECRET_FILE_NAME


class Test_Feed(unittest.TestCase):
    def setUp(self):
        """
        The initial balance is fetched in the context of the initialization of the BT_CCXT_Account_or_Store.
        But as the BT_CCXT_Account_or_Store is a singleton it's normally initialized only once and the instance is
        reused causing side effects.
        If the  first test run initializes the store without fetching the balance a subsequent test run
        would not try to fetch the balance again as the initialization won't happen again.
        Resetting the singleton to None here causes the initialization of the store to happen in every test method.
        """
        BT_CCXT_Account_or_Store._singleton = None

        enable_rate_limit = True

        # INFO: Bybit exchange-specific value
        account_type = "CONTRACT"

        file_path = pathlib.Path(__file__).parent.resolve()
        api_key_and_secret_full_path = os.path.join(
            file_path, API_KEY_AND_SECRET_FILE_NAME)
        assert os.path.exists(api_key_and_secret_full_path)

        self.exchange_specific_config = None
        with open(api_key_and_secret_full_path, "r") as file_to_read:
            json_data = json.load(file_to_read)
            api_key = json_data['key']
            secret = json_data['secret']
            account_alias__dropdown_value = json_data['account_alias__dropdown_value']

            self.exchange_specific_config = {
                'apiKey': api_key,
                'secret': secret,
                'nonce': lambda: str(int(time.time() * 1000)),
                'enableRateLimit': enable_rate_limit,
                'account_alias': account_alias__dropdown_value,
                'account_type': account_type,
            }

        legality_check_not_none_obj(
            self.exchange_specific_config, "self.exchange_specific_config")

        self.day_delta = 5
        assert self.day_delta > 1
        self.latest_utc_dt = datetime.datetime.utcnow()
        self.prev_day = self.latest_utc_dt - \
            datetime.timedelta(days=self.day_delta)

    # @unittest.skip("To be enabled")
    # @unittest.skip("Ready for regression")
    def test_10__standard_timeframe__historical_datafeed(self):
        custom__bt_ccxt_feed__dict = dict(
            compression=1,
            timeframe=backtrader.TimeFrame.Days,
            fromdate=datetime.datetime(
                self.prev_day.year, self.prev_day.month, self.prev_day.day),
            todate=datetime.datetime(
                self.latest_utc_dt.year, self.latest_utc_dt.month, self.latest_utc_dt.day),
            historical=True,
        )

        finished_strategies = backtesting(
            self.exchange_specific_config, custom__bt_ccxt_feed__dict)
        self.assertEqual(finished_strategies[0].next_runs, self.day_delta)

    # @unittest.skip("To be enabled")
    # @unittest.skip("Ready for regression")
    def test_11__standard_timeframe__recent_datafeed__keep_newest(self):
        custom__bt_ccxt_feed__dict = dict(
            compression=1,
            timeframe=backtrader.TimeFrame.Days,
            fromdate=datetime.datetime(
                self.prev_day.year, self.prev_day.month, self.prev_day.day),
            todate=datetime.datetime(
                self.latest_utc_dt.year, self.latest_utc_dt.month, self.latest_utc_dt.day),
            drop_newest=False,
            ut__halt_if_no_ohlcv=True,
            # debug=True,
        )

        finished_strategies = backtesting(
            self.exchange_specific_config, custom__bt_ccxt_feed__dict)
        self.assertEqual(finished_strategies[0].next_runs, self.day_delta + 1)

    # @unittest.skip("To be enabled")
    # @unittest.skip("Ready for regression")
    def test_12__standard_timeframe__recent_datafeed__drop_newest(self):
        custom__bt_ccxt_feed__dict = dict(
            compression=1,
            timeframe=backtrader.TimeFrame.Days,
            fromdate=datetime.datetime(
                self.prev_day.year, self.prev_day.month, self.prev_day.day),
            todate=datetime.datetime(
                self.latest_utc_dt.year, self.latest_utc_dt.month, self.latest_utc_dt.day),
            drop_newest=True,
            ut__halt_if_no_ohlcv=True,
            # debug=True,
        )

        finished_strategies = backtesting(
            self.exchange_specific_config, custom__bt_ccxt_feed__dict)
        self.assertEqual(finished_strategies[0].next_runs, self.day_delta)


class TestStrategy(backtrader.Strategy):

    def __init__(self):
        self.next_runs = 0

    def next(self, dt=None):
        dt = dt or self.datafeeds[0].datetime.datetime(0)
        print('%s closing price: %s' %
              (dt.isoformat(), self.datafeeds[0].close[0]))
        self.next_runs += 1


def backtesting(exchange_specific_config, custom__bt_ccxt_feed__dict):
    cerebro = backtrader.Cerebro()

    cerebro.add_strategy(TestStrategy)

    main_net_toggle_switch_value = False
    exchange_dropdown_value = BYBIT_EXCHANGE_ID
    isolated_toggle_switch_value = False
    symbol_name = 'ETH/USDT'
    symbol_id = symbol_name.replace("/", "")

    initial__capital_reservation__value = 0.0
    is_ohlcv_provider = False
    account__thread__connectivity__lock = threading.Lock()
    symbols_id = [symbol_id]
    wallet_currency = get_wallet_currency(symbol_id)

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
        # debug=True,
    ))

    bt_ccxt_account_or_store = BT_CCXT_Account_or_Store(
        **account_or_store__dict)

    commission = 0.0006
    leverage_in_percent = 50.0
    get_commission_info__dict = dict(
        symbol_id=symbol_id,
        isolated_toggle_switch_value=isolated_toggle_switch_value,
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

    # Validate assumption made
    assert isinstance(custom__bt_ccxt_feed__dict, dict)

    bt_ccxt_feed__dict = dict(exchange=exchange_dropdown_value,
                              dataname=symbol_id,
                              ohlcv_limit=BYBIT_OHLCV_LIMIT,
                              currency=wallet_currency,
                              config=exchange_specific_config,
                              retries=MAX_LIVE_EXCHANGE_RETRIES,
                              )
    bt_ccxt_feed__dict.update(custom__bt_ccxt_feed__dict)
    datafeed = BT_CCXT_Feed(**bt_ccxt_feed__dict)
    datafeed.set__parent(instrument)

    cerebro.add_datafeed(datafeed)

    finished_strategies = cerebro.run()
    return finished_strategies


if __name__ == '__main__':
    unittest.main()
