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
from __future__ import division, absolute_import, print_function, unicode_literals

import backtrader
import copy
import datetime
import inspect
import json

from ccxtbt.bt_ccxt__specifications import CCXT_SIDE_KEY, DERIVED__CCXT_ORDER__KEYS, EXECUTION_TYPE, \
    STATUS
from ccxtbt.exchange.binance.binance__exchange__specifications import BINANCE_EXCHANGE_ID
from ccxtbt.exchange.bybit.bybit__exchange__specifications import BYBIT_EXCHANGE_ID


class BT_CCXT_Order(backtrader.OrderBase):
    params = dict(
        ccxt_order=None,
        exchange_dropdown_value=None,
        symbol_id=None,
        position_type=None,
        ordering_type=None,
        order_intent=None,
    )

    def __init__(self):
        # Legality Check
        assert isinstance(self.p.ccxt_order, object)
        assert isinstance(self.p.exchange_dropdown_value, str)
        assert isinstance(self.p.symbol_id, str)

        if self.p.position_type not in range(len(backtrader.Position.Position_Types)):
            raise ValueError("{}: {} position_type must be one of {}!!!".format(
                inspect.currentframe(), self.p.position_type, range(len(backtrader.Position.Position_Types))))

        if self.p.ordering_type not in range(len(self.Ordering_Types)):
            raise ValueError("{} ordering_type must be one of {}!!!".format(
                self.p.ordering_type, range(len(self.Ordering_Types))))

        if self.p.order_intent not in range(len(self.Order_Intents)):
            raise ValueError("{} order_intent must be one of {}!!!".format(
                self.p.order_intent, range(len(self.Order_Intents))))

        self.executed_fills = []
        self.extract_from_ccxt_order(self.p.ccxt_order)
        self.indent = 4

        super(BT_CCXT_Order, self).__init__()

        # Mark order as submitted first
        self.submit()

        if self.p.exchange_dropdown_value == BYBIT_EXCHANGE_ID or self.p.exchange_dropdown_value == BINANCE_EXCHANGE_ID:
            # Legality Check
            if self.p.symbol_id.endswith("USDT"):
                stop_out = False
                if 'position_idx' in self.ccxt_order['info'].keys():
                    '''
                    0-One-Way Mode
                    1-Buy side of both side mode
                    2-Sell side of both side mode
                    '''
                    throws_out_error = False
                    point_of_reference = self.ccxt_order['info']['position_idx']
                    if self.p.position_type == backtrader.Position.LONG_POSITION:
                        if int(point_of_reference) != 1:
                            throws_out_error = True
                    else:
                        # Validate assumption made
                        assert self.p.position_type == backtrader.Position.SHORT_POSITION

                        if int(point_of_reference) != 2:
                            throws_out_error = True

                    if throws_out_error == True:
                        frameinfo = inspect.getframeinfo(
                            inspect.currentframe())
                        msg = "{} Line: {}: ERROR: {}: {}: For {} position vs position_idx: {}, ccxt_order:".format(
                            frameinfo.function, frameinfo.lineno,
                            self.ref,
                            datetime.datetime.now().isoformat().replace(
                                "T", " ")[:-3],
                            backtrader.Position.Position_Types[self.p.position_type],
                            point_of_reference,
                        )
                        print(msg)
                        print(json.dumps(self.ccxt_order, indent=self.indent))
                        stop_out = True

                if self.p.exchange_dropdown_value == BINANCE_EXCHANGE_ID:
                    reduce_only_key = 'reduceOnly'
                elif self.p.exchange_dropdown_value == BYBIT_EXCHANGE_ID:
                    reduce_only_key = 'reduce_only'
                else:
                    raise NotImplementedError(
                        "{} exchange is yet to be supported!!!".format(self.p.exchange_dropdown_value))

                if reduce_only_key in self.ccxt_order['info'].keys():
                    point_of_reference = self.ccxt_order['info'][reduce_only_key]
                    # Validate assumption made
                    assert isinstance(point_of_reference, bool)

                    throws_out_error = False

                    if self.p.order_intent == backtrader.Order.Entry_Order:
                        if point_of_reference != False:
                            throws_out_error = True
                    else:
                        # Validate assumption made
                        assert self.p.order_intent == backtrader.Order.Exit_Order

                        if point_of_reference != True:
                            throws_out_error = True

                    if throws_out_error == True:
                        frameinfo = inspect.getframeinfo(
                            inspect.currentframe())
                        msg = "{} Line: {}: ERROR: {}: {}: For {} order_intent vs {}: {}, ccxt_order:".format(
                            frameinfo.function, frameinfo.lineno,
                            self.ref,
                            datetime.datetime.now().isoformat().replace(
                                "T", " ")[:-3],
                            self.order_intent_name(),
                            reduce_only_key,
                            point_of_reference,
                        )
                        print(msg)
                        print(json.dumps(self.ccxt_order, indent=self.indent))
                        stop_out = True

                if stop_out == True:
                    raise RuntimeError(
                        "Abort due to at least one error is found...")
            else:
                raise NotImplementedError(
                    "symbol_id: {} is yet to be supported!!!".format(self.p.symbol_id))
        else:
            raise NotImplementedError(
                "{} exchange is yet to be supported!!!".format(self.p.exchange_dropdown_value))

    def extract_from_ccxt_order(self, ccxt_order):
        self.ccxt_order = ccxt_order

        if type(self.ccxt_order).__name__ == BT_CCXT_Order.__name__:
            self.ccxt_id = ccxt_order['ref']
        else:
            self.ccxt_id = ccxt_order['id']

        # Do NOT remove. Required by backtrader
        self.order_type = \
            self.Buy if ccxt_order[CCXT_SIDE_KEY].lower(
            ) == 'buy' else self.Sell

        for key in DERIVED__CCXT_ORDER__KEYS:
            # Skip status as it is not requested by user
            if key == DERIVED__CCXT_ORDER__KEYS[STATUS]:
                continue

            if hasattr(self, key):
                # Validate if the attribute is matching
                assert getattr(self, key) == ccxt_order[key], \
                    "Expected: \'{}\'={} != Actual: [\'{}\']={}".format(
                        key,
                        getattr(self, key),
                        key,
                        ccxt_order[key],
                )
            else:
                # Propagate over the attributes from ccxt_order
                setattr(self, key, ccxt_order[key])

        self.size = ccxt_order['amount']

        if ccxt_order['average'] != 0.0:
            self.price = ccxt_order['average']
        elif ccxt_order['price'] != 0.0:
            self.price = ccxt_order['price']
        else:
            # WARNING: The following code might cause assertion error during execute.
            self.price = 0.0

        if self.price == 0.0:
            if ccxt_order['stopPrice'] != 0.0:
                # For market order, the completed price is captured in stopPrice a.k.a. trigger_price
                self.price = ccxt_order['stopPrice']

        if ccxt_order['filled'] != 0.0:
            self.filled = ccxt_order['filled']
        else:
            # For market order, the ccxt_order['filled'] will always be None
            if ccxt_order[DERIVED__CCXT_ORDER__KEYS[EXECUTION_TYPE]] == backtrader.Order.Market:
                self.filled = self.size
            else:
                # Look for Conditional Limit Order
                if self.p.exchange_dropdown_value == BINANCE_EXCHANGE_ID:
                    conditional_limit_order__met = \
                        ccxt_order[DERIVED__CCXT_ORDER__KEYS[EXECUTION_TYPE]] == backtrader.Order.StopLimit and \
                        ccxt_order['stopPrice'] != 0.0
                elif self.p.exchange_dropdown_value == BYBIT_EXCHANGE_ID:
                    conditional_limit_order__met = \
                        ccxt_order[DERIVED__CCXT_ORDER__KEYS[EXECUTION_TYPE]] == backtrader.Order.Limit and \
                        ccxt_order['stopPrice'] != 0.0
                else:
                    raise NotImplementedError(
                        "{} exchange is yet to be supported!!!".format(self.p.exchange_dropdown_value))

                if conditional_limit_order__met == True:
                    self.filled = self.size
                else:
                    self.filled = 0.0

        self.remaining = ccxt_order['remaining']

        if ccxt_order['stopPrice'] != 0.0:
            if self.p.exchange_dropdown_value == BINANCE_EXCHANGE_ID:
                if 'status' in ccxt_order['info'].keys():
                    if ccxt_order['info']['status'] is not None:
                        if ccxt_order['info']['status'].upper() != "NEW":
                            self.triggered = True
                pass
            elif self.p.exchange_dropdown_value == BYBIT_EXCHANGE_ID:
                if 'order_status' in ccxt_order['info'].keys():
                    if ccxt_order['info']['order_status'] is not None:
                        if ccxt_order['info']['order_status'].lower() == "triggered":
                            self.triggered = True
            else:
                raise NotImplementedError(
                    "{} exchange is yet to be supported!!!".format(self.p.exchange_dropdown_value))

    def __repr__(self):
        return str(self)

    def __str__(self):
        tojoin = list()
        if self.p.datafeed is not None:
            tojoin.append('datafeed: {}'.format(self.p.datafeed._name))
        tojoin.append('id: \'{}\''.format(self.ccxt_id))
        tojoin.append('{}: Position'.format(
            backtrader.Position.Position_Types[self.p.position_type]))
        tojoin.append('Order Intent: {}'.format(self.order_intent_name()))
        tojoin.append('{} Ordering Type'.format(self.ordering_type_name()))
        tojoin.append('Order Type: {}'.format(self.order_type_name()))
        tojoin.append('{}: Execution Type'.format(self.execution_type_name()))
        tojoin.append('Backtrader Status: {}'.format(
            backtrader.Order.Status[self.status]))
        tojoin.append('CCXT Status: {}'.format(
            self.ccxt_order['{}_name'.format(DERIVED__CCXT_ORDER__KEYS[STATUS])]))

        if type(self.ccxt_order).__name__ == BT_CCXT_Order.__name__:
            if getattr(self.ccxt_order, 'created'):
                tojoin.append('Created Price: {} x Size: {} @ {}'.format(
                    self.ccxt_order['created']['price'],
                    self.ccxt_order['created']['size'],
                    backtrader.num2date(
                        self.ccxt_order['created']['dt']).isoformat().replace("T", " ")[:-3],
                ))
            if getattr(self.ccxt_order, 'executed'):
                tojoin.append('Executed Price: {} x Size: {} @ {}'.format(
                    self.ccxt_order['executed']['price'],
                    self.ccxt_order['executed']['size'],
                    backtrader.num2date(
                        self.ccxt_order['executed']['dt']).isoformat().replace("T", " ")[:-3],
                ))
        else:
            tojoin.append('Price: {} x Size: {} @ {}'.format(
                self.price,
                self.size,
                self.ccxt_order['datetime'].replace("T", " "),
            ))
        ret_value = "\n".join(tojoin)
        return ret_value

    def clone(self):
        # This is required so that the outcome will be reflected when calling order.executed.iterpending()
        self.executed.mark_pending()
        obj = copy.copy(self)
        return obj
