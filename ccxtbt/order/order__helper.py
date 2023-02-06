import backtrader
import inspect

from ccxtbt.exchange_or_broker.binance.binance__exchange__specifications import BINANCE_EXCHANGE_ID
from ccxtbt.exchange_or_broker.bybit.bybit__exchange__specifications import BYBIT_EXCHANGE_ID
from ccxtbt.order.order__classes import BT_CCXT_Order
from ccxtbt.order.order__specifications import CCXT_ORDER_KEYS__MUST_BE_IN_FLOAT, CCXT_ORDER_KEYS__MUST_EXIST, \
    CCXT_ORDER_TYPES, CCXT_TYPE_KEY, DERIVED__CCXT_ORDER__KEYS, PLURAL__CCXT_ORDER__KEYS, STATUSES, CANCELED_ORDER, \
    CLOSED_ORDER, EXECUTION_TYPE, EXECUTION_TYPES, EXPIRED_ORDER, OPENED_ORDER, ORDERING_TYPE, ORDERING_TYPES, \
    ORDER_INTENT, ORDER_INTENTS, PARTIALLY_FILLED_ORDER, POSITION_TYPE, POSITION_TYPES, REJECTED_ORDER, \
    SIDE, SIDES, STATUS
from ccxtbt.utils import capitalize_sentence, legality_check_not_none_obj


def converge_ccxt_reduce_only_value(params):
    exchange_dropdown_value = params['exchange_dropdown_value']
    ccxt_order = params['ccxt_order']

    assert isinstance(exchange_dropdown_value, str)
    assert isinstance(ccxt_order, dict)

    if exchange_dropdown_value == BINANCE_EXCHANGE_ID:
        assert 'reduceOnly' in ccxt_order.keys()
        ccxt_order['reduce_only'] = bool(ccxt_order['reduceOnly'])
        # Rename dict from 'reduceOnly' key with 'reduce_only' key while maintaining its ordering
        ccxt_order = {'reduce_only' if k ==
                      'reduceOnly' else k: v for k, v in ccxt_order.items()}
    elif exchange_dropdown_value == BYBIT_EXCHANGE_ID:
        assert 'info' in ccxt_order.keys()
        assert 'reduce_only' in ccxt_order['info'].keys()
        ccxt_order['reduce_only'] = bool(ccxt_order['info']['reduce_only'])
    else:
        raise NotImplementedError(
            "{} exchange is yet to be supported!!!".format(exchange_dropdown_value))
    return ccxt_order


