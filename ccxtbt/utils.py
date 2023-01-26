import backtrader
import decimal
import inspect
import datetime
import math

import numpy as np
import pandas as pd

from time import time as timer

from ccxtbt.exchange.binance.binance__exchange__specifications import BINANCE_EXCHANGE_ID
from ccxtbt.exchange.bybit.bybit__exchange__specifications import BYBIT_EXCHANGE_ID

from .bt_ccxt__specifications import CCXT_DATA_COLUMNS, OPEN_COL, HIGH_COL, LOW_COL, CLOSE_COL, VOLUME_COL, \
    DATE_TIME_FORMAT_WITH_MS_PRECISION


def print_timestamp_checkpoint(function, lineno, comment="Checkpoint timestamp", start=None):
    # Convert datetime to string
    # Refer to https://docs.python.org/3/library/datetime.html#strftime-and-strptime-format-codes
    timestamp_str = get_strftime(
        datetime.datetime.now(), DATE_TIME_FORMAT_WITH_MS_PRECISION)
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


def get_ha_bars(df, price_digits, tick_size):
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
                (df_ha[CCXT_DATA_COLUMNS[OPEN_COL]][i - 1] +
                 df_ha[CCXT_DATA_COLUMNS[CLOSE_COL]][i - 1]) / 2

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
                                                                                  tick_size / 2))
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
            function, lineno, data_name, i +
            1, kline_dt.isoformat().replace("T", " ")[:-3],
        )
        msg += "{}: {}, ".format(CCXT_DATA_COLUMNS[OPEN_COL], kline_open)
        msg += "{}: {}, ".format(CCXT_DATA_COLUMNS[HIGH_COL], kline_high)
        msg += "{}: {}, ".format(CCXT_DATA_COLUMNS[LOW_COL], kline_low)
        msg += "{}: {}, ".format(CCXT_DATA_COLUMNS[CLOSE_COL], kline_close)
        msg += "{}: {}, ".format(CCXT_DATA_COLUMNS[VOLUME_COL], kline_volume)

        # INFO: Strip ", " from the string
        print(msg[:-2])


def legality_check_not_none_obj(obj, obj_name):
    if obj is None:
        if obj_name is None:
            obj_name = get_var_name(obj)
        raise Exception("{}: {} must NOT be {}!!!".format(
            inspect.currentframe(), obj_name, obj))


def round_to_nearest_decimal_points(x, prec, base):
    '''
    # Credits: https://www.codegrepper.com/search.php?answer_removed=1&q=python%20round%20to%20the%20nearest
    '''
    legality_check_not_none_obj(x, "x")
    legality_check_not_none_obj(prec, "prec")
    legality_check_not_none_obj(base, "base")

    assert isinstance(prec, int)

    if type(x) == float or type(x) == int or type(x) == np.float64:
        ret_number = round(base * round(float(x)/base), prec)
        return ret_number
    elif type(x) == pd.Series:
        numbers = x.tolist()
        new_numbers = []
        for number in numbers:
            if math.isnan(number) == False:
                new_numbers.append(
                    round(base * round(float(number)/base), prec))
            else:
                # INFO: For NaN, just remain as it is
                new_numbers.append(number)

        # Create series form a list
        ret_value = pd.Series(new_numbers, dtype='float64')
        return ret_value
    else:
        raise Exception("Unsupported type: {}!!!".format(type(x)))


def get_var_name(variable):
    '''
    Credits: https://www.codespeedy.com/get-a-variable-name-as-a-string-in-python/
    '''
    var_name = None
    for name in globals():
        if eval(name) == variable:
            if eval(name) is not None:
                var_name = name
                break
            else:
                var_name = "None"
    return var_name


def dump_obj(obj, name="obj"):
    '''
    Credits: https://stackoverflow.com/questions/192109/is-there-a-built-in-function-to-print-all-the-current-properties-and-values-of-a?rq=1
    Credits: https://stackoverflow.com/questions/21542753/dir-without-built-in-methods
    '''
    # INFO: Exclude built-in methods
    attribute_list = [attr for attr in dir(obj) if not attr.startswith('__')]
    for attribute in attribute_list:
        print("{}.{} = {}".format(name, attribute, getattr(obj, attribute)))


def truncate(f, n):
    '''
    # Credits: https://stackoverflow.com/questions/29246455/python-setting-decimal-place-range-without-rounding
    '''
    return math.floor(f * 10 ** n) / 10 ** n


def get_time_diff(start):
    prog_time_diff = timer() - start
    hours, rem = divmod(prog_time_diff, 3600)
    minutes, seconds = divmod(rem, 60)
    minutes = int(minutes)
    return hours, minutes, seconds


def get_ccxt_order_id(exchange, order):
    ccxt_order_id = None
    if isinstance(order, dict):
        if 'id' in order.keys():
            ccxt_order_id = order['id']
        elif 'stop_order_id' in order.keys():
            ccxt_order_id = order['stop_order_id']
        elif 'order_id' in order.keys():
            ccxt_order_id = order['order_id']
    else:
        # Validate assumption made
        assert isinstance(order, object)

        if hasattr(order, 'ccxt_id'):
            ccxt_order_id = order.ccxt_id
        elif hasattr(order, 'ccxt_order'):
            if order.ccxt_order is not None:
                if isinstance(order.ccxt_order, dict):
                    if 'id' in order.ccxt_order.keys():
                        ccxt_order_id = order.ccxt_order['id']

                    if str(exchange).lower() == BINANCE_EXCHANGE_ID:
                        raise NotImplementedError(
                            "{} exchange is yet to be supported!!!".format(str(exchange).lower()))
                    elif str(exchange).lower() == BYBIT_EXCHANGE_ID:
                        if 'stop_order_id' in order.ccxt_order['info'].keys():
                            ccxt_order_id = order.ccxt_order['info']['stop_order_id']
                        elif 'order_id' in order.ccxt_order['info'].keys():
                            ccxt_order_id = order.ccxt_order['info']['order_id']
                    else:
                        raise NotImplementedError(
                            "{} exchange is yet to be supported!!!".format(str(exchange).lower()))
                else:
                    # Validate assumption made
                    assert isinstance(order.ccxt_order, object)

                    raise NotImplementedError()
            else:
                raise NotImplementedError()
        else:
            raise NotImplementedError()
    legality_check_not_none_obj(ccxt_order_id, "ccxt_order_id")
    return ccxt_order_id


