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

from .utils import legality_check_not_none_obj


class BT_CCXT_Exchange(backtrader.with_metaclass(backtrader.MetaSingleton, object)):
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

    The broker_or_exchange mapping should contain a new dict for order_types and mappings like below:

    broker_mapping = {
        'order_types': {
            bt.Order.Market: 'market',
            bt.Order.Limit: 'limit',
            bt.Order.StopMarket: 'stop-loss', #stop-loss for kraken, stop for bitmex
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

    order_types = {backtrader.Order.Market: 'market',
                   backtrader.Order.Limit: 'limit',
                   backtrader.Order.StopMarket: 'stop',  # stop-loss for kraken, stop for bitmex
                   backtrader.Order.StopLimit: 'stop limit'}

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

    Account_or_Store_Cls = None  # account_or_store class will auto register

    @classmethod
    def instantiate__account_or_store(cls, *args, **kwargs):
        '''Returns account_or_store with *args, **kwargs from registered ``Account_or_Store_Cls``'''
        return cls.Account_or_Store_Cls(*args, **kwargs)

    def __init__(self, broker_mapping=None):
        super().__init__()

        if broker_mapping is not None:
            try:
                self.order_types = broker_mapping['order_types']
            except KeyError:  # Might not want to change the order types
                pass
            try:
                self.mappings = broker_mapping['mappings']
            except KeyError:  # might not want to change the mappings
                pass

        self.account_or_store = None
        self.commission_info = dict()

        self.accounts_or_stores = []

    def set__child(self, account_or_store):
        assert account_or_store in self.accounts_or_stores
        self.account_or_store = account_or_store

    def get__child(self):
        legality_check_not_none_obj(self.account_or_store, "self.account_or_store")
        return self.account_or_store

    def get__children(self):
        return self.accounts_or_stores

    def add__account_or_store(self, account_or_store):
        if account_or_store not in self.accounts_or_stores:
            account_or_store.add_commission_info(self.commission_info)
            self.accounts_or_stores.append(account_or_store)

    def add_commission_info(self, commission_info):
        self.commission_info = commission_info

    def get_commission_info(self):
        return self.commission_info

    def get_ohlcv_provider__account_or_store(self):
        ohlcv_provider__account_or_store = None

        for account_or_store in self.accounts_or_stores:
            if account_or_store.is_ohlcv_provider == True:
                ohlcv_provider__account_or_store = account_or_store

        legality_check_not_none_obj(ohlcv_provider__account_or_store, "ohlcv_provider__account_or_store")
        return ohlcv_provider__account_or_store

    def get_account_alias(self, owner):
        ret_account_alias = owner.p.own__account_object.account_alias__dropdown_value
        return ret_account_alias

    def set_account_or_store(self, main_net_toggle_switch_value, account_alias, account_type):
        # Legality Check
        assert isinstance(main_net_toggle_switch_value, bool)
        
        success = False
        for account_or_store in self.accounts_or_stores:
            if account_or_store.main_net_toggle_switch_value == main_net_toggle_switch_value:
                if account_or_store.account_alias == account_alias:
                    if account_or_store.account_type == account_type:
                        self.account_or_store = account_or_store
                        success = True
                        break

        if success == False:
            raise ValueError("Unable to locate {}!!!".format(account_alias))

    def get_account_or_store(self, main_net_toggle_switch_value, account_alias, account_type):
        # Legality Check
        assert isinstance(main_net_toggle_switch_value, bool)
        
        success = False
        ret_account_or_store = None
        for account_or_store in self.accounts_or_stores:
            if account_or_store.main_net_toggle_switch_value == main_net_toggle_switch_value:
                if account_or_store.account_alias == account_alias:
                    if account_or_store.account_type == account_type:
                        ret_account_or_store = account_or_store
                        success = True
                        break

        if success == False:
            raise ValueError("Unable to locate {}!!!".format(account_alias))
        return ret_account_or_store

    def get_balance(self):
        '''
        :return: Cash and value of all accounts
        '''
        cash = 0.0
        value = 0.0
        for account_or_store in self.accounts_or_stores:
            account_or_store.get_balance()
            cash += account_or_store._cash
            value += account_or_store._value
        return cash, value

    def run_pulse_check_for_ws(self):
        for account_or_store in self.accounts_or_stores:
            account_or_store.run_pulse_check_for_ws()
