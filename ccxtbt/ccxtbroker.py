#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
#
# Copyright (C) 2015, 2016, 2017 Daniel Rodriguez
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
import copy
import collections
import datetime
import inspect
import json

from backtrader import BrokerBase, OrderBase, Order
from backtrader.utils.py3 import queue, with_metaclass
from ccxt.base.errors import OrderNotFound
from time import time as timer
from pprint import pprint

from .ccxtstore import CCXTStore
from .enhanced_position_class import Enhanced_Position
from .utils import print_timestamp_checkpoint, legality_check_not_none_obj, round_to_nearest_decimal_points


class CCXTOrder(OrderBase):
    def __init__(self, owner, data, ccxt_order, exectype):
        self.owner = owner
        self.data = data
        self.executed_fills = []
        self.exectype = exectype
        self.set_ccxt_order(ccxt_order)

        super(CCXTOrder, self).__init__()

    def set_ccxt_order(self, ccxt_order):
        self.ccxt_order = ccxt_order
        self.ordtype = self.Buy if ccxt_order['side'] == 'buy' else self.Sell
        self.size = float(ccxt_order['amount'])
        self.price = float(ccxt_order['price']) if ccxt_order['price'] is not None else 0.0

    def __repr__(self):
        return str(self)

    def __str__(self):
        items = list()
        items.append('Data: {}'.format(self.data._name))

        if type(self.ccxt_order).__name__ == CCXTOrder.__name__:
            items.append('id: {}'.format(self.ccxt_order['ref']))
        else:
            items.append('id: {}'.format(self.ccxt_order['id']))
        items.append('Type: {}'.format(backtrader.Order.OrdTypes[self.ordtype]))

        items.append('Status: {}'.format(self.ccxt_order['status']))

        if type(self.ccxt_order).__name__ == CCXTOrder.__name__:
            if getattr(self.ccxt_order, 'executed'):
                items.append('Created Price: {} x Size: {} @ {}'.format(
                    self.ccxt_order['created']['price'],
                    self.ccxt_order['created']['size'],
                    backtrader.num2date(self.ccxt_order['created']['dt']).isoformat().replace("T", " "),
                ))
            if getattr(self.ccxt_order, 'executed'):
                items.append('Executed Price: {} x Size: {} @ {}'.format(
                    self.ccxt_order['executed']['price'],
                    self.ccxt_order['executed']['size'],
                    backtrader.num2date(self.ccxt_order['executed']['dt']).isoformat().replace("T", " "),
                ))
        else:
            items.append('Price: {} x Size: {} @ {}'.format(
                self.ccxt_order['price'],
                self.size,
                self.ccxt_order['datetime'].replace("T", " "),
            ))
        ret_value = str('\n'.join(items))
        return ret_value

    def clone(self):
        # INFO: This is required so that the outcome will be reflected when calling order.executed.iterpending()
        self.executed.markpending()
        obj = copy.copy(self)
        return obj


class MetaCCXTBroker(BrokerBase.__class__):
    def __init__(cls, name, bases, dct):
        '''Class has already been created ... register'''
        # Initialize the class
        super(MetaCCXTBroker, cls).__init__(name, bases, dct)
        CCXTStore.BrokerCls = cls


