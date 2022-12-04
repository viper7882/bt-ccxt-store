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

from .utils import dump_obj


class BT_CCXT_Order(backtrader.OrderBase):
    def __init__(self, owner, datafeed, ccxt_order, execution_type, symbol_id, position_type, ordering_type,
                 order_intent):
        self.owner = owner
        self.datafeed = datafeed
        self.executed_fills = []
        self.execution_type = execution_type
        self.symbol_id = symbol_id
        self.position_type = position_type
        self.ordering_type = ordering_type
        self.order_intent = order_intent
        self.extract_from_ccxt_order(ccxt_order)
        self.indent = 4

        super(BT_CCXT_Order, self).__init__()

        # Legality Check
        if self.symbol_id.endswith("USDT"):
            stop_out = False
            if 'position_idx' in self.ccxt_order['info'].keys():
                '''
                0-One-Way Mode
                1-Buy side of both side mode
                2-Sell side of both side mode
                '''
                throws_out_error = False
                if self.position_type == backtrader.Position.LONG_POSITION:
                    if int(self.ccxt_order['info']['position_idx']) != 1:
                        throws_out_error = True
                else:
                    # Validate assumption made
                    assert self.position_type == backtrader.Position.SHORT_POSITION

                    if int(self.ccxt_order['info']['position_idx']) != 2:
                        throws_out_error = True

                if throws_out_error == True:
                    frameinfo = inspect.getframeinfo(inspect.currentframe())
                    msg = "{} Line: {}: ERROR: {}: {}: For {} position vs position_idx: {}, ccxt_order:".format(
                        frameinfo.function, frameinfo.lineno,
                        self.ref,
                        datetime.datetime.now().isoformat().replace("T", " ")[:-3],
                        backtrader.Position.Position_Types[self.position_type],
                        self.ccxt_order['info']['position_idx'],
                    )
                    print(msg)
                    print(json.dumps(ccxt_order, indent=self.indent))
                    stop_out = True

            if 'reduce_only' in self.ccxt_order['info'].keys():
                throws_out_error = False
                if self.order_intent == backtrader.Order.Entry_Order:
                    if self.ccxt_order['info']['reduce_only'] != False:
                        throws_out_error = True
                else:
                    # Validate assumption made
                    assert self.order_intent == backtrader.Order.Exit_Order

                    if self.ccxt_order['info']['reduce_only'] != True:
                        throws_out_error = True

                if throws_out_error == True:
                    frameinfo = inspect.getframeinfo(inspect.currentframe())
                    msg = "{} Line: {}: ERROR: {}: {}: For {} order_intent vs reduce_only: {}, ccxt_order:".format(
                        frameinfo.function, frameinfo.lineno,
                        self.ref,
                        datetime.datetime.now().isoformat().replace("T", " ")[:-3],
                        self.order_intent_name(),
                        self.ccxt_order['info']['reduce_only'],
                    )
                    print(msg)
                    print(json.dumps(ccxt_order, indent=self.indent))
                    stop_out = True

            if stop_out == True:
                raise RuntimeError("Abort due to at least one error is found...")
        else:
            raise NotImplementedError("symbol_id: {} is yet to be supported!!!".format(self.symbol_id))

    def extract_from_ccxt_order(self, ccxt_order):
        self.ccxt_order = ccxt_order

        if type(self.ccxt_order).__name__ == BT_CCXT_Order.__name__:
            self.ccxt_id = ccxt_order['ref']
        else:
            self.ccxt_id = ccxt_order['id']

        self.order_type = self.Buy if ccxt_order['side'] == 'buy' else self.Sell

        self.size = float(ccxt_order['amount'])

        if ccxt_order['average'] is not None:
            self.price = float(ccxt_order['average'])
        elif ccxt_order['price'] is not None:
            self.price = float(ccxt_order['price'])
        else:
            # WARNING: The following code might cause assertion error during execute.
            self.price = 0.0

        if self.price == 0.0:
            # WARNING: The following code could be Bybit-specific
            if ccxt_order['stopPrice'] is not None:
                # INFO: For market order, the completed price is captured in stopPrice a.k.a. trigger_price
                self.price = float(ccxt_order['stopPrice'])

        if ccxt_order['filled'] is not None:
            self.filled = float(ccxt_order['filled'])
        else:
            self.filled = 0.0

        if ccxt_order['remaining'] is not None:
            self.remaining = float(ccxt_order['remaining'])
        else:
            self.remaining = 0.0

        # WARNING: The following code could be Bybit-specific
        if 'order_status' in ccxt_order['info'].keys():
            if ccxt_order['info']['order_status'] is not None:
                if ccxt_order['info']['order_status'].lower() == "triggered":
                    self.triggered = True

    def __repr__(self):
        return str(self)

    def __str__(self):
        tojoin = list()
        tojoin.append('Datafeed: {}'.format(self.datafeed._name))
        tojoin.append('ID: {}'.format(self.ccxt_id))
        tojoin.append('Order Type Name: {}'.format(self.order_type_name()))
        tojoin.append('Ordering Type Name: {}'.format(self.ordering_type_name()))
        tojoin.append('Order Intent Name: {}'.format(self.order_intent_name()))
        tojoin.append('Status Name: {}'.format(self.ccxt_order['status']))
        tojoin.append('Execution Type Name: {}'.format(self.execution_type_name()))
        tojoin.append('Position Type Name: {}'.format(backtrader.Position.Position_Types[self.position_type]))

        if type(self.ccxt_order).__name__ == BT_CCXT_Order.__name__:
            if getattr(self.ccxt_order, 'created'):
                tojoin.append('Created Price: {} x Size: {} @ {}'.format(
                    self.ccxt_order['created']['price'],
                    self.ccxt_order['created']['size'],
                    backtrader.num2date(self.ccxt_order['created']['dt']).isoformat().replace("T", " ")[:-3],
                ))
            if getattr(self.ccxt_order, 'executed'):
                tojoin.append('Executed Price: {} x Size: {} @ {}'.format(
                    self.ccxt_order['executed']['price'],
                    self.ccxt_order['executed']['size'],
                    backtrader.num2date(self.ccxt_order['executed']['dt']).isoformat().replace("T", " ")[:-3],
                ))
        else:
            tojoin.append('Price: {} x Size: {} @ {}'.format(
                self.price,
                self.size,
                self.ccxt_order['datetime'].replace("T", " "),
            ))
        ret_value = str('\n'.join(tojoin))
        return ret_value

    def clone(self):
        # INFO: This is required so that the outcome will be reflected when calling order.executed.iterpending()
        self.executed.mark_pending()
        obj = copy.copy(self)
        return obj
