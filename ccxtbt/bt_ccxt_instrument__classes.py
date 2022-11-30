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

import threading
from pprint import pprint

import backtrader
import collections
import inspect

from .bt_ccxt_account_or_store__classes import BT_CCXT_Account_or_Store
from .bt_ccxt_expansion__classes import Enhanced_Position
from .utils import legality_check_not_none_obj


class Meta_Instrument(backtrader.MetaParams):
    def __init__(cls, name, bases, dct):
        '''
        Class has already been created ... fill missing methods if needed be
        '''
        # Initialize the class
        super().__init__(name, bases, dct)

        # Register with broker_or_exchange
        BT_CCXT_Account_or_Store.Instrument_Cls = cls


class BT_CCXT_Instrument(backtrader.with_metaclass(Meta_Instrument, object)):
    Datafeed_Cls = None  # datafeed class will auto register

    @classmethod
    def instantiate_datafeed(cls, *args, **kwargs):
        '''Returns ``Datafeed_Cls`` with args, kwargs'''
        return cls.Datafeed_Cls(*args, **kwargs)

    def __init__(self, symbol_id):
        super().__init__()

        legality_check_not_none_obj(symbol_id, "symbol_id")

        self.symbol_id = symbol_id
        self.parent = None
        self.ccxt_datafeeds = []

        # INFO: Switch positions to exercise Enhanced Position instead
        self.positions = collections.defaultdict(Enhanced_Position)

        self.payload = backtrader.AutoOrderedDict()
        self.current_thread = threading.current_thread()
        self._generation = None
        self._event_stop = False

    def __repr__(self):
        return str(self)

    def __str__(self):
        items = list()
        items.append('--- BT_CCXT_Instrument Begin ---')
        items.append('- Symbol ID: {}'.format(self.symbol_id))
        items.append('--- BT_CCXT_Instrument End ---')
        ret_value = str('\n'.join(items))
        return ret_value

    def set__parent(self, owner):
        self.parent = owner

    def get__parent(self):
        return self.parent

    def add__datafeed(self, datafeed):
        found_datafeed = False
        for ccxt_datafeed in self.ccxt_datafeeds:
            if datafeed._name == ccxt_datafeed._name:
                found_datafeed = True
                break

        if found_datafeed == False:
            self.ccxt_datafeeds.append(datafeed)

    def fetch_ohlcv(self, symbol, timeframe, since, limit):
        return self.parent.fetch_ohlcv(symbol, timeframe, since, limit)

    def get_granularity(self, timeframe, compression):
        return self.parent.get_granularity(timeframe, compression)

    def parse_timeframe(self, granularity):
        return self.parent.parse_timeframe(granularity)

    def filter_by_since_limit(self, all_ohlcv, since, limit, key):
        return self.parent.filter_by_since_limit(all_ohlcv, since, limit, key)

    def is_ws_available(self):
        return self.parent.is_ws_available

    def get_ws_klines(self, dataname):
        return self.parent.fetch_ws_klines(dataname)

    def get_ws_active_orders(self, symbol_id):
        return self.parent.ws_active_orders[symbol_id]

    def remove_ws_active_order(self, symbol_id, ws_active_order):
        self.parent.ws_active_orders[symbol_id].remove(ws_active_order)

        # INFO: Double check if the entry has been removed properly
        ws_active_orders = self.get_ws_active_orders(symbol_id)
        assert ws_active_order not in ws_active_orders

    def get_ws_conditional_orders(self, symbol_id):
        return self.parent.ws_conditional_orders[symbol_id]

    def remove_ws_conditional_order(self, symbol_id, ws_conditional_order):
        self.parent.ws_conditional_orders[symbol_id].remove(ws_conditional_order)

        # INFO: Double check if the entry has been removed properly
        ws_conditional_orders = self.get_ws_conditional_orders(symbol_id)
        assert ws_conditional_order not in ws_conditional_orders

    def fetch_order_book(self, symbol):
        return self.parent.fetch_order_book(symbol)

    def get_commission_info(self):
        return self.parent.get_commission_info()

    def fetch_order(self, oid, symbol, params={}):
        return self.parent.fetch_order(oid, symbol, params)

    def get_orders(self, **kwarg):
        return self.parent.get_orders(**kwarg)

    def set_cash(self, cash):
        return self.parent.set_cash(cash)

    def get_cash(self, **kwarg):
        return self.parent.get_cash(**kwarg)

    def get_value(self, **kwarg):
        return self.parent.get_value(**kwarg)

    def set_live__capital_reservation__value(self, live__capital_reservation__value):
        return self.parent.set_live__capital_reservation__value(live__capital_reservation__value)

    def get_live__capital_reservation__value(self):
        return self.parent.get_live__capital_reservation__value()

    def get_initial__capital_reservation__value(self):
        return self.parent.get_initial__capital_reservation__value()

    def set_cash_snapshot(self):
        return self.parent.set_cash_snapshot()

    def get_cash_snapshot(self):
        return self.parent.get_cash_snapshot()

    def set__stop_running(self):
        self._event_stop = True

    def get__stop_running(self):
        return self._event_stop

    def modify_order(self, order_id, symbol, type, side, amount=None, price=None, trigger_price=None, params={}):
        return self.parent.modify_order(order_id, symbol, type, side, amount=amount, price=price, 
                                        trigger_price=trigger_price, params=params)

    def fetch_ccxt_order(self, symbol_id, oid=None, stop_order_id=None):
        return self.parent.fetch_ccxt_order(symbol_id=symbol_id, oid=oid, stop_order_id=stop_order_id)

    def set__payload(self, payload):
        self.payload = payload

    def get__payload(self):
        return self.payload

    def set__payload_with_value(self, key, value):
        setattr(self.payload, key, value)

    def get__payload_with_value(self, key):
        return getattr(self.payload, key)

    def get__thread_name(self):
        return self.current_thread.name

    def set__generation(self, generation):
        self._generation = generation

    def get__generation(self):
        return self._generation

    def get_position(self, position_type, clone=True, debug=False):
        '''Returns the current position status (a ``Position`` instance) for a given ``position_type``'''
        if position_type not in range(len(backtrader.Position.Position_Types)):
            raise ValueError("{}: {} position_type must be one of {}!!!".format(
                inspect.currentframe(), position_type, range(len(backtrader.Position.Position_Types))))

        if len(self.positions.items()) < position_type:
            self.positions[position_type] = Enhanced_Position(size=0.0, price=0.0)
            ret_value = self.positions[position_type]
        else:
            if clone:
                ret_value = self.positions[position_type].clone()
            else:
                ret_value = self.positions[position_type]

        # TODO: Debug use
        if debug == True:
            if position_type == backtrader.Position.SHORT_POSITION:
                msg = "{} Line: {}: DEBUG: ".format(
                    inspect.getframeinfo(inspect.currentframe()).function,
                    inspect.getframeinfo(inspect.currentframe()).lineno,
                )
                sub_msg = "position_type: {}, clone: {}, ret_value:".format(
                    backtrader.Position.Position_Types[position_type], clone,
                )
                print(msg + sub_msg)
                pprint(ret_value)

        return ret_value

    def set_position(self, position_type, size, price, debug=False):
        '''Stores the position status (a ``Position`` instance) for the given ``position_type``'''
        if position_type not in range(len(backtrader.Position.Position_Types)):
            raise ValueError("{}: {} position_type must be one of {}!!!".format(
                inspect.currentframe(), position_type, range(len(backtrader.Position.Position_Types))))

        # TODO: Debug use
        if debug == True:
            if position_type == backtrader.Position.SHORT_POSITION:
                msg = "{} Line: {}: DEBUG: ".format(
                    inspect.getframeinfo(inspect.currentframe()).function,
                    inspect.getframeinfo(inspect.currentframe()).lineno,
                )
                sub_msg = "position_type: {}, len(self.parent.open_orders): {}".format(
                    backtrader.Position.Position_Types[position_type],
                    len(self.parent.open_orders),
                )
                print(msg + sub_msg)

        permit_position_update = False
        # INFO: If there is no pending order to be processed, allow position changes from higher level
        if len(self.parent.open_orders) == 0:
            permit_position_update = True
        else:
            for open_order in self.parent.open_orders:
                # INFO: We should not gate position update if there is conditional order
                if open_order.ordering_type == backtrader.Order.CONDITIONAL_ORDERING_TYPE:
                    permit_position_update = True

            if permit_position_update == False:
                # INFO: Try to move BT_CCXT_Account_or_Store to get rid of the open_orders
                self.parent.next()

                if len(self.parent.open_orders) == 0:
                    permit_position_update = True

        if permit_position_update == True:
            self.positions[position_type].set(size, price)

    def buy(self, owner, symbol_id, datafeed, size,
            # Optional Params
            price=None, price_limit=None,
            execution_type=None, valid=None, tradeid=0, oco=None,
            trailing_amount=None, trailing_percent=None,
            parent=None, transmit=True,
            histnotify=False, _checksubmit=True,
            ordering_type=None,
            order_intent=None,
            position_type=None,
            **kwargs):
        return self.parent.buy(owner, symbol_id, datafeed, size,
                               # Optional Params
                               price=price, price_limit=price_limit,
                               execution_type=execution_type, valid=valid, tradeid=tradeid, oco=oco,
                               trailing_amount=trailing_amount, trailing_percent=trailing_percent,
                               parent=parent, transmit=transmit,
                               histnotify=histnotify, _checksubmit=_checksubmit,
                               ordering_type=ordering_type,
                               order_intent=order_intent,
                               position_type=position_type,
                               **kwargs)

    def sell(self, owner, symbol_id, datafeed, size,
             # Optional Params
             price=None, price_limit=None,
             execution_type=None, valid=None, tradeid=0, oco=None,
             trailing_amount=None, trailing_percent=None,
             parent=None, transmit=True,
             histnotify=False, _checksubmit=True,
             ordering_type=None,
             order_intent=None,
             position_type=None,
             **kwargs):
        return self.parent.sell(owner, symbol_id, datafeed, size,
                                # Optional Params
                                price=price, price_limit=price_limit,
                                execution_type=execution_type, valid=valid, tradeid=tradeid, oco=oco,
                                trailing_amount=trailing_amount, trailing_percent=trailing_percent,
                                parent=parent, transmit=transmit,
                                histnotify=histnotify, _checksubmit=_checksubmit,
                                ordering_type=ordering_type,
                                order_intent=order_intent,
                                position_type=position_type,
                                **kwargs)

    def get_pnl(self, position_types):
        '''
        Reference: https://help.bybit.com/hc/en-us/articles/900000630066-P-L-calculations-USDT-Contract-#Unrealized_P&L
        '''
        assert isinstance(position_types, list)
        assert len(position_types) > 0

        for position_type in position_types:
            if position_type not in range(len(backtrader.Position.Position_Types)):
                raise ValueError("{}: {} position_type must be one of {}!!!".format(
                    inspect.currentframe(), position_type, range(len(backtrader.Position.Position_Types))))

        pnl_comm = 0.0
        normalized_initial_margin = 0.0

        assert len(self.ccxt_datafeeds) > 0
        close_price = None
        for ccxt_datafeed in self.ccxt_datafeeds:
            if "Ticks" in ccxt_datafeed._name:
                close_price = ccxt_datafeed
            else:
                close_price = ccxt_datafeed.close[0]
            break
        legality_check_not_none_obj(close_price, "close_price")

        commission_info = self.get_commission_info()
        for position_type, position in self.positions.items():
            if position_type in position_types:
                if position.size != 0.0:
                    per_data_pnl = commission_info.profit_and_loss(position.size, position.price, close_price)
                    entry_comm = commission_info.get_commission_rate(position.size, position.price)
                    exit_comm = commission_info.get_commission_rate(position.size, close_price)
                    pnl_comm += per_data_pnl - entry_comm - exit_comm

                    force = False
                    if commission_info.p.mult is None:
                        force = True

                    # For Short
                    if position.size < 0.0:
                        max_price = max(position.price, close_price)
                        max_initial_margin = commission_info.get_initial_margin(position.size, max_price, force)
                        normalized_initial_margin += max_initial_margin
                    # For Long
                    elif position.size > 0.0:
                        min_price = min(position.price, close_price)
                        min_initial_margin = commission_info.get_initial_margin(position.size, min_price, force)
                        normalized_initial_margin += min_initial_margin

        pnl_in_percentage = pnl_comm * 100.0 / (normalized_initial_margin or 1.0)
        return pnl_comm, pnl_in_percentage, normalized_initial_margin