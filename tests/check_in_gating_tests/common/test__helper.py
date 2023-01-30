import inspect

import backtrader

from ccxtbt.bt_ccxt__specifications import CCXT__MARKET_TYPES, CCXT__MARKET_TYPE__FUTURE, \
    CCXT__MARKET_TYPE__LINEAR_PERPETUAL_SWAP

from ccxtbt.exchange.binance.binance__exchange__specifications import BINANCE_EXCHANGE_ID
from ccxtbt.exchange.bybit.bybit__exchange__specifications import BYBIT_EXCHANGE_ID


def ut_handle_datafeed(datafeed, price=None):
    datafeed.start()
    datafeed.forward()
    datafeed._load()
    datafeed._tz = None
    if price is not None:
        datafeed.close[0] = price


def ut_reverse_engineer__ccxt_order(bt_ccxt_order__dict):
    # Un-serialize Params
    ccxt_order = bt_ccxt_order__dict['ccxt_order']
    exchange_dropdown_value = bt_ccxt_order__dict['exchange_dropdown_value']

    if ccxt_order['type'] == backtrader.Order.Execution_Types[backtrader.Order.Limit].lower():
        execution_type = backtrader.Order.Limit
    else:
        execution_type = backtrader.Order.Market

    if ccxt_order['stopPrice'] is None:
        stop_price = None
    elif isinstance(ccxt_order['stopPrice'], str):
        stop_price = float(ccxt_order['stopPrice'])
    elif isinstance(ccxt_order['stopPrice'], int) or isinstance(ccxt_order['stopPrice'], float):
        stop_price = ccxt_order['stopPrice']
    else:
        raise NotImplementedError()

    if stop_price is None:
        ordering_type = backtrader.Order.ACTIVE_ORDERING_TYPE
    else:
        ordering_type = backtrader.Order.CONDITIONAL_ORDERING_TYPE

    if exchange_dropdown_value == BINANCE_EXCHANGE_ID:
        raise NotImplementedError(
            "{} exchange is yet to be supported!!!".format(exchange_dropdown_value))
    elif exchange_dropdown_value == BYBIT_EXCHANGE_ID:
        if 'info' in ccxt_order.keys():
            if 'reduce_only' in ccxt_order['info'].keys():
                # Validate assumption made
                assert isinstance(ccxt_order['info']['reduce_only'], bool)

                if ccxt_order['info']['reduce_only'] == False:
                    order_intent = backtrader.Order.Entry_Order
                else:
                    order_intent = backtrader.Order.Exit_Order
            else:
                raise NotImplementedError()
        else:
            raise NotImplementedError()
    else:
        raise NotImplementedError(
            "{} exchange is yet to be supported!!!".format(exchange_dropdown_value))

    bt_ccxt_order__dict.update(dict(
        execution_type=execution_type,
        ordering_type=ordering_type,
        order_intent=order_intent,
    ))
    return bt_ccxt_order__dict


def ut_get_valid_market_types(exchange_dropdown_value, target__market_types):
    assert isinstance(exchange_dropdown_value, str)
    assert isinstance(target__market_types, tuple)

    for market_type in target__market_types:
        if market_type not in range(len(CCXT__MARKET_TYPES)):
            raise ValueError("{}: {} market_type must be one of {}!!!".format(
                inspect.currentframe(),
                market_type, range(len(CCXT__MARKET_TYPES))))

    valid_market_types = []
    if exchange_dropdown_value == BINANCE_EXCHANGE_ID:
        for market_type in target__market_types:
            if market_type != CCXT__MARKET_TYPE__LINEAR_PERPETUAL_SWAP:
                valid_market_types.append(market_type)
    elif exchange_dropdown_value == BYBIT_EXCHANGE_ID:
        for market_type in target__market_types:
            if market_type != CCXT__MARKET_TYPE__FUTURE:
                valid_market_types.append(market_type)
        pass
    else:
        raise NotImplementedError(
            "{} exchange is yet to be supported!!!".format(exchange_dropdown_value))
    return valid_market_types