def reverse_engineer__ccxt_order(params):
    '''
    The following codes made assumption where def post_process__ccxt_orders has been called prior to this
    '''
    # Un-serialize Params
    bt_ccxt_exchange = params['bt_ccxt_exchange']
    bt_ccxt_account_or_store = params['bt_ccxt_account_or_store']
    ccxt_order = params['ccxt_order']

    # Legality Check
    legality_check_not_none_obj(bt_ccxt_exchange, "bt_ccxt_exchange")
    legality_check_not_none_obj(
        bt_ccxt_account_or_store, "bt_ccxt_account_or_store")

    for key in CCXT_ORDER_KEYS__MUST_BE_IN_FLOAT:
        assert isinstance(ccxt_order[key], float), "ccxt_order[{}]: {} must be in float!!!".format(
            key, ccxt_order[key])

    for key in CCXT_ORDER_KEYS__MUST_EXIST:
        assert key in ccxt_order.keys(), "{} key must exist in ccxt_order.keys()!!!".format(key)
    assert isinstance(ccxt_order['reduce_only'], bool)

    assert hasattr(bt_ccxt_exchange, 'order_types')
    assert isinstance(bt_ccxt_exchange.order_types, dict)
    assert ccxt_order[CCXT_TYPE_KEY] in bt_ccxt_exchange.order_types.values()

    # Identify 'ordering_type'
    if ccxt_order['stopPrice'] == 0.0:
        ccxt_order[DERIVED__CCXT_ORDER__KEYS[ORDERING_TYPE]
                   ] = backtrader.Order.ACTIVE_ORDERING_TYPE
    else:
        ccxt_order[DERIVED__CCXT_ORDER__KEYS[ORDERING_TYPE]
                   ] = backtrader.Order.CONDITIONAL_ORDERING_TYPE
    ccxt_order['{}_name'.format(DERIVED__CCXT_ORDER__KEYS[ORDERING_TYPE])] = \
        backtrader.Order.Ordering_Types[ccxt_order[DERIVED__CCXT_ORDER__KEYS[ORDERING_TYPE]]]

    # Identify 'execution_type'
    execution_type = None
    for key, value in bt_ccxt_exchange.order_types.items():
        if ccxt_order[CCXT_TYPE_KEY] == value:
            execution_type = key
            break
    legality_check_not_none_obj(execution_type, "execution_type")

    ccxt_order[DERIVED__CCXT_ORDER__KEYS[EXECUTION_TYPE]] = execution_type
    ccxt_order['{}_name'.format(DERIVED__CCXT_ORDER__KEYS[EXECUTION_TYPE])] = \
        backtrader.Order.Execution_Types[ccxt_order['execution_type']]

    # Identify 'order_intent'
    ccxt_order[DERIVED__CCXT_ORDER__KEYS[ORDER_INTENT]] = \
        backtrader.Order.Exit_Order if ccxt_order['reduce_only'] == True else backtrader.Order.Entry_Order
    ccxt_order['{}_name'.format(DERIVED__CCXT_ORDER__KEYS[ORDER_INTENT])] = \
        backtrader.Order.Order_Intents[ccxt_order[DERIVED__CCXT_ORDER__KEYS[ORDER_INTENT]]]

    # Identify 'position_type'
    side = backtrader.Order.Order_Types.index(
        capitalize_sentence(ccxt_order['side_name']))
    if ccxt_order[DERIVED__CCXT_ORDER__KEYS[ORDER_INTENT]] == backtrader.Order.Entry_Order:
        # Entry order, the side is matching
        if side == backtrader.Order.Buy:
            ccxt_order[DERIVED__CCXT_ORDER__KEYS[POSITION_TYPE]
                       ] = backtrader.Position.LONG_POSITION
        else:
            assert side == backtrader.Order.Sell

            ccxt_order[DERIVED__CCXT_ORDER__KEYS[POSITION_TYPE]
                       ] = backtrader.Position.SHORT_POSITION
    else:
        assert ccxt_order[DERIVED__CCXT_ORDER__KEYS[ORDER_INTENT]
                          ] == backtrader.Order.Exit_Order

        # Exit order, the side is opposite
        if side == backtrader.Order.Buy:
            ccxt_order[DERIVED__CCXT_ORDER__KEYS[POSITION_TYPE]
                       ] = backtrader.Position.SHORT_POSITION
        else:
            assert side == backtrader.Order.Sell

            ccxt_order[DERIVED__CCXT_ORDER__KEYS[POSITION_TYPE]
                       ] = backtrader.Position.LONG_POSITION
    ccxt_order['{}_name'.format(DERIVED__CCXT_ORDER__KEYS[POSITION_TYPE])] = \
        backtrader.Position.Position_Types[ccxt_order[DERIVED__CCXT_ORDER__KEYS[POSITION_TYPE]]]

    # Identify CCXT order's 'ccxt_status' -> backtrader's 'status'
    for ccxt_order_type in range(len(CCXT_ORDER_TYPES)):
        key = bt_ccxt_exchange.mappings[CCXT_ORDER_TYPES[ccxt_order_type]]['key']
        value = bt_ccxt_exchange.mappings[CCXT_ORDER_TYPES[ccxt_order_type]]['value']

        if ccxt_order[key] == value:
            if ccxt_order_type == OPENED_ORDER:
                ccxt_order[DERIVED__CCXT_ORDER__KEYS[STATUS]
                           ] = backtrader.Order.Accepted
                break
            elif ccxt_order_type == PARTIALLY_FILLED_ORDER:
                ccxt_order[DERIVED__CCXT_ORDER__KEYS[STATUS]
                           ] = backtrader.Order.Partial
                break
            elif ccxt_order_type == CLOSED_ORDER:
                ccxt_order[DERIVED__CCXT_ORDER__KEYS[STATUS]
                           ] = backtrader.Order.Completed
                break
            elif ccxt_order_type == CANCELED_ORDER:
                ccxt_order[DERIVED__CCXT_ORDER__KEYS[STATUS]
                           ] = backtrader.Order.Canceled
                break
            elif ccxt_order_type == REJECTED_ORDER:
                ccxt_order[DERIVED__CCXT_ORDER__KEYS[STATUS]
                           ] = backtrader.Order.Rejected
                break
            elif ccxt_order_type == EXPIRED_ORDER:
                ccxt_order[DERIVED__CCXT_ORDER__KEYS[STATUS]
                           ] = backtrader.Order.Expired
                break
            else:
                raise NotImplementedError()

    if DERIVED__CCXT_ORDER__KEYS[STATUS] not in ccxt_order.keys():
        frameinfo = inspect.getframeinfo(inspect.currentframe())
        msg = "{} Line: {}: ERROR: Tried combinations:".format(
            frameinfo.function, frameinfo.lineno,
        )

        for ccxt_order_type in range(len(CCXT_ORDER_TYPES)):
            key = bt_ccxt_exchange.mappings[CCXT_ORDER_TYPES[ccxt_order_type]]['key']
            value = bt_ccxt_exchange.mappings[CCXT_ORDER_TYPES[ccxt_order_type]]['value']

            sub_msg = "ccxt_order[\'{}\']: {} vs value: {}".format(
                key,
                ccxt_order[key],
                value,
            )
            print(msg + sub_msg)

    ccxt_order['{}_name'.format(DERIVED__CCXT_ORDER__KEYS[STATUS])] = \
        backtrader.Order.Status[ccxt_order[DERIVED__CCXT_ORDER__KEYS[STATUS]]]
    return ccxt_order


