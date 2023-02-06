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
import copy
import collections
import inspect
import threading

from pprint import pprint

from ccxtbt.bt_ccxt__specifications import CCXT__MARKET_TYPES, CCXT__MARKET_TYPE__FUTURE, \
    CCXT__MARKET_TYPE__LINEAR_PERPETUAL_SWAP, CCXT__MARKET_TYPE__SPOT, \
    risk_limit__dict_template, symbol_stationary__dict_template
from ccxtbt.account_or_store.account_or_store__classes import BT_CCXT_Account_or_Store
from ccxtbt.exchange_or_broker.binance.binance__exchange__classes import Binance_Symbol_Info__HTTP_Parser
from ccxtbt.exchange_or_broker.binance.binance__exchange__specifications import BINANCE_EXCHANGE_ID
from ccxtbt.exchange_or_broker.bybit.bybit__exchange__classes import Bybit_Symbol_Info__HTTP_Parser
from ccxtbt.exchange_or_broker.bybit.bybit__exchange__specifications import BYBIT_EXCHANGE_ID, \
    BYBIT__DERIVATIVES__DEFAULT_POSITION_MODE
from ccxtbt.expansion.bt_ccxt_expansion__classes import Enhanced_Position
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
        self.commission_info = dict()

        # Switch positions to exercise Enhanced Position instead
        self.positions = collections.defaultdict(Enhanced_Position)

        self.payload = backtrader.AutoOrderedDict()
        self.current_thread = threading.current_thread()
        self._generation = None
        self._event_stop = False

        for key in symbol_stationary__dict_template.keys():
            if hasattr(self, key) == False:
                setattr(self, key, None)

        # Derived Attributes
        self.exchange_dropdown_value = None
        self._name = symbol_id

        # Required by offline dataset
        self.risk_limit = None

    def __repr__(self):
        return str(self)

    def __str__(self):
        return self.symbol_id

    def set__parent(self, owner):
        self.parent = owner

        # Run post-processing AFTER parent has been set
        self._post_process__after_parent_is_added()

    def get__parent(self):
        return self.parent

    def add_commission_info(self, commission_info):
        self.commission_info = commission_info

        # Required by offline dataset
        assert hasattr(commission_info, 'commission')
        assert isinstance(commission_info.commission, int) or isinstance(
            commission_info.commission, float)

        # Rename 'commission' to 'commission_rate' in instrument
        setattr(self, 'commission_rate', commission_info.commission)

        legality_check_not_none_obj(self.parent, "self.parent")
        legality_check_not_none_obj(
            self.exchange_dropdown_value, "self.exchange_dropdown_value")

        if self.parent.market_type == CCXT__MARKET_TYPE__SPOT:
            # Do nothing
            pass
        else:
            if self.exchange_dropdown_value == BINANCE_EXCHANGE_ID:
                if self.parent.market_type == CCXT__MARKET_TYPE__FUTURE:
                    response = self.parent.exchange.fapiPrivate_get_leveragebracket(
                        {'symbol': self.symbol_id})

                    point_of_reference = response[0]
                    # Validate assumption made
                    assert point_of_reference['symbol'] == self.symbol_id

                    for risk_limit in point_of_reference['brackets']:
                        if self.risk_limit is None:
                            self.risk_limit = []

                        risk_limit_dict = copy.deepcopy(
                            risk_limit__dict_template)
                        risk_limit_dict['id'] = risk_limit['bracket']
                        risk_limit_dict['starting_margin'] = \
                            float(risk_limit['cum'])
                        risk_limit_dict['maintenance_margin_ratio'] = \
                            float(risk_limit['maintMarginRatio'])
                        risk_limit_dict['max_leverage'] = \
                            float(risk_limit['initialLeverage'])
                        risk_limit_dict['min_position_value'] = \
                            float(risk_limit['notionalFloor'])
                        risk_limit_dict['max_position_value'] = \
                            float(risk_limit['notionalCap'])
                        self.risk_limit.append(risk_limit_dict)
                    pass
                else:
                    raise NotImplementedError("{} market type is not yet enabled for {} exchange".format(
                        CCXT__MARKET_TYPES[self.parent.market_type],
                        self.exchange_dropdown_value,
                    ))
            elif self.exchange_dropdown_value == BYBIT_EXCHANGE_ID:
                if self.parent.market_type == CCXT__MARKET_TYPE__LINEAR_PERPETUAL_SWAP:
                    response = self.parent.exchange.public_get_public_linear_risk_limit(
                        {'symbol': self.symbol_id})

                    prev_max_position_value = 0
                    for risk_limit in response['result']:
                        if self.risk_limit is None:
                            self.risk_limit = []

                        risk_limit_dict = copy.deepcopy(
                            risk_limit__dict_template)
                        risk_limit_dict['id'] = risk_limit['id']
                        risk_limit_dict['starting_margin'] = \
                            float(risk_limit['starting_margin'])
                        risk_limit_dict['maintenance_margin_ratio'] = \
                            float(risk_limit['maintain_margin'])
                        risk_limit_dict['max_leverage'] = \
                            float(risk_limit['max_leverage'])
                        risk_limit_dict['min_position_value'] = prev_max_position_value
                        risk_limit_dict['max_position_value'] = \
                            float(risk_limit['limit'])
                        self.risk_limit.append(risk_limit_dict)

                        prev_max_position_value = risk_limit_dict['max_position_value']
                    pass
                else:
                    raise NotImplementedError("{} market type is not yet enabled for {} exchange".format(
                        CCXT__MARKET_TYPES[self.parent.market_type],
                        self.exchange_dropdown_value,
                    ))
            else:
                raise NotImplementedError(
                    "{} exchange is yet to be supported!!!".format(self.exchange_dropdown_value))
            pass

    def get_commission_info(self):
        return self.commission_info

    def add__datafeed(self, datafeed):
        found_datafeed = False
        for ccxt_datafeed in self.ccxt_datafeeds:
            if datafeed._name == ccxt_datafeed._name:
                found_datafeed = True
                break

        if found_datafeed == False:
            self.ccxt_datafeeds.append(datafeed)

    def get__datafeed(self, datafeed_name):
        ccxt_datafeed = None
        found_datafeed = False
        for ccxt_datafeed in self.ccxt_datafeeds:
            if datafeed_name == ccxt_datafeed._name:
                found_datafeed = True
                break

        if found_datafeed == False:
            raise RuntimeError("{}: {} datafeed_name NOT found!!!".format(
                inspect.currentframe(), datafeed_name))
        legality_check_not_none_obj(ccxt_datafeed, "ccxt_datafeed")
        return ccxt_datafeed

    def fetch_ohlcv(self, symbol, timeframe, since, limit, until=None):
        assert self.symbol_id == symbol, \
            "Instrument: {} does NOT support {}!!!".format(
                self.symbol_id, symbol)

        params = {}
        if until is not None:
            params['until'] = until

        legality_check_not_none_obj(self.parent, "self.parent")
        return self.parent.fetch_ohlcv(symbol, timeframe, since, limit, params)

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

    def fetch_order(self, order_id, symbol, params={}):
        assert self.symbol_id == symbol, "Instrument: {} does NOT support {}!!!".format(
            self.symbol_id, symbol)
        legality_check_not_none_obj(self.parent, "self.parent")
        return self.parent.fetch_order(order_id, symbol, params)

    def get_orders(self, **kwarg):
        legality_check_not_none_obj(self.parent, "self.parent")
        return self.parent.get_orders(**kwarg)

    def fetch_opened_orders(self, since=None, limit=None, params=None):
        if params is None:
            params = {}
        legality_check_not_none_obj(self.parent, "self.parent")
        return self.parent.fetch_opened_orders(symbol=self.symbol_id, since=since, limit=limit, params=params)

    def fetch_closed_orders(self, since=None, limit=None, params=None):
        if params is None:
            params = {}
        legality_check_not_none_obj(self.parent, "self.parent")
        return self.parent.fetch_closed_orders(symbol=self.symbol_id, since=since, limit=limit, params=params)

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

        self.positions[position_type].set(size, price)

    def buy(self, owner, symbol_id, size,
            # Optional Params
            datafeed=None, price=None, price_limit=None,
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

    def sell(self, owner, symbol_id, size,
             # Optional Params
             datafeed=None, price=None, price_limit=None,
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

    def cancel(self, order):
        legality_check_not_none_obj(self.parent, "self.parent")
        return self.parent.cancel(order)

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

    def get_exchange_dropdown_value(self):
        legality_check_not_none_obj(self.parent, "self.parent")
        return self.parent.exchange_dropdown_value

    def get_open_orders(self):
        legality_check_not_none_obj(self.parent, "self.parent")
        return self.parent.get_open_orders()

    def _post_process__after_parent_is_added(self):
        self.exchange_dropdown_value = self.get_exchange_dropdown_value()
        self.populate__symbol_static_info()
        self.sync_symbol_positions()

    def _get_bybit_position_list(self) -> list:
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
        return point_of_reference

    def sync_symbol_positions(self) -> None:
        legality_check_not_none_obj(self.parent, "self.parent")
        if self.exchange_dropdown_value == BINANCE_EXCHANGE_ID:
            if self.parent.market_type == CCXT__MARKET_TYPE__SPOT:
                # Spot account does not have any position as the orders are meant to convert from one currency to
                # another currency. Basically it is an account to exchange currency, not meant for trading using
                # position.
                pass
            elif self.parent.market_type == CCXT__MARKET_TYPE__FUTURE:
                balance = self.parent._get_balance()
                point_of_reference = balance['info']['positions']

                for position in point_of_reference:
                    if position['symbol'].upper() == self.symbol_id.upper():
                        position_side = capitalize_sentence(
                            position['positionSide'])
                        position_type = backtrader.Position.Position_Types.index(
                            position_side)
                        price = float(position['entryPrice'])
                        size = float(position['positionAmt'])
                        self.set_position(position_type, size, price)
                        pass
            else:
                raise NotImplementedError("{} market type is not yet enabled for {} exchange".format(
                    CCXT__MARKET_TYPES[self.parent.market_type],
                    self.exchange_dropdown_value,
                ))
        elif self.exchange_dropdown_value == BYBIT_EXCHANGE_ID:
            if self.parent.market_type == CCXT__MARKET_TYPE__SPOT:
                # Spot account does not have any position as the orders are meant to convert from one currency to
                # another currency. Basically it is an account to exchange currency, not meant for trading using
                # position.
                pass
            elif self.parent.market_type == CCXT__MARKET_TYPE__LINEAR_PERPETUAL_SWAP:
                # Get account balance is required here so that the cash and value are updated in the account as well
                # despite no use in this function
                _ = self.parent._get_balance()

                point_of_reference = self._get_bybit_position_list()

                updated_position_mode = False
                for position in point_of_reference:
                    if position['symbol'].upper() == self.symbol_id.upper():
                        if position['mode'] != BYBIT__DERIVATIVES__DEFAULT_POSITION_MODE:
                            set_position_mode__dict = dict(
                                type=CCXT__MARKET_TYPES[self.parent.market_type],
                            )
                            set__response = \
                                self.parent.exchange.set_position_mode(hedged=True, symbol=self.symbol_id,
                                                                       params=set_position_mode__dict)
                            # Confirmation
                            assert set__response['ret_msg'] == "OK"

                            frameinfo = inspect.getframeinfo(
                                inspect.currentframe())
                            msg = "{}: {} Line: {}: INFO: {}: Sync with {}: ".format(
                                CCXT__MARKET_TYPES[self.parent.market_type],
                                frameinfo.function, frameinfo.lineno,
                                self.symbol_id, self.parent.exchange_dropdown_value,
                            )
                            sub_msg = "Adjusted Dual/Hedge Position Mode from {} -> {}".format(
                                False,
                                True,
                            )
                            print(msg + sub_msg)
                            updated_position_mode = True
                            break
                        pass

                if updated_position_mode == True:
                    point_of_reference = self._get_bybit_position_list()

                for position in point_of_reference:
                    if position['symbol'].upper() == self.symbol_id.upper():
                        position_order_based_side = position['side']
                        position_type = backtrader.Order.Order_Types.index(
                            position_order_based_side)
                        price = float(position['entry_price'])
                        size = float(position['size'])
                        if size != 0.0:
                            if position_type == backtrader.Position.SHORT_POSITION:
                                # Guarantee to return negative sign
                                size = -abs(size)
                                assert size < 0.0
                        self.set_position(position_type, size, price)
                pass
            else:
                raise NotImplementedError("{} market type is not yet enabled for {} exchange".format(
                    CCXT__MARKET_TYPES[self.parent.market_type],
                    self.exchange_dropdown_value,
                ))
        else:
            raise NotImplementedError(
                "{} exchange is yet to be supported!!!".format(self.exchange_dropdown_value))

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
            raise NotImplementedError(
                "{} exchange is yet to be supported!!!".format(self.exchange_dropdown_value))
        http_parser.run()

        # Populate symbol static info over according to symbol_stationary__dict_template
        for key in symbol_stationary__dict_template.keys():
            if hasattr(http_parser, key):
                attribute_value = getattr(http_parser, key)
                if attribute_value is not None:
                    setattr(self, key, attribute_value)
        pass

    def get_orderbook_prices(self) -> tuple:
        legality_check_not_none_obj(self.parent, "self.parent")
        orderbook = self.parent.get_orderbook(symbol_id=self.symbol_id)
        asks = []
        bids = []
        for ask, bid in zip(orderbook['asks'], orderbook['bids']):
            assert isinstance(ask[0], float)
            assert isinstance(bid[0], float)
            asks.append(ask[0])
            bids.append(bid[0])
        return asks, bids

    def get_orderbook_price_by_offset(self, offset) -> tuple:
        legality_check_not_none_obj(self.parent, "self.parent")
        orderbook = self.parent.get_orderbook(symbol_id=self.symbol_id)

        # Legality Check
        assert offset < len(orderbook['asks']), \
            "Expected: {} vs Actual: {}".format(
                len(orderbook['asks']) - 1, offset)
        assert offset >= -len(orderbook['asks']), \
            "Expected: {} vs Actual: {}".format(
                len(orderbook['asks']) - 1, offset)

        ask = orderbook['asks'][offset][0]
        bid = orderbook['bids'][offset][0]

        assert isinstance(ask, float)
        assert isinstance(bid, float)
        return ask, bid
