import backtrader
import datetime
import inspect
import threading
import traceback
import unittest

from time import time as timer
from pprint import pprint

from ccxtbt.bt_ccxt__specifications import CCXT__MARKET_TYPE__LINEAR_PERPETUAL_SWAP, \
    DEFAULT__INITIAL__CAPITAL_RESERVATION__VALUE, DEFAULT__LEVERAGE_IN_PERCENT
from ccxtbt.datafeed.datafeed__classes import BT_CCXT_Feed
from ccxtbt.exchange_or_broker.exchange__specifications import CCXT_COMMON_MAPPING_VALUES, CLOSED_VALUE, OPEN_VALUE
from ccxtbt.exchange_or_broker.bybit.bybit__exchange__helper import get_wallet_currency
from ccxtbt.exchange_or_broker.bybit.bybit__exchange__specifications import BYBIT_EXCHANGE_ID, BYBIT_OHLCV_LIMIT
from ccxtbt.expansion.bt_ccxt_expansion__helper import construct_standalone_account_or_store, \
    construct_standalone_instrument
from ccxtbt.order.order__classes import BT_CCXT_Order
from ccxtbt.utils import get_time_diff

from check_in_gating_tests.common.test__helper import ut_handle_datafeed, ut_reverse_engineer__ccxt_order