class CCXTBroker(with_metaclass(MetaCCXTBroker, BrokerBase)):
    '''Broker implementation for CCXT cryptocurrency trading library.
    This class maps the orders/positions from CCXT to the
    internal API of ``backtrader``.

    Broker mapping added as I noticed that there differences between the expected
    order_types and retuned status's from canceling an order

    Added a new mappings parameter to the script with defaults.

    Added a get_balance function. Manually check the account balance and update brokers
    self.cash and self.value. This helps alleviate rate limit issues.

    Added a new get_wallet_balance method. This will allow manual checking of the any coins
        The method will allow setting parameters. Useful for dealing with multiple assets

    Modified getcash() and getvalue():
        Backtrader will call getcash and getvalue before and after next, slowing things down
        with rest calls. As such, th

    The broker mapping should contain a new dict for order_types and mappings like below:

    broker_mapping = {
        'order_types': {
            bt.Order.Market: 'market',
            bt.Order.Limit: 'limit',
            bt.Order.Stop: 'stop-loss', #stop-loss for kraken, stop for bitmex
            bt.Order.StopLimit: 'stop limit'
        },
        'mappings':{
            'closed_order':{
                'key': 'status',
                'value':'closed'
                },
            'canceled_order':{
                'key': 'result',
                'value':1}
                }
        }

    Added new private_end_point method to allow using any private non-unified end point

    '''

    order_types = {Order.Market: 'market',
                   Order.Limit: 'limit',
                   Order.Stop: 'stop',  # stop-loss for kraken, stop for bitmex
                   Order.StopLimit: 'stop limit'}

    # Documentation: https://docs.ccxt.com/en/latest/manual.html#order-structure
    mappings = {
        'opened_order': {
            'key': "status",
            'value': "open"
        },
        'closed_order': {
            'key': "status",
            'value': "closed"
        },
        'canceled_order': {
            'key': "status",
            'value': "canceled"
        },
        'expired_order': {
            'key': "status",
            'value': "expired"
        },
        'rejected_order': {
            'key': "status",
            'value': "rejected"
        }
    }

    def __init__(self, broker_mapping=None, debug=False, **kwargs):
        super(CCXTBroker, self).__init__()

        if broker_mapping is not None:
            try:
                self.order_types = broker_mapping['order_types']
            except KeyError:  # Might not want to change the order types
                pass
            try:
                self.mappings = broker_mapping['mappings']
            except KeyError:  # might not want to change the mappings
                pass

        self.store = CCXTStore(**kwargs)

        self.currency = self.store.currency

        self.positions = collections.defaultdict(Enhanced_Position)

        self.debug = debug
        self.indent = 4  # For pretty printing dictionaries

        self.notifs = queue.Queue()  # holds orders which are notified

        self.open_orders = list()

        self.startingcash = self.store._cash
        self.startingvalue = self.store._value

        self.use_order_params = True
        self.max_retry = 5

    def get_balance(self):
        self.store.get_balance()
        self.cash = self.store._cash
        self.value = self.store._value
        return self.cash, self.value

    def get_wallet_balance(self, currency, params={}):
        balance = self.store.get_wallet_balance(currency, params=params)
        try:
            cash = balance['free'][currency] if balance['free'][currency] else 0
        except KeyError:  # never funded or eg. all USD exchanged
            cash = 0
        try:
            value = balance['total'][currency] if balance['total'][currency] else 0
        except KeyError:  # never funded or eg. all USD exchanged
            value = 0
        return cash, value

    def getcash(self, force=False):
        if force == True:
            self.store.get_balance()
        self.cash = self.store._cash
        return self.cash

    def getvalue(self, datas=None):
        self.value = self.store._value
        return self.value

    def get_notification(self):
        try:
            return self.notifs.get(False)
        except queue.Empty:
            return None

    def notify(self, order):
        # Legality Check
        assert type(order).__name__ == CCXTOrder.__name__, "{} Line: {}: Expected {} but observed {} instead!!!".format(
            inspect.getframeinfo(inspect.currentframe()).function,
            inspect.getframeinfo(inspect.currentframe()).lineno,
            CCXTOrder.__name__, type(order).__name__,
        )
        self.notifs.put(order.clone())

        # if type(order).__name__ == CCXTOrder.__name__:
        #     order_id = order.ccxt_order['info']['order_id']
        # elif isinstance(order, dict):
        #     if 'stop_order_id' in order.keys():
        #         order_id = order['stop_order_id']
        #     elif 'order_id' in order.keys():
        #         order_id = order['order_id']
        #     elif 'id' in order.keys():
        #         order_id = order['id']
        #
        # # TODO: Debug Use
        # msg = "{} Line: {}: DEBUG: order:".format(
        #     inspect.getframeinfo(inspect.currentframe()).function,
        #     inspect.getframeinfo(inspect.currentframe()).lineno,
        # )
        # print(msg)
        # pprint(order)
        pass

    def getposition(self, data, clone=True):
        ret_value = Enhanced_Position(size=0.0, price=0.0)
        for pos_data, pos in self.positions.items():
            if data._name == pos_data._name:
                if clone:
                    ret_value = pos.clone()
                else:
                    ret_value = pos
                break
        return ret_value

    def setposition(self, data, size, price):
        '''Stores the position status (a ``Position`` instance) for the given ``data``'''
        # INFO: Prohibit access to negative index data or else self.positions will be initialized to this data.
        #       This has proven to be true in free running mode, hence gym step running mode must provide the same
        #       guarantee.
        assert data.lines.datetime.idx >= 0

        # # TODO: Debug Use
        # msg = "{} Line: {}: DEBUG: data._name: {}".format(
        #     inspect.getframeinfo(inspect.currentframe()).function,
        #     inspect.getframeinfo(inspect.currentframe()).lineno,
        #     data._name,
        # )
        # print(msg)

        # INFO: If there is no pending order to be processed, allow position changes from higher level
        if len(self.open_orders) == 0:
            self.positions[data].set(size, price)

    def get_pnl(self, datas=None):
        pnl_comm = 0.0
        initial_margin = 0.0

        tick_data = None
        for data in datas or self.positions:
            if "Ticks" in data._name:
                tick_data = data

        for data in datas or self.positions:
            comminfo = self.getcommissioninfo(data)
            position = self.positions[data]

            if tick_data is None:
                close_price = data.close[0]
            else:
                close_price = tick_data.close[0]

            if comminfo is not None:
                if position.size != 0.0:
                    per_data_pnl = comminfo.profitandloss(position.size, position.price, close_price)
                    entry_comm = comminfo.getcommission(position.size, position.price)
                    exit_comm = comminfo.getcommission(position.size, close_price)
                    pnl_comm += per_data_pnl - entry_comm - exit_comm

                    force = False
                    if comminfo.p.mult is None:
                        force = True

                    # For Short
                    if position.size < 0.0:
                        max_price = max(position.price, close_price)
                        max_initial_margin = comminfo.get_initial_margin(position.size, max_price, force)
                        initial_margin += max_initial_margin
                    # For Long
                    elif position.size > 0.0:
                        min_price = min(position.price, close_price)
                        min_initial_margin = comminfo.get_initial_margin(position.size, min_price, force)
                        initial_margin += min_initial_margin

        pnl_in_percentage = pnl_comm / (initial_margin or 1.0)
        return pnl_comm, pnl_in_percentage

    def next(self):
        if self.debug:
            print('Broker next() called')

        for o_order in list(self.open_orders):
            oID = o_order.ccxt_order['id']

            # Print debug before fetching so we know which order is giving an
            # issue if it crashes
            if self.debug:
                print('Fetching Order ID: {}'.format(oID))

            # Get the order
            ccxt_order = self.store.fetch_order(oID, o_order.data.p.dataname)

            if ccxt_order is not None:
                # Check for new fills
                if 'trades' in ccxt_order and ccxt_order['trades'] is not None:
                    for fill in ccxt_order['trades']:
                        if fill not in o_order.executed_fills:
                            o_order.execute(fill['datetime'], fill['amount'], fill['price'],
                                            0, 0.0, 0.0,
                                            0, 0.0, 0.0,
                                            0.0, 0.0,
                                            0, 0.0)
                            o_order.executed_fills.append(fill['id'])

                if self.debug:
                    print(json.dumps(ccxt_order, indent=self.indent))

                # Check if the exchange order is opened
                if ccxt_order[self.mappings['opened_order']['key']] == self.mappings['opened_order']['value']:
                    if o_order.status != Order.Accepted:
                        # INFO: Refresh the content of ccxt_order with the latest ccxt_order
                        o_order.set_ccxt_order(ccxt_order)
                        o_order.accept()
                        self.notify(o_order)
                # Check if the exchange order is closed
                elif ccxt_order[self.mappings['closed_order']['key']] == self.mappings['closed_order']['value']:
                    # INFO: Refresh the content of ccxt_order with the latest ccxt_order
                    o_order.set_ccxt_order(ccxt_order)
                    o_order.completed()
                    self._execute(o_order, ago=0, price=o_order.price)
                    self.open_orders.remove(o_order)
                    self.get_balance()
                # Check if the exchange order is rejected
                elif ccxt_order[self.mappings['rejected_order']['key']] == self.mappings['rejected_order']['value']:
                    # INFO: Refresh the content of ccxt_order with the latest ccxt_order
                    o_order.set_ccxt_order(ccxt_order)
                    o_order.reject()
                    self.notify(o_order)
                    self.open_orders.remove(o_order)
                # Manage case when an order is being Canceled or Expired from the Exchange
                #  from https://github.com/juancols/bt-ccxt-store/
                elif ccxt_order[self.mappings['canceled_order']['key']] == self.mappings['canceled_order']['value']:
                    # INFO: Refresh the content of ccxt_order with the latest ccxt_order
                    o_order.set_ccxt_order(ccxt_order)
                    o_order.cancel()
                    self.notify(o_order)
                    self.open_orders.remove(o_order)
                elif ccxt_order[self.mappings['expired_order']['key']] == self.mappings['expired_order']['value']:
                    # INFO: Refresh the content of ccxt_order with the latest ccxt_order
                    o_order.set_ccxt_order(ccxt_order)
                    o_order.expire()
                    self.notify(o_order)
                    self.open_orders.remove(o_order)

    def _submit(self, owner, data, exectype, side, amount, price, simulated, params):
        if amount == 0 or price == 0:
        # do not allow failing orders
            return None
        order_type = self.order_types.get(exectype) if exectype else 'market'

        if data:
            created = int(data.datetime.datetime(0).timestamp()*1000)
            symbol_id = params['params']['symbol']
        else:
            # INFO: Use the current UTC datetime
            utc_dt = datetime.datetime.utcnow()
            created = int(utc_dt.timestamp()*1000)
            symbol_id = params['params']['symbol']
            # INFO: Remove symbol name from params
            params['params'].pop('symbol', None)

        # Extract CCXT specific params if passed to the order
        params = params['params'] if 'params' in params else params
        if not self.use_order_params:
            ret_ord = self.store.create_order(symbol=symbol_id, order_type=order_type, side=side,
                                              amount=amount, price=price, params={})
        else:
            try:
                # all params are exchange specific: https://github.com/ccxt/ccxt/wiki/Manual#custom-order-params
                params['created'] = created  # Add timestamp of order creation for backtesting
                ret_ord = self.store.create_order(symbol=symbol_id, order_type=order_type, side=side,
                                                  amount=amount, price=price, params=params)
            except:
                # save some API calls after failure
                self.use_order_params = False
                return None

        if ret_ord is None or ret_ord['id'] is None:
            return None

        order = None
        ccxt_order = None
        for _ in range(self.max_retry):
            try:
                # INFO: Due to nature of order is processed async, the order could not be found immediately right after
                #       order is is opened. Hence, perform retry to confirm if that's the case.
                if 'stop_order_id' in ret_ord['info'].keys():
                    # Conditional Order
                    params = dict(
                        stop_order_id=ret_ord['id'],
                    )
                    ccxt_order = \
                        self.store.fetch_order(oid=None, symbol_id=symbol_id, params=params)
                else:
                    # Active Order
                    ccxt_order = self.store.fetch_order(oid=ret_ord['id'], symbol_id=symbol_id)
            except OrderNotFound:
                pass

            if ccxt_order is not None:
                # INFO: Exposed simulated so that we could proceed with order without running cerebro
                order = CCXTOrder(owner, data, ccxt_order, exectype, simulated=simulated)

                # INFO: Retrieve order.price from ccxt_order['price'] is proven more reliable than ret_ord['price']
                order.price = ccxt_order['price']

                # Check if the exchange order is NOT closed
                if ccxt_order[self.mappings['closed_order']['key']] != self.mappings['closed_order']['value']:
                    # Mark order as submitted
                    order.submit()
                    order = self._add_comminfo(order)
                    self.notify(order)
                self.open_orders.append(order)
                break

        return order

    def _add_comminfo(self, order):
        # Get comminfo object for the data
        data = order.data
        comminfo = self.getcommissioninfo(data)
        order.addcomminfo(comminfo)
        return order

    def _execute(self, order, ago, price):
        # Legality Check
        legality_check_not_none_obj(order, "order")
        # ago = None is used a flag for pseudo execution
        legality_check_not_none_obj(ago, "ago")
        legality_check_not_none_obj(price, "price")

        size = order.executed.remsize

        # Get comminfo object for the data
        data = order.data
        comminfo = self.getcommissioninfo(data)

        # Adjust position with operation size
        # Real execution with date
        position = self.getposition(data, clone=False)
        pprice_orig = position.price

        # Do a real position update
        psize, pprice, opened, closed = position.update(size, price, data.datetime.datetime())
        psize = round_to_nearest_decimal_points(psize, comminfo.qty_digits, comminfo.qty_step)
        pprice = round_to_nearest_decimal_points(pprice, comminfo.price_digits, comminfo.symbol_tick_size)
        opened = round_to_nearest_decimal_points(opened, comminfo.qty_digits, comminfo.qty_step)
        closed = round_to_nearest_decimal_points(closed, comminfo.qty_digits, comminfo.qty_step)

        # split commission between closed and opened
        if closed:
            closedcomm = order.ccxt_order['fee']['cost']
        else:
            closedcomm = 0.0

        if opened:
            openedcomm = order.ccxt_order['fee']['cost']
        else:
            openedcomm = 0.0

        closedvalue = comminfo.getvaluesize(-closed, pprice_orig)
        openedvalue = comminfo.getvaluesize(opened, price)

        # The internal broker calc should yield the same result
        if closed:
            pnl = comminfo.profitandloss(-closed, pprice_orig, price)
        else:
            pnl = 0.0

        # Need to simulate a margin, but it plays no role, because it is
        # controlled by a real broker. Let's set the price of the item
        margin = order.data.close[0]

        # Execute and notify the order
        order.execute(data.datetime[ago],
                      size, price,
                      closed, closedvalue, closedcomm,
                      opened, openedvalue, openedcomm,
                      margin, pnl,
                      psize, pprice)

        # INFO: size and price could deviate from its original value due to floating point precision error. The
        #       following codes are to provide remedy for that situation.
        order.executed.size = \
            round_to_nearest_decimal_points(order.executed.size, comminfo.qty_digits, comminfo.qty_step)
        order.executed.price = \
            round_to_nearest_decimal_points(order.executed.price, comminfo.price_digits,
                                            comminfo.symbol_tick_size)

        order.addcomminfo(comminfo)
        self.notify(order)

    def buy(self, owner, data, size, price=None, plimit=None,
            exectype=None, valid=None, tradeid=0, oco=None,
            trailamount=None, trailpercent=None,
            simulated=False,
            **kwargs):
        del kwargs['parent']
        del kwargs['transmit']
        return self._submit(owner, data, exectype, 'buy', size, price, simulated, kwargs)

    def sell(self, owner, data, size, price=None, plimit=None,
             exectype=None, valid=None, tradeid=0, oco=None,
             trailamount=None, trailpercent=None,
             simulated=False,
             **kwargs):
        del kwargs['parent']
        del kwargs['transmit']
        return self._submit(owner, data, exectype, 'sell', size, price, simulated, kwargs)

    def cancel(self, order):

        oID = order.ccxt_order['id']

        if self.debug:
            print('Broker cancel() called')
            print('Fetching Order ID: {}'.format(oID))

        # check first if the order has already been filled otherwise an error
        # might be raised if we try to cancel an order that is not open.
        ccxt_order = self.store.fetch_order(oID, order.data.p.dataname)

        if self.debug:
            print(json.dumps(ccxt_order, indent=self.indent))

        # Check if the exchange order is closed
        if ccxt_order[self.mappings['closed_order']['key']] == self.mappings['closed_order']['value']:
            return order

        ccxt_order = self.store.cancel_order(oID, order.data.p.dataname)

        if self.debug:
            print(json.dumps(ccxt_order, indent=self.indent))
            print('Value Received: {}'.format(ccxt_order[self.mappings['canceled_order']['key']]))
            print('Value Expected: {}'.format(self.mappings['canceled_order']['value']))

        # Check if the exchange order is cancelled
        if ccxt_order[self.mappings['canceled_order']['key']] == self.mappings['canceled_order']['value']:
            self.open_orders.remove(order)
            order.cancel()
            self.notify(order)
        return order

    def run_pulse_check_for_ws(self):
        return self.store.run_pulse_check_for_ws()

    def modify_order(self, order_id, symbol, type, side, amount=None, price=None, trigger_price=None, params={}):
        return self.store.edit_order(order_id, symbol, type, side, amount=amount, price=price, 
                                     trigger_price=trigger_price, params=params)

    def fetch_order(self, order_id, symbol, params={}):
        return self.store.fetch_order(order_id, symbol, params)

    def fetch_orders(self, symbol=None, since=None, limit=None, params={}):
        return self.store.fetch_orders(symbol=symbol, since=since, limit=limit, params=params)

    def fetch_opened_orders(self, symbol=None, since=None, limit=None, params={}):
        return self.store.fetch_opened_orders(symbol=symbol, since=since, limit=limit, params=params)

    def fetch_closed_orders(self, symbol=None, since=None, limit=None, params={}):
        return self.store.fetch_closed_orders(symbol=symbol, since=since, limit=limit, params=params)

    def get_positions(self, symbols=None, params={}):
        return self.store.fetch_opened_positions(symbols, params)

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

        return self.store.private_end_point(type=type, endpoint=method_str, params=params)

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