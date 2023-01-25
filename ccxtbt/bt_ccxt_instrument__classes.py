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
import collections
import datetime
import inspect
import threading

from pprint import pprint

from ccxtbt.bt_ccxt__specifications import CCXT__MARKET_TYPE__FUTURE, CCXT__MARKET_TYPE__SPOT, STANDARD_ATTRIBUTES, \
    symbol_stationary__dict_template
from ccxtbt.bt_ccxt_account_or_store__classes import BT_CCXT_Account_or_Store
from ccxtbt.bt_ccxt_expansion__classes import Enhanced_Position
from ccxtbt.exchange.binance.binance__exchange__classes import Binance_Symbol_Info__HTTP_Parser
from ccxtbt.exchange.binance.binance__exchange__specifications import BINANCE_EXCHANGE_ID
from ccxtbt.exchange.bybit.bybit__exchange__classes import Bybit_Symbol_Info__HTTP_Parser
from ccxtbt.exchange.bybit.bybit__exchange__specifications import BYBIT_EXCHANGE_ID, \
    BYBIT__DERIVATIVES__DEFAULT_POSITION_MODE
from ccxtbt.utils import capitalize_sentence, legality_check_not_none_obj


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
        assert isinstance(symbol_id, str)

        self.symbol_id = symbol_id
        self.parent = None
        self.ccxt_datafeeds = []

        # INFO: Switch positions to exercise Enhanced Position instead
        self.positions = collections.defaultdict(Enhanced_Position)

        self.payload = backtrader.AutoOrderedDict()
        self.current_thread = threading.current_thread()
        self._generation = None
        self._event_stop = False

        for key in symbol_stationary__dict_template.keys():
            if hasattr(self, key) == False:
                setattr(self, key, None)

        for standard_attribute in STANDARD_ATTRIBUTES:
            if hasattr(self, standard_attribute) == False:
                setattr(self, standard_attribute, None)

        # Derived Attributes
        self.exchange_dropdown_value = None

    def __repr__(self):
        return str(self)

    def __str__(self):
        return self.symbol_id

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
        assert self.symbol_id == symbol, "Instrument: {} does NOT support {}!!!".format(
            self.symbol_id, symbol)
        legality_check_not_none_obj(self.parent, "self.parent")
        return self.parent.fetch_ohlcv(symbol, timeframe, since, limit)

    def get_granularity(self, timeframe, compression):
        legality_check_not_none_obj(self.parent, "self.parent")
        return self.parent.get_granularity(timeframe, compression)

    def parse_timeframe(self, granularity):
        legality_check_not_none_obj(self.parent, "self.parent")
        return self.parent.parse_timeframe(granularity)

    def filter_by_since_limit(self, all_ohlcv, since, limit, key):
        legality_check_not_none_obj(self.parent, "self.parent")
        return self.parent.filter_by_since_limit(all_ohlcv, since, limit, key)

    def is_ws_available(self):
        legality_check_not_none_obj(self.parent, "self.parent")
        return self.parent.is_ws_available

    def get_ws_klines(self, dataname):
        legality_check_not_none_obj(self.parent, "self.parent")
        return self.parent.fetch_ws_klines(dataname)

    def get_ws_active_orders(self, symbol_id):
        assert self.symbol_id == symbol_id, "Instrument: {} does NOT support {}!!!".format(
            self.symbol_id, symbol_id)
        legality_check_not_none_obj(self.parent, "self.parent")
        return self.parent.ws_active_orders[symbol_id]

    def get_ws_conditional_orders(self, symbol_id):
        assert self.symbol_id == symbol_id, "Instrument: {} does NOT support {}!!!".format(
            self.symbol_id, symbol_id)
        legality_check_not_none_obj(self.parent, "self.parent")
        return self.parent.ws_conditional_orders[symbol_id]

    def fetch_order_book(self, symbol):
        assert self.symbol_id == symbol, "Instrument: {} does NOT support {}!!!".format(
            self.symbol_id, symbol)
        legality_check_not_none_obj(self.parent, "self.parent")
        return self.parent.fetch_order_book(symbol)

    def get_commission_info(self):
        legality_check_not_none_obj(self.parent, "self.parent")
        return self.parent.get_commission_info()

    def fetch_order(self, order_id, symbol, params={}):
        assert self.symbol_id == symbol, "Instrument: {} does NOT support {}!!!".format(
            self.symbol_id, symbol)
        legality_check_not_none_obj(self.parent, "self.parent")
        return self.parent.fetch_order(order_id, symbol, params)

    def get_orders(self, **kwarg):
        legality_check_not_none_obj(self.parent, "self.parent")
        return self.parent.get_orders(**kwarg)

    def set_cash(self, cash):
        legality_check_not_none_obj(self.parent, "self.parent")
        return self.parent.set_cash(cash)

    def get_cash(self, **kwarg):
        legality_check_not_none_obj(self.parent, "self.parent")
        return self.parent.get_cash(**kwarg)

    def get_value(self, **kwarg):
        legality_check_not_none_obj(self.parent, "self.parent")
        return self.parent.get_value(**kwarg)

    def set_live__capital_reservation__value(self, live__capital_reservation__value):
        legality_check_not_none_obj(self.parent, "self.parent")
        return self.parent.set_live__capital_reservation__value(live__capital_reservation__value)

    def get_live__capital_reservation__value(self):
        legality_check_not_none_obj(self.parent, "self.parent")
        return self.parent.get_live__capital_reservation__value()

    def get_initial__capital_reservation__value(self):
        legality_check_not_none_obj(self.parent, "self.parent")
        return self.parent.get_initial__capital_reservation__value()

    def set_cash_snapshot(self):
        legality_check_not_none_obj(self.parent, "self.parent")
        return self.parent.set_cash_snapshot()

    def get_cash_snapshot(self):
        legality_check_not_none_obj(self.parent, "self.parent")
        return self.parent.get_cash_snapshot()

    def set__stop_running(self):
        self._event_stop = True

    def get__stop_running(self):
        return self._event_stop

    def modify_order(self, order_id, symbol, type, side, amount=None, price=None, trigger_price=None, params={}):
        assert self.symbol_id == symbol, "Instrument: {} does NOT support {}!!!".format(
            self.symbol_id, symbol)
        legality_check_not_none_obj(self.parent, "self.parent")
        return self.parent.modify_order(order_id, symbol, type, side, amount=amount, price=price,
                                        trigger_price=trigger_price, params=params)

    def fetch_ccxt_order(self, symbol_id, order_id=None, stop_order_id=None):
        assert self.symbol_id == symbol_id, "Instrument: {} does NOT support {}!!!".format(
            self.symbol_id, symbol_id)
        legality_check_not_none_obj(self.parent, "self.parent")
        return self.parent.fetch_ccxt_order(symbol_id=symbol_id, order_id=order_id, stop_order_id=stop_order_id)

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
            self.positions[position_type] = Enhanced_Position(
                size=0.0, price=0.0)
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
        assert self.symbol_id == symbol_id, "Instrument: {} does NOT support {}!!!".format(
            self.symbol_id, symbol_id)
        legality_check_not_none_obj(self.parent, "self.parent")
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
        assert self.symbol_id == symbol_id, "Instrument: {} does NOT support {}!!!".format(
            self.symbol_id, symbol_id)
        legality_check_not_none_obj(self.parent, "self.parent")
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
                    per_data_pnl = commission_info.profit_and_loss(
                        position.size, position.price, close_price)
                    entry_comm = commission_info.get_commission_rate(
                        position.size, position.price)
                    exit_comm = commission_info.get_commission_rate(
                        position.size, close_price)
                    pnl_comm += per_data_pnl - entry_comm - exit_comm

                    force = False
                    if commission_info.p.mult is None:
                        force = True

                    # For Short
                    if position.size < 0.0:
                        max_price = max(position.price, close_price)
                        max_initial_margin = commission_info.get_initial_margin(
                            position.size, max_price, force)
                        normalized_initial_margin += max_initial_margin
                    # For Long
                    elif position.size > 0.0:
                        min_price = min(position.price, close_price)
                        min_initial_margin = commission_info.get_initial_margin(
                            position.size, min_price, force)
                        normalized_initial_margin += min_initial_margin

        pnl_in_percentage = pnl_comm * 100.0 / \
            (normalized_initial_margin or 1.0)
        return pnl_comm, pnl_in_percentage, normalized_initial_margin

    def get_account_alias(self):
        legality_check_not_none_obj(self.parent, "self.parent")
        return self.parent.get_account_alias()

    def get_exchange_dropdown_value(self):
        legality_check_not_none_obj(self.parent, "self.parent")
        return str(self.parent.exchange).lower()

    def get_open_orders(self):
        legality_check_not_none_obj(self.parent, "self.parent")
        return self.parent.get_open_orders()

    def post_process__after_parent_is_added(self):
        self.exchange_dropdown_value = self.get_exchange_dropdown_value()
        self.populate__symbol_static_info()
        self.sync_symbol_positions()

    def sync_symbol_positions(self):
        legality_check_not_none_obj(self.parent, "self.parent")
        if self.exchange_dropdown_value == BINANCE_EXCHANGE_ID:
            if self.parent.market_type == CCXT__MARKET_TYPE__SPOT:
                response = self.parent.exchange.fetch_open_orders(
                    symbol=self.symbol_id)
                if len(response) > 0:
                    raise NotImplementedError()
                pass
            elif self.parent.market_type == CCXT__MARKET_TYPE__FUTURE:
                balance = self.parent._get_wallet_balance()
                point_of_reference = balance['info']['positions']

                for position in point_of_reference:
                    if position['symbol'].upper() == self.symbol_id.upper():
                        position_side = capitalize_sentence(
                            position['positionSide'])
                        position_type = backtrader.Position.Position_Types.index(
                            position_side)
                        price = float(position['entryPrice'])
                        size = float(position['positionAmt'])
                        self.set_position(position_type, price, size)
                        pass
            else:
                raise NotImplementedError()
        elif self.exchange_dropdown_value == BYBIT_EXCHANGE_ID:
            if self.symbol_id.endswith("USDT"):
                response = self.parent.exchange.private_get_private_linear_position_list(
                    {'symbol': self.symbol_id})
                point_of_reference = response['result']
            elif self.symbol_id.endswith("USD"):
                response = self.parent.exchange.private_get_v2_private_position_list(
                    {'symbol': self.symbol_id})
                point_of_reference = response['result']
            elif self.symbol_id.endswith("USDC"):
                raise NotImplementedError()
            else:
                raise NotImplementedError()

            for position in point_of_reference:
                if position['symbol'].upper() == self.symbol_id.upper():
                    position_order_based_side = position['side']
                    position_type = backtrader.Order.Order_Types.index(
                        position_order_based_side)
                    price = float(position['entry_price'])
                    size = float(position['size'])
                    self.set_position(position_type, price, size)

                    assert position['mode'] == BYBIT__DERIVATIVES__DEFAULT_POSITION_MODE
                    pass
            pass
        else:
            raise NotImplementedError()

        # Dump positions
        # pprint(self.positions)

    def populate__symbol_static_info(self):
        '''
        We could only populate symbol static info AFTER parent has been set
        '''
        http_parser__dict = dict(
            symbol_id=self.symbol_id,
            market_type=self.parent.market_type,
        )
        if self.exchange_dropdown_value == BINANCE_EXCHANGE_ID:
            http_parser = Binance_Symbol_Info__HTTP_Parser(
                params=http_parser__dict)
        elif self.exchange_dropdown_value == BYBIT_EXCHANGE_ID:
            http_parser = Bybit_Symbol_Info__HTTP_Parser(
                params=http_parser__dict)
        else:
            raise NotImplementedError()
        http_parser.run()

        # Populate symbol static info over according to symbol_stationary__dict_template
        for key in symbol_stationary__dict_template.keys():
            if hasattr(http_parser, key):
                attribute_value = getattr(http_parser, key)
                if attribute_value is not None:
                    setattr(self, key, attribute_value)

        # Populate symbol static info over according to STANDARD_ATTRIBUTES
        for standard_attribute in STANDARD_ATTRIBUTES:
            assert hasattr(http_parser, standard_attribute)
            attribute_value = getattr(http_parser, standard_attribute)
            legality_check_not_none_obj(attribute_value, "attribute_value")
            setattr(self, standard_attribute, attribute_value)
        pass
