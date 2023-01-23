import backtrader
from check_in_gating_tests.common.test__classes import FAKE_COMMISSION_INFO


def get_commission_info(params):
    commission_info = FAKE_COMMISSION_INFO(params)
    return commission_info


def handle_datafeed(datafeed, price):
    datafeed.start()
    datafeed.forward()
    datafeed._load()
    datafeed._tz = None
    datafeed.close[0] = price


def reverse_engineer__ccxt_order(bt_ccxt_order__dict):
    # INFO: Un-serialize Params
    ccxt_order = bt_ccxt_order__dict['ccxt_order']

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

    # TOOD: Bybit exchange-specific codes
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

    bt_ccxt_order__dict.update(dict(
        execution_type=execution_type,
        ordering_type=ordering_type,
        order_intent=order_intent,
    ))
    return bt_ccxt_order__dict
