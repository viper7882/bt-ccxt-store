#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
#
# Copyright (C) 2017 Ed Bartosh <bartosh@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
###############################################################################
import backtrader
import ccxt
import collections
import copy
import datetime
import gc
import inspect
import json
import math
import time
import traceback
import websocket

from backtrader.utils.py3 import queue
from ccxt.base.errors import NetworkError, ExchangeError, OrderNotFound
from functools import wraps

from pybit import usdt_perpetual
from pprint import pprint
from time import time as timer

from ccxtbt.bt_ccxt_exchange__classes import BT_CCXT_Exchange
from ccxtbt.bt_ccxt_order__classes import BT_CCXT_Order
from ccxtbt.bt_ccxt_order__helper import converge_ccxt_reduce_only_value, get_ccxt_order_id, \
    reverse_engineer__ccxt_order
from ccxtbt.bt_ccxt__specifications import CANCELED_ORDER, CASH_DIGITS, CCXT_ORDER_KEYS__MUST_BE_IN_FLOAT, \
    CCXT_ORDER_TYPES, CCXT_SIDE_KEY, CCXT_SYMBOL_KEY, CCXT__MARKET_TYPES, CCXT__MARKET_TYPE__FUTURE, \
    CCXT__MARKET_TYPE__LINEAR_PERPETUAL_SWAP, CCXT__MARKET_TYPE__SPOT, \
    CLOSED_ORDER, DERIVED__CCXT_ORDER__KEYS, EXECUTION_TYPE, EXPIRED_ORDER, LIST_OF_CCXT_KEY_TO_BE_RENAMED, \
    MAX_LEVERAGE_IN_PERCENT, \
    MIN_LEVERAGE, \
    MIN_LEVERAGE_IN_PERCENT, OPENED_ORDER, ORDERING_TYPE, ORDER_INTENT, PARTIALLY_FILLED_ORDER, POSITION_TYPE, \
    REJECTED_ORDER
from ccxtbt.exchange.binance.binance__exchange__helper import get_binance_leverages, set_binance_leverage
from ccxtbt.exchange.binance.binance__exchange__specifications import BINANCE_EXCHANGE_ID, \
    BINANCE__FUTURES__DEFAULT_DUAL_POSITION_MODE
from ccxtbt.exchange.bybit.bybit__exchange__helper import get_bybit_leverages, get_ccxt_market_symbol_name, \
    set_bybit_leverage
from ccxtbt.exchange.bybit.bybit__exchange__specifications import BYBIT_EXCHANGE_ID
from ccxtbt.exchange.exchange__helper import get_symbol_id
from ccxtbt.utils import capitalize_sentence, convert_slider_from_percent, legality_check_not_none_obj, \
    round_to_nearest_decimal_points, truncate, get_time_diff


class Meta_Account_or_Store(backtrader.Broker_or_Exchange_Base.__class__):
    def __init__(cls, name, bases, dct):
        '''
        Class has already been created ... fill missing methods if needed be
        '''
        # Initialize the class
        super().__init__(name, bases, dct)

        # Register with broker_or_exchange
        BT_CCXT_Exchange.Account_or_Store_Cls = cls


