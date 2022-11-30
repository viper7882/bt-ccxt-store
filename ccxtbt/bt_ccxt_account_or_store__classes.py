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
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

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

from .bt_ccxt__specifications import CASH_DIGITS
from .bt_ccxt_order__classes import BT_CCXT_Order
from .bt_ccxt_exchange__classes import BT_CCXT_Exchange
from .utils import legality_check_not_none_obj, round_to_nearest_decimal_points, dump_obj, truncate, get_time_diff, \
    get_ccxt_order_id


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

    def __init__(self, exchange_dropdown_value, wallet_currency, config, retries, symbols_id,
                 main_net_toggle_switch_value, initial__capital_reservation__value, is_ohlcv_provider,
                 account__thread__connectivity__lock, debug=False):
        super().__init__()

        # WARNING: Must rename to init2 here or else it will cause
        #          TypeError: BT_CCXT_Account_or_Store.init() missing 7 required positional arguments:
        self.init2(exchange_dropdown_value, wallet_currency, config, retries, symbols_id, main_net_toggle_switch_value,
                   initial__capital_reservation__value, is_ohlcv_provider, account__thread__connectivity__lock,
                   debug)
    
    def init2(self, exchange_dropdown_value, wallet_currency, config, retries, symbols_id, main_net_toggle_switch_value,
             initial__capital_reservation__value, is_ohlcv_provider, account__thread__connectivity__lock, debug=False):
        # Legality Check
        assert isinstance(retries, int)
        assert isinstance(symbols_id, list)
        assert isinstance(main_net_toggle_switch_value, bool)
        assert isinstance(initial__capital_reservation__value, int) or \
               isinstance(initial__capital_reservation__value, float)
        assert isinstance(is_ohlcv_provider, bool)

        # Alias
        self.wallet_currency = wallet_currency
        self.account_alias = config['account_alias']
        self.account_type = config['account_type']
        self.retries = retries
        self.symbols_id = symbols_id
        self.main_net_toggle_switch_value = main_net_toggle_switch_value
        self._initial__capital_reservation__value = initial__capital_reservation__value
        self._live__capital_reservation__value = initial__capital_reservation__value
        self.is_ohlcv_provider = is_ohlcv_provider
        self.account__thread__connectivity__lock = account__thread__connectivity__lock
        self.debug = debug
        self._cash_snapshot = 0.0

        # Legality Check
        legality_check_not_none_obj(self.account__thread__connectivity__lock,
                                    "self.account__thread__connectivity__lock")

        self.parent = None
        self.ccxt_instruments = []

        self.account = collections.defaultdict(backtrader.utils.AutoOrderedDict)
        self.exchange = getattr(ccxt, exchange_dropdown_value)(config)
        self.exchange.set_sandbox_mode(not self.main_net_toggle_switch_value)

        self.config__api_key = None
        self.config__api_secret = None

        self.notifs = queue.Queue()  # holds orders which are notified
        self.open_orders = list()
        self.indent = 4  # For pretty printing dictionaries
        self.use_order_params = True

        # INFO: 15 seconds of retry
        self.max_retry = 15 * 10

        # INFO: Track the partially_filled_earlier status
        self.partially_filled_earlier = None

        # INFO: Invoke websocket if available
        self.is_ws_available = False
        self.ws_mainnet_usdt_perpetual = None
        self.ws_usdt_perpetual = None

        # INFO: For sensitive section, apply thread-safe locking mechanism to guarantee connection is completely
        #       established before moving on to another thread
        with self.account__thread__connectivity__lock:
            # INFO: Support for Bybit below
            if str(self.exchange).lower() == "bybit":
                self.is_ws_available = True
                self.config__api_key = config['apiKey']
                self.config__api_secret = config['secret']

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
            balance = self.exchange.fetch_balance() if 'secret' in config else 0.0

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

    def get_commission_info(self):
        return self.commission_info[None]

    def get_balance(self):
        self.get_balance()
        self.cash = self._cash
        self.value = self._value
        return self.cash, self.value

    def get_wallet_balance(self, currency, params={}):
        balance = self.get_wallet_balance(currency, params=params)
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
            self.get_balance()
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
        assert type(order).__name__ == BT_CCXT_Order.__name__, \
            "{} Line: {}: Expected {} but observed {} instead!!!".format(
                inspect.getframeinfo(inspect.currentframe()).function,
                inspect.getframeinfo(inspect.currentframe()).lineno,
                BT_CCXT_Order.__name__, type(order).__name__,
            )
        self.notifs.put(order.clone())

    def next(self):
        if self.debug:
            print('Broker next() called')

        for order in self.open_orders:
            oID = order.ccxt_order['id']

            # Print debug before fetching so we know which order is giving an
            # issue if it crashes
            if self.debug:
                print('Fetching Order ID: {}'.format(oID))

            if self.partially_filled_earlier is not None:
                # INFO: Carry forward partially_filled_earlier status to the next order
                order.partially_filled_earlier = self.partially_filled_earlier

            # Get the order
            if order.ordering_type == backtrader.Order.ACTIVE_ORDERING_TYPE:
                ccxt_order = self.fetch_order(oID, order.datafeed.p.dataname)
            else:
                # Validate assumption made
                assert order.ordering_type == backtrader.Order.CONDITIONAL_ORDERING_TYPE

                fetch_order__dict = dict(
                    stop_order_id=oID,
                )
                ccxt_order = self.fetch_order(None, order.datafeed.p.dataname, params=fetch_order__dict)

            if ccxt_order is not None:
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
                if 'trades' in ccxt_order and ccxt_order['trades'] is not None:
                    for fill in ccxt_order['trades']:
                        if fill not in order.executed_fills:
                            # INFO: Execute according to the OrderExecutionBit
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
                    msg = "{} Line: {}: DEBUG: ccxt_order:".format(
                        frameinfo.function, frameinfo.lineno,
                    )
                    print(msg)
                    print(json.dumps(ccxt_order, indent=self.indent))

                # Check if the exchange order is opened
                if ccxt_order[self.parent.mappings['opened_order']['key']] == \
                        self.parent.mappings['opened_order']['value']:
                    if order.status != backtrader.Order.Accepted:
                        # INFO: Reset partially_filled_earlier status
                        self.partially_filled_earlier = None

                        # INFO: Refresh the content of ccxt_order with the latest ccxt_order
                        order.extract_from_ccxt_order(ccxt_order)
                        order.accept()
                        self.notify(order)
                # Check if the exchange order is partially filled
                elif ccxt_order[self.parent.mappings['partially_filled_order']['key']] == \
                        self.parent.mappings['partially_filled_order']['value']:
                    if order.status != backtrader.Order.Partial:
                        # INFO: Refresh the content of ccxt_order with the latest ccxt_order
                        order.extract_from_ccxt_order(ccxt_order)
                        order.partial()

                        # INFO: Only notify but NOT execute as it wouldn't create any impact to the trade.update
                        # self.execute(order, order.price)
                        self.notify(order)

                        # INFO: Carry forward partially_filled_earlier status to the next order
                        self.partially_filled_earlier = order.partially_filled_earlier
                # Check if the exchange order is closed
                elif ccxt_order[self.parent.mappings['closed_order']['key']] == \
                        self.parent.mappings['closed_order']['value']:
                    # INFO: Refresh the content of ccxt_order with the latest ccxt_order
                    order.extract_from_ccxt_order(ccxt_order)
                    order.completed()
                    self.execute(order, order.price)
                    self.open_orders.remove(order)
                    self.get_balance()
                # Check if the exchange order is rejected
                elif ccxt_order[self.parent.mappings['rejected_order']['key']] == \
                        self.parent.mappings['rejected_order']['value']:
                    # INFO: Refresh the content of ccxt_order with the latest ccxt_order
                    order.extract_from_ccxt_order(ccxt_order)
                    order.reject()
                    self.notify(order)
                    self.open_orders.remove(order)
                # Manage case when an order is being Canceled or Expired from the Exchange
                #  from https://github.com/juancols/bt-ccxt-store/
                elif ccxt_order[self.parent.mappings['canceled_order']['key']] == \
                        self.parent.mappings['canceled_order']['value']:
                    # INFO: Refresh the content of ccxt_order with the latest ccxt_order
                    order.extract_from_ccxt_order(ccxt_order)
                    order.cancel()
                    self.notify(order)
                    self.open_orders.remove(order)
                elif ccxt_order[self.parent.mappings['expired_order']['key']] == \
                        self.parent.mappings['expired_order']['value']:
                    # INFO: Refresh the content of ccxt_order with the latest ccxt_order
                    order.extract_from_ccxt_order(ccxt_order)
                    order.expire()
                    self.notify(order)
                    self.open_orders.remove(order)
                else:
                    msg = "{} Line: {}: {}: WARNING: ".format(
                        inspect.getframeinfo(inspect.currentframe()).function,
                        inspect.getframeinfo(inspect.currentframe()).lineno,
                        datetime.datetime.now().isoformat().replace("T", " ")[:-3],
                    )
                    sub_msg = "ccxt_order id: {}, status: {} is not processed".format(
                        ccxt_order['id'],
                        ccxt_order[self.parent.mappings['opened_order']['key']],
                    )
                    print(msg + sub_msg)
                    pass

    def _submit(self, owner, datafeed, execution_type, side, amount, price, position_type, ordering_type, order_intent,
                simulated, params):
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

        execution_type_name = self.parent.order_types.get(execution_type) if execution_type else 'market'

        if datafeed:
            created = int(datafeed.datetime.datetime(0).timestamp()*1000)
            symbol_id = params['params']['symbol']
        else:
            # INFO: Use the current UTC datetime
            utc_dt = datetime.datetime.utcnow()
            created = int(utc_dt.timestamp()*1000)
            symbol_id = params['params']['symbol']
            # INFO: Remove symbol name from params
            params['params'].pop('symbol', None)

        # Extract CCXT specific params if passed to the order
        order_params = params['params'] if 'params' in params else params
        if not self.use_order_params:
            ret_ord = \
                self.create_order(symbol=symbol_id, order_type=execution_type_name, side=side, amount=amount,
                                  price=price, params={})
        else:
            try:
                # all params are exchange specific: https://github.com/ccxt/ccxt/wiki/Manual#custom-order-params
                order_params['created'] = created  # Add timestamp of order creation for backtesting
                ret_ord = \
                    self.create_order(symbol=symbol_id, order_type=execution_type_name, side=side, amount=amount,
                                      price=price, params=order_params)
            except:
                # save some API calls after failure
                self.use_order_params = False
                return None

        if ret_ord is None or ret_ord['id'] is None:
            return None

        if 'stop_order_id' in ret_ord['info'].keys():
            oid = None
            stop_order_id = ret_ord['id']
        else:
            oid = ret_ord['id']
            stop_order_id = None

        ccxt_order = self.fetch_ccxt_order(symbol_id, oid=oid, stop_order_id=stop_order_id)
        legality_check_not_none_obj(ccxt_order, "ccxt_order")

        # INFO: Exposed simulated so that we could proceed with order without running cerebro
        order = BT_CCXT_Order(owner, datafeed, ccxt_order, execution_type, symbol_id, position_type, ordering_type, 
                              order_intent)

        # Check if the exchange order is NOT closed
        if ccxt_order[self.parent.mappings['closed_order']['key']] != self.parent.mappings['closed_order']['value']:
            # Mark order as submitted
            order.submit()
            order = self.add__commission_info(order)
            self.notify(order)
        self.open_orders.append(order)
        return order

    def fetch_ccxt_order(self, symbol_id, oid=None, stop_order_id=None):
        # Mutually exclusive legality check
        if oid is None:
            legality_check_not_none_obj(stop_order_id, "stop_order_id")

        if stop_order_id is None:
            legality_check_not_none_obj(oid, "oid")

        # One of these must be valid
        assert oid is not None or stop_order_id is not None

        ccxt_order = None
        for retry_no in range(self.max_retry):
            try:
                # INFO: Due to nature of order is processed async, the order could not be found immediately right after
                #       order is opened. Hence, perform retry to confirm if that's the case.
                if stop_order_id is not None:
                    # Conditional Order
                    params = dict(
                        stop_order_id=stop_order_id,
                    )
                    ccxt_order = \
                        self.fetch_order(oid=None, symbol_id=symbol_id, params=params)
                else:
                    # Active Order
                    ccxt_order = self.fetch_order(oid=oid, symbol_id=symbol_id)

                if ccxt_order is not None:
                    if stop_order_id is not None:
                        order_type_name = 'Conditional'
                    else:
                        order_type_name = 'Active'
                    break
            except OrderNotFound:
                time.sleep(0.1)
                pass

        return ccxt_order

    def add__commission_info(self, order):
        # Get commission_info object for the datafeed
        commission_info = self.get_commission_info()
        order.add_commission_info(commission_info)
        return order

    def execute(self, order, price, spread_in_ticks=1, dt_in_float=None, skip_notification=False):
        # Legality Check
        legality_check_not_none_obj(order, "order")
        # ago = None is used a flag for pseudo execution
        legality_check_not_none_obj(price, "price")
        assert math.isnan(price) == False, "price must not be NaN value!!!"
        assert isinstance(spread_in_ticks, int) or isinstance(spread_in_ticks, float)
        if dt_in_float is not None:
            assert isinstance(dt_in_float, float)
        assert isinstance(skip_notification, bool)

        datafeed = order.datafeed

        # Legality Check
        legality_check_not_none_obj(datafeed, "datafeed")

        datafeed_dt = datafeed.datetime.datetime(0)

        # Legality Check
        assert isinstance(datafeed_dt, datetime.datetime)

        if order.ccxt_order is None:
            # Validate assumption made
            assert isinstance(order, dict)

            ccxt_order_id = self.get_ccxt_order_id(order)
            legality_check_not_none_obj(order.ordering_type, "order.ordering_type")

            if order.ordering_type == backtrader.Order.ACTIVE_ORDERING_TYPE:
                order.ccxt_order = self.fetch_ccxt_order(order.symbol_id, oid=ccxt_order_id)
            else:
                # Validate assumption made
                assert order.ordering_type == backtrader.Order.CONDITIONAL_ORDERING_TYPE

                order.ccxt_order = \
                    self.fetch_ccxt_order(order.symbol_id, oid=None, stop_order_id=ccxt_order_id)

        # Legality Check
        legality_check_not_none_obj(order.ccxt_order, "order.ccxt_order")

        if order.status == order.Partial:
            size = order.executed.filled_size
        else:
            size = order.executed.remaining_size

        if size == 0.0:
            if skip_notification == False:
                self.notify(order)
            return

        # Get commission_info object for the datafeed
        commission_info = self.get_commission_info()

        # Adjust position with operation size
        # Real execution with date
        for ccxt_instrument in self.ccxt_instruments:
            if ccxt_instrument.symbol_id == order.symbol_id:
                position = ccxt_instrument.get_position(order.position_type, clone=False)
                pprice_orig = position.price

                # Do a real position update
                position_size, position_average_price, opened, closed = position.update(size, price, datafeed_dt)
                position_size = \
                    round_to_nearest_decimal_points(position_size, commission_info.qty_digits, commission_info.qty_step)
                position_average_price = \
                    round_to_nearest_decimal_points(position_average_price, commission_info.price_digits,
                                                    commission_info.symbol_tick_size)
                opened = round_to_nearest_decimal_points(opened, commission_info.qty_digits, commission_info.qty_step)
                closed = round_to_nearest_decimal_points(closed, commission_info.qty_digits, commission_info.qty_step)

                # split commission between closed and opened
                closed_commission = 0.0
                if closed:
                    if order.ccxt_order['fee'] is not None:
                        if order.ccxt_order['fee']['cost'] is not None:
                            closed_commission = order.ccxt_order['fee']['cost']

                    if closed_commission == 0.0:
                        closed_commission = commission_info.get_commission_rate(closed, price)

                opened_commission = 0.0
                if opened:
                    if order.ccxt_order['fee'] is not None:
                        if order.ccxt_order['fee']['cost'] is not None:
                            opened_commission = order.ccxt_order['fee']['cost']

                    if opened_commission == 0.0:
                        opened_commission = commission_info.get_commission_rate(opened, price)

                closed_value = commission_info.get_value_size(-closed, pprice_orig)
                opened_value = commission_info.get_value_size(opened, price)

                # The internal broker_or_exchange calc should yield the same result
                if closed:
                    profit_and_loss_amount = commission_info.profit_and_loss(-closed, pprice_orig, price)
                else:
                    profit_and_loss_amount = 0.0

                # Need to simulate a margin, but it plays no role, because it is
                # controlled by a real broker_or_exchange. Let's set the price of the item
                margin = datafeed.close[0]

                if dt_in_float is None:
                    execute_dt = datafeed.datetime[0]
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
                    ccxt_order_id = get_ccxt_order_id(order)
                    raise ValueError(
                        "{}: order id: {}: Both {:.{}f} x opened:{:.{}f}/closed:{:.{}f} of must be positive!!!".format(
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

                # INFO: size and price could deviate from its original value due to floating point precision error. The
                #       following codes are to provide remedy for that situation.
                order.executed.size = \
                    round_to_nearest_decimal_points(order.executed.size, commission_info.qty_digits,
                                                    commission_info.qty_step)
                order.executed.price = \
                    round_to_nearest_decimal_points(order.executed.price, commission_info.price_digits,
                                                    commission_info.symbol_tick_size)

                # Legality Check
                assert abs(order.executed.filled_size) == order.ccxt_order['filled'], \
                    "abs(order.executed.filled_size): {:.{}f} != Exchange's filled: {:.{}f}!!!".format(
                        abs(order.executed.filled_size), commission_info.qty_digits,
                        order.ccxt_order['filled'], commission_info.qty_digits,
                    )
                assert abs(order.executed.remaining_size) == order.ccxt_order['remaining'] , \
                    "abs(order.executed.remaining_size): {:.{}f} != Exchange's remaining: {:.{}f}!!!".format(
                        abs(order.executed.remaining_size), commission_info.qty_digits,
                        order.ccxt_order['remaining'], commission_info.qty_digits,
                    )

                order.add_commission_info(commission_info)
                if skip_notification == False:
                    self.notify(order)

                # Legality Check
                if order.symbol_id.endswith("USDT"):
                    if order.position_type == backtrader.Position.LONG_POSITION:
                        assert position_size >= 0.0, \
                            "For {} position, size: {:.{}f} must be zero or positive!!!".format(
                                backtrader.Position.Position_Types[order.position_type],
                                position_size, commission_info.qty_digits,
                            )
                    else:
                        # Validate assumption made
                        assert order.position_type == backtrader.Position.SHORT_POSITION

                        assert position_size <= 0.0, \
                            "For {} position, size: {:.{}f} must be zero or negative!!!".format(
                                backtrader.Position.Position_Types[order.position_type],
                                position_size, commission_info.qty_digits,
                            )
                else:
                    raise NotImplementedError("symbol_id: {} is yet to be supported!!!".format(order.symbol_id))

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

        return self._submit(owner, datafeed, execution_type, 'buy', size, price, position_type, ordering_type,
                            order_intent, simulated, kwargs)

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

        return self._submit(owner, datafeed, execution_type, 'sell', size, price, position_type, ordering_type,
                            order_intent, simulated, kwargs)

    def cancel(self, order):
        oID = order.ccxt_order['id']

        if self.debug:
            print('Broker cancel() called')
            print('Fetching Order ID: {}'.format(oID))

        # check first if the order has already been filled otherwise an error
        # might be raised if we try to cancel an order that is not open.
        # Get the order
        ccxt_order = None
        if order.ordering_type == backtrader.Order.ACTIVE_ORDERING_TYPE:
            ccxt_order = self.fetch_order(oID, order.datafeed.p.dataname)
        else:
            # Validate assumption made
            assert order.ordering_type == backtrader.Order.CONDITIONAL_ORDERING_TYPE

            fetch_order__dict = dict(
                stop_order_id=oID,
            )
            ccxt_order = self.fetch_order(None, order.datafeed.p.dataname, params=fetch_order__dict)
        legality_check_not_none_obj(ccxt_order, "ccxt_order")

        if self.debug:
            frameinfo = inspect.getframeinfo(inspect.currentframe())
            msg = "{} Line: {}: DEBUG: ccxt_order:".format(
                frameinfo.function, frameinfo.lineno,
            )
            print(msg)
            print(json.dumps(ccxt_order, indent=self.indent))

        # Check if the exchange order is closed
        if ccxt_order[self.parent.mappings['closed_order']['key']] == self.parent.mappings['closed_order']['value']:
            return order

        if order.ordering_type == backtrader.Order.ACTIVE_ORDERING_TYPE:
            ccxt_order = self.cancel_order(oID, order.datafeed.p.dataname)
        else:
            # Validate assumption made
            assert order.ordering_type == backtrader.Order.CONDITIONAL_ORDERING_TYPE

            fetch_order__dict = dict(
                stop_order_id=oID,
            )
            ccxt_order = self.cancel_order(None, order.datafeed.p.dataname, params=fetch_order__dict)

        if self.debug:
            frameinfo = inspect.getframeinfo(inspect.currentframe())
            msg = "{} Line: {}: DEBUG: ccxt_order:".format(
                frameinfo.function, frameinfo.lineno,
            )
            print(msg)
            print(json.dumps(ccxt_order, indent=self.indent))
            print('Value Expected: {}'.format(self.parent.mappings['canceled_order']['value']))
            print('Value Received: {}'.format(ccxt_order[self.parent.mappings['canceled_order']['key']]))

        # Check if the exchange order is cancelled
        if ccxt_order[self.parent.mappings['canceled_order']['key']] == self.parent.mappings['canceled_order']['value']:
            self.open_orders.remove(order)
            order.cancel()
            self.notify(order)
        return order

    def modify_order(self, order_id, symbol, type, side, amount=None, price=None, trigger_price=None, params={}):
        return self._edit_order(order_id, symbol, type, side, amount=amount, price=price,
                                trigger_price=trigger_price, params=params)

    def get_orders(self, symbol=None, since=None, limit=None, params={}):
        return self._fetch_orders(symbol=symbol, since=since, limit=limit, params=params)

    def fetch_opened_orders(self, symbol=None, since=None, limit=None, params={}):
        return self._fetch_opened_orders(symbol=symbol, since=since, limit=limit, params=params)

    def fetch_closed_orders(self, symbol=None, since=None, limit=None, params={}):
        return self.fetch_closed_orders(symbol=symbol, since=since, limit=limit, params=params)

    def get_positions(self, symbols=None, params={}):
        return self._fetch_opened_positions(symbols, params)

    def __common_end_point(self, is_private, type, endpoint, params, prefix):
        endpoint_str = endpoint.replace('/', '_')
        endpoint_str = endpoint_str.replace('-', '_')
        endpoint_str = endpoint_str.replace('{', '')
        endpoint_str = endpoint_str.replace('}', '')

        private_or_public = "public"
        if is_private == True:
            private_or_public = "private"

        if prefix != "":
            method_str = prefix.lower() + "_" + private_or_public + "_" + type.lower() + endpoint_str.lower()
        else:
            method_str = private_or_public + "_" + type.lower() + endpoint_str.lower()

        return self.__private_end_point(type=type, endpoint=method_str, params=params)

    def public_end_point(self, type, endpoint, params, prefix = ""):
        is_private = False
        return self.__common_end_point(is_private, type, endpoint, params, prefix)

    def private_end_point(self, type, endpoint, params, prefix = ""):
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
                    )

                try:
                    self.ws_usdt_perpetual.order_stream(self.handle_active_order)
                    time.sleep(0.1)

                    self.ws_usdt_perpetual.stop_order_stream(self.handle_conditional_order)
                    time.sleep(0.1)

                    self.ws_usdt_perpetual.position_stream(self.handle_positions)
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

        # INFO: Only OHLCV_PROVIDER should be connected to ws_mainnet_usdt_perpetual
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
                )

                try:
                    if self.ws_mainnet_usdt_perpetual.is_connected() == True:
                        # Reference: https://bybit-exchange.github.io/docs/futuresV2/linear/#t-websocketkline
                        # INFO: Subscribe to 1 minute candle
                        if len(self.symbols_id) == 1:
                            self.ws_mainnet_usdt_perpetual.kline_stream(self.handle_klines, self.symbols_id[0], "1")
                            time.sleep(0.1)

                            self.ws_mainnet_usdt_perpetual.instrument_info_stream(self.handle_instrument_info_stream,
                                                                                  symbol=self.symbols_id[0])
                        else:
                            self.ws_mainnet_usdt_perpetual.kline_stream(self.handle_klines, self.symbols_id, "1")
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

    def get_account_alias(self):
        return self.account_alias

    def get_granularity(self, timeframe, compression):
        if not self.exchange.has['fetchOHLCV']:
            raise NotImplementedError("'%s' exchange doesn't support fetching OHLCV datafeed" %
                                      self.exchange.name)

        granularity = self._GRANULARITIES.get((timeframe, compression))
        if granularity is None:
            raise ValueError("backtrader CCXT module doesn't support fetching OHLCV "
                             "datafeed for time frame %s, compression %s" %
                             (backtrader.TimeFrame.getname(timeframe), compression))

        if self.exchange.timeframes and \
                granularity not in self.exchange.timeframes:
            raise ValueError("'%s' exchange doesn't support fetching OHLCV datafeed for "
                             "%s time frame" % (self.exchange.name, granularity))

        return granularity

    def handle_positions(self, message):
        '''
        This routine gets triggered whenever there is a position change. If the position does not changed, it will not
        appear in the message.
        '''
        try:
            # print("{} Line: {}: message:".format(
            #     inspect.getframeinfo(inspect.currentframe()).function,
            #     inspect.getframeinfo(inspect.currentframe()).lineno,
            # ))
            # pprint(message)
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
                results.append(self.exchange.parse_position(rawPosition, market))
            latest_changed_positions = self.exchange.filter_by_array(results, 'symbol', symbols, False)

            for symbol_id in symbols:
                if len(self.ws_positions[symbol_id]) == 0:
                    # Exercise the longer time route
                    # Store the outdated positions first
                    self.ws_positions[symbol_id] = \
                        self._fetch_opened_positions_from_exchange([symbol_id], params={'type': symbol_type})

                # INFO: Identify ws_position to be changed
                positions_to_be_changed = []
                for i, _ in enumerate(self.ws_positions[symbol_id]):
                    for latest_changed_position in latest_changed_positions:
                        if latest_changed_position['symbol'] == symbol_id:
                            if self.ws_positions[symbol_id][i]['side'] == \
                                    latest_changed_position['side']:
                                positions_to_be_changed.append((i, latest_changed_position))

                # INFO: Update with the latest position from websocket
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
            # print("{} Line: {}: message:".format(
            #     inspect.getframeinfo(inspect.currentframe()).function,
            #     inspect.getframeinfo(inspect.currentframe()).lineno,
            # ))
            # pprint(message)
            responses = message['data']
            assert type(responses) == list
            active_orders_to_be_added = collections.defaultdict(list)
            symbols_id = []
            for order in responses:
                market = self.get_market(order['symbol'])
                result = self.exchange.safe_value(message, 'data')
                active_order = self.exchange.parse_order(result[0], market)

                # INFO: Strip away "/" and ":USDT"
                active_order['symbol'] = active_order['symbol'].replace("/", "")
                active_order['symbol'] = active_order['symbol'].replace(":USDT", "")

                symbol_id = active_order['symbol']
                if symbol_id not in symbols_id:
                    symbols_id.append(symbol_id)

                active_orders_to_be_added[symbol_id].append(active_order)

            for symbol_id in symbols_id:
                active_order_ids_to_be_added = \
                    [active_order['id'] for active_order in active_orders_to_be_added[symbol_id]]

                # INFO: Look for existing order in the list
                ws_active_orders_to_be_removed = []
                for ws_active_order in self.ws_active_orders[symbol_id]:
                    if ws_active_order['id'] in active_order_ids_to_be_added:
                        ws_active_orders_to_be_removed.append(ws_active_order)

                # INFO: Remove the existing ws active order
                for ws_active_order in ws_active_orders_to_be_removed:
                    self.ws_active_orders[symbol_id].remove(ws_active_order)

                # INFO: Add the latest active orders
                for active_order in active_orders_to_be_added[symbol_id]:
                    self.ws_active_orders[symbol_id].append(active_order)
        except Exception:
            traceback.print_exc()

    def handle_conditional_order(self, message):
        try:
            # print("{} Line: {}: message:".format(
            #     inspect.getframeinfo(inspect.currentframe()).function,
            #     inspect.getframeinfo(inspect.currentframe()).lineno,
            # ))
            # pprint(message)
            responses = message['data']
            assert type(responses) == list
            conditional_orders_to_be_added = collections.defaultdict(list)
            symbols_id = []
            for order in responses:
                market = self.get_market(order['symbol'])
                result = self.exchange.safe_value(message, 'data')
                conditional_order = self.exchange.parse_order(result[0], market)

                # INFO: Strip away "/" and ":USDT"
                conditional_order['symbol'] = conditional_order['symbol'].replace("/", "")
                conditional_order['symbol'] = conditional_order['symbol'].replace(":USDT", "")

                symbol_id = conditional_order['symbol']
                if symbol_id not in symbols_id:
                    symbols_id.append(symbol_id)

            for symbol_id in symbols_id:
                conditional_order_ids_to_be_added = \
                    [conditional_order['id'] for conditional_order in conditional_orders_to_be_added[symbol_id]]

                # INFO: Look for existing order in the list
                ws_conditional_orders_to_be_removed = []
                for ws_conditional_order in self.ws_conditional_orders[symbol_id]:
                    if ws_conditional_order['id'] in conditional_order_ids_to_be_added:
                        ws_conditional_orders_to_be_removed.append(ws_conditional_order)

                # INFO: Remove the existing ws conditional order
                for ws_conditional_order in ws_conditional_orders_to_be_removed:
                    self.ws_conditional_orders[symbol_id].remove(ws_conditional_order)

                # INFO: Add the latest conditional orders
                for conditional_order in conditional_orders_to_be_added[symbol_id]:
                    self.ws_conditional_orders[symbol_id].append(conditional_order)
        except Exception:
            traceback.print_exc()

    def handle_klines(self, message):
        '''
        This routine gets triggered whenever there is a kline update.
        '''
        try:
            # print("{} Line: {}: message:".format(
            #     inspect.getframeinfo(inspect.currentframe()).function,
            #     inspect.getframeinfo(inspect.currentframe()).lineno,
            # ))
            # pprint(message)
            assert type(message['data']) == list
            topic_responses = self.exchange.safe_value(message, 'topic')
            data_responses = self.exchange.safe_value(message, 'data')

            topic_responses_split = topic_responses.split(".")
            assert len(topic_responses_split) == 3
            symbol_id = topic_responses_split[2]
            if len(data_responses) > 0:
                # References: https://bybit-exchange.github.io/docs/futuresV2/linear/#t-websocketkline
                # INFO: Data sent timestamp in seconds * 10^6
                tstamp = int(data_responses[0]['timestamp']) / 1e6
                ohlcv = \
                    (float(data_responses[0]['open']), float(data_responses[0]['high']),
                     float(data_responses[0]['low']), float(data_responses[0]['close']),
                     float(data_responses[0]['volume']))
                self.ws_klines[symbol_id] = (tstamp, ohlcv)
        except Exception:
            traceback.print_exc()

    def handle_instrument_info_stream(self, message):
        '''
        This routine gets triggered whenever there is instrument info update.
        '''
        try:
            # print("{} Line: {}: message:".format(
            #     inspect.getframeinfo(inspect.currentframe()).function,
            #     inspect.getframeinfo(inspect.currentframe()).lineno,
            # ))
            # pprint(message)
            assert type(message['data']) == dict
            responses = self.exchange.safe_value(message, 'data')
            if len(responses) > 0:
                # References: https://bybit-exchange.github.io/docs/futuresV2/linear/#t-websocketinstrumentinfo
                symbol_id = responses['symbol']
                mark_price = float(responses['mark_price'])
                ask1_price = float(responses['ask1_price'])
                bid1_price = float(responses['bid1_price'])
                self.ws_instrument_info[symbol_id] = (mark_price, ask1_price, bid1_price)
        except Exception:
            traceback.print_exc()

    def run_pulse_check_for_ws(self):
        if self.is_ws_available == True:
            self.establish_bybit_usdt_perpetual_websocket()
            self.establish_bybit_mainnet_usdt_perpetual_websocket()

    def retry(method):
        @wraps(method)
        def retry_method(self, *args, **kwargs):
            for i in range(self.retries):
                if self.debug:
                    print('{} - {} - Attempt {}'.format(datetime.datetime.now(), method.__name__, i))
                time.sleep(self.exchange.rateLimit / 1000)
                try:
                    return method(self, *args, **kwargs)
                except (NetworkError, ExchangeError) as e:
                    if i == self.retries - 1:
                        raise

                    if isinstance(e, ccxt.base.errors.ExchangeError):
                        # INFO: Extract the exchange name from the exception
                        json_error = e.args[0].replace(str(self.exchange).lower() + " ", "")
                        exchange_error_dict = json.loads(json_error)
                        if str(self.exchange).lower() == "bybit":
                            if exchange_error_dict['ret_code'] == 130125:
                                '''
                                'ret_msg' = 'current position is zero, cannot fix reduce-only order qty'
                                '''
                                break

                            # INFO: Print out warning regarding the response received from ExchangeError
                            msg = "{} Line: {}: WARNING: {}: {}/{}: ".format(
                                inspect.getframeinfo(inspect.currentframe()).function,
                                inspect.getframeinfo(inspect.currentframe()).lineno,
                                datetime.datetime.now().isoformat().replace("T", " ")[:-3],
                                i + 1, self.retries,
                            )
                            sub_msg = "{}: ret_msg: {}".format(
                                str(self.exchange).lower(),
                                exchange_error_dict['ret_msg'],
                            )
                            print(msg + sub_msg)
                    pass

        return retry_method

    @retry
    def get_market(self, symbol):
        market = self.exchange.market(symbol)
        return market

    @retry
    def get_wallet_balance(self, wallet_currency, params=None):
        balance = self.exchange.fetch_balance(params)
        return balance

    @retry
    def get_balance(self):
        balance = self.exchange.fetch_balance()

        cash = balance['free'][self.wallet_currency]
        value = balance['total'][self.wallet_currency]
        # Fix if None is returned
        self._cash = cash if cash else 0
        self._value = value if value else 0

    def get_position(self):
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
    def cancel_order(self, order_id, symbol, params):
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

        # INFO: Always fetch klines from MAINNET instead of TESTNET
        ret_value = mainnet__account_or_store.ws_klines[dataname]
        return ret_value

    @retry
    def fetch_ohlcv(self, symbol, timeframe, since, limit, params={}):
        if self.debug:
            since_dt = datetime.datetime.utcfromtimestamp(since // 1000) if since is not None else 'NA'
            print('Fetching: {}, timeframe:{}, since TS:{}, since_dt:{}, limit:{}, params:{}'.format(
                symbol, timeframe, since, since_dt, limit, params))

        if self.main_net_toggle_switch_value == True:
            mainnet_exchange = self.exchange
        else:
            ohlcv_provider__account_or_store = self.parent.get_ohlcv_provider__account_or_store()
            mainnet_exchange = ohlcv_provider__account_or_store.exchange

        # INFO: Always fetch OHLCV from MAINNET instead of TESTNET
        ret_value = mainnet_exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit, params=params)
        return ret_value

    @retry
    def fetch_order_book(self, symbol, limit=None, params={}):
        if self.main_net_toggle_switch_value == True:
            mainnet_exchange = self.exchange
        else:
            ohlcv_provider__account_or_store = self.parent.get_ohlcv_provider__account_or_store()
            mainnet_exchange = ohlcv_provider__account_or_store.exchange

        # INFO: Always fetch order book from MAINNET instead of TESTNET
        ret_value = mainnet_exchange.fetch_order_book(symbol, limit=limit, params=params)
        return ret_value

    @retry
    def _fetch_order_from_exchange(self, oid, symbol_id, params={}):
        order = None
        try:
            # INFO: Due to nature of order is processed async, the order could not be found immediately right after
            #       order is is opened. Hence, perform retry to confirm if that's the case.
            order = self.exchange.fetch_order(oid, symbol_id, params)
        except OrderNotFound:
            # INFO: Ignore order not found error
            pass
        return order

    def fetch_order(self, oid, symbol_id, params={}):
        conditional_oid = params.get('stop_order_id', None)
        if oid is None:
            legality_check_not_none_obj(conditional_oid, "conditional_oid")

        if self.is_ws_available == True:
            found_ws_order = False
            # If we are looking for Active Order
            if oid is not None:
                for active_order in self.ws_active_orders[symbol_id]:
                    if oid == active_order['id']:
                        # Extract the order from the websocket
                        order = active_order
                        # self.ws_active_orders[symbol_id].remove(active_order)
                        found_ws_order = True
                        break
            # Else if we are looking for Conditional Order
            else:
                for conditional_order in self.ws_conditional_orders[symbol_id]:
                    if conditional_oid == conditional_order['id']:
                        # Extract the order from the websocket
                        order = conditional_order
                        # self.ws_conditional_orders[symbol_id].remove(conditional_order)
                        found_ws_order = True
                        break

            if found_ws_order == False:
                if oid is not None:
                    # Exercise the longer time route
                    order = self._fetch_order_from_exchange(oid, symbol_id, params)
                else:
                    order = self._fetch_order_from_exchange(conditional_oid, symbol_id, params)
        else:
            if oid is not None:
                order = self._fetch_order_from_exchange(oid, symbol_id, params)
            else:
                order = self._fetch_order_from_exchange(conditional_oid, symbol_id, params)
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
        return self.exchange.fetch_positions(symbols=symbols, params=params)

    def _fetch_opened_positions(self, symbols=None, params={}):
        assert len(symbols) == 1
        symbol_id = symbols[0]
        if self.is_ws_available == True:
            if len(self.ws_positions[symbol_id]) > 0:
                ret_positions = self.ws_positions[symbol_id]
            else:
                # Exercise the longer time route
                ret_positions = self._fetch_opened_positions_from_exchange([symbol_id], params)

                # Cache the position as if websocket positions. This will prevent us to hit the exchange rate limit.
                self.ws_positions[symbol_id] = ret_positions
        else:
            ret_positions = self._fetch_opened_positions_from_exchange([symbol_id], params)
        return ret_positions

    @retry
    def __private_end_point(self, type, endpoint, params):
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
