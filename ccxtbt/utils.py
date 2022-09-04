import inspect
import datetime
import math

import numpy as np
import pandas as pd

from time import time as timer

from .specs import CCXT_DATA_COLUMNS, DATETIME_COL, OPEN_COL, HIGH_COL, LOW_COL, CLOSE_COL, VOLUME_COL, DATE_TIME_FORMAT_WITH_MS_PRECISION


def print_timestamp_checkpoint(function, lineno, comment="Checkpoint timestamp", start=None):
    # Convert datetime to string
    # Refer to https://docs.python.org/3/library/datetime.html#strftime-and-strptime-format-codes
    timestamp_str = get_strftime(datetime.datetime.now(), DATE_TIME_FORMAT_WITH_MS_PRECISION)
    if start:
        minutes, seconds, milliseconds = get_ms_time_diff(start)
        print("{} Line: {}: {}: {}, Delta: {}m:{}s.{}ms".format(
            function, lineno, comment, timestamp_str, minutes, seconds, milliseconds,
        ))
    else:
        print("{} Line: {}: {}: {}".format(
            function, lineno, comment, timestamp_str,
        ))


def get_ms_time_diff(start):
    prog_time_diff = timer() - start
    _, rem = divmod(prog_time_diff, 3600)
    minutes, seconds = divmod(rem, 60)
    minutes = int(minutes)
    fraction_of_seconds = seconds - int(seconds)
    seconds = int(seconds)
    milliseconds = fraction_of_seconds * 1000
    milliseconds = int(milliseconds)
    return minutes, seconds, milliseconds


def get_strftime(dt, date_format):
    # Convert datetime to string
    return str(dt.strftime(date_format))


def get_ha_bars(df, price_digits, symbol_tick_size):
    '''
    Heiken Ashi bars
    (Partially correct) Credits: https://towardsdatascience.com/how-to-calculate-heikin-ashi-candles-in-python-for-trading-cff7359febd7
    (Correct) Credits: https://tradewithpython.com/constructing-heikin-ashi-candlesticks-using-python

    Heikin Ashi candles are calculated this way:
        Candle	Regular Candlestick	Heikin Ashi Candlestick
        Open	Open0	            (HAOpen(-1) + HAClose(-1))/2
        High	High0	            MAX(High0, HAOpen0, HAClose0)
        Low	    Low0	            MIN(Low0, HAOpen0, HAClose0
        Close	Close0	            (Open0 + High0 + Low0 + Close0)/4
    '''
    df_ha = df.copy()
    for i in range(df_ha.shape[0]):
        if i > 0:
            df_ha.loc[df_ha.index[i], CCXT_DATA_COLUMNS[OPEN_COL]] = \
                (df_ha[CCXT_DATA_COLUMNS[OPEN_COL]][i - 1] + df_ha[CCXT_DATA_COLUMNS[CLOSE_COL]][i - 1]) / 2

        df_ha.loc[df_ha.index[i], CCXT_DATA_COLUMNS[CLOSE_COL]] = \
            (df[CCXT_DATA_COLUMNS[OPEN_COL]][i] + df[CCXT_DATA_COLUMNS[CLOSE_COL]][i] +
             df[CCXT_DATA_COLUMNS[LOW_COL]][i] + df[CCXT_DATA_COLUMNS[HIGH_COL]][i]) / 4

        df_ha.loc[df_ha.index[i], CCXT_DATA_COLUMNS[HIGH_COL]] = \
            max(df[CCXT_DATA_COLUMNS[HIGH_COL]][i], df_ha[CCXT_DATA_COLUMNS[OPEN_COL]][i],
                df_ha[CCXT_DATA_COLUMNS[CLOSE_COL]][i])

        df_ha.loc[df_ha.index[i], CCXT_DATA_COLUMNS[LOW_COL]] = \
            min(df[CCXT_DATA_COLUMNS[LOW_COL]][i], df_ha[CCXT_DATA_COLUMNS[OPEN_COL]][i],
                df_ha[CCXT_DATA_COLUMNS[CLOSE_COL]][i])

    # INFO: Remove the first row if uncomment the line below
    # df_ha = df_ha.iloc[1:, :]

    columns_to_process = [CCXT_DATA_COLUMNS[OPEN_COL],
                          CCXT_DATA_COLUMNS[HIGH_COL],
                          CCXT_DATA_COLUMNS[LOW_COL],
                          CCXT_DATA_COLUMNS[CLOSE_COL]]

    # INFO: The following formula has been reviewed side by side with TradingView using 1 minute chart, it is about 95%
    #       identical with TradingView
    df_ha[columns_to_process] = \
        df_ha[columns_to_process].apply(lambda x: round_to_nearest_decimal_points(x, price_digits + 1,
                                                                                  symbol_tick_size / 2))
    return df_ha


def dump_ohlcv(function, lineno, data_name, ohlcv_list):
    assert isinstance(ohlcv_list, list)

    print("{} Line: {}: DEBUG: len of ohlcv: {}".format(
            function, lineno, len(ohlcv_list),
        ))

    for i, ohlcv in enumerate(ohlcv_list):
        tstamp = ohlcv[0] / 1e3

        # Convert timestamp to datetime in UTC timezone
        kline_dt = datetime.datetime.utcfromtimestamp(tstamp)

        kline_open = ohlcv[1]
        kline_high = ohlcv[2]
        kline_low = ohlcv[3]
        kline_close = ohlcv[4]
        kline_volume = ohlcv[5]

        msg = "{} Line: {}: INFO: {}: [{}]: {}: ".format(
            function, lineno, data_name, i + 1, kline_dt.isoformat().replace("T", " "),
        )
        msg += "{}: {}, ".format(CCXT_DATA_COLUMNS[OPEN_COL], kline_open)
        msg += "{}: {}, ".format(CCXT_DATA_COLUMNS[HIGH_COL], kline_high)
        msg += "{}: {}, ".format(CCXT_DATA_COLUMNS[LOW_COL], kline_low)
        msg += "{}: {}, ".format(CCXT_DATA_COLUMNS[CLOSE_COL], kline_close)
        msg += "{}: {}, ".format(CCXT_DATA_COLUMNS[VOLUME_COL], kline_volume)

        # INFO: Strip ", " from the string
        print(msg[:-2])


def round_to_nearest_decimal_points(x, prec, base):
    '''
    # Credits: https://www.codegrepper.com/search.php?answer_removed=1&q=python%20round%20to%20the%20nearest
    '''
    legality_check_not_none_obj(x, "x")
    legality_check_not_none_obj(prec, "prec")
    legality_check_not_none_obj(base, "base")
    if type(x) == float or type(x) == int or type(x) == np.float64:
        ret_number = round(base * round(float(x)/base), prec)
        return ret_number
    elif type(x) == pd.Series:
        numbers = x.tolist()
        new_numbers = []
        for number in numbers:
            if math.isnan(number) == False:
                new_numbers.append(round(base * round(float(number)/base), prec))
            else:
                # INFO: For NaN, just remain as it is
                new_numbers.append(number)

        # Create series form a list
        ret_value = pd.Series(new_numbers, dtype='float64')
        return ret_value
    else:
        raise Exception("Unsupported type: {}!!!".format(type(x)))


def legality_check_not_none_obj(obj, obj_name):
    if obj is None:
        if obj_name is None:
            obj_name = get_var_name(obj)
        raise Exception("{}: {} must NOT be {}!!!".format(inspect.currentframe(), obj_name, obj))