def get_digits(step_size) -> int:
    if isinstance(step_size, float):
        # Credits: https://stackoverflow.com/questions/6189956/easy-way-of-finding-decimal-places
        number_of_digits = abs(decimal.Decimal(
            str(step_size)).as_tuple().exponent)
    elif isinstance(step_size, int):
        # Credits: https://stackoverflow.com/questions/2189800/how-to-find-length-of-digits-in-an-integer
        number_of_digits = int(math.log10(step_size)) + 1
    else:
        raise NotImplementedError("{}: Unsupported step_size type: {}".format(
            inspect.currentframe(),
            type(step_size),
        ))
    return number_of_digits


def convert_slider_from_percent(slider_in_percent, min_value, max_value, step_size=1):
    '''
    Convert slider in % into the nearest value
    '''
    ret_slider_value = min_value
    assert slider_in_percent >= 0.0

    if slider_in_percent > 0.0:
        # INFO: We zero-based the formula below to counter for easier leverage calculation where 50.0% => 50.0,
        #       50.0% => 25 etc.
        ret_slider_value = slider_in_percent * max_value / 100.0

    if ret_slider_value < min_value:
        ret_slider_value = min_value
    elif ret_slider_value > max_value:
        ret_slider_value = max_value

    step_digits = get_digits(step_size)
    ret_slider_value = round_to_nearest_decimal_points(
        ret_slider_value, step_digits, step_size)
    return ret_slider_value


def capitalize_sentence(sentences):
    sentences = sentences.replace("_", " ")
    words = sentences.split(" ")
    new = " ".join([word.capitalize() for word in words])
    return new


def get_order_exit_price_and_queue(position_type, ask, bid):
    if position_type not in range(len(backtrader.Position.Position_Types)):
        raise ValueError("{}: {} position_type must be one of {}!!!".format(
            inspect.currentframe(), position_type, range(len(backtrader.Position.Position_Types))))

    legality_check_not_none_obj(ask, "ask")
    legality_check_not_none_obj(bid, "bid")

    if position_type == backtrader.Position.LONG_POSITION:
        exit_price = ask
    else:
        # Validate assumption made
        assert position_type == backtrader.Position.SHORT_POSITION

        exit_price = bid
    return exit_price


def get_order_entry_price_without_queue(position_type, ask, bid, disable_message=False, function=None, lineno=None):
    '''
    WARNING: This API is created to accelerate the queue time of limit order in unit test. Logically this should not
             be used for production. Use at your own risk!
             The impact is that this will bring the [Entry] Price nearer to TP price.
    '''
    # INFO: Swapped the ask and bid to accelerate the queue time
    entry_price = get_order_exit_price_and_queue(position_type, ask, bid)

    if disable_message == False:
        legality_check_not_none_obj(function, "function")
        legality_check_not_none_obj(lineno, "lineno")

        print("{} Line: {}: INFO: Accelerated the [Entry] Price of {} @ {} for {} position_type to "
              "guarantee immediate position entrance".format(
                  function, lineno,
                  entry_price, "Ask" if entry_price == ask else "Bid", backtrader.Position.Position_Types[
                      position_type],
              ))
    return entry_price


def get_order_entry_price_and_queue(position_type, ask, bid):
    '''
    WARNING: This API will bring the [Entry] Price nearer to SL price.
    '''
    if position_type not in range(len(backtrader.Position.Position_Types)):
        raise ValueError("{}: {} position_type must be one of {}!!!".format(
            inspect.currentframe(), position_type, range(len(backtrader.Position.Position_Types))))

    legality_check_not_none_obj(ask, "ask")
    legality_check_not_none_obj(bid, "bid")

    if position_type == backtrader.Position.LONG_POSITION:
        entry_price = bid
    else:
        # Validate assumption made
        assert position_type == backtrader.Position.SHORT_POSITION

        entry_price = ask
    return entry_price


def get_order_exit_price_without_queue(position_type, ask, bid, disable_message=False, function=None, lineno=None):
    '''
    WARNING: This API is created to accelerate the queue time of limit order. Practical use case of this API is to
             address positions closure issue when we are in hedged positions, one position got closed whereas another
             position remains opened.
    '''
    # INFO: Swapped the ask and bid to accelerate the queue time
    exit_price = get_order_entry_price_and_queue(position_type, ask, bid)

    if disable_message == False:
        legality_check_not_none_obj(function, "function")
        legality_check_not_none_obj(lineno, "lineno")

        # INFO: Print out message to inform user
        print("{} Line: {}: INFO: Accelerated the [Exit] Price of {} @ {} for {} position_type to "
              "guarantee immediate position closure".format(
                  function,
                  lineno,
                  exit_price, "Ask" if exit_price == ask else "Bid", backtrader.Position.Position_Types[
                      position_type],
              ))

    return exit_price
