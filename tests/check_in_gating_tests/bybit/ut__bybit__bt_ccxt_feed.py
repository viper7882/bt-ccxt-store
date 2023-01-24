import backtrader
import datetime
import json
import threading
import time
import unittest

from ccxtbt.bt_ccxt__specifications import CCXT__MARKET_TYPES, CCXT__MARKET_TYPE__LINEAR, MAX_LIVE_EXCHANGE_RETRIES
from ccxtbt.bt_ccxt_account_or_store__classes import BT_CCXT_Account_or_Store
from ccxtbt.bt_ccxt_feed__classes import BT_CCXT_Feed
from ccxtbt.bt_ccxt_instrument__classes import BT_CCXT_Instrument
from ccxtbt.exchange.bybit.bybit__exchange__specifications import BYBIT_EXCHANGE_ID, BYBIT_OHLCV_LIMIT
from ccxtbt.exchange.exchange__helper import get_api_and_secret_file_path
from ccxtbt.utils import legality_check_not_none_obj, get_wallet_currency

from check_in_gating_tests.common.test__classes import FAKE_EXCHANGE
from check_in_gating_tests.common.test__helper import get_commission_info


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

        self.main_net_toggle_switch_value = False
        self.exchange_dropdown_value = BYBIT_EXCHANGE_ID

        market_type = CCXT__MARKET_TYPE__LINEAR
        ccxt_market_type_name = CCXT__MARKET_TYPES[market_type]

        # INFO: Bybit exchange-specific value
        account_type_name = "CONTRACT"

        enable_rate_limit = True

        self.api_and_secret_file_path__dict = dict(
            exchange_dropdown_value=self.exchange_dropdown_value,
            market_type=market_type,
            main_net_toggle_switch_value=self.main_net_toggle_switch_value,
        )
        api_key_and_secret_full_path = get_api_and_secret_file_path(
            **self.api_and_secret_file_path__dict)

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
                'type': ccxt_market_type_name,

                'account_alias': account_alias__dropdown_value,
                'account_type': account_type_name,
            }

        legality_check_not_none_obj(
            self.exchange_specific_config, "self.exchange_specific_config")

        self.day_delta = 5
        assert self.day_delta > 1
        self.latest_utc_dt = datetime.datetime.utcnow()
        self.prev_day = self.latest_utc_dt - \
            datetime.timedelta(days=self.day_delta)

    @unittest.skip("Only run if required")
    def test_01__ticks_timeframe__datafeed(self):
        '''
        This test will run forever non-stop. That's why it should not be enabled as permanent test.
        '''
        custom__bt_ccxt_feed__dict = dict(
            timeframe=backtrader.TimeFrame.Ticks,
        )
        finished_strategies = backtesting(
            self.exchange_specific_config, custom__bt_ccxt_feed__dict, self.api_and_secret_file_path__dict)

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
            self.exchange_specific_config, custom__bt_ccxt_feed__dict, self.api_and_secret_file_path__dict)
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
            self.exchange_specific_config, custom__bt_ccxt_feed__dict, self.api_and_secret_file_path__dict)
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
            self.exchange_specific_config, custom__bt_ccxt_feed__dict, self.api_and_secret_file_path__dict)
        self.assertEqual(finished_strategies[0].next_runs, self.day_delta)


class TestStrategy(backtrader.Strategy):

    def __init__(self):
        self.next_runs = 0

    def next(self, dt=None):
        dt = dt or self.datafeeds[0].datetime.datetime(0)
        print('%s closing price: %s' %
              (dt.isoformat().replace("T", " ")[:-3], self.datafeeds[0].close[0]))
        self.next_runs += 1


def backtesting(exchange_specific_config, custom__bt_ccxt_feed__dict, api_and_secret_file_path__dict):
    cerebro = backtrader.Cerebro()

    cerebro.add_strategy(TestStrategy)

    isolated_toggle_switch_value = False
    symbol_name = 'ETH/USDT'
    symbol_id = symbol_name.replace("/", "")

    initial__capital_reservation__value = 0.0

    # INFO: Set to True if websocket feed is required. E.g. Ticks data
    is_ohlcv_provider = True

    account__thread__connectivity__lock = threading.Lock()
    symbols_id = [symbol_id]
    wallet_currency = get_wallet_currency(symbol_id)

    account_or_store__dict = dict(
        main_net_toggle_switch_value=api_and_secret_file_path__dict['main_net_toggle_switch_value'],
        config=exchange_specific_config,
        initial__capital_reservation__value=initial__capital_reservation__value,
        is_ohlcv_provider=is_ohlcv_provider,
    )

    # INFO: Live-specific Params
    account_or_store__dict.update(dict(
        exchange_dropdown_value=api_and_secret_file_path__dict['exchange_dropdown_value'],
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

    bt_ccxt_feed__dict = dict(exchange=api_and_secret_file_path__dict['exchange_dropdown_value'],
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
