#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
#
# Copyright (C) 2015, 2016, 2017 Daniel Rodriguez
# Copyright (C) 2017 Ed Bartosh
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

import dateutil.parser
import datetime
import inspect
import pandas as pd

from collections import deque

import backtrader as bt
from backtrader.feed import DataBase
from backtrader.utils.py3 import with_metaclass

from ccxtbt.bt_ccxt__specifications import CCXT_DATA_COLUMNS, MAX_LIVE_EXCHANGE_RETRIES, MIN_LIVE_EXCHANGE_RETRIES
from ccxtbt.bt_ccxt_instrument__classes import BT_CCXT_Instrument
from ccxtbt.utils import get_ha_bars, legality_check_not_none_obj


class MetaCCXTFeed(DataBase.__class__):
    def __init__(cls, name, bases, dct):
        '''Class has already been created ... register'''
        # Initialize the class
        super().__init__(name, bases, dct)

        # Register with account_or_store
        BT_CCXT_Instrument.Datafeed_Cls = cls


class BT_CCXT_Feed(with_metaclass(MetaCCXTFeed, DataBase)):
    """
    CryptoCurrency eXchange Trading Library Data Feed.
    Params:
      - ``historical`` (default: ``False``)
        If set to ``True`` the data feed will stop after doing the first
        download of data.
        The standard data feed parameters ``fromdate`` and ``todate`` will be
        used as reference.
      - ``backfill_start`` (default: ``True``)
        Perform backfilling at the start. The maximum possible historical data
        will be fetched in a single request.

    Changes From Ed's package

        - Added option to send some additional fetch_ohlcv_params. Some exchanges (e.g Bitmex)
          support sending some additional fetch parameters.
        - Added drop_newest option to avoid loading incomplete candles where exchanges
          do not support sending ohlcv params to prevent returning partial data

    """

    params = (
        ('historical', False),  # only historical download
        ('backfill_start', False),  # do backfilling at the start
        ('fetch_ohlcv_params', {}),
        ('ohlcv_limit', 20),
        ('min_retries', MIN_LIVE_EXCHANGE_RETRIES),
        ('max_retries', MAX_LIVE_EXCHANGE_RETRIES),
        # True if the klines are converted into Heiken Ashi candlesticks
        ('convert_to_heikin_ashi', False),
        ('tick_size', None),
        ('price_digits', None),
        ('dataname', None),
        ('drop_newest', False),
        ('ut__halt_if_no_ohlcv', False),
        ('debug', False)
    )

    _instrument = BT_CCXT_Instrument

    # States for the Finite State Machine in _load
    _LIVE_STATE, _HISTORY_BACK_STATE, _OVER_STATE = range(3)

    # def __init__(self, exchange, symbol, ohlcv_limit=None, config={}, retries=5):
    def __init__(self, **kwargs):
        super().__init__()

        self._data = deque()  # data queue for price data
        self._last_ts = 0  # last processed timestamp for ohlcv
        self._ts_delta = None  # timestamp delta for ohlcv
        self._name = self.p.dataname  # name of datafeed
        self._last_ws_ts = 0  # last processed timestamp for ohlcv from websocket

        # Legality Check
        if self.p.convert_to_heikin_ashi:
            assert self.p.tick_size is not None
            assert self.p.price_digits is not None

    def __repr__(self):
        return str(self)

    def __str__(self):
        return self._name

    def set__parent(self, owner):
        self.instrument = owner

    def start(self, ):
        DataBase.start(self)

        if self.p.fromdate:
            self._state = self._HISTORY_BACK_STATE
            self.put_notification(self.DELAYED)
            self._fetch_ohlcv(self.p.fromdate, self.p.todate)

        else:
            self._state = self._LIVE_STATE
            self.put_notification(self.LIVE)

    def _load(self):
        if self._state == self._OVER_STATE:
            return False

        while True:
            if self._state == self._LIVE_STATE:
                if self._timeframe == bt.TimeFrame.Ticks:
                    ret_value = self._load_ticks()
                    return ret_value
                else:
                    # Fix to address slow loading time after enter into LIVE state.
                    if len(self._data) == 0:
                        # Only call _fetch_ohlcv when self._data is fully consumed as it will cause execution
                        #       inefficiency due to network latency. Furthermore, it is extremely inefficiency to fetch
                        #       an amount of bars but only load one bar at a given time.
                        self._fetch_ohlcv()
                    ret = self._load_ohlcv()

                    if self.p.ut__halt_if_no_ohlcv:
                        # For unit test, we must halt the state machine so that we could continue to the next
                        #       test case
                        if ret is None:
                            ret = False

                    if self.p.debug:
                        print('----     LOAD    ----')
                        print('{} Line: {}: {} Load OHLCV Returning: {}'.format(
                            inspect.getframeinfo(
                                inspect.currentframe()).function,
                            inspect.getframeinfo(
                                inspect.currentframe()).lineno,
                            datetime.datetime.utcnow(), ret
                        ))
                    return ret

            elif self._state == self._HISTORY_BACK_STATE:
                ret = self._load_ohlcv()
                if ret:
                    if self.p.debug:
                        print('----     LOAD    ----')
                        print('{} Line: {}: {} Load OHLCV Returning: {}'.format(
                            inspect.getframeinfo(
                                inspect.currentframe()).function,
                            inspect.getframeinfo(
                                inspect.currentframe()).lineno,
                            datetime.datetime.utcnow(), ret
                        ))
                    return ret
                else:
                    # End of historical data
                    if self.p.historical:  # only historical
                        self.put_notification(self.DISCONNECTED)
                        self._state = self._OVER_STATE
                        return False  # end of historical
                    else:
                        self._state = self._LIVE_STATE
                        self.put_notification(self.LIVE)

    def retry_fetch_ohlcv(self, granularity_dropdown_value, since, until):
        legality_check_not_none_obj(self.instrument, "self.instrument")

        # Validate assumption made
        assert isinstance(granularity_dropdown_value, str)

        timeframe_duration_in_seconds = self.instrument.parse_timeframe(
            granularity_dropdown_value)
        timeframe_duration_in_ms = timeframe_duration_in_seconds * 1000
        time_delta = self.p.ohlcv_limit * timeframe_duration_in_ms

        all_ohlcv = []
        fetch_since = since
        while fetch_since < until:
            try:
                ohlcv = self.instrument.fetch_ohlcv(
                    symbol=self.instrument.symbol_id,
                    timeframe=granularity_dropdown_value,
                    since=fetch_since,
                    until=until,
                    limit=self.p.ohlcv_limit)
            except Exception as error:
                raise RuntimeError("{}: Failed to fetch {} {} klines!!!".format(
                    error,
                    granularity_dropdown_value, self.instrument.symbol_id,
                ))

            if len(ohlcv) == 0:
                break

            # Update to since value after the most recent ohlcv
            fetch_since = ohlcv[-1][0] + 1
            all_ohlcv += ohlcv

        ohlcv = self.instrument.parent.exchange.filter_by_since_limit(
            all_ohlcv, since, limit=None, key=0)
        # Filter off excessive data should there is any
        ohlcv = [entry for i, entry in enumerate(ohlcv) if ohlcv[i][0] < until]
        return ohlcv

    def _fetch_ohlcv(self, fromdate=None, todate=None):
        """Fetch OHLCV data into self._data queue"""
        legality_check_not_none_obj(self.instrument, "self.instrument")
        granularity = self.instrument.get_granularity(
            self._timeframe, self._compression)

        if fromdate:
            since = int((fromdate - datetime.datetime(1970, 1, 1)
                         ).total_seconds() * 1000)
        else:
            if self._last_ts > 0:
                if self._ts_delta is None:
                    since = self._last_ts
                else:
                    since = self._last_ts - self._ts_delta
            else:
                raise ValueError("Unable to determine the since value!!!")

        if todate:
            until = int((todate - datetime.datetime(1970, 1, 1)
                         ).total_seconds() * 1000)
        else:
            until = int((datetime.datetime.utcnow() - datetime.datetime(1970, 1, 1)
                         ).total_seconds() * 1000)

        ohlcv_list = self.retry_fetch_ohlcv(granularity, since, until)

        # Check to see if dropping the latest candle will help with
        # exchanges which return partial data
        if self.p.drop_newest:
            # Begin to drop the newest if we only have more than one ohlcv
            if len(ohlcv_list) > 1:
                del ohlcv_list[-1]

        if self.p.convert_to_heikin_ashi:
            if len(ohlcv_list) > 0:
                df = pd.DataFrame(ohlcv_list)

                # Configure the columns to be CCXT
                df.columns = CCXT_DATA_COLUMNS[:-1]

                df_ha = get_ha_bars(df, self.p.price_digits,
                                    self.p.tick_size)

                ohlcv_list = df_ha.values.tolist()
                # print("{} Line: {}: {}: {}: AFTER: ohlcv_list[-1]: ".format(
                #     inspect.getframeinfo(inspect.currentframe()).function,
                #     inspect.getframeinfo(inspect.currentframe()).lineno,
                #     self.p.dataname,
                #     self._name,
                # ))
                # pprint(ohlcv_list[-1])

        prev_tstamp = None
        for ohlcv in ohlcv_list:
            tstamp = ohlcv[0]

            # if prev_tstamp is not None and self._ts_delta is None:
            #     # Record down the TS delta so that it can be used to increment TS
            #     self._ts_delta = tstamp - prev_tstamp

            if self.p.debug:
                print('tstamp: {}'.format(tstamp))

            if tstamp > self._last_ts:
                if self.p.debug:
                    print('Adding: {}'.format(ohlcv))
                self._data.append(ohlcv)
                self._last_ts = tstamp

            if prev_tstamp is None:
                prev_tstamp = tstamp

    def _load_ticks(self):
        # start = timer()

        if self.instrument.is_ws_available():
            try:
                (tstamp, ohlcv) = self.instrument.get_ws_klines(self.p.dataname)

                # If there is an update
                if tstamp > self._last_ws_ts:
                    self._last_ws_ts = tstamp

                    # Convert timestamp to datetime in UTC timezone
                    kline_dt = datetime.datetime.utcfromtimestamp(tstamp)

                    self.lines.datetime[0] = bt.date2num(kline_dt)
                    self.lines.open[0] = ohlcv[0]
                    self.lines.high[0] = ohlcv[1]
                    self.lines.low[0] = ohlcv[2]
                    self.lines.close[0] = ohlcv[3]
                    self.lines.volume[0] = ohlcv[4]
                else:
                    return None
            except ValueError as err:
                frameinfo = inspect.getframeinfo(inspect.currentframe())
                msg = "{} Line: {}: {}: {}: ".format(
                    frameinfo.function, frameinfo.lineno,
                    self.p.dataname,
                    datetime.datetime.utcnow().isoformat().replace("T", " ")[
                        :-3],
                )
                sub_msg = "err: {}".format(err)
                print("\r" + msg + sub_msg, end="")
                return False
        else:
            order_book = self.instrument.fetch_order_book(
                symbol=self.p.dataname)
            # nearest_ask = order_book['asks'][0][0]
            nearest_bid = order_book['bids'][0][0]
            nearest_ask_volume = order_book['asks'][0][1]
            nearest_bid_volume = order_book['bids'][0][1]

            # Convert isoformat to datetime
            order_book_datetime = dateutil.parser.isoparse(
                order_book['datetime'])

            self.lines.datetime[0] = bt.date2num(order_book_datetime)
            self.lines.open[0] = nearest_bid
            self.lines.high[0] = nearest_bid
            self.lines.low[0] = nearest_bid
            self.lines.close[0] = nearest_bid

            # Volume below is not an actual value provided by most exchange
            # Consuming average volume is probably a better way to go
            self.lines.volume[0] = (
                nearest_bid_volume + nearest_ask_volume) / 2

        return True

    def _load_ohlcv(self):
        try:
            ohlcv = self._data.popleft()
        except IndexError:
            return None  # no data in the queue

        tstamp, open_, high, low, close, volume = ohlcv

        dtime = datetime.datetime.utcfromtimestamp(tstamp // 1000)

        self.lines.datetime[0] = bt.date2num(dtime)
        self.lines.open[0] = open_
        self.lines.high[0] = high
        self.lines.low[0] = low
        self.lines.close[0] = close
        self.lines.volume[0] = volume

        return True

    def has_live_data(self):
        return self._state == self._LIVE_STATE and self._data

    def is_live(self):
        return not self.p.historical
