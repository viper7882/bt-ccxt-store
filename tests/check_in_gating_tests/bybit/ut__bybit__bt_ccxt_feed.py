import backtrader
import datetime
import threading
import traceback
import unittest

from ccxtbt.bt_ccxt__specifications import CCXT__MARKET_TYPES, CCXT__MARKET_TYPE__LINEAR_PERPETUAL_SWAP, \
    MAX_LIVE_EXCHANGE_RETRIES
from ccxtbt.bt_ccxt_feed__classes import BT_CCXT_Feed
from ccxtbt.exchange.bybit.bybit__exchange__helper import get_wallet_currency
from ccxtbt.exchange.bybit.bybit__exchange__specifications import BYBIT_EXCHANGE_ID, BYBIT_OHLCV_LIMIT
from ccxtbt.utils import legality_check_not_none_obj

from check_in_gating_tests.common.test__helper import ut__construct_standalone_account_or_store, \
    ut__construct_standalone_instrument


class Test_Feed(unittest.TestCase):
    def setUp(self):
        self.day_delta = 5
        assert self.day_delta > 1
        self.latest_utc_dt = datetime.datetime.utcnow()
        self.prev_day = self.latest_utc_dt - \
            datetime.timedelta(days=self.day_delta)

        self.bt_ccxt_account_or_stores = []

    def tearDown(self):
        try:
            for bt_ccxt_account_or_store in self.bt_ccxt_account_or_stores:
                if bt_ccxt_account_or_store.is_ws_available:
                    bt_ccxt_account_or_store.close_bybit_websocket()

            self.bt_ccxt_account_or_stores = []
            pass
        except Exception:
            traceback.print_exc()

    @unittest.skip("Only run if required")
    def test_01__ticks_timeframe__datafeed(self):
        '''
        This test will run forever non-stop. That's why it should not be enabled as permanent test.
        '''
        custom__bt_ccxt_feed__dict = dict(
            timeframe=backtrader.TimeFrame.Ticks,
        )
        finished_strategies = backtesting(
            custom__bt_ccxt_feed__dict, self.bt_ccxt_account_or_stores)

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
            custom__bt_ccxt_feed__dict, self.bt_ccxt_account_or_stores)
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
            custom__bt_ccxt_feed__dict, self.bt_ccxt_account_or_stores)
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
            custom__bt_ccxt_feed__dict, self.bt_ccxt_account_or_stores)
        self.assertEqual(finished_strategies[0].next_runs, self.day_delta)


class TestStrategy(backtrader.Strategy):

    def __init__(self):
        self.next_runs = 0

    def next(self, dt=None):
        dt = dt or self.datafeeds[0].datetime.datetime(0)
        print('%s closing price: %s' %
              (dt.isoformat().replace("T", " ")[:-3], self.datafeeds[0].close[0]))
        self.next_runs += 1


def backtesting(custom__bt_ccxt_feed__dict, bt_ccxt_account_or_stores):
    cerebro = backtrader.Cerebro()

    cerebro.add_strategy(TestStrategy)

    main_net_toggle_switch_value = True
    # main_net_toggle_switch_value = False

    exchange_dropdown_value = BYBIT_EXCHANGE_ID

    market_type = CCXT__MARKET_TYPE__LINEAR_PERPETUAL_SWAP

    # INFO: Bybit exchange-specific value
    account_type_name = "CONTRACT"

    enable_rate_limit = True

    isolated_toggle_switch_value = False
    symbol_name = 'ETH/USDT'
    symbol_id = symbol_name.replace("/", "")

    initial__capital_reservation__value = 0.0
    leverage_in_percent = 50.0

    # INFO: Set to True if websocket feed is required. E.g. Ticks data
    is_ohlcv_provider = True

    account__thread__connectivity__lock = threading.Lock()
    symbols_id = [symbol_id]
    wallet_currency = get_wallet_currency(symbol_id)

    construct_standalone_account_or_store__dict = dict(
        exchange_dropdown_value=exchange_dropdown_value,
        main_net_toggle_switch_value=main_net_toggle_switch_value,
        market_type=market_type,
        symbols_id=symbols_id,
        enable_rate_limit=enable_rate_limit,
        initial__capital_reservation__value=initial__capital_reservation__value,
        is_ohlcv_provider=is_ohlcv_provider,
        account__thread__connectivity__lock=account__thread__connectivity__lock,
        leverage_in_percent=leverage_in_percent,
        wallet_currency=wallet_currency,

        # INFO: Optional Params
        account_type=account_type_name,
    )
    (bt_ccxt_account_or_store, exchange_specific_config, ) = \
        ut__construct_standalone_account_or_store(
            params=construct_standalone_account_or_store__dict)

    legality_check_not_none_obj(
        exchange_specific_config, "exchange_specific_config")
    bt_ccxt_account_or_stores.append(bt_ccxt_account_or_store)

    construct_standalone_instrument__dict = dict(
        bt_ccxt_account_or_store=bt_ccxt_account_or_store,
        isolated_toggle_switch_value=isolated_toggle_switch_value,
        leverage_in_percent=leverage_in_percent,
        market_type=market_type,
        symbol_id=symbol_id,
    )
    ut__construct_standalone_instrument(
        params=construct_standalone_instrument__dict)
    instrument = bt_ccxt_account_or_store.get__child(symbol_id)

    # Validate assumption made
    assert isinstance(custom__bt_ccxt_feed__dict, dict)

    bt_ccxt_feed__dict = dict(
        exchange=exchange_dropdown_value,
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