class BT_CCXT_Account_or_Store(backtrader.with_metaclass(Meta_Account_or_Store, backtrader.Broker_or_Exchange_Base)):
    '''API provider for CCXT feed and broker_or_exchange classes.

    Added a new get_wallet_balance method. This will allow manual checking of the balance.
        The method will allow setting parameters. Useful for getting margin balances

    Added new private_end_point method to allow using any private non-unified end point
    '''

    # Supported granularities
    _GRANULARITIES = {
        (backtrader.TimeFrame.Minutes, 1): '1m',
        (backtrader.TimeFrame.Minutes, 3): '3m',
        (backtrader.TimeFrame.Minutes, 5): '5m',
        (backtrader.TimeFrame.Minutes, 15): '15m',
        (backtrader.TimeFrame.Minutes, 30): '30m',
        (backtrader.TimeFrame.Hours, 1): '1h',
        (backtrader.TimeFrame.Minutes, 90): '90m',
        (backtrader.TimeFrame.Hours, 2): '2h',
        (backtrader.TimeFrame.Hours, 3): '3h',
        (backtrader.TimeFrame.Hours, 4): '4h',
        (backtrader.TimeFrame.Hours, 6): '6h',
        (backtrader.TimeFrame.Hours, 8): '8h',
        (backtrader.TimeFrame.Hours, 12): '12h',
        (backtrader.TimeFrame.Days, 1): '1d',
        (backtrader.TimeFrame.Days, 3): '3d',
        (backtrader.TimeFrame.Weeks, 1): '1w',
        (backtrader.TimeFrame.Weeks, 2): '2w',
        (backtrader.TimeFrame.Months, 1): '1M',
        (backtrader.TimeFrame.Months, 3): '3M',
        (backtrader.TimeFrame.Months, 6): '6M',
        (backtrader.TimeFrame.Years, 1): '1y',
    }

    Instrument_Cls = None  # datafeed class will auto register

    @classmethod
    def instantiate_instrument(cls, *args, **kwargs):
        '''Returns ``Instrument_Cls`` with args, kwargs'''
        return cls.Instrument_Cls(*args, **kwargs)

    def retry(method):
        @wraps(method)
        def retry_method(self, *args, **kwargs):
            for i in range(self.retries):
                if self.debug:
                    print(
                        '{} - {} - Attempt {}'.format(datetime.datetime.now(), method.__name__, i))
                time.sleep(self.exchange.rateLimit / 1000)
                try:
                    return method(self, *args, **kwargs)
                except (NetworkError, ExchangeError) as e:
                    if i == self.retries - 1:
                        raise

                    if isinstance(e, ExchangeError):
                        # Extract the exchange name from the exception
                        json_error = e.args[0].replace(
                            self.exchange_dropdown_value + " ", "")
                        exchange_error_dict = json.loads(json_error)
                        if self.exchange_dropdown_value == BYBIT_EXCHANGE_ID:
                            if exchange_error_dict['ret_code'] == 130125:
                                '''
                                'ret_msg' = 'current position is zero, cannot fix reduce-only order qty'
                                '''
                                break
                            elif exchange_error_dict['ret_code'] == 130074:
                                '''
                                'ret_msg' = 'expect Rising, but trigger_price[12705000] <= current[12706500]'
                                '''
                                # This error is likely caused by base_price is incorrectly configured. Hence, it should
                                # be raised immediately without retry
                                raise
                            elif exchange_error_dict['ret_code'] == 130075:
                                '''
                                'ret_msg' = 'expect Failling, but trigger_price[11975000] \u003e= current[11968000]??1'
                                '''
                                # This error is likely caused by base_price is incorrectly configured. Hence, it should
                                # be raised immediately without retry
                                raise
                            elif exchange_error_dict['ret_code'] == 130010:
                                '''
                                'ret_msg' = 'order not exists or too late to repalce'
                                '''
                                break

                            # Print out warning regarding the response received from ExchangeError
                            frameinfo = inspect.getframeinfo(
                                inspect.currentframe())
                            msg = "{} Line: {}: INFO: {}: {}/{}: ".format(
                                frameinfo.function, frameinfo.lineno,
                                datetime.datetime.now().isoformat().replace(
                                    "T", " ")[:-3],
                                i + 1, self.retries,
                            )
                            sub_msg = "{}: ret_code: {}, ret_msg: {}{}".format(
                                self.exchange_dropdown_value,
                                exchange_error_dict['ret_code'],
                                exchange_error_dict['ret_msg'],
                                " " * 3,
                            )

                            # Credits: https://stackoverflow.com/questions/3419984/print-to-the-same-line-and-not-a-new-line
                            # Print on the same line without newline, customized accordingly to cater for our requirement
                            print("\r" + msg + sub_msg, end="")

                    pass

        return retry_method

    def __init__(self, exchange_dropdown_value, wallet_currency, config, retries, symbols_id,
                 main_net_toggle_switch_value, initial__capital_reservation__value, is_ohlcv_provider,
                 account__thread__connectivity__lock, isolated_toggle_switch_value, leverage_in_percent, debug=False):
        super().__init__()

        # WARNING: Must rename to init2 here or else it will cause
        #          TypeError: BT_CCXT_Account_or_Store.init() missing 7 required positional arguments:
        self.init2(exchange_dropdown_value, wallet_currency, config, retries, symbols_id, main_net_toggle_switch_value,
                   initial__capital_reservation__value, is_ohlcv_provider, account__thread__connectivity__lock,
                   isolated_toggle_switch_value, leverage_in_percent, debug)

    def init2(self, exchange_dropdown_value, wallet_currency, config, retries, symbols_id, main_net_toggle_switch_value,
              initial__capital_reservation__value, is_ohlcv_provider, account__thread__connectivity__lock,
              isolated_toggle_switch_value, leverage_in_percent, debug=False):
        # Legality Check
        assert isinstance(retries, int)
        assert isinstance(symbols_id, list)
        assert isinstance(main_net_toggle_switch_value, bool)
        assert isinstance(initial__capital_reservation__value, int) or \
            isinstance(initial__capital_reservation__value, float)
        assert isinstance(is_ohlcv_provider, bool)
        assert isinstance(isolated_toggle_switch_value, bool)
        assert isinstance(leverage_in_percent, int) or \
            isinstance(leverage_in_percent, float)

        # Alias
        self.wallet_currency = wallet_currency
        self.account_alias = config['account_alias']
        self.account_type = config['account_type']
        self.market_type = config['market_type']
        self.market_type_name = config['type']
        self.retries = retries
        self.symbols_id = symbols_id
        self.main_net_toggle_switch_value = main_net_toggle_switch_value
        self.isolated_toggle_switch_value = isolated_toggle_switch_value
        self._initial__capital_reservation__value = initial__capital_reservation__value
        self._live__capital_reservation__value = initial__capital_reservation__value
        self.is_ohlcv_provider = is_ohlcv_provider
        self.account__thread__connectivity__lock = account__thread__connectivity__lock
        self.debug = debug
        self._cash_snapshot = 0.0

        # Legality Check
        legality_check_not_none_obj(self.account__thread__connectivity__lock,
                                    "self.account__thread__connectivity__lock")
        if self.market_type not in range(len(CCXT__MARKET_TYPES)):
            raise ValueError("{}: {} market_type must be one of {}!!!".format(
                inspect.currentframe(), self.market_type, range(len(CCXT__MARKET_TYPES))))

        self.parent = None
        self.ccxt_instruments = []

        self.account = collections.defaultdict(
            backtrader.utils.AutoOrderedDict)
        self.exchange = getattr(ccxt, exchange_dropdown_value)(config)
        self.exchange.set_sandbox_mode(not self.main_net_toggle_switch_value)

        # Alias
        self.exchange_dropdown_value = self.exchange.name.lower()

        # Preload all markets from the exchange base on the market type specified by user
        load_markets__dict = dict(
            type=config['type'],  # CCXT Market Type
        )
        self.exchange.load_markets(params=load_markets__dict)

        self.config__api_key = None
        self.config__api_secret = None

        self.notifs = queue.Queue()  # holds orders which are notified
        self.open_orders = list()
        self.indent = 4  # For pretty printing dictionaries

        # 30 seconds of retry
        self.max_retry = 30 * 10

        # Track the partially_filled_earlier status
        self.partially_filled_earlier = None

        # Invoke websocket if available
        self.is_ws_available = False
        self.ws_mainnet_usdt_perpetual = None
        self.ws_usdt_perpetual = None
        self.twm = None

        # For sensitive section, apply thread-safe locking mechanism to guarantee connection is completely
        #       established before moving on to another thread
        with self.account__thread__connectivity__lock:
            # Support for Binance below
            if self.exchange_dropdown_value == BINANCE_EXCHANGE_ID:
                self.fetch_balance__dict = dict(
                    type=config['type'],
                )
                self.config__api_key = config['apiKey']
                self.config__api_secret = config['secret']
                # self.is_ws_available = True
                #
                # Gated by: https://github.com/sammchardy/python-binance/issues/1243
                # # socket manager using threads
                # twm__dict = dict(
                #     api_key=config['apiKey'],
                #     api_secret=config['secret'],
                # )
                # self.twm = binance.ThreadedWebsocketManager(**twm__dict)
                # self.twm.start()
                #
                # self.establish_binance_websocket()
                pass
            # Support for Bybit below
            elif self.exchange_dropdown_value == BYBIT_EXCHANGE_ID:
                self.is_ws_available = True
                self.config__api_key = config['apiKey']
                self.config__api_secret = config['secret']
                self.fetch_balance__dict = {}

                self.ws_instrument_info = collections.defaultdict(tuple)
                self.ws_klines = collections.defaultdict(tuple)
                self.ws_active_orders = collections.defaultdict(list)
                self.ws_conditional_orders = collections.defaultdict(list)
                self.ws_positions = collections.defaultdict(list)

                self.establish_bybit_websocket()
            else:
                self.ws_instrument_info = None
                self.ws_klines = None
                self.ws_active_orders = None
                self.ws_conditional_orders = None
                self.ws_positions = None

            balance = \
                self.exchange.fetch_balance(
                    params=self.fetch_balance__dict) if 'secret' in config else 0.0
            try:
                if balance == 0 or not balance['free'][wallet_currency]:
                    self._cash = 0
                else:
                    self._cash = balance['free'][wallet_currency]
            except KeyError:  # never funded or eg. all USD exchanged
                self._cash = 0

            try:
                if balance == 0 or not balance['total'][wallet_currency]:
                    self._value = 0
                else:
                    self._value = balance['total'][wallet_currency]
            except KeyError:
                self._value = 0

        # It is crucial to initialize leverage here
        self.set_leverage_in_percent(leverage_in_percent)

    def set_leverage_in_percent(self, leverage_in_percent, position_value=0.0):
        # Legality Check
        legality_check_not_none_obj(leverage_in_percent, "leverage_in_percent")
        assert isinstance(leverage_in_percent, int) or isinstance(
            leverage_in_percent, float)

        if leverage_in_percent < MIN_LEVERAGE_IN_PERCENT or leverage_in_percent > MAX_LEVERAGE_IN_PERCENT:
            raise RuntimeError("leverage_in_percent: {} must be from {} -> {}!!!".format(
                leverage_in_percent,
                MIN_LEVERAGE_IN_PERCENT,
                MAX_LEVERAGE_IN_PERCENT,
            ))

        success = True
        self.leverage_in_percent = leverage_in_percent

        # Support for Binance and Bybit below
        if self.exchange_dropdown_value == BINANCE_EXCHANGE_ID or self.exchange_dropdown_value == BYBIT_EXCHANGE_ID:
            if self.market_type == CCXT__MARKET_TYPE__FUTURE or \
                    self.market_type == CCXT__MARKET_TYPE__LINEAR_PERPETUAL_SWAP:
                for symbol_id in self.symbols_id:
                    get_leverage__dict = dict(
                        bt_ccxt_account_or_store=self,
                        market_type=self.market_type,
                        symbol_id=symbol_id,
                        notional_value=position_value,
                    )
                    if self.exchange_dropdown_value == BINANCE_EXCHANGE_ID:
                        (from_leverage, max_leverage,) = get_binance_leverages(
                            params=get_leverage__dict)
                    else:
                        assert self.exchange_dropdown_value == BYBIT_EXCHANGE_ID

                        (from_leverage, max_leverage,) = get_bybit_leverages(
                            params=get_leverage__dict)

                    to_leverage = int(convert_slider_from_percent(
                        self.leverage_in_percent, MIN_LEVERAGE, max_leverage))

                    if to_leverage != from_leverage:
                        set_leverage__dict = copy.copy(get_leverage__dict)
                        set_leverage__dict.update(dict(
                            from_leverage=from_leverage,
                            to_leverage=to_leverage,
                        ))
                        if self.exchange_dropdown_value == BINANCE_EXCHANGE_ID:
                            set_binance_leverage(params=set_leverage__dict)
                        else:
                            assert str(self.exchange).lower(
                            ) == BYBIT_EXCHANGE_ID

                            set_bybit_leverage(params=set_leverage__dict)
                    else:
                        success = False
            # Spot Market does not support leverage
        else:
            raise NotImplementedError(
                "{} exchange is yet to be supported!!!".format(self.exchange_dropdown_value))
        return success

    def __repr__(self):
        return str(self)

    def __str__(self):
        items = list()
        items.append('--- BT_CCXT_Account_or_Store Begin ---')
        items.append('- Alias: {}'.format(self.account_alias))
        items.append('--- BT_CCXT_Account_or_Store End ---')
        ret_value = str('\n'.join(items))
        return ret_value

    def set__parent(self, owner):
        self.parent = owner

        # Run post-processing AFTER parent has been set
        self._post_process__after_parent_is_added()

    def get__parent(self):
        return self.parent

    def add__instrument(self, instrument):
        found_instrument = False
        for ccxt_instrument in self.ccxt_instruments:
            if instrument._name == ccxt_instrument._name:
                found_instrument = True
                break

        if found_instrument == False:
            self.ccxt_instruments.append(instrument)

    def get__child(self, symbol_id):
        legality_check_not_none_obj(symbol_id, "symbol_id")

        instrument = None
        for ccxt_instrument in self.ccxt_instruments:
            if ccxt_instrument.symbol_id == symbol_id:
                instrument = ccxt_instrument
                break

        legality_check_not_none_obj(instrument, "instrument")
        return instrument

    def add_commission_info(self, commission_info):
        raise NotImplementedError(
            "This method should be implemented in instrument instead!!!")

    def get_commission_info(self):
        raise NotImplementedError(
            "This method should be implemented in instrument instead!!!")

    def get_balance(self) -> tuple:
        self._get_balance()
        self.cash = self._cash
        self.value = self._value
        ret_value = self.cash, self.value
        return ret_value

    def get_wallet_balance(self, currency, params={}):
        balance = self._get_wallet_balance(params=params)
        try:
            cash = balance['free'][currency] if balance['free'][currency] else 0
        except KeyError:  # never funded or eg. all USD exchanged
            cash = 0
        try:
            value = balance['total'][currency] if balance['total'][currency] else 0
        except KeyError:  # never funded or eg. all USD exchanged
            value = 0
        return cash, value

    def get_cash(self, force=False):
        if force == True:
            self._get_balance()
        self._cash = truncate(self._cash, CASH_DIGITS)
        self.cash = self._cash
        return self.cash

    def get_value(self, datafeeds=None):
        self.value = self._value
        return self.value

    def set_live__capital_reservation__value(self, live__capital_reservation__value):
        self._live__capital_reservation__value = live__capital_reservation__value

    def get_live__capital_reservation__value(self):
        return self._live__capital_reservation__value

    def get_initial__capital_reservation__value(self):
        return self._initial__capital_reservation__value

    def set_cash_snapshot(self):
        self._cash_snapshot = self.cash

    def get_cash_snapshot(self):
        return self._cash_snapshot

    def get_notification(self):
        try:
            return self.notifs.get(False)
        except queue.Empty:
            return None

    def notify(self, order):
        # Legality Check
        frameinfo = inspect.getframeinfo(inspect.currentframe())
        assert type(order).__name__ == BT_CCXT_Order.__name__, \
            "{} Line: {}: Expected {} but observed {} instead!!!".format(
                frameinfo.function, frameinfo.lineno,
                BT_CCXT_Order.__name__, type(order).__name__,
        )
        self.notifs.put(order)

    def next(self):
        if self.debug:
            # # TODO: Debug use
            # if len(self.open_orders) > 0:
            #     frameinfo = inspect.getframeinfo(inspect.currentframe())
            #     msg = "{} Line: {}: DEBUG: len(self.open_orders): {}".format(
            #         frameinfo.function, frameinfo.lineno,
            #         len(self.open_orders),
            #     )
            #     print(msg)
            pass

        for order in self.open_orders:
            ccxt_order_id = order.ccxt_order['id']

            # Print debug before fetching so we know which order is giving an
            # issue if it crashes
            if self.debug:
                # # TODO: Debug use
                # frameinfo = inspect.getframeinfo(inspect.currentframe())
                # msg = "{} Line: {}: DEBUG: ".format(
                #     frameinfo.function, frameinfo.lineno,
                # )
                # msg += "order.ccxt_order:"
                # print(msg)
                # print(json.dumps(order.ccxt_order, indent=self.indent))
                # msg += "order.executed:"
                # print(msg)
                # dump_obj(order.executed, "order.executed")
                # msg += "order.created:"
                # print(msg)
                # dump_obj(order.created, "order.created")
                pass

            if self.partially_filled_earlier is not None:
                # Carry forward partially_filled_earlier status to the next order
                order.partially_filled_earlier = self.partially_filled_earlier

            # Get the order
            if order.ordering_type == backtrader.Order.ACTIVE_ORDERING_TYPE:
                if self.debug:
                    # # TODO: Debug use
                    # frameinfo = inspect.getframeinfo(inspect.currentframe())
                    # msg = "{} Line: {}: DEBUG: ordering_type == backtrader.Order.ACTIVE_ORDERING_TYPE, ".format(
                    #     frameinfo.function, frameinfo.lineno,
                    # )
                    # msg += "order_id: {}".format(ccxt_order_id)
                    # print(msg)
                    pass

                new_ccxt_order = self.fetch_ccxt_order(
                    order.symbol_id, order_id=ccxt_order_id)
            else:
                # Validate assumption made
                assert order.ordering_type == backtrader.Order.CONDITIONAL_ORDERING_TYPE

                if self.debug:
                    # # TODO: Debug use
                    # frameinfo = inspect.getframeinfo(inspect.currentframe())
                    # msg = "{} Line: {}: DEBUG: ordering_type == backtrader.Order.CONDITIONAL_ORDERING_TYPE, ".format(
                    #     frameinfo.function, frameinfo.lineno,
                    # )
                    # msg += "stop_order_id: {}".format(ccxt_order_id)
                    # print(msg)
                    pass

                new_ccxt_order = self.fetch_ccxt_order(
                    order.symbol_id, stop_order_id=ccxt_order_id)

            if new_ccxt_order is None:
                if self.debug:
                    # # TODO: Debug use
                    # frameinfo = inspect.getframeinfo(inspect.currentframe())
                    # msg = "{} Line: {}: DEBUG: new_ccxt_order is None, skipping....".format(
                    #     frameinfo.function, frameinfo.lineno,
                    # )
                    # print(msg)
                    pass

                continue

            '''
            next Line: 397: DEBUG: ccxt_order:
            {
                "info": {
                    "order_id": "b788dac1-8ebd-4bdb-9a5e-265ffee07b7d",
                    "order_link_id": "",
                    "symbol": "ETHUSDT",
                    "side": "Buy",
                    "order_type": "Market",
                    "price": 1272.6,
                    "qty": 0.61,
                    "leaves_qty": 0,
                    "last_exec_price": 1212,
                    "cum_exec_qty": 0.61,
                    "cum_exec_value": 739.31995,
                    "cum_exec_fee": 0.443592,
                    "time_in_force": "ImmediateOrCancel",
                    "create_type": "CreateByUser",
                    "cancel_type": "UNKNOWN",
                    "order_status": "Filled",
                    "take_profit": 0,
                    "stop_loss": 0,
                    "trailing_stop": 0,
                    "create_time": "2022-11-27T13:48:13.684754416Z",
                    "update_time": "2022-11-27T13:48:13.687587957Z",
                    "reduce_only": false,
                    "close_on_trigger": false,
                    "position_idx": "1"
                },
                "id": "b788dac1-8ebd-4bdb-9a5e-265ffee07b7d",
                "clientOrderId": null,
                "timestamp": 1669556893684,
                "datetime": "2022-11-27T13:48:13.684Z",
                "lastTradeTimestamp": 1669556893687,
                "symbol": "ETHUSDT",
                "type": "market",
                "timeInForce": "IOC",
                "postOnly": false,
                "side": "buy",
                "price": 1272.6,
                "stopPrice": null,
                "amount": 0.61,
                "cost": 739.31995,
                "average": 1211.9999180327868,
                "filled": 0.61,
                "remaining": 0.0,
                "status": "closed",
                "fee": {
                    "cost": 0.443592,
                    "currency": "USDT"
                },
                "trades": [],
                "fees": [
                    {
                        "cost": 0.443592,
                        "currency": "USDT"
                    }
                ]
            }
            '''
            # Check for new fills
            if 'trades' in new_ccxt_order and new_ccxt_order['trades'] is not None:
                for fill in new_ccxt_order['trades']:
                    if fill not in order.executed_fills:
                        # Execute according to the OrderExecutionBit
                        dt = fill['datetime']
                        size = fill['amount']
                        price = fill['price']
                        closed = 0.0
                        closed_value = 0.0
                        closed_commission = 0.0
                        opened = 0.0
                        opened_value = 0.0
                        opened_commission = 0.0
                        margin = 0.0
                        profit_and_loss_amount = 0.0
                        spread_in_ticks = 0.0
                        position_size = 0.0
                        position_average_price = 0.0
                        order.execute(dt, size, price,
                                      closed, closed_value, closed_commission,
                                      opened, opened_value, opened_commission,
                                      margin, profit_and_loss_amount, spread_in_ticks,
                                      position_size, position_average_price)
                        order.executed_fills.append(fill['id'])

            # TODO: Debug use
            if self.debug:
                frameinfo = inspect.getframeinfo(inspect.currentframe())
                msg = "{} Line: {}: DEBUG: new_ccxt_order:".format(
                    frameinfo.function, frameinfo.lineno,
                )
                print(msg)
                print(json.dumps(new_ccxt_order, indent=self.indent))

            # Check if the exchange order is opened
            if new_ccxt_order[self.parent.mappings[CCXT_ORDER_TYPES[OPENED_ORDER]]['key']] == \
                    self.parent.mappings[CCXT_ORDER_TYPES[OPENED_ORDER]]['value']:
                if order.status != backtrader.Order.Accepted:
                    # Reset partially_filled_earlier status
                    self.partially_filled_earlier = None

                    # Refresh the content of ccxt_order with the latest ccxt_order
                    order.extract_from_ccxt_order(new_ccxt_order)
                    order.accept()

                    # Notify using clone so that UT could snapshot the order
                    self.notify(order.clone())
            # Check if the exchange order is partially filled
            elif new_ccxt_order[self.parent.mappings[CCXT_ORDER_TYPES[PARTIALLY_FILLED_ORDER]]['key']] == \
                    self.parent.mappings[CCXT_ORDER_TYPES[PARTIALLY_FILLED_ORDER]]['value']:
                if order.status != backtrader.Order.Partial:
                    # Refresh the content of ccxt_order with the latest ccxt_order
                    order.extract_from_ccxt_order(new_ccxt_order)
                    order.partial()

                    # Only notify but NOT execute as it wouldn't create any impact to the trade.update
                    # self.execute(order, order.price)

                    # Notify using clone so that UT could snapshot the order
                    self.notify(order.clone())

                    # Carry forward partially_filled_earlier status to the next order
                    self.partially_filled_earlier = order.partially_filled_earlier

                    instrument = self.get__child(order.p.symbol_id)
                    instrument.sync_symbol_positions()
            # Check if the exchange order is closed
            elif new_ccxt_order[self.parent.mappings[CCXT_ORDER_TYPES[CLOSED_ORDER]]['key']] == \
                    self.parent.mappings[CCXT_ORDER_TYPES[CLOSED_ORDER]]['value']:
                # Refresh the content of ccxt_order with the latest ccxt_order
                order.extract_from_ccxt_order(new_ccxt_order)
                order.completed()

                # Notify using clone so that UT could snapshot the order
                self.notify(order.clone())

                self.execute(order, order.price)
                assert order.executed.remaining_size == 0.0

                instrument = self.get__child(order.p.symbol_id)
                instrument.sync_symbol_positions()

                self.open_orders.remove(order)
            # Check if the exchange order is rejected
            elif new_ccxt_order[self.parent.mappings[CCXT_ORDER_TYPES[REJECTED_ORDER]]['key']] == \
                    self.parent.mappings[CCXT_ORDER_TYPES[REJECTED_ORDER]]['value']:
                # Refresh the content of ccxt_order with the latest ccxt_order
                order.extract_from_ccxt_order(new_ccxt_order)
                order.reject()
                # Notify using clone so that UT could snapshot the order
                self.notify(order.clone())
                self.open_orders.remove(order)
            # Manage case when an order is being Canceled or Expired from the Exchange
            #  from https://github.com/juancols/bt-ccxt-store/
            elif new_ccxt_order[self.parent.mappings[CCXT_ORDER_TYPES[CANCELED_ORDER]]['key']] == \
                    self.parent.mappings[CCXT_ORDER_TYPES[CANCELED_ORDER]]['value']:
                # Refresh the content of ccxt_order with the latest ccxt_order
                order.extract_from_ccxt_order(new_ccxt_order)
                order.cancel()
                # Notify using clone so that UT could snapshot the order
                self.notify(order.clone())
                self.open_orders.remove(order)
            elif new_ccxt_order[self.parent.mappings[CCXT_ORDER_TYPES[EXPIRED_ORDER]]['key']] == \
                    self.parent.mappings[CCXT_ORDER_TYPES[EXPIRED_ORDER]]['value']:
                # Refresh the content of ccxt_order with the latest ccxt_order
                order.extract_from_ccxt_order(new_ccxt_order)
                order.expire()
                self.notify(order.clone())
                self.open_orders.remove(order)
            else:
                msg = "{} Line: {}: {}: WARNING: ".format(
                    inspect.getframeinfo(inspect.currentframe()).function,
                    inspect.getframeinfo(inspect.currentframe()).lineno,
                    datetime.datetime.now().isoformat().replace("T", " ")[:-3],
                )
                sub_msg = "new_ccxt_order ID: {}, status: {} is not processed".format(
                    new_ccxt_order['id'],
                    new_ccxt_order[self.parent.mappings[CCXT_ORDER_TYPES[OPENED_ORDER]]['key']],
                )
                print(msg + sub_msg)
                pass

    def _submit(self, owner, symbol_id, datafeed, execution_type, side, amount, price, position_type, ordering_type,
                order_intent, simulated, params):
        if amount == 0.0 or price == 0.0:
            # do not allow failing orders
            msg = "{} Line: {}: ERROR: Invalid Price: {} x Size: {}!!!".format(
                inspect.getframeinfo(inspect.currentframe()).function,
                inspect.getframeinfo(inspect.currentframe()).lineno,
                price,
                amount,
            )
            print(msg)
            return None

        # CCXT requires the market type name to be specified correctly
        assert 'type' in params.keys()
        if params['type'] not in CCXT__MARKET_TYPES:
            raise RuntimeError("{}: {} type must be one of {}!!!".format(
                inspect.currentframe(), params['type'], CCXT__MARKET_TYPES))
        market_type = CCXT__MARKET_TYPES.index(params['type'])

        if order_intent not in range(len(backtrader.Order.Order_Intents)):
            raise ValueError("{} order_intent must be one of {}!!!".format(
                order_intent, range(len(backtrader.Order.Order_Intents))))

        execution_type_name = self.parent.order_types.get(
            execution_type) if execution_type else 'market'

        # Extract CCXT specific params if passed to the order
        order_params = params['params'] if 'params' in params else params
        start = timer()

        # all params are exchange specific: https://github.com/ccxt/ccxt/wiki/Manual#custom-order-params
        # Exchange will likely fail if the following entries are sent
        REMOVE__FOR__SPOT_MARKET = ('histnotify', '_checksubmit', )
        for attribute in REMOVE__FOR__SPOT_MARKET:
            order_params.pop(attribute)

        # TODO: User to perform exchange-specific parameter customization here
        if self.exchange_dropdown_value == BINANCE_EXCHANGE_ID:
            if market_type == CCXT__MARKET_TYPE__SPOT:
                '''
                Reference: https://binance-docs.github.io/apidocs/spot/en/#new-order-trade
                '''
                # Include timestamp
                order_params['timestamp'] = \
                    int(datetime.datetime.now().timestamp() * 1000)
                pass
            elif market_type == CCXT__MARKET_TYPE__FUTURE:
                '''
                Reference: https://binance-docs.github.io/apidocs/futures/en/#new-order-trade
                '''
                # Binance requires positionSide to be sent in Hedge Mode
                order_params['positionSide'] = \
                    backtrader.Position.Position_Types[position_type].upper()
            else:
                raise NotImplementedError("{} market type is not yet enabled for {} exchange".format(
                    CCXT__MARKET_TYPES[market_type],
                    self.exchange_dropdown_value,
                ))
            pass
        elif self.exchange_dropdown_value == BYBIT_EXCHANGE_ID:
            if market_type == CCXT__MARKET_TYPE__SPOT:
                raise NotImplementedError("{} market type is not yet enabled for {} exchange".format(
                    CCXT__MARKET_TYPES[market_type],
                    self.exchange_dropdown_value,
                ))
            elif market_type == CCXT__MARKET_TYPE__LINEAR_PERPETUAL_SWAP:
                if order_intent == backtrader.Order.Entry_Order:
                    if 'reduce_only' in order_params.keys():
                        assert order_params['reduce_only'] == False
                    else:
                        order_params['reduce_only'] = False
                elif order_intent == backtrader.Order.Exit_Order:
                    if 'reduce_only' in order_params.keys():
                        assert order_params['reduce_only'] == True
                    else:
                        order_params['reduce_only'] = True
                else:
                    raise NotImplementedError()
            else:
                raise NotImplementedError("{} market type is not yet enabled for {} exchange".format(
                    CCXT__MARKET_TYPES[market_type],
                    self.exchange_dropdown_value,
                ))
            pass
        else:
            pass

        if self.debug:
            # TODO: Debug use
            frameinfo = inspect.getframeinfo(inspect.currentframe())
            msg = "{} Line: {}: DEBUG: ".format(
                frameinfo.function, frameinfo.lineno,
            )
            msg += "symbol_id: {}, ".format(symbol_id)
            msg += "execution_type_name: {}, ".format(execution_type_name)
            msg += "side: {}, ".format(side)
            msg += "price: {}, ".format(price)
            msg += "amount: {}, ".format(amount)
            msg += "order_params:"
            print(msg)
            pprint(order_params)
            pass

        ret_ord = \
            self.create_order(symbol=symbol_id, order_type=execution_type_name, side=side, amount=amount,
                              price=price, params=order_params)

        if ret_ord is None or ret_ord['id'] is None:
            return None

        # Based on experience in Testnet, it is better to wait momentarily as the server will require time to
        #       process the order, inclusive of providing websocket response.
        time.sleep(0.1)

        # Perform exchange-specific parameter extraction here
        order_type_name = None
        if self.exchange_dropdown_value == BINANCE_EXCHANGE_ID:
            if market_type == CCXT__MARKET_TYPE__SPOT:
                assert 'stopPrice' in ret_ord.keys()
                if ret_ord['stopPrice'] is not None and float(ret_ord['stopPrice']) != 0.0:
                    order_id = None
                    stop_order_id = ret_ord['info']['orderId']
                    order_type_name = 'Conditional'
                else:
                    order_id = ret_ord['info']['orderId']
                    stop_order_id = None
                    order_type_name = 'Active'
            elif market_type == CCXT__MARKET_TYPE__FUTURE:
                assert 'stopPrice' in ret_ord['info'].keys()
                if float(ret_ord['info']['stopPrice']) != 0.0:
                    order_id = None
                    stop_order_id = ret_ord['info']['orderId']
                    order_type_name = 'Conditional'
                else:
                    order_id = ret_ord['info']['orderId']
                    stop_order_id = None
                    order_type_name = 'Active'
            else:
                raise NotImplementedError("{} market type is not yet enabled for {} exchange".format(
                    CCXT__MARKET_TYPES[market_type],
                    self.exchange_dropdown_value,
                ))
            pass
        elif self.exchange_dropdown_value == BYBIT_EXCHANGE_ID:
            if 'stop_order_id' in ret_ord['info'].keys():
                order_id = None
                stop_order_id = ret_ord['id']
                order_type_name = 'Conditional'
            else:
                order_id = ret_ord['id']
                stop_order_id = None
                order_type_name = 'Active'
        else:
            raise NotImplementedError(
                "{} exchange is yet to be supported!!!".format(self.exchange_dropdown_value))
        legality_check_not_none_obj(order_type_name, "order_type_name")

        # TODO: Debug use
        if self.debug:
            # # TODO: Debug use
            # frameinfo = inspect.getframeinfo(inspect.currentframe())
            # msg = "{} Line: {}: DEBUG: {}: {}: {} Order: ".format(
            #     frameinfo.function, frameinfo.lineno,
            #     threading.current_thread().name,
            #     datetime.datetime.now().isoformat().replace("T", " ")[:-3],
            #     order_type_name,
            # )
            # if order_id is not None:
            #     msg += "order_id: {}".format(order_id)
            # else:
            #     # Validate assumption made
            #     legality_check_not_none_obj(stop_order_id, "stop_order_id")
            #
            #     msg += "stop_order_id: {}".format(stop_order_id)
            # print(msg)
            pass

        start = timer()
        ccxt_order = \
            self.fetch_ccxt_order(
                symbol_id, order_id=order_id, stop_order_id=stop_order_id)
        if self.debug:
            _, minutes, seconds = get_time_diff(start)
            frameinfo = inspect.getframeinfo(inspect.currentframe())
            print("{} Line: {}: {}: {} Order, fetch_ccxt_order Took {}m:{:.2f}s".format(
                frameinfo.function, frameinfo.lineno,
                datetime.datetime.now().isoformat().replace("T", " ")[:-3],
                order_type_name,
                int(minutes), seconds)
            )

        legality_check_not_none_obj(ccxt_order, "ccxt_order")

        # TODO: Debug use
        if self.debug:
            frameinfo = inspect.getframeinfo(inspect.currentframe())
            msg = "{} Line: {}: DEBUG: {}: ".format(
                frameinfo.function, frameinfo.lineno,
                datetime.datetime.now().isoformat().replace("T", " ")[:-3],
            )
            msg += "[{}] ".format(
                backtrader.Order.Order_Intents[ccxt_order[DERIVED__CCXT_ORDER__KEYS[ORDER_INTENT]]]
            )
            msg += "{} Order, order_id: \'{}\' vs stop_order_id: \'{}\', submitted ccxt_order:".format(
                order_type_name,
                order_id,
                stop_order_id,
            )
            print(msg)
            print(json.dumps(ccxt_order, indent=self.indent))

        # Exposed simulated so that we could proceed with order without running cerebro
        bt_ccxt_order__dict = dict(
            owner=owner,
            exchange_dropdown_value=self.exchange_dropdown_value,
            symbol_id=symbol_id,
            ccxt_order=ccxt_order,
            execution_type=execution_type,
            position_type=position_type,
            ordering_type=ordering_type,
            order_intent=order_intent,
        )
        if datafeed is not None:
            # Assign the datafeed since it exists
            bt_ccxt_order__dict.update(dict(
                datafeed=datafeed,
            ))
        else:
            # Turn on simulated should there is no datafeed
            bt_ccxt_order__dict.update(dict(
                simulated=True,
            ))
        order = BT_CCXT_Order(**bt_ccxt_order__dict)

        # Mark order as submitted first
        order.submit()
        instrument = self.get__child(order.p.symbol_id)
        commission_info = instrument.get_commission_info()
        order.add_commission_info(commission_info)

        # Notify using clone so that UT could snapshot the order
        self.notify(order.clone())
        self.open_orders.append(order)

        # Explicitly call next one round prior to releasing order to caller. The intention is to provide guarantee for
        # caller to sync up position thereafter
        self.next()
        return order

    def fetch_ccxt_order(self, symbol_id, order_id=None, stop_order_id=None):
        # Mutually exclusive legality check
        if order_id is None:
            legality_check_not_none_obj(stop_order_id, "stop_order_id")

        if stop_order_id is None:
            legality_check_not_none_obj(order_id, "order_id")

        # One of these must be valid
        assert order_id is not None or stop_order_id is not None

        start = timer()
        ccxt_order = None

        # CCXT Market Type is explicitly required
        params = dict(
            type=self.market_type_name,
        )
        # Due to nature of order is processed async, the order could not be found immediately right after
        #       order is opened. Hence, perform retry to confirm if that's the case.
        for retry_no in range(self.max_retry):
            try:
                if stop_order_id is not None:
                    # Conditional Order
                    params.update(dict(
                        stop_order_id=stop_order_id,
                    ))
                    ccxt_order = \
                        self.fetch_order(
                            order_id=None, symbol_id=symbol_id, params=params)
                else:
                    # Active Order
                    ccxt_order = self.fetch_order(
                        order_id=order_id, symbol_id=symbol_id, params=params)

                if ccxt_order is not None:
                    if stop_order_id is not None:
                        order_type_name = 'Conditional'
                    else:
                        legality_check_not_none_obj(order_id, "order_id")
                        order_type_name = 'Active'

                    if self.debug:
                        # TODO: Debug use
                        frameinfo = inspect.getframeinfo(
                            inspect.currentframe())
                        msg = "{} Line: {}: DEBUG: {}: For ".format(
                            frameinfo.function, frameinfo.lineno,
                            datetime.datetime.now().isoformat().replace(
                                "T", " ")[:-3],
                        )
                        msg += "[{}] ".format(
                            backtrader.Order.Order_Intents[ccxt_order[DERIVED__CCXT_ORDER__KEYS[ORDER_INTENT]]]
                        )
                        msg += "{} Order, order_id: \'{}\' vs stop_order_id: \'{}\'".format(
                            order_type_name,
                            order_id,
                            stop_order_id,
                        )
                        print(msg)

                        frameinfo = inspect.getframeinfo(
                            inspect.currentframe())
                        msg = "{} Line: {}: DEBUG: {}: Found \'{}\' ".format(
                            frameinfo.function, frameinfo.lineno,
                            datetime.datetime.now().isoformat().replace(
                                "T", " ")[:-3],
                            order_id if order_id is not None else stop_order_id,
                        )
                        if ccxt_order[DERIVED__CCXT_ORDER__KEYS[ORDER_INTENT]] is not None:
                            msg += "[{}] ".format(
                                backtrader.Order.Order_Intents[ccxt_order[DERIVED__CCXT_ORDER__KEYS[ORDER_INTENT]]])
                        msg += "{} Order during retry#{}/{}".format(
                            order_type_name,
                            retry_no + 1,
                            self.max_retry,
                        )
                        print(msg)
                    break
            except OrderNotFound:
                time.sleep(0.1)
                pass

        if self.debug:
            _, minutes, seconds = get_time_diff(start)
            print("{} Line: {}: Took {}m:{:.2f}s".format(inspect.getframeinfo(inspect.currentframe()).function,
                                                         inspect.getframeinfo(
                                                             inspect.currentframe()).lineno,
                                                         int(minutes), seconds))

        # Confirmation
        assert ccxt_order['id'] == order_id if order_id is not None else stop_order_id, \
            "Expected: {}, Actual: {}".format(
                order_id if order_id is not None else stop_order_id, ccxt_order['id'])

        # Post-process the CCXT order so that they are consistent across multiple exchanges
        post_process__ccxt_orders__dict = dict(
            bt_ccxt_exchange=self.parent,
            bt_ccxt_account_or_store=self,
            ccxt_orders=[ccxt_order],
        )
        ccxt_orders = self._post_process__ccxt_orders(
            params=post_process__ccxt_orders__dict)
        return ccxt_orders[0]

    def execute(self, order, price, spread_in_ticks=1, dt_in_float=None, skip_notification=False):
        # Legality Check
        legality_check_not_none_obj(order, "order")
        # ago = None is used a flag for pseudo execution
        legality_check_not_none_obj(price, "price")
        assert math.isnan(price) == False, "price must not be NaN value!!!"
        assert isinstance(spread_in_ticks, int) or isinstance(
            spread_in_ticks, float)
        if dt_in_float is not None:
            assert isinstance(dt_in_float, float)
        assert isinstance(skip_notification, bool)

        datafeed = order.datafeed
        if datafeed is not None:
            position_timestamp_dt = datafeed.datetime.datetime(0)
        else:
            # Use the current UTC datetime
            position_timestamp_dt = datetime.datetime.utcnow()

        # Legality Check
        assert isinstance(position_timestamp_dt, datetime.datetime)

        if order.ccxt_order is None:
            ccxt_order_id = get_ccxt_order_id(self.exchange, order)
            legality_check_not_none_obj(
                order.ordering_type, "order.ordering_type")

            if order.ordering_type == backtrader.Order.ACTIVE_ORDERING_TYPE:
                if self.debug:
                    # TODO: Debug use
                    frameinfo = inspect.getframeinfo(inspect.currentframe())
                    msg = "{} Line: {}: DEBUG: ordering_type == backtrader.Order.ACTIVE_ORDERING_TYPE, ".format(
                        frameinfo.function, frameinfo.lineno,
                    )
                    msg += "ccxt_order_id: {}".format(ccxt_order_id)
                    print(msg)

                # Refresh Active Order
                order.ccxt_order = self.fetch_ccxt_order(
                    order.symbol_id, order_id=ccxt_order_id)
            else:
                # Validate assumption made
                assert order.ordering_type == backtrader.Order.CONDITIONAL_ORDERING_TYPE

                if self.debug:
                    # TODO: Debug use
                    frameinfo = inspect.getframeinfo(inspect.currentframe())
                    msg = "{} Line: {}: DEBUG: ordering_type == backtrader.Order.CONDITIONAL_ORDERING_TYPE, ".format(
                        frameinfo.function, frameinfo.lineno,
                    )
                    msg += "ccxt_order_id: {}".format(ccxt_order_id)
                    print(msg)

                # Refresh Conditional Order
                order.ccxt_order = self.fetch_ccxt_order(
                    order.symbol_id, stop_order_id=ccxt_order_id)

        # Legality Check
        legality_check_not_none_obj(order.ccxt_order, "order.ccxt_order")

        # Refresh the content of ccxt_order with the latest ccxt_order
        order.extract_from_ccxt_order(order.ccxt_order)

        if order.status == order.Partial:
            size = order.executed.filled_size
        else:
            # Refresh contents of executed with the latest size
            remaining_size = abs(order.filled)
            if order.order_type == backtrader.Order.Sell:
                # Invert the sign
                remaining_size = -remaining_size
            order.executed = backtrader.OrderData(
                remaining_size=remaining_size)

            size = order.executed.remaining_size

        if size == 0.0:
            if skip_notification == False:
                # Notify using clone so that UT could snapshot the order
                self.notify(order.clone())
            return

        instrument = self.get__child(order.p.symbol_id)
        commission_info = instrument.get_commission_info()
        order.add_commission_info(commission_info)

        # Adjust position with operation size
        # Real execution with date
        original_position = \
            instrument.get_position(order.position_type, clone=True)
        position = \
            instrument.get_position(order.position_type, clone=False)
        pprice_orig = position.price

        # Do a real position update
        position_size, position_average_price, opened, closed = position.update(
            size, price, position_timestamp_dt)
        position_size = \
            round_to_nearest_decimal_points(
                position_size, commission_info.qty_digits, commission_info.qty_step)
        position_average_price = \
            round_to_nearest_decimal_points(position_average_price, commission_info.price_digits,
                                            commission_info.tick_size)
        opened = round_to_nearest_decimal_points(
            opened, commission_info.qty_digits, commission_info.qty_step)
        closed = round_to_nearest_decimal_points(
            closed, commission_info.qty_digits, commission_info.qty_step)

        # split commission between closed and opened
        closed_commission = 0.0
        if closed:
            if order.ccxt_order['fee'] is not None:
                if order.ccxt_order['fee']['cost'] is not None:
                    closed_commission = order.ccxt_order['fee']['cost']

            if closed_commission == 0.0:
                closed_commission = commission_info.get_commission_rate(
                    closed, price)

        opened_commission = 0.0
        if opened:
            if order.ccxt_order['fee'] is not None:
                if order.ccxt_order['fee']['cost'] is not None:
                    opened_commission = order.ccxt_order['fee']['cost']

            if opened_commission == 0.0:
                opened_commission = commission_info.get_commission_rate(
                    opened, price)

        closed_value = commission_info.get_value_size(
            -closed, pprice_orig)
        opened_value = commission_info.get_value_size(opened, price)

        # The internal broker_or_exchange calc should yield the same result
        if closed:
            profit_and_loss_amount = commission_info.profit_and_loss(
                -closed, pprice_orig, price)
        else:
            profit_and_loss_amount = 0.0

        # Need to simulate a margin, but it plays no role, because it is
        # controlled by a real broker_or_exchange. Let's set the price of the item
        if datafeed is not None:
            margin = datafeed.close[0]
        else:
            margin = price

        if dt_in_float is None:
            if datafeed is not None:
                execute_dt = datafeed.datetime[0]
            else:
                execute_dt = backtrader.date2num(position_timestamp_dt)
        else:
            execute_dt = dt_in_float
        assert isinstance(execute_dt, float)

        # Legality Check
        flag_as_error = False
        if price <= 0.0:
            flag_as_error = True
        elif abs(opened) == 0.0 and abs(closed) == 0.0:
            flag_as_error = True

        if flag_as_error == True:
            ccxt_order_id = get_ccxt_order_id(self.exchange, order)
            raise ValueError(
                "{}: order id: \'{}\': Both {:.{}f} x opened:{:.{}f}/closed:{:.{}f} of "
                "must be positive!!!".format(
                    inspect.currentframe(),
                    ccxt_order_id,
                    price, commission_info.price_digits,
                    opened, commission_info.qty_digits,
                    closed, commission_info.qty_digits,
                ))

        # Execute and notify the order
        order.execute(execute_dt,
                      size, price,
                      closed, closed_value, closed_commission,
                      opened, opened_value, opened_commission,
                      margin, profit_and_loss_amount, spread_in_ticks,
                      position_size, position_average_price)

        # size and price could deviate from its original value due to floating point precision error. The
        #       following codes are to provide remedy for that situation.
        order.executed.size = \
            round_to_nearest_decimal_points(order.executed.size, commission_info.qty_digits,
                                            commission_info.qty_step)
        order.executed.price = \
            round_to_nearest_decimal_points(order.executed.price, commission_info.price_digits,
                                            commission_info.tick_size)

        # Legality Check
        throws_out_error = False
        sub_error_msg = None
        if abs(order.executed.size) != abs(order.size):
            sub_error_msg = \
                " abs(order.executed.size): {:.{}f} != Exchange's abs(size): {:.{}f}!!!".format(
                    abs(order.executed.size), commission_info.qty_digits,
                    abs(order.size), commission_info.qty_digits,
                )
            throws_out_error = True

        if abs(order.executed.filled_size) != order.filled:
            sub_error_msg = \
                " abs(order.executed.filled_size): {:.{}f} != Exchange's filled: {:.{}f}!!!".format(
                    abs(order.executed.filled_size), commission_info.qty_digits,
                    order.filled, commission_info.qty_digits,
                )
            throws_out_error = True

        if abs(order.executed.remaining_size) != order.remaining:
            sub_error_msg = \
                " abs(order.executed.remaining_size): {:.{}f} != Exchange's remaining: {:.{}f}!!!".format(
                    abs(order.executed.remaining_size), commission_info.qty_digits,
                    order.remaining, commission_info.qty_digits,
                )
            throws_out_error = True

        if throws_out_error == True:
            msg_type = "ERROR"
        else:
            msg_type = "DEBUG"

        frameinfo = inspect.getframeinfo(inspect.currentframe())
        msg = "{} Line: {}: {}: ".format(
            frameinfo.function, frameinfo.lineno,
            msg_type,
        )

        # sub_msg = "order.ccxt_order:"
        # print(msg + sub_msg)
        # print(json.dumps(order.ccxt_order, indent=self.indent))
        #
        # sub_msg = "order:"
        # print(msg + sub_msg)
        # pprint(order)
        #
        # sub_msg = "pre-position:"
        # print(msg + sub_msg)
        # pprint(original_position)
        #
        # sub_msg = "post-position:"
        # print(msg + sub_msg)
        # pprint(position)
        #
        # if throws_out_error == False:
        #     sub_msg = \
        #         "abs(order.executed.filled_size): {:.{}f} vs Exchange's filled: {:.{}f}".format(
        #             abs(order.executed.filled_size), commission_info.qty_digits,
        #             order.filled, commission_info.qty_digits,
        #         )
        #     print(msg + sub_msg)
        #
        #     sub_msg = \
        #         "abs(order.executed.remaining_size): {:.{}f} vs Exchange's remaining: {:.{}f}".format(
        #             abs(order.executed.remaining_size), commission_info.qty_digits,
        #             order.remaining, commission_info.qty_digits,
        #         )
        #     print(msg + sub_msg)

        if throws_out_error == True:
            legality_check_not_none_obj(sub_error_msg, "sub_error_msg")
            error_msg = "{}:".format(
                inspect.currentframe(),
            )
            raise ValueError(error_msg + sub_error_msg)

        order.add_commission_info(commission_info)
        if skip_notification == False:
            # Notify using clone so that UT could snapshot the order
            self.notify(order.clone())

        # Legality Check
        throws_out_error = False
        sub_error_msg = None
        if order.symbol_id.endswith("USDT"):
            if order.position_type == backtrader.Position.LONG_POSITION:
                if position_size < 0.0:
                    sub_error_msg = \
                        "For {} position, size: {:.{}f} must be zero or positive!!!".format(
                            backtrader.Position.Position_Types[order.position_type],
                            position_size, commission_info.qty_digits,
                        )
                    throws_out_error = True
            else:
                # Validate assumption made
                assert order.position_type == backtrader.Position.SHORT_POSITION

                if position_size > 0.0:
                    sub_error_msg = \
                        "For {} position, size: {:.{}f} must be zero or negative!!!".format(
                            backtrader.Position.Position_Types[order.position_type],
                            position_size, commission_info.qty_digits,
                        )
                    throws_out_error = True

            if throws_out_error == True:
                legality_check_not_none_obj(
                    sub_error_msg, "sub_error_msg")
                frameinfo = inspect.getframeinfo(
                    inspect.currentframe())
                msg = "{} Line: {}: ERROR: ".format(
                    frameinfo.function, frameinfo.lineno,
                )
                sub_msg = "order.ccxt_order:"
                print(msg + sub_msg)
                print(json.dumps(order.ccxt_order, indent=self.indent))

                msg = "{} Line: {}: INFO: ".format(
                    frameinfo.function, frameinfo.lineno,
                )
                sub_msg = "pre-position:"
                print(msg + sub_msg)
                pprint(original_position)

                msg = "{} Line: {}: DEBUG: ".format(
                    frameinfo.function, frameinfo.lineno,
                )
                sub_msg = "post-position:"
                print(msg + sub_msg)
                pprint(position)

                msg = "{} Line: {}: INFO: ".format(
                    frameinfo.function, frameinfo.lineno,
                )
                ccxt_order_id = get_ccxt_order_id(self.exchange, order)
                sub_msg = \
                    "order id: \'{}\': price: {:.{}f} x opened:{:.{}f}/closed:{:.{}f}, size: {:.{}f}".format(
                        ccxt_order_id,
                        price, commission_info.price_digits,
                        opened, commission_info.qty_digits,
                        closed, commission_info.qty_digits,
                        size, commission_info.qty_digits,
                    )
                print(msg + sub_msg)

                error_msg = "{}:".format(
                    inspect.currentframe(),
                )
                raise ValueError(error_msg + sub_error_msg)
        else:
            raise NotImplementedError(
                "symbol_id: {} is yet to be supported!!!".format(order.symbol_id))

    def buy(self, owner, symbol_id, datafeed, size,
            # Optional Params
            price=None, price_limit=None,
            execution_type=None, valid=None, tradeid=0, oco=None,
            trailing_amount=None, trailing_percent=None,
            simulated=False,
            ordering_type=None,
            order_intent=None,
            position_type=None,
            **kwargs):
        del kwargs['parent']
        del kwargs['transmit']

        legality_check_not_none_obj(symbol_id, "symbol_id")
        legality_check_not_none_obj(ordering_type, "ordering_type")
        legality_check_not_none_obj(order_intent, "order_intent")
        legality_check_not_none_obj(position_type, "position_type")

        return self._submit(owner, symbol_id, datafeed, execution_type, 'buy', size, price, position_type,
                            ordering_type, order_intent, simulated, kwargs)

    def sell(self, owner, symbol_id, datafeed, size,
             # Optional Params
             price=None, price_limit=None,
             execution_type=None, valid=None, tradeid=0, oco=None,
             trailing_amount=None, trailing_percent=None,
             simulated=False,
             ordering_type=None,
             order_intent=None,
             position_type=None,
             **kwargs):
        del kwargs['parent']
        del kwargs['transmit']

        legality_check_not_none_obj(symbol_id, "symbol_id")
        legality_check_not_none_obj(ordering_type, "ordering_type")
        legality_check_not_none_obj(order_intent, "order_intent")
        legality_check_not_none_obj(position_type, "position_type")

        return self._submit(owner, symbol_id, datafeed, execution_type, 'sell', size, price, position_type,
                            ordering_type, order_intent, simulated, kwargs)

    def cancel(self, order):
        frameinfo = inspect.getframeinfo(inspect.currentframe())
        assert type(order).__name__ == BT_CCXT_Order.__name__, \
            "{} Line: {}: Expected {} but observed {} instead!!!".format(
                frameinfo.function, frameinfo.lineno,
                BT_CCXT_Order.__name__, type(order).__name__,
        )
        assert hasattr(order, 'ccxt_order')

        ccxt_order_id = order.ccxt_order['id']

        if self.debug:
            print('Broker cancel() called')
            print('Fetching Order ID: {}'.format(ccxt_order_id))

        # Check first if the order has already been filled otherwise an error
        # might be raised if we try to cancel an order that is not open.
        # Get the latest CCXT order
        # CCXT Market Type is explicitly required
        fetch_order__dict = dict(
            type=self.market_type_name,   # CCXT Market Type
        )
        if order.ordering_type == backtrader.Order.ACTIVE_ORDERING_TYPE:
            new_ccxt_order = self.fetch_order(
                ccxt_order_id, order.symbol_id, params=fetch_order__dict)
        else:
            # Validate assumption made
            assert order.ordering_type == backtrader.Order.CONDITIONAL_ORDERING_TYPE

            fetch_order__dict.update(dict(
                stop_order_id=ccxt_order_id,
            ))
            new_ccxt_order = self.fetch_order(
                None, order.symbol_id, params=fetch_order__dict)
        legality_check_not_none_obj(new_ccxt_order, "new_ccxt_order")

        # Post-process the CCXT order so that they are consistent across multiple exchanges
        post_process__ccxt_orders__dict = dict(
            bt_ccxt_exchange=self.parent,
            bt_ccxt_account_or_store=self,
            ccxt_orders=[new_ccxt_order],
        )
        post_processed__ccxt_orders = self._post_process__ccxt_orders(
            params=post_process__ccxt_orders__dict)
        assert len(post_processed__ccxt_orders) == 1
        post_processed__ccxt_order = post_processed__ccxt_orders[0]

        if self.debug:
            frameinfo = inspect.getframeinfo(inspect.currentframe())
            msg = "{} Line: {}: DEBUG: new_ccxt_order:".format(
                frameinfo.function, frameinfo.lineno,
            )
            print(msg)
            print(json.dumps(post_processed__ccxt_order, indent=self.indent))

        # Check if the exchange order is closed
        if post_processed__ccxt_order[self.parent.mappings[CCXT_ORDER_TYPES[CLOSED_ORDER]]['key']] == \
                self.parent.mappings[CCXT_ORDER_TYPES[CLOSED_ORDER]]['value']:
            return order

        # CCXT Market Type is explicitly required
        cancel_order__dict = dict(
            type=self.market_type_name,   # CCXT Market Type
        )
        if order.ordering_type == backtrader.Order.CONDITIONAL_ORDERING_TYPE:
            cancel_order__dict.update(dict(
                stop=True,
            ))
        cancelled_ccxt_order = \
            self.cancel_order(ccxt_order_id, order.symbol_id,
                              params=cancel_order__dict)

        # Confirm the ccxt_order is cancelled in the exchange
        success = False
        if cancelled_ccxt_order['id'] is not None:
            orders_to_be_removed = []
            for open_order in self.open_orders:
                if open_order.ccxt_id == ccxt_order_id:
                    orders_to_be_removed.append(open_order)

            for order_to_be_removed in orders_to_be_removed:
                # Remove the original order
                self.open_orders.remove(order_to_be_removed)

            # Mark the queried order as cancelled
            order.cancel()

            # Notify using clone so that UT could snapshot the order
            self.notify(order.clone())
            success = True
        return success

    def modify_order(self, order_id, symbol, type, side, amount=None, price=None, trigger_price=None, params={}):
        return self._edit_order(order_id, symbol, type, side, amount=amount, price=price,
                                trigger_price=trigger_price, params=params)

    def _post_process__ccxt_orders(self, params):
        # Un-serialize Params
        ccxt_orders = params['ccxt_orders']

        ret_ccxt_orders = []

        legality_check_not_none_obj(self.parent, "self.parent")
        for ccxt_order in ccxt_orders:
            assert isinstance(ccxt_order, dict)

            from_items = []
            to_items = []
            for ccxt_key_tuple in LIST_OF_CCXT_KEY_TO_BE_RENAMED:
                from_items.append(ccxt_key_tuple[0])
                to_items.append(ccxt_key_tuple[1])

            # Rename dict while maintaining its ordering
            renamed_ccxt_order = {}
            for k, v in ccxt_order.items():
                if k in from_items:
                    index = from_items.index(k)
                    to_item = to_items[index]

                    # Rename the key
                    renamed_ccxt_order.update({
                        to_item: v,
                    })
                else:
                    # Retain the same item
                    renamed_ccxt_order.update({
                        k: v,
                    })

            if CCXT_SYMBOL_KEY in renamed_ccxt_order.keys():
                get_symbol_id__dict = dict(
                    exchange_dropdown_value=self.exchange_dropdown_value,
                    symbol_name=renamed_ccxt_order[CCXT_SYMBOL_KEY],
                )
                renamed_ccxt_order['symbol_id'] = \
                    get_symbol_id(params=get_symbol_id__dict)

            if CCXT_SIDE_KEY in renamed_ccxt_order.keys():
                renamed_ccxt_order[CCXT_SIDE_KEY] = \
                    capitalize_sentence(renamed_ccxt_order[CCXT_SIDE_KEY])

                # Convert CCXT_SIDE_KEY to enum
                renamed_ccxt_order['side'] = backtrader.Order.Order_Types.index(
                    renamed_ccxt_order[CCXT_SIDE_KEY])

            for ccxt_order_key in CCXT_ORDER_KEYS__MUST_BE_IN_FLOAT:
                if ccxt_order_key in renamed_ccxt_order.keys():
                    if renamed_ccxt_order[ccxt_order_key] is not None:
                        renamed_ccxt_order[ccxt_order_key] = \
                            self.exchange.safe_float(
                                renamed_ccxt_order, ccxt_order_key)
                    else:
                        # Convert None to 0.0 for consistency
                        renamed_ccxt_order[ccxt_order_key] = 0.0

            ccxt_reduce_only_value__dict = dict(
                exchange_dropdown_value=self.exchange_dropdown_value,
                ccxt_order=renamed_ccxt_order,
            )
            ccxt_order = converge_ccxt_reduce_only_value(
                params=ccxt_reduce_only_value__dict)

            reverse_engineer__ccxt_order__dict = dict(
                ccxt_order=ccxt_order,
            )
            reverse_engineer__ccxt_order__dict.update(params)
            ccxt_order = reverse_engineer__ccxt_order(
                params=reverse_engineer__ccxt_order__dict)

            ret_ccxt_orders.append(ccxt_order)
        return ret_ccxt_orders

    def _common_handle_orders_routine(self, params):
        # Un-serialize Params
        ccxt_orders = params['ccxt_orders']

        # Optional Params
        datafeed = params.get('datafeed', None)

        # Post-process the CCXT orders so that they are consistent across multiple exchanges
        post_process__ccxt_orders__dict = dict(
            bt_ccxt_exchange=self.parent,
            bt_ccxt_account_or_store=self,
            ccxt_orders=ccxt_orders,
        )
        post_processed__ccxt_opened_orders = self._post_process__ccxt_orders(
            params=post_process__ccxt_orders__dict)

        ret_opened_orders = []
        for ccxt_order in post_processed__ccxt_opened_orders:
            # Exposed simulated so that we could proceed with order without running cerebro
            bt_ccxt_order__dict = dict(
                owner=self,
                exchange_dropdown_value=self.exchange_dropdown_value,
                symbol_id=ccxt_order['symbol_id'],
                ccxt_order=ccxt_order,
                execution_type=ccxt_order[DERIVED__CCXT_ORDER__KEYS[EXECUTION_TYPE]],
                position_type=ccxt_order[DERIVED__CCXT_ORDER__KEYS[POSITION_TYPE]],
                ordering_type=ccxt_order[DERIVED__CCXT_ORDER__KEYS[ORDERING_TYPE]],
                order_intent=ccxt_order[DERIVED__CCXT_ORDER__KEYS[ORDER_INTENT]],
            )
            if datafeed is not None:
                # Assign the datafeed since it exists
                bt_ccxt_order__dict.update(dict(
                    datafeed=datafeed,
                ))
            else:
                # Turn on simulated should there is no datafeed
                bt_ccxt_order__dict.update(dict(
                    simulated=True,
                ))
            ret_opened_orders.append(BT_CCXT_Order(**bt_ccxt_order__dict))
        return ret_opened_orders

    def get_orders(self, symbol=None, since=None, limit=None, datafeed=None, params=None):
        if params is None:
            params = {}

        ccxt_orders = self._fetch_orders(
            symbol=symbol, since=since, limit=limit, params=params)

        handle_orders_routine__dict = dict(
            ccxt_orders=ccxt_orders,

            # Optional Params
            datafeed=datafeed,
        )
        return self._common_handle_orders_routine(params=handle_orders_routine__dict)

    def fetch_opened_orders(self, symbol=None, since=None, limit=None, datafeed=None, params=None):
        if params is None:
            params = {}
        ccxt_opened_orders = self._fetch_opened_orders(
            symbol=symbol, since=since, limit=limit, params=params)

        handle_orders_routine__dict = dict(
            ccxt_orders=ccxt_opened_orders,

            # Optional Params
            datafeed=datafeed,
        )
        return self._common_handle_orders_routine(params=handle_orders_routine__dict)

    def fetch_closed_orders(self, symbol=None, since=None, limit=None, datafeed=None, params=None):
        if params is None:
            params = {}
        ccxt_closed_orders = self.fetch_closed_orders(
            symbol=symbol, since=since, limit=limit, params=params)

        handle_orders_routine__dict = dict(
            ccxt_orders=ccxt_closed_orders,

            # Optional Params
            datafeed=datafeed,
        )
        return self._common_handle_orders_routine(params=handle_orders_routine__dict)

    def get_positions(self, symbols=None, params={}):
        return self._fetch_opened_positions(symbols, params)

    @retry
    def __exchange_end_point(self, type, endpoint, params):
        '''
        Open method to allow calls to be made to any private end point.
        See here: https://github.com/ccxt/ccxt/wiki/Manual#implicit-api-methods

        - type: String, 'Get', 'Post','Put' or 'Delete'.
        - endpoint = String containing the endpoint address eg. 'order/{id}/cancel'
        - Params: Dict: An implicit method takes a dictionary of parameters, sends
          the request to the exchange and returns an exchange-specific JSON
          result from the API as is, unparsed.

        To get a list of all available methods with an exchange instance,
        including implicit methods and unified methods you can simply do the
        following:

        print(dir(ccxt.hitbtc()))
        '''
        return getattr(self.exchange, endpoint)(params)

    def __common_end_point(self, is_private, type, endpoint, params, prefix):
        endpoint_str = endpoint.replace('/', '_')
        endpoint_str = endpoint_str.replace('-', '_')
        endpoint_str = endpoint_str.replace('{', '')
        endpoint_str = endpoint_str.replace('}', '')

        if is_private == True:
            private_or_public = "private"
        else:
            private_or_public = "public"

        if prefix != "":
            method_str = prefix.lower() + "_" + private_or_public + "_" + \
                type.lower() + endpoint_str.lower()
        else:
            method_str = private_or_public + "_" + type.lower() + endpoint_str.lower()

        return self.__exchange_end_point(type=type, endpoint=method_str, params=params)

    def public_end_point(self, type, endpoint, params, prefix=""):
        is_private = False
        return self.__common_end_point(is_private, type, endpoint, params, prefix)

    def private_end_point(self, type, endpoint, params, prefix=""):
        '''
        Open method to allow calls to be made to any private end point.
        See here: https://github.com/ccxt/ccxt/wiki/Manual#implicit-api-methods

        - type: String, 'Get', 'Post','Put' or 'Delete'.
        - endpoint = String containing the endpoint address eg. 'order/{id}/cancel'
        - Params: Dict: An implicit method takes a dictionary of parameters, sends
          the request to the exchange and returns an exchange-specific JSON
          result from the API as is, unparsed.
        - Optional prefix to be appended to the front of method_str should your
          exchange needs it. E.g. v2_private_xxx

        To get a list of all available methods with an exchange instance,
        including implicit methods and unified methods you can simply do the
        following:

        print(dir(ccxt.hitbtc()))
        '''
        is_private = True
        return self.__common_end_point(is_private, type, endpoint, params, prefix)

    def handle_socket_message(self, msg):
        print(f"message type: {msg['e']}")
        print(msg)

    def establish_binance_websocket(self):
        for symbol_id in self.symbols_id:
            self.twm.start_kline_socket(
                callback=self.handle_socket_message, symbol=symbol_id)

    def establish_bybit_websocket(self):
        self.establish_bybit_usdt_perpetual_websocket()
        self.establish_bybit_mainnet_usdt_perpetual_websocket()

    def establish_bybit_usdt_perpetual_websocket(self):
        proceed_with_connection = False

        if self.ws_usdt_perpetual is None:
            proceed_with_connection = True
        else:
            # Validate assumption made
            assert self.ws_usdt_perpetual is not None

            if self.ws_usdt_perpetual.is_connected() == False:
                proceed_with_connection = True

        if proceed_with_connection == True:
            # Legality Check
            assert isinstance(self.symbols_id, list)
            assert len(self.symbols_id) > 0

            while True:
                self.ws_usdt_perpetual = \
                    usdt_perpetual.WebSocket(
                        test=not self.main_net_toggle_switch_value,
                        api_key=self.config__api_key,
                        api_secret=self.config__api_secret,
                        # to pass a custom domain in case of connectivity problems, you can use:
                        # domain="bytick"  # the default is "bybit"

                        # Attempting to resolve WebSocket USDT Perp encountered error: ping/pong timed out in
                        #       dashboard
                        # ping_interval=20,
                        # ping_timeout=10,
                        retries=20,
                        # trace_logging=True,
                    )

                try:
                    self.ws_usdt_perpetual.order_stream(
                        self.handle_active_order)
                    time.sleep(0.1)

                    self.ws_usdt_perpetual.stop_order_stream(
                        self.handle_conditional_order)
                    time.sleep(0.1)

                    self.ws_usdt_perpetual.position_stream(
                        self.handle_positions)
                except websocket._exceptions.WebSocketConnectionClosedException:
                    pass
                except websocket._exceptions.WebSocketTimeoutException:
                    '''
                    To address: WebSocket USDT Perp connection failed. Too many connection attempts. pybit will no
                    longer try to reconnect.
                    '''
                    pass

                if len(self.ws_usdt_perpetual.active_connections) > 0 and \
                        self.ws_usdt_perpetual.is_connected() == True:
                    break
                else:
                    self.ws_usdt_perpetual = None
                    time.sleep(0.1)
                    gc.collect()

    def establish_bybit_mainnet_usdt_perpetual_websocket(self):
        proceed_with_connection = False

        # Only OHLCV_PROVIDER should be connected to ws_mainnet_usdt_perpetual
        if self.is_ohlcv_provider == True:
            if self.ws_mainnet_usdt_perpetual is None:
                proceed_with_connection = True
            else:
                # Validate assumption made
                assert self.ws_mainnet_usdt_perpetual is not None

                if self.ws_mainnet_usdt_perpetual.is_connected() == False:
                    proceed_with_connection = True

        if proceed_with_connection == True:
            # Legality Check
            assert isinstance(self.symbols_id, list)
            assert len(self.symbols_id) > 0

            while True:
                # Connect with authentication
                self.ws_mainnet_usdt_perpetual = usdt_perpetual.WebSocket(
                    test=False,
                    api_key=self.config__api_key,
                    api_secret=self.config__api_secret,
                    # to pass a custom domain in case of connectivity problems, you can use:
                    # domain="bytick"  # the default is "bybit"

                    # Attempting to resolve WebSocket USDT Perp encountered error: ping/pong timed out in
                    #       dashboard
                    # ping_interval=20,
                    # ping_timeout=10,
                    retries=20,
                    # trace_logging=True,
                )

                try:
                    if self.ws_mainnet_usdt_perpetual.is_connected() == True:
                        # Reference: https://bybit-exchange.github.io/docs/futuresV2/linear/#t-websocketkline
                        # Subscribe to 1 minute candle
                        if len(self.symbols_id) == 1:
                            self.ws_mainnet_usdt_perpetual.kline_stream(
                                self.handle_klines, self.symbols_id[0], "1")
                            time.sleep(0.1)

                            self.ws_mainnet_usdt_perpetual.instrument_info_stream(self.handle_instrument_info_stream,
                                                                                  symbol=self.symbols_id[0])
                        else:
                            self.ws_mainnet_usdt_perpetual.kline_stream(
                                self.handle_klines, self.symbols_id, "1")
                            time.sleep(0.1)

                            self.ws_mainnet_usdt_perpetual.instrument_info_stream(self.handle_instrument_info_stream,
                                                                                  symbol=self.symbols_id)
                except websocket._exceptions.WebSocketConnectionClosedException:
                    pass
                except websocket._exceptions.WebSocketTimeoutException:
                    '''
                    To address: WebSocket USDT Perp connection failed. Too many connection attempts. pybit will no
                    longer try to reconnect.
                    '''
                    pass

                if len(self.ws_mainnet_usdt_perpetual.active_connections) > 0 and \
                        self.ws_mainnet_usdt_perpetual.is_connected() == True:
                    break
                else:
                    self.ws_mainnet_usdt_perpetual = None
                    time.sleep(0.1)
                    gc.collect()

    def close_bybit_websocket(self):
        self.close_bybit_usdt_perpetual_websocket()
        self.close_bybit_mainnet_usdt_perpetual_websocket()

    def close_bybit_usdt_perpetual_websocket(self):
        if self.ws_usdt_perpetual is not None:
            if len(self.ws_usdt_perpetual.active_connections) > 0 and \
                    self.ws_usdt_perpetual.is_connected() == True:
                try:
                    if hasattr(self.ws_usdt_perpetual, 'ws'):
                        self.ws_usdt_perpetual.ws.close()
                    self.ws_usdt_perpetual.close()
                except Exception:
                    pass

                self.ws_usdt_perpetual = None
                time.sleep(0.1)
                gc.collect()

    def close_bybit_mainnet_usdt_perpetual_websocket(self):
        # Only OHLCV_PROVIDER should be connected to ws_mainnet_usdt_perpetual
        if self.is_ohlcv_provider == True:
            if self.ws_mainnet_usdt_perpetual is not None:
                if len(self.ws_mainnet_usdt_perpetual.active_connections) > 0 and \
                        self.ws_mainnet_usdt_perpetual.is_connected() == True:
                    try:
                        if hasattr(self.ws_mainnet_usdt_perpetual, 'ws'):
                            self.ws_mainnet_usdt_perpetual.ws.close()
                        self.ws_mainnet_usdt_perpetual.close()
                    except Exception:
                        pass

                    self.ws_mainnet_usdt_perpetual = None
                    time.sleep(0.1)
                    gc.collect()

    def get_account_alias(self):
        return self.account_alias

    def get_open_orders(self):
        # In order to prevent manipulation from caller
        cloned_open_orders = []
        for open_order in self.open_orders:
            cloned_open_orders.append(copy.copy(open_order))
        return cloned_open_orders

    def get_granularity(self, timeframe, compression):
        if not self.exchange.has['fetchOHLCV']:
            raise NotImplementedError("'%s' exchange doesn't support fetching OHLCV datafeed" %
                                      self.exchange_dropdown_value)

        granularity = self._GRANULARITIES.get((timeframe, compression))
        if granularity is None:
            raise ValueError("backtrader CCXT module doesn't support fetching OHLCV "
                             "datafeed for time frame %s, compression %s" %
                             (backtrader.TimeFrame.getname(timeframe), compression))

        if self.exchange.timeframes and \
                granularity not in self.exchange.timeframes:
            raise ValueError("'%s' exchange doesn't support fetching OHLCV datafeed for "
                             "%s time frame" % (self.exchange_dropdown_value, granularity))

        return granularity

    def handle_positions(self, message):
        '''
        This routine gets triggered whenever there is a position change. If the position does not change, it will not
        appear in the message.
        '''
        try:
            if self.debug:
                # # TODO: Debug use
                # frameinfo = inspect.getframeinfo(inspect.currentframe())
                # print("{} Line: {}: {}: {}: {}: message:".format(
                #     frameinfo.function, frameinfo.lineno,
                #     threading.current_thread().name,
                #     datetime.datetime.now().isoformat().replace("T", " ")[:-3],
                #     self.account_alias,
                # ))
                # pprint(message)
                pass

            assert type(message['data']) == list
            responses = self.exchange.safe_value(message, 'data')

            '''
            Ported the following codes from CCXT Bybit Exchange
            '''
            results = []
            symbols = []
            symbol_type = None
            for rawPosition in responses:
                symbol = self.exchange.safe_string(rawPosition, 'symbol')
                if symbol not in symbols:
                    symbols.append(symbol)
                market = self.get_market(symbol)
                if symbol_type is None:
                    symbol_type = market['type']
                results.append(
                    self.exchange.parse_position(rawPosition, market))
            latest_changed_positions = self.exchange.filter_by_array(
                results, 'symbol', symbols, False)

            for symbol_id in symbols:
                if len(self.ws_positions[symbol_id]) == 0:
                    # Exercise the longer time route
                    market_type = CCXT__MARKET_TYPES.index(symbol_type)
                    ccxt_market_symbol_name = get_ccxt_market_symbol_name(
                        market_type, symbol_id)

                    # Store the outdated positions first
                    self.ws_positions[symbol_id] = \
                        self._fetch_opened_positions_from_exchange(
                            symbols=[ccxt_market_symbol_name], params={'type': symbol_type})

                # Identify ws_position to be changed
                positions_to_be_changed = []
                for i, _ in enumerate(self.ws_positions[symbol_id]):
                    for latest_changed_position in latest_changed_positions:
                        if latest_changed_position['symbol'] == symbol_id:
                            if self.ws_positions[symbol_id][i]['side'] == \
                                    latest_changed_position['side']:
                                positions_to_be_changed.append(
                                    (i, latest_changed_position))

                # Update with the latest position from websocket
                for position_to_be_changed_tuple in positions_to_be_changed:
                    index, latest_changed_position = position_to_be_changed_tuple
                    self.ws_positions[symbol_id][index] = latest_changed_position

                # Legality Check
                assert len(self.ws_positions[symbol_id]) <= 2, \
                    "len(ws_positions): {} should not be greater than 2!!!".format(
                        len(self.ws_positions[symbol_id]))

                if symbol_type == "linear":
                    assert len(self.ws_positions[symbol_id]) == 2, \
                        "For {} symbol, len(ws_positions): {} does not equal to 2!!!".format(
                            symbol_type, len(self.ws_positions[symbol_id])
                    )

                # Sort dictionary list by key
                reverse = False
                sort_by_key = 'side'
                self.ws_positions[symbol_id] = \
                    sorted(self.ws_positions[symbol_id],
                           key=lambda k: k[sort_by_key],
                           reverse=reverse)
        except Exception:
            traceback.print_exc()

    def handle_active_order(self, message):
        try:
            if self.debug:
                # # TODO: Debug use
                # frameinfo = inspect.getframeinfo(inspect.currentframe())
                # print("{} Line: {}: {}: {}: message:".format(
                #     frameinfo.function, frameinfo.lineno,
                #     datetime.datetime.now().isoformat().replace("T", " ")[:-3],
                #     self.account_alias,
                # ))
                # pprint(message)
                pass

            responses = message['data']
            assert type(responses) == list
            active_orders_to_be_added = collections.defaultdict(list)
            symbols_id = []
            for order in responses:
                market = self.get_market(order['symbol'])
                result = self.exchange.safe_value(message, 'data')
                active_order = self.exchange.parse_order(result[0], market)

                # Strip away "/" and ":USDT"
                active_order['symbol'] = active_order['symbol'].replace(
                    "/", "")
                active_order['symbol'] = active_order['symbol'].replace(
                    ":USDT", "")

                symbol_id = active_order['symbol']
                if symbol_id not in symbols_id:
                    symbols_id.append(symbol_id)

                active_orders_to_be_added[symbol_id].append(active_order)

                if self.debug:
                    # TODO: Debug use
                    frameinfo = inspect.getframeinfo(inspect.currentframe())
                    msg = "{} Line: {}: DEBUG: {}: {}: ".format(
                        frameinfo.function, frameinfo.lineno,
                        datetime.datetime.now().isoformat().replace(
                            "T", " ")[:-3],
                        self.account_alias,
                    )
                    msg += "appended active_order['id']: {} into active_orders_to_be_added".format(
                        active_order['id'])
                    print(msg)

            for symbol_id in symbols_id:
                active_order_ids_to_be_added = \
                    [active_order['id']
                        for active_order in active_orders_to_be_added[symbol_id]]

                # Look for existing order in the list
                ws_active_orders_to_be_removed = []
                for ws_active_order in self.ws_active_orders[symbol_id]:
                    if ws_active_order['id'] in active_order_ids_to_be_added:
                        ws_active_orders_to_be_removed.append(ws_active_order)

                # Remove the existing ws active order
                for ws_active_order in ws_active_orders_to_be_removed:
                    if self.debug:
                        # TODO: Debug use
                        frameinfo = inspect.getframeinfo(
                            inspect.currentframe())
                        msg = "{} Line: {}: WARNING: {}: {}: ".format(
                            frameinfo.function, frameinfo.lineno,
                            datetime.datetime.now().isoformat().replace(
                                "T", " ")[:-3],
                            self.account_alias,
                        )
                        msg += "removing ws_active_order['id']: {} from ws_active_orders".format(
                            ws_active_order['id'])
                        print(msg)

                    self.ws_active_orders[symbol_id].remove(ws_active_order)

                # Add the latest active orders
                for active_order in active_orders_to_be_added[symbol_id]:
                    self.ws_active_orders[symbol_id].append(active_order)

                    if self.debug:
                        # TODO: Debug use
                        frameinfo = inspect.getframeinfo(
                            inspect.currentframe())
                        msg = "{} Line: {}: DEBUG: {}: {}: ".format(
                            frameinfo.function, frameinfo.lineno,
                            datetime.datetime.now().isoformat().replace(
                                "T", " ")[:-3],
                            self.account_alias,
                        )
                        msg += "appended active_order['id']: {} into ws_active_orders".format(
                            active_order['id'])
                        print(msg)

        except Exception:
            traceback.print_exc()

    def handle_conditional_order(self, message):
        try:
            if self.debug:
                # # TODO: Debug use
                # frameinfo = inspect.getframeinfo(inspect.currentframe())
                # print("{} Line: {}: {}: {}: message:".format(
                #     frameinfo.function, frameinfo.lineno,
                #     datetime.datetime.now().isoformat().replace("T", " ")[:-3],
                #     self.account_alias,
                # ))
                # pprint(message)
                pass

            responses = message['data']
            assert type(responses) == list
            conditional_orders_to_be_added = collections.defaultdict(list)
            symbols_id = []
            for order in responses:
                market = self.get_market(order['symbol'])
                result = self.exchange.safe_value(message, 'data')
                conditional_order = self.exchange.parse_order(
                    result[0], market)

                # Strip away "/" and ":USDT"
                conditional_order['symbol'] = conditional_order['symbol'].replace(
                    "/", "")
                conditional_order['symbol'] = conditional_order['symbol'].replace(
                    ":USDT", "")

                symbol_id = conditional_order['symbol']
                if symbol_id not in symbols_id:
                    symbols_id.append(symbol_id)

                conditional_orders_to_be_added[symbol_id].append(
                    conditional_order)

                if self.debug:
                    # TODO: Debug use
                    frameinfo = inspect.getframeinfo(inspect.currentframe())
                    msg = "{} Line: {}: DEBUG: {}: {}: ".format(
                        frameinfo.function, frameinfo.lineno,
                        datetime.datetime.now().isoformat().replace(
                            "T", " ")[:-3],
                        self.account_alias,
                    )
                    msg += "appended conditional_order['id']: {} into conditional_orders_to_be_added".format(
                        conditional_order['id'])
                    print(msg)

            for symbol_id in symbols_id:
                conditional_order_ids_to_be_added = \
                    [conditional_order['id']
                        for conditional_order in conditional_orders_to_be_added[symbol_id]]

                # Look for existing order in the list
                ws_conditional_orders_to_be_removed = []
                for ws_conditional_order in self.ws_conditional_orders[symbol_id]:
                    if ws_conditional_order['id'] in conditional_order_ids_to_be_added:
                        ws_conditional_orders_to_be_removed.append(
                            ws_conditional_order)

                # Remove the existing ws conditional order
                for ws_conditional_order in ws_conditional_orders_to_be_removed:
                    if self.debug:
                        # TODO: Debug use
                        frameinfo = inspect.getframeinfo(
                            inspect.currentframe())
                        msg = "{} Line: {}: WARNING: {}: {}: ".format(
                            frameinfo.function, frameinfo.lineno,
                            datetime.datetime.now().isoformat().replace(
                                "T", " ")[:-3],
                            self.account_alias,
                        )
                        msg += "removing ws_conditional_order['id']: {} from ws_conditional_orders".format(
                            ws_conditional_order['id'])
                        print(msg)

                    self.ws_conditional_orders[symbol_id].remove(
                        ws_conditional_order)

                # Add the latest conditional orders
                for conditional_order in conditional_orders_to_be_added[symbol_id]:
                    self.ws_conditional_orders[symbol_id].append(
                        conditional_order)

                    if self.debug:
                        # TODO: Debug use
                        frameinfo = inspect.getframeinfo(
                            inspect.currentframe())
                        msg = "{} Line: {}: DEBUG: {}: {}: ".format(
                            frameinfo.function, frameinfo.lineno,
                            datetime.datetime.now().isoformat().replace(
                                "T", " ")[:-3],
                            self.account_alias,
                        )
                        msg += "appended conditional_order['id']: {} into ws_conditional_orders".format(
                            conditional_order['id'])
                        print(msg)

        except Exception:
            traceback.print_exc()

    def handle_klines(self, message):
        '''
        This routine gets triggered whenever there is a kline update.
        '''
        try:
            if self.debug:
                # # TODO: Debug use
                # frameinfo = inspect.getframeinfo(inspect.currentframe())
                # print("{} Line: {}: {}: {}: message:".format(
                #     frameinfo.function, frameinfo.lineno,
                #     datetime.datetime.now().isoformat().replace("T", " ")[:-3],
                #     self.account_alias,
                # ))
                # pprint(message)
                pass

            assert type(message['data']) == list
            topic_responses = self.exchange.safe_value(message, 'topic')
            data_responses = self.exchange.safe_value(message, 'data')

            topic_responses_split = topic_responses.split(".")
            assert len(topic_responses_split) == 3
            symbol_id = topic_responses_split[2]
            if len(data_responses) > 0:
                # References: https://bybit-exchange.github.io/docs/futuresV2/linear/#t-websocketkline
                # Data sent timestamp in seconds * 10^6
                tstamp = int(data_responses[0]['timestamp']) / 1e6
                ohlcv = \
                    (float(data_responses[0]['open']), float(data_responses[0]['high']),
                     float(data_responses[0]['low']), float(
                         data_responses[0]['close']),
                     float(data_responses[0]['volume']))
                self.ws_klines[symbol_id] = (tstamp, ohlcv)
        except Exception:
            traceback.print_exc()

    def handle_instrument_info_stream(self, message):
        '''
        This routine gets triggered whenever there is instrument info update.
        '''
        try:
            if self.debug:
                # # TODO: Debug use
                # frameinfo = inspect.getframeinfo(inspect.currentframe())
                # print("{} Line: {}: {}: {}: message:".format(
                #     frameinfo.function, frameinfo.lineno,
                #     datetime.datetime.now().isoformat().replace("T", " ")[:-3],
                #     self.account_alias,
                # ))
                # pprint(message)
                pass

            assert type(message['data']) == dict
            responses = self.exchange.safe_value(message, 'data')
            if len(responses) > 0:
                # References: https://bybit-exchange.github.io/docs/futuresV2/linear/#t-websocketinstrumentinfo
                symbol_id = responses['symbol']
                mark_price = float(responses['mark_price'])
                ask1_price = float(responses['ask1_price'])
                bid1_price = float(responses['bid1_price'])
                self.ws_instrument_info[symbol_id] = (
                    mark_price, ask1_price, bid1_price)
        except Exception:
            traceback.print_exc()

    def run_pulse_check_for_ws(self):
        if self.is_ws_available == True:
            self.establish_bybit_usdt_perpetual_websocket()
            self.establish_bybit_mainnet_usdt_perpetual_websocket()

    @retry
    def get_market(self, symbol):
        market = self.exchange.market(symbol)
        return market

    @retry
    def _get_wallet_balance(self, params=None):
        if params is None:
            params = self.fetch_balance__dict
        balance = self.exchange.fetch_balance(params)
        return balance

    def _get_balance(self):
        balance = self._get_wallet_balance()

        # Legality Check
        assert self.wallet_currency in balance['free'].keys()
        assert self.wallet_currency in balance['total'].keys()

        cash = balance['free'][self.wallet_currency]
        value = balance['total'][self.wallet_currency]

        # Fix for scenario where None is returned
        self._cash = cash if cash else 0.0
        self._value = value if value else 0.0
        return balance

    def get_value(self):
        return self._value

    @retry
    def create_order(self, symbol, order_type, side, amount, price, params):
        # returns the order
        return self.exchange.create_order(
            symbol=symbol, type=order_type, side=side, amount=amount, price=price, params=params)

    @retry
    def _edit_order(self, order_id, symbol, type, side, amount=None, price=None, trigger_price=None, params={}):
        # returns the order
        return self.exchange.edit_order(
            order_id, symbol, type, side, amount=amount, price=price, trigger_price=trigger_price, params=params)

    @retry
    def cancel_order(self, order_id, symbol, params=None):
        if params is None:
            params = {}
        return self.exchange.cancel_order(order_id, symbol, params=params)

    @retry
    def fetch_trades(self, symbol):
        return self.exchange.fetch_trades(symbol)

    @retry
    def parse_timeframe(self, timeframe):
        return self.exchange.parse_timeframe(timeframe)

    @retry
    def filter_by_since_limit(self, array, since=None, limit=None, key='timestamp', tail=False):
        return self.exchange.filter_by_since_limit(array, since, limit, key, tail)

    def fetch_ws_klines(self, dataname):
        if self.main_net_toggle_switch_value == True:
            mainnet__account_or_store = self
        else:
            ohlcv_provider__account_or_store = self.parent.get_ohlcv_provider__account_or_store()
            mainnet__account_or_store = ohlcv_provider__account_or_store

        # Always fetch klines from MAINNET instead of TESTNET
        ret_value = mainnet__account_or_store.ws_klines[dataname]
        return ret_value

    @retry
    def fetch_ohlcv(self, symbol, timeframe, since, limit, params={}):
        if self.debug:
            since_dt = datetime.datetime.utcfromtimestamp(
                since // 1000) if since is not None else 'NA'
            print('Fetching: {}, timeframe:{}, since TS:{}, since_dt:{}, limit:{}, params:{}'.format(
                symbol, timeframe, since, since_dt, limit, params))

        if self.main_net_toggle_switch_value == True:
            mainnet_exchange = self.exchange
        else:
            legality_check_not_none_obj(self.parent, "self.parent")
            ohlcv_provider__account_or_store = self.parent.get_ohlcv_provider__account_or_store()
            mainnet_exchange = ohlcv_provider__account_or_store.exchange

        # Always fetch OHLCV from MAINNET instead of TESTNET
        ret_value = mainnet_exchange.fetch_ohlcv(
            symbol, timeframe=timeframe, since=since, limit=limit, params=params)
        return ret_value

    @retry
    def fetch_order_book(self, symbol, limit=None, params={}):
        if self.main_net_toggle_switch_value == True:
            mainnet_exchange = self.exchange
        else:
            ohlcv_provider__account_or_store = self.parent.get_ohlcv_provider__account_or_store()
            mainnet_exchange = ohlcv_provider__account_or_store.exchange

        # Always fetch order book from MAINNET instead of TESTNET
        ret_value = mainnet_exchange.fetch_order_book(
            symbol, limit=limit, params=params)
        return ret_value

    @retry
    def _fetch_order_from_exchange(self, order_id, symbol_id, params={}):
        order = None
        try:
            # Due to nature of order is processed async, the order could not be found immediately right after
            #       order is opened. Hence, perform retry to confirm if that's the case.
            order = self.exchange.fetch_order(order_id, symbol_id, params)
        except OrderNotFound:
            # Ignore order not found error
            pass
        return order

    def _snail_path_to_fetch_order_from_exchange(self, order_id, symbol_id, params):
        # Optional Params
        conditional_oid = params.get('stop_order_id', None)

        order = None

        # If we are looking for Conditional Order
        if conditional_oid is not None:
            # Exercise the longer time route @ Conditional Order
            order = self._fetch_order_from_exchange(
                conditional_oid, symbol_id, params)

            if order is None:
                # Exercise the longer time route @ Active Order
                order = self._fetch_order_from_exchange(
                    conditional_oid, symbol_id, params)
        # If we are looking for Active Order
        else:
            # Validate assumption made
            legality_check_not_none_obj(order_id, "order_id")

            # Exercise the longer time route @ Active Order
            order = self._fetch_order_from_exchange(
                order_id, symbol_id, params)

        # It is OK to have order is None here
        return order

    def fetch_order(self, order_id, symbol_id, params={}):
        # Optional Params
        conditional_oid = params.get('stop_order_id', None)

        # Enforce mutually exclusive rule
        search_order_id = None
        order_type_name = None
        if order_id is None:
            legality_check_not_none_obj(conditional_oid, "conditional_oid")
            search_order_id = conditional_oid
            order_type_name = 'Conditional'
        elif conditional_oid is None:
            legality_check_not_none_obj(order_id, "order_id")
            search_order_id = order_id
            order_type_name = 'Active'
        legality_check_not_none_obj(search_order_id, "search_order_id")
        legality_check_not_none_obj(order_type_name, "order_type_name")

        if self.debug:
            # # TODO: Debug use
            # frameinfo = inspect.getframeinfo(inspect.currentframe())
            # msg = "{} Line: {}: DEBUG: {}: ".format(
            #     frameinfo.function, frameinfo.lineno,
            #     threading.current_thread().name,
            # )
            # msg += "order_id: {}, ".format(order_id)
            # msg += "conditional_oid: {}, ".format(conditional_oid)
            #
            # # Strip ", " from the string
            # print(msg[:-2])
            pass

        found_order_in_ws = False
        search_into_ws_conditional_order = False
        search_into_ws_active_order = False
        order = None
        searched__conditional_order_ids = []
        searched__active_order_ids = []

        if self.is_ws_available == True:
            # If we are looking for Conditional Order
            if conditional_oid is not None:
                search_into_ws_conditional_order = True
                search_into_ws_active_order = True
            # If we are looking for Active Order
            else:
                legality_check_not_none_obj(order_id, "order_id")
                search_into_ws_active_order = True

            if self.debug:
                # # TODO: Debug use
                # frameinfo = inspect.getframeinfo(inspect.currentframe())
                # msg = "{} Line: {}: DEBUG: {}: ".format(
                #     frameinfo.function, frameinfo.lineno,
                #     threading.current_thread().name,
                # )
                # msg += "search_into_ws_conditional_order: {}, ".format(search_into_ws_conditional_order)
                # msg += "search_into_ws_active_order: {}, ".format(search_into_ws_active_order)
                #
                # # Strip ", " from the string
                # print(msg[:-2])
                pass

            if search_into_ws_conditional_order == True:
                if self.debug:
                    # TODO: Debug use
                    frameinfo = inspect.getframeinfo(inspect.currentframe())
                    msg = "{} Line: {}: DEBUG: {}: ".format(
                        frameinfo.function, frameinfo.lineno,
                        datetime.datetime.now().isoformat().replace(
                            "T", " ")[:-3],
                    )
                    msg += "len(self.ws_conditional_orders[{}]): {}".format(
                        symbol_id,
                        len(self.ws_conditional_orders[symbol_id]),
                    )
                    print(msg)
                    pass

                for i, conditional_order in enumerate(self.ws_conditional_orders[symbol_id]):
                    searched__conditional_order_ids.append(
                        conditional_order['id'])
                    if self.debug:
                        # TODO: Debug use
                        frameinfo = inspect.getframeinfo(
                            inspect.currentframe())
                        msg = "{} Line: {}: DEBUG: {}: ".format(
                            frameinfo.function, frameinfo.lineno,
                            datetime.datetime.now().isoformat().replace(
                                "T", " ")[:-3],
                        )
                        msg += "{}/{}: detected conditional_order['id']: {}".format(
                            i + 1,
                            len(self.ws_conditional_orders[symbol_id]),
                            conditional_order['id'],
                        )
                        print(msg)

                    if search_order_id == conditional_order['id']:
                        # Extract the order from the websocket
                        order = conditional_order
                        found_order_in_ws = True
                        break

            if found_order_in_ws == False:
                if search_into_ws_active_order == True:
                    if self.debug:
                        # TODO: Debug use
                        frameinfo = inspect.getframeinfo(
                            inspect.currentframe())
                        msg = "{} Line: {}: DEBUG: {}: ".format(
                            frameinfo.function, frameinfo.lineno,
                            datetime.datetime.now().isoformat().replace(
                                "T", " ")[:-3],
                        )
                        msg += "len(self.ws_active_orders[{}]): {}".format(
                            symbol_id,
                            len(self.ws_active_orders[symbol_id]),
                        )
                        print(msg)

                    for i, active_order in enumerate(self.ws_active_orders[symbol_id]):
                        searched__active_order_ids.append(active_order['id'])
                        if self.debug:
                            # TODO: Debug use
                            frameinfo = inspect.getframeinfo(
                                inspect.currentframe())
                            msg = "{} Line: {}: DEBUG: {}: ".format(
                                frameinfo.function, frameinfo.lineno,
                                datetime.datetime.now().isoformat().replace(
                                    "T", " ")[:-3],
                            )
                            msg += "{}/{}: detected active_order['id']: {}".format(
                                i + 1,
                                len(self.ws_active_orders[symbol_id]),
                                active_order['id'],
                            )
                            print(msg)

                        if search_order_id == active_order['id']:
                            # Extract the order from the websocket
                            order = active_order
                            found_order_in_ws = True
                            break

            if found_order_in_ws == False:
                frameinfo = inspect.getframeinfo(inspect.currentframe())

                # TODO: Debug use
                msg = "{} Line: {}: DEBUG: {}: ".format(
                    frameinfo.function, frameinfo.lineno,
                    datetime.datetime.now().isoformat().replace("T", " ")[:-3],
                )
                sub_msg = "searched__conditional_order_ids:"
                print(msg + sub_msg)
                pprint(searched__conditional_order_ids)
                sub_msg = "searched__active_order_ids:"
                print(msg + sub_msg)
                pprint(searched__active_order_ids)

                msg = "{} Line: {}: WARNING: {}: ".format(
                    frameinfo.function, frameinfo.lineno,
                    datetime.datetime.now().isoformat().replace("T", " ")[:-3],
                )
                sub_msg = "order id: \'{}\' not found in Websocket. Trying to search using HTTP instead...".format(
                    search_order_id,
                )
                # Credits: https://stackoverflow.com/questions/3419984/print-to-the-same-line-and-not-a-new-line
                # Print on the same line without newline, customized accordingly to cater for our requirement
                print("\r" + msg + sub_msg, end="")
                order = self._snail_path_to_fetch_order_from_exchange(
                    order_id, symbol_id, params)
        else:
            frameinfo = inspect.getframeinfo(inspect.currentframe())
            msg = "{} Line: {}: WARNING: {}: ".format(
                frameinfo.function, frameinfo.lineno,
                datetime.datetime.now().isoformat().replace("T", " ")[:-3],
            )
            sub_msg = "Websocket is not available, searching order id: \'{}\' using HTTP...".format(
                search_order_id,
            )
            print(msg + sub_msg)
            order = self._snail_path_to_fetch_order_from_exchange(
                order_id, symbol_id, params)

        # It is OK to have order is None here
        return order

    @retry
    def _fetch_orders(self, symbol=None, since=None, limit=None, params={}):
        if symbol is None:
            return self.exchange.fetch_orders(
                since=since, limit=limit, params=params)
        else:
            return self.exchange.fetch_orders(
                symbol=symbol, since=since, limit=limit, params=params)

    @retry
    def _fetch_opened_orders(self, symbol=None, since=None, limit=None, params={}):
        if symbol is None:
            return self.exchange.fetch_open_orders(
                since=since, limit=limit, params=params)
        else:
            return self.exchange.fetch_open_orders(
                symbol=symbol, since=since, limit=limit, params=params)

    @retry
    def _fetch_closed_orders(self, symbol=None, since=None, limit=None, params={}):
        if symbol is None:
            return self.exchange.fetch_closed_orders(
                since=since, limit=limit, params=params)
        else:
            return self.exchange.fetch_closed_orders(
                symbol=symbol, since=since, limit=limit, params=params)

    @retry
    def _fetch_opened_positions_from_exchange(self, symbols=None, params={}):
        assert len(symbols) == 1
        # pprint("symbols: {}, params: {}".format(symbols, params))
        return self.exchange.fetch_positions(symbols=symbols, params=params)

    def _fetch_opened_positions(self, symbols=None, params={}):
        assert len(symbols) == 1
        symbol_id = symbols[0]
        if self.is_ws_available == True:
            if len(self.ws_positions[symbol_id]) > 0:
                ret_positions = self.ws_positions[symbol_id]
            else:
                # Exercise the longer time route
                ret_positions = self._fetch_opened_positions_from_exchange(
                    [symbol_id], params)

                # Cache the position as if websocket positions. This will prevent us to hit the exchange rate limit.
                self.ws_positions[symbol_id] = ret_positions
        else:
            ret_positions = self._fetch_opened_positions_from_exchange(
                [symbol_id], params)
        return ret_positions

    def _post_process__after_parent_is_added(self):
        if self.exchange_dropdown_value == BINANCE_EXCHANGE_ID:
            if self.market_type == CCXT__MARKET_TYPE__FUTURE:
                get__response = self.exchange.fapiPrivate_get_positionside_dual()
                if get__response['dualSidePosition'] != BINANCE__FUTURES__DEFAULT_DUAL_POSITION_MODE:
                    set_position_mode__dict = dict(
                        type=CCXT__MARKET_TYPES[self.market_type],
                    )
                    set__response = self.exchange.set_position_mode(
                        hedged=BINANCE__FUTURES__DEFAULT_DUAL_POSITION_MODE, params=set_position_mode__dict)
                    # Confirmation
                    assert set__response['msg'] == "success"

                    frameinfo = inspect.getframeinfo(inspect.currentframe())
                    msg = "{}: {} Line: {}: INFO: Sync with {}: ".format(
                        CCXT__MARKET_TYPES[self.market_type],
                        frameinfo.function, frameinfo.lineno,
                        self.exchange_dropdown_value,
                    )
                    sub_msg = "Adjusted Dual/Hedge Position Mode from {} -> {}".format(
                        False,
                        BINANCE__FUTURES__DEFAULT_DUAL_POSITION_MODE,
                    )
                    print(msg + sub_msg)
                    pass
            elif self.market_type == CCXT__MARKET_TYPE__SPOT:
                # Do nothing here
                pass
            else:
                raise NotImplementedError("{} market type is not yet enabled for {} exchange".format(
                    CCXT__MARKET_TYPES[self.market_type],
                    self.exchange_dropdown_value,
                ))
        else:
            # Do nothing here
            pass

    @retry
    def _get_orderbook(self, symbol_id):
        return self.exchange.fetchOrderBook(symbol=symbol_id)

    def get_orderbook(self, symbol_id):
        response = self._get_orderbook(symbol_id=symbol_id)
        '''
        Sample response:
        {'asks': [[0.06398, 13.0],
                  [0.064, 644.0],
                  .
                  .
                  .
                  [0.08939, 232861.0],
                  [0.0895, 458091.0]],
         'bids': [[0.06397, 1689.0],
                  [0.0638, 859.0],
                  .
                  .
                  .
                  [0.06205, 452512.0],
                  [0.06203, 208200.0]],
        '''
        return response