def get_ccxt_order_id(exchange_dropdown_value, order):
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

                    if exchange_dropdown_value == BINANCE_EXCHANGE_ID:
                        raise NotImplementedError(
                            "{} exchange is yet to be supported!!!".format(exchange_dropdown_value))
                    elif exchange_dropdown_value == BYBIT_EXCHANGE_ID:
                        if 'stop_order_id' in order.ccxt_order['info'].keys():
                            ccxt_order_id = order.ccxt_order['info']['stop_order_id']
                        elif 'order_id' in order.ccxt_order['info'].keys():
                            ccxt_order_id = order.ccxt_order['info']['order_id']
                    else:
                        raise NotImplementedError(
                            "{} exchange is yet to be supported!!!".format(exchange_dropdown_value))
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


def get_filtered_orders(params):
    # Un-serialize Params
    filter_order__dict = params['filter_order__dict']
    orders = params['orders']

    assert isinstance(filter_order__dict, dict)
    assert isinstance(orders, list)
    for key, item in filter_order__dict.items():
        if item is not None:
            assert isinstance(
                item, list), "filter_order__dict[{}]: {} must be of list type!!!".format(key, item)

            for list_item in item:
                if key == PLURAL__CCXT_ORDER__KEYS[STATUSES]:
                    assert list_item in range(len(backtrader.Order.Status))
                elif key == PLURAL__CCXT_ORDER__KEYS[ORDERING_TYPES]:
                    assert list_item in range(
                        len(backtrader.Order.Ordering_Types))
                elif key == PLURAL__CCXT_ORDER__KEYS[EXECUTION_TYPES]:
                    assert list_item in range(
                        len(backtrader.Order.Execution_Types))
                elif key == PLURAL__CCXT_ORDER__KEYS[ORDER_INTENTS]:
                    assert list_item in range(
                        len(backtrader.Order.Order_Intents))
                elif key == PLURAL__CCXT_ORDER__KEYS[POSITION_TYPES]:
                    assert list_item in range(
                        len(backtrader.Position.Position_Types))
                elif key == PLURAL__CCXT_ORDER__KEYS[SIDES]:
                    assert list_item in range(
                        len(backtrader.Order.Order_Types))
                else:
                    raise NotImplementedError(
                        "{} key is not yet enabled!!!".format(key))

    ret_orders = []
    for order in orders:
        frameinfo = inspect.getframeinfo(inspect.currentframe())
        assert type(order).__name__ == BT_CCXT_Order.__name__, \
            "{} Line: {}: Expected {} but observed {} instead!!!".format(
                frameinfo.function, frameinfo.lineno,
                BT_CCXT_Order.__name__, type(order).__name__,
        )
        assert hasattr(order, 'ccxt_order')

        # Alias
        ccxt_order = order.ccxt_order

        accepted = False
        if filter_order__dict[PLURAL__CCXT_ORDER__KEYS[STATUSES]] is None or \
                len(filter_order__dict[PLURAL__CCXT_ORDER__KEYS[STATUSES]]) == 0 or \
                ccxt_order[DERIVED__CCXT_ORDER__KEYS[STATUS]] in \
                filter_order__dict[PLURAL__CCXT_ORDER__KEYS[STATUSES]]:
            accepted = True

        if accepted == True:
            accepted = False
            if filter_order__dict[PLURAL__CCXT_ORDER__KEYS[ORDERING_TYPES]] is None or \
                    len(filter_order__dict[PLURAL__CCXT_ORDER__KEYS[ORDERING_TYPES]]) == 0 or \
                    ccxt_order[DERIVED__CCXT_ORDER__KEYS[ORDERING_TYPE]] in \
                    filter_order__dict[PLURAL__CCXT_ORDER__KEYS[ORDERING_TYPES]]:
                accepted = True

        if accepted == True:
            accepted = False
            if filter_order__dict[PLURAL__CCXT_ORDER__KEYS[EXECUTION_TYPES]] is None or \
                    len(filter_order__dict[PLURAL__CCXT_ORDER__KEYS[EXECUTION_TYPES]]) == 0 or \
                    ccxt_order[DERIVED__CCXT_ORDER__KEYS[EXECUTION_TYPE]] in \
                    filter_order__dict[PLURAL__CCXT_ORDER__KEYS[EXECUTION_TYPES]]:
                accepted = True

        if accepted == True:
            accepted = False
            if filter_order__dict[PLURAL__CCXT_ORDER__KEYS[ORDER_INTENTS]] is None or \
                    len(filter_order__dict[PLURAL__CCXT_ORDER__KEYS[ORDER_INTENTS]]) == 0 or \
                    ccxt_order[DERIVED__CCXT_ORDER__KEYS[ORDER_INTENT]] in \
                    filter_order__dict[PLURAL__CCXT_ORDER__KEYS[ORDER_INTENTS]]:
                accepted = True

        if accepted == True:
            accepted = False
            if filter_order__dict[PLURAL__CCXT_ORDER__KEYS[POSITION_TYPES]] is None or \
                    len(filter_order__dict[PLURAL__CCXT_ORDER__KEYS[POSITION_TYPES]]) == 0 or \
                    ccxt_order[DERIVED__CCXT_ORDER__KEYS[POSITION_TYPE]] in \
                    filter_order__dict[PLURAL__CCXT_ORDER__KEYS[POSITION_TYPES]]:
                accepted = True

        if accepted == True:
            accepted = False
            if filter_order__dict[PLURAL__CCXT_ORDER__KEYS[SIDES]] is None or \
                    len(filter_order__dict[PLURAL__CCXT_ORDER__KEYS[SIDES]]) == 0 or \
                    ccxt_order[DERIVED__CCXT_ORDER__KEYS[SIDE]] in filter_order__dict[PLURAL__CCXT_ORDER__KEYS[SIDES]]:
                accepted = True

        if accepted == True:
            ret_orders.append(order)
    return ret_orders


def force_ccxt_order_status(params) -> object:
    # Un-serialize Params
    ccxt_order = params['ccxt_order']
    ut_modify_open_to_ccxt_status = params['ut_modify_open_to_ccxt_status']
    bt_ccxt_exchange = params['bt_ccxt_exchange']

    # Alias
    ccxt_order_type = CCXT_ORDER_TYPES[ut_modify_open_to_ccxt_status]
    ccxt_status_key = bt_ccxt_exchange.mappings[ccxt_order_type]['key']
    ccxt_status_value = bt_ccxt_exchange.mappings[ccxt_order_type]['value']

    ccxt_order["{}_name".format(
        DERIVED__CCXT_ORDER__KEYS[STATUS])] = ccxt_status_value
    ccxt_order[DERIVED__CCXT_ORDER__KEYS[STATUS]
               ] = ut_modify_open_to_ccxt_status
    ccxt_order[ccxt_status_key] = ccxt_status_value

    return ccxt_order