class Bybit__bt_ccxt_account_or_store__Static_Orders__TestCases(unittest.TestCase):
    def setUp(self):
        try:
            self.bt_ccxt_account_or_store = None

            self.main_net_toggle_switch_value = False
            self.exchange_dropdown_value = BYBIT_EXCHANGE_ID
            self.isolated_toggle_switch_value = False

            # WARNING: Avoid assigning market_type to CCXT__MARKET_TYPE__SPOT and run all check in tests altogether.
            #          Doing so will cause _fetch_opened_positions_from_exchange to mix up between swap and spot market
            #          and eventually causing whole bunch of "invalid symbols" error
            market_type = CCXT__MARKET_TYPE__LINEAR_PERPETUAL_SWAP

            self.initial__capital_reservation__value = DEFAULT__INITIAL__CAPITAL_RESERVATION__VALUE
            self.leverage_in_percent = DEFAULT__LEVERAGE_IN_PERCENT
            self.is_ohlcv_provider = False
            self.enable_rate_limit = True
            self.account__thread__connectivity__lock = threading.Lock()

            self.symbol_id = "ETHUSDT"
            self.symbols_id = [self.symbol_id]
            self.wallet_currency = get_wallet_currency(self.symbols_id[0])

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
            construct_standalone_account_or_store__dict = dict(
                exchange_dropdown_value=exchange_dropdown_value,
                main_net_toggle_switch_value=main_net_toggle_switch_value,
                isolated_toggle_switch_value=isolated_toggle_switch_value,
                leverage_in_percent=leverage_in_percent,
                market_type=market_type,
                symbols_id=self.symbols_id,
                enable_rate_limit=enable_rate_limit,
                initial__capital_reservation__value=initial__capital_reservation__value,
                is_ohlcv_provider=is_ohlcv_provider,
                account__thread__connectivity__lock=account__thread__connectivity__lock,
                wallet_currency=wallet_currency,
            )
            (self.bt_ccxt_account_or_store, _, ) = \
                construct_standalone_account_or_store(
                    params=construct_standalone_account_or_store__dict)

            for symbol_id in self.symbols_id:
                construct_standalone_instrument__dict = dict(
                    bt_ccxt_account_or_store=self.bt_ccxt_account_or_store,
                    market_type=market_type,
                    symbol_id=symbol_id,
                )
                instrument = \
                    construct_standalone_instrument(
                        params=construct_standalone_instrument__dict)
                commission_info = instrument.get_commission_info()

                # Create Long and Short datafeeds
                convert_to_heikin_ashi = False
                drop_newest = True
                historical = False
                granularity_compression = 1
                granularity_timeframe = backtrader.TimeFrame.Minutes

                # TODO: User to customize the entries below
                self.primary_entry_price = 1193.55
                self.primary_entry_qty = -1.03

                self.hedging_entry_price = 1195.4
                self.hedging_entry_qty = 1.78

                start_date = \
                    datetime.datetime.utcnow() - datetime.timedelta(minutes=granularity_compression + 1)

                datafeed__dict = dict(
                    dataname=symbol_id,
                    timeframe=granularity_timeframe,
                    compression=granularity_compression,
                    ohlcv_limit=BYBIT_OHLCV_LIMIT,

                    convert_to_heikin_ashi=convert_to_heikin_ashi,
                    tick_size=commission_info.tick_size,
                    price_digits=commission_info.price_digits,

                    fromdate=start_date,
                    drop_newest=drop_newest,

                    # If historical is True, the strategy will not enter into next()
                    historical=historical,

                    # debug=True,
                )
                datafeed__dict.update(dict(
                    name="Long",
                ))
                self.long_bb_data = BT_CCXT_Feed(**datafeed__dict)
                self.long_bb_data.set__parent(instrument)
                ut_handle_datafeed(self.long_bb_data,
                                   price=self.hedging_entry_price)

                datafeed__dict.update(dict(
                    name="Short",
                ))
                self.short_bb_data = BT_CCXT_Feed(**datafeed__dict)
                self.short_bb_data.set__parent(instrument)
                ut_handle_datafeed(self.short_bb_data,
                                   price=self.primary_entry_price)

                primary_entry__ccxt_order = \
                    {
                        "info": {
                            "order_id": "41992e55-3ed8-4ea0-80f6-085a36e73d86",
                            "last_exec_price": "1193.55",
                            "cum_exec_qty": "{}".format(abs(self.primary_entry_qty)),
                            "cum_exec_value": "1229.3565",
                            "cum_exec_fee": "0.7376139",
                            "user_id": "660978",
                            "symbol": "ETHUSDT",
                            "side": "Sell",
                            "order_type": "Limit",
                            "time_in_force": "GoodTillCancel",
                            "order_status": "Filled",
                            "tp_trigger_by": "UNKNOWN",
                            "sl_trigger_by": "UNKNOWN",
                            "price": "{}".format(self.primary_entry_price),
                            "qty": "{}".format(abs(self.primary_entry_qty)),
                            "order_link_id": "",
                            "reduce_only": False,
                            "close_on_trigger": False,
                            "take_profit": "0",
                            "stop_loss": "0",
                            "created_time": "2022-12-28T11:55:13Z",
                            "updated_time": "2022-12-28T11:55:13Z"
                        },
                        "id": "41992e55-3ed8-4ea0-80f6-085a36e73d86",
                        "clientOrderId": None,
                        "timestamp": 1672228513000,
                        "datetime": "2022-12-28T11:55:13.000Z",
                        "lastTradeTimestamp": 1672228513000,
                        "symbol": "ETH/USDT:USDT",
                        "type": "limit",
                        "timeInForce": "GTC",
                        "postOnly": False,
                        "side": "sell",
                        "price": self.primary_entry_price,
                        "stopPrice": None,
                        "amount": abs(self.primary_entry_qty),
                        "cost": 1229.3565,
                        "average": self.primary_entry_price,
                        "filled": abs(self.primary_entry_qty),
                        "remaining": 0.0,
                        "status": CCXT_COMMON_MAPPING_VALUES[CLOSED_VALUE],
                        "fee": {
                            "cost": 0.7376139,
                            "currency": "USDT"
                        },
                        "trades": [],
                        "fees": [
                            {
                                "cost": 0.7376139,
                                "currency": "USDT"
                            }
                        ]
                    }

                bt_ccxt_order__dict = dict(
                    owner=self,
                    exchange_dropdown_value=self.bt_ccxt_account_or_store.exchange_dropdown_value,
                    symbol_id=symbol_id,
                    position_type=backtrader.Position.SHORT_POSITION,
                    datafeed=self.short_bb_data,
                    ccxt_order=primary_entry__ccxt_order,
                )
                reverse_engineered__bt_ccxt_order__dict = ut_reverse_engineer__ccxt_order(
                    bt_ccxt_order__dict)
                self.primary_entry_order = BT_CCXT_Order(
                    **reverse_engineered__bt_ccxt_order__dict)

                offset_entry__ccxt_order = \
                    {
                        "info": {
                            "stop_order_id": "823f4c52-2be2-4fb2-9231-fd3281733e5f",
                            "trigger_price": "{}".format(self.hedging_entry_price),
                            "base_price": "1193.55",
                            "trigger_by": "LastPrice",
                            "user_id": "660978",
                            "symbol": "ETHUSDT",
                            "side": "Buy",
                            "order_type": "Limit",
                            "time_in_force": "GoodTillCancel",
                            "order_status": "Untriggered",
                            "tp_trigger_by": "UNKNOWN",
                            "sl_trigger_by": "UNKNOWN",
                            "price": "{}".format(self.hedging_entry_price),
                            "qty": "{}".format(abs(self.primary_entry_qty)),
                            "order_link_id": "",
                            "reduce_only": False,
                            "close_on_trigger": False,
                            "take_profit": "0",
                            "stop_loss": "0",
                            "created_time": "2022-12-28T11:55:14Z",
                            "updated_time": "2022-12-28T14:50:47Z"
                        },
                        "id": "823f4c52-2be2-4fb2-9231-fd3281733e5f",
                        "clientOrderId": None,
                        "timestamp": 1672228514000,
                        "datetime": "2022-12-28T11:55:14.000Z",
                        "lastTradeTimestamp": 1672239047000,
                        "symbol": "ETH/USDT:USDT",
                        "type": "limit",
                        "timeInForce": "GTC",
                        "postOnly": False,
                        "side": "buy",
                        "price": self.hedging_entry_price,
                        "stopPrice": "{}".format(self.hedging_entry_price),
                        "amount": abs(self.primary_entry_qty),
                        "cost": None,
                        "average": None,
                        "filled": None,
                        "remaining": None,
                        "status": CCXT_COMMON_MAPPING_VALUES[OPEN_VALUE],
                        "fee": None,
                        "trades": [],
                        "fees": []
                    }

                # The later CCXT order that has been updated with new size which will be returned by exchange
                self.hedging_entry__ccxt_order = \
                    {
                        "info": {
                            "stop_order_id": "823f4c52-2be2-4fb2-9231-fd3281733e5f",
                            "trigger_price": "{}".format(self.hedging_entry_price),
                            "base_price": "1193.55",
                            "trigger_by": "LastPrice",
                            "user_id": "660978",
                            "symbol": "ETHUSDT",
                            "side": "Buy",
                            "order_type": "Limit",
                            "time_in_force": "GoodTillCancel",
                            "order_status": "Filled",
                            "tp_trigger_by": "UNKNOWN",
                            "sl_trigger_by": "UNKNOWN",
                            "price": "{}".format(self.hedging_entry_price),
                            "qty": "{}".format(abs(self.hedging_entry_qty)),
                            "order_link_id": "",
                            "reduce_only": False,
                            "close_on_trigger": False,
                            "take_profit": "0",
                            "stop_loss": "0",
                            "created_time": "2022-12-28T11:55:14Z",
                            "updated_time": "2022-12-28T14:50:47Z"
                        },
                        "id": "823f4c52-2be2-4fb2-9231-fd3281733e5f",
                        "clientOrderId": None,
                        "timestamp": 1672228514000,
                        "datetime": "2022-12-28T11:55:14.000Z",
                        "lastTradeTimestamp": 1672239047000,
                        "symbol": "ETH/USDT:USDT",
                        "type": "limit",
                        "timeInForce": "GTC",
                        "postOnly": False,
                        "side": "buy",
                        "price": self.hedging_entry_price,
                        "stopPrice": "{}".format(self.hedging_entry_price),
                        "amount": abs(self.hedging_entry_qty),
                        "cost": None,
                        "average": None,
                        "filled": None,
                        "remaining": None,
                        "status": CCXT_COMMON_MAPPING_VALUES[CLOSED_VALUE],
                        "fee": None,
                        "trades": [],
                        "fees": []
                    }

                # Ideal situation
                bt_ccxt_order__dict = dict(
                    owner=self,
                    exchange_dropdown_value=self.bt_ccxt_account_or_store.exchange_dropdown_value,
                    symbol_id=symbol_id,
                    position_type=backtrader.Position.LONG_POSITION,
                    datafeed=self.long_bb_data,
                    ccxt_order=offset_entry__ccxt_order,
                    # ccxt_order=hedging_entry__ccxt_order,
                )
                reverse_engineered__bt_ccxt_order__dict = ut_reverse_engineer__ccxt_order(
                    bt_ccxt_order__dict)
                self.hedging_entry_order = BT_CCXT_Order(
                    **reverse_engineered__bt_ccxt_order__dict)

        except Exception:
            traceback.print_exc()

    def tearDown(self):
        try:
            if self.bt_ccxt_account_or_store is not None:
                if self.bt_ccxt_account_or_store.is_ws_available:
                    self.bt_ccxt_account_or_store.close_bybit_websocket()

            self.bt_ccxt_account_or_store = None
            pass
        except Exception:
            traceback.print_exc()

    @unittest.skip("Only run if required")
    def test_01__fetch__primary_order(self):
        start = timer()
        try:
            primary_entry_order_id = "41992e55-3ed8-4ea0-80f6-085a36e73d86"
            ccxt_order = \
                self.bt_ccxt_account_or_store.fetch_ccxt_order(self.symbol_id,
                                                               order_id=primary_entry_order_id,
                                                               stop_order_id=None)

            frameinfo = inspect.getframeinfo(inspect.currentframe())
            msg = "{} Line: {}: INFO: ".format(
                frameinfo.function, frameinfo.lineno,
            )
            sub_msg = "ccxt_order:"
            print(msg + sub_msg)
            pprint(ccxt_order, indent=self.bt_ccxt_account_or_store.indent)

            pass
        except Exception:
            traceback.print_exc()

        _, minutes, seconds = get_time_diff(start)
        frameinfo = inspect.getframeinfo(inspect.currentframe())
        print("{} Line: {}: Took {}m:{:.2f}s".format(frameinfo.function, frameinfo.lineno,
                                                     int(minutes), seconds))

    @unittest.skip("Only run if required")
    def test_02__fetch__hedging_order(self):
        start = timer()
        try:
            hedging_entry_order_id = "823f4c52-2be2-4fb2-9231-fd3281733e5f"
            ccxt_order = \
                self.bt_ccxt_account_or_store.fetch_ccxt_order(self.symbol_id,
                                                               order_id=None,
                                                               stop_order_id=hedging_entry_order_id)

            frameinfo = inspect.getframeinfo(inspect.currentframe())
            msg = "{} Line: {}: INFO: ".format(
                frameinfo.function, frameinfo.lineno,
            )
            sub_msg = "ccxt_order:"
            print(msg + sub_msg)
            pprint(ccxt_order, indent=self.bt_ccxt_account_or_store.indent)

            pass
        except Exception:
            traceback.print_exc()

        _, minutes, seconds = get_time_diff(start)
        frameinfo = inspect.getframeinfo(inspect.currentframe())
        print("{} Line: {}: Took {}m:{:.2f}s".format(frameinfo.function, frameinfo.lineno,
                                                     int(minutes), seconds))

    # @unittest.skip("To be enabled")
    # @unittest.skip("Ready for regression")
    def test_10__execute__primary_order(self):
        start = timer()
        try:
            current_price = self.primary_entry_price

            # Test Assumption
            self.assertEqual(self.primary_entry_order.price,
                             self.primary_entry_price)
            self.assertEqual(self.primary_entry_order.size,
                             self.primary_entry_qty)
            self.assertEqual(
                self.primary_entry_order.executed.remaining_size, self.primary_entry_qty)

            self.bt_ccxt_account_or_store.execute(
                self.primary_entry_order, current_price)

            # Test Assertion
            self.assertEqual(
                self.primary_entry_order.executed.price, self.primary_entry_price)
            self.assertEqual(
                self.primary_entry_order.executed.size, self.primary_entry_qty)
            self.assertEqual(
                self.primary_entry_order.executed.remaining_size, 0.0)
            pass
        except Exception:
            traceback.print_exc()

        _, minutes, seconds = get_time_diff(start)
        frameinfo = inspect.getframeinfo(inspect.currentframe())
        print("{} Line: {}: Took {}m:{:.2f}s".format(frameinfo.function, frameinfo.lineno,
                                                     int(minutes), seconds))

    # @unittest.skip("To be enabled")
    # @unittest.skip("Ready for regression")
    def test_11__execute__primary_order_and_then_hedging_order(self):
        start = timer()
        try:
            current_price = self.hedging_entry_price

            self.bt_ccxt_account_or_store.execute(
                self.primary_entry_order, current_price)

            # Mimicking actual situation in exchange due to modification of hedging size
            self.hedging_entry_order.extract_from_ccxt_order(
                self.hedging_entry__ccxt_order)
            self.hedging_entry_order.executed.remaining_size = self.hedging_entry_qty

            # Test Assumption
            self.assertEqual(self.hedging_entry_order.price,
                             self.hedging_entry_price)
            self.assertEqual(self.hedging_entry_order.size,
                             self.hedging_entry_qty)
            self.assertEqual(
                self.hedging_entry_order.executed.remaining_size, self.hedging_entry_qty)

            self.bt_ccxt_account_or_store.execute(
                self.hedging_entry_order, current_price)

            # Test Assertion
            self.assertEqual(
                self.hedging_entry_order.executed.price, self.hedging_entry_price)
            self.assertEqual(
                self.hedging_entry_order.executed.size, self.hedging_entry_qty)
            self.assertEqual(
                self.hedging_entry_order.executed.remaining_size, 0.0)
            pass
        except Exception:
            traceback.print_exc()

        _, minutes, seconds = get_time_diff(start)
        frameinfo = inspect.getframeinfo(inspect.currentframe())
        print("{} Line: {}: Took {}m:{:.2f}s".format(frameinfo.function, frameinfo.lineno,
                                                     int(minutes), seconds))


if __name__ == '__main__':
    unittest.main()
