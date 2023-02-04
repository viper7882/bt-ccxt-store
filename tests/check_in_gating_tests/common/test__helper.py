import copy
import inspect

import backtrader

from time import time as timer
from unittest.mock import patch

from ccxtbt.bt_ccxt_expansion__helper import construct_standalone_account_or_store, construct_standalone_exchange, \
    construct_standalone_instrument
from ccxtbt.bt_ccxt_feed__classes import BT_CCXT_Feed
from ccxtbt.bt_ccxt__specifications import CCXT_COMMON_MAPPING_VALUES, CCXT__MARKET_TYPES, CCXT__MARKET_TYPE__FUTURE, \
    CCXT__MARKET_TYPE__LINEAR_PERPETUAL_SWAP, DERIVED__CCXT_ORDER__KEYS, MAX_LIVE_EXCHANGE_RETRIES, REJECTED_VALUE, \
    STATUS
from ccxtbt.bt_ccxt_order__classes import BT_CCXT_Order

from ccxtbt.exchange.binance.binance__exchange__specifications import BINANCE_EXCHANGE_ID, \
    BINANCE_OHLCV_LIMIT, BINANCE__PARTIALLY_FILLED__ORDER_STATUS__VALUE
from ccxtbt.exchange.bybit.bybit__exchange__specifications import BYBIT_EXCHANGE_ID, \
    BYBIT__PARTIALLY_FILLED__ORDER_STATUS__VALUE
from ccxtbt.exchange.exchange__helper import get_minimum_instrument_quantity
from ccxtbt.utils import get_order_entry_price_and_queue, get_time_diff, legality_check_not_none_obj


def ut_handle_datafeed(datafeed, price=None) -> None:
    datafeed.start()
    datafeed.forward()
    datafeed._load()
    datafeed._tz = None
    if price is not None:
        datafeed.close[0] = price


def ut_reverse_engineer__ccxt_order(bt_ccxt_order__dict) -> dict:
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


def ut_get_valid_market_types(exchange_dropdown_value, target__market_types) -> list:
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


def ut_enter_or_exit_using_market_order(params) -> tuple:
    # Un-serialize Params
    bt_ccxt_account_or_store = params['bt_ccxt_account_or_store']
    instrument = params['instrument']
    position_type = params['position_type']
    order_intent = params['order_intent']

    # Optional Params
    size = params.get('size', None)

    # Legality check
    if position_type not in range(len(backtrader.Position.Position_Types)):
        raise ValueError("{}: {} position_type must be one of {}!!!".format(
            inspect.currentframe(), position_type, range(len(backtrader.Position.Position_Types))))

    if order_intent not in range(len(backtrader.Order.Order_Intents)):
        raise ValueError("{} order_intent must be one of {}!!!".format(
            order_intent, range(len(backtrader.Order.Order_Intents))))

    if order_intent == backtrader.Order.Entry_Order:
        if size is None:
            offset = 0
            (nearest_ask, nearest_bid,) = \
                instrument.get_orderbook_price_by_offset(
                    offset)

            price = \
                get_order_entry_price_and_queue(
                    position_type, nearest_ask, nearest_bid)
            size = \
                get_minimum_instrument_quantity(
                    price, instrument)
    else:
        assert order_intent == backtrader.Order.Exit_Order
        legality_check_not_none_obj(size, "size")

    entry_or_exit__dict = dict(
        owner=instrument,
        symbol_id=instrument.symbol_id,
        size=size,
        execution_type=backtrader.Order.Market,
        ordering_type=backtrader.Order.ACTIVE_ORDERING_TYPE,
        order_intent=order_intent,
        position_type=position_type,

        # CCXT requires the market type name to be specified correctly
        type=CCXT__MARKET_TYPES[bt_ccxt_account_or_store.market_type],
    )

    # Patch def notify so that we could perform UT assertion if it is called
    with patch.object(bt_ccxt_account_or_store, 'notify') as mock:
        entry_or_exit_order_start = timer()
        if position_type == backtrader.Position.LONG_POSITION:
            if order_intent == backtrader.Order.Entry_Order:
                entry_or_exit_order = instrument.buy(**entry_or_exit__dict)
            else:
                assert order_intent == backtrader.Order.Exit_Order

                # To close a position you need to make the inverse operation with same amount
                entry_or_exit_order = instrument.sell(
                    **entry_or_exit__dict)
        else:
            assert position_type == backtrader.Position.SHORT_POSITION

            if order_intent == backtrader.Order.Entry_Order:
                entry_or_exit_order = instrument.sell(
                    **entry_or_exit__dict)
            else:
                assert order_intent == backtrader.Order.Exit_Order

                # To close a position you need to make the inverse operation with same amount
                entry_or_exit_order = instrument.buy(**entry_or_exit__dict)

        _, entry_or_exit_order_minutes, entry_or_exit_order_seconds = \
            get_time_diff(entry_or_exit_order_start)

        if order_intent == backtrader.Order.Entry_Order:
            entry_or_exit_name = "[Entry]"
        else:
            assert order_intent == backtrader.Order.Exit_Order

            entry_or_exit_name = "[Exit]"

        print("HTTP {} Order Took {}m:{:.2f}s".format(
            entry_or_exit_name,
            int(entry_or_exit_order_minutes), entry_or_exit_order_seconds)
        )
        # Test Assertion
        total_time_spent_in_seconds = entry_or_exit_order_minutes * \
            60 + entry_or_exit_order_seconds

    ret_value = (entry_or_exit_order, total_time_spent_in_seconds, mock, )
    return ret_value


def ut_enter_or_exit_using_limit_or_conditional_order(params) -> tuple:
    # Un-serialize Params
    bt_ccxt_account_or_store = params['bt_ccxt_account_or_store']
    instrument = params['instrument']
    position_type = params['position_type']
    order_intent = params['order_intent']
    execution_type = params['execution_type']
    ordering_type = params['ordering_type']
    price = params['price']

    # Optional Params
    size = params.get('size', None)

    # Legality Check
    if position_type not in range(len(backtrader.Position.Position_Types)):
        raise ValueError("{}: {} position_type must be one of {}!!!".format(
            inspect.currentframe(), position_type, range(len(backtrader.Position.Position_Types))))

    if order_intent not in range(len(backtrader.Order.Order_Intents)):
        raise ValueError("{} order_intent must be one of {}!!!".format(
            order_intent, range(len(backtrader.Order.Order_Intents))))

    assert isinstance(price, int) or isinstance(price, float)
    assert price > 0.0

    if order_intent == backtrader.Order.Entry_Order:
        if size is None:
            size = \
                get_minimum_instrument_quantity(
                    price, instrument)
    else:
        assert order_intent == backtrader.Order.Exit_Order
        legality_check_not_none_obj(size, "size")

    entry_or_exit__dict = dict(
        owner=instrument,
        symbol_id=instrument.symbol_id,
        price=price,
        size=size,
        execution_type=execution_type,
        ordering_type=ordering_type,
        order_intent=order_intent,
        position_type=position_type,

        # CCXT requires the market type name to be specified correctly
        type=CCXT__MARKET_TYPES[bt_ccxt_account_or_store.market_type],
    )
    if ordering_type == backtrader.Order.CONDITIONAL_ORDERING_TYPE:
        entry_or_exit__dict.update(dict(
            stopPrice=price,
        ))
        if bt_ccxt_account_or_store.exchange_dropdown_value == BYBIT_EXCHANGE_ID:
            offset = 0
            (nearest_ask, nearest_bid,) = \
                instrument.get_orderbook_price_by_offset(
                    offset)

            base_price = \
                get_order_entry_price_and_queue(
                    position_type, nearest_ask, nearest_bid)

            # Bybit requires to configure base price
            entry_or_exit__dict.update(dict(
                base_price=base_price,
            ))

    # Patch def notify so that we could perform UT assertion if it is called
    with patch.object(bt_ccxt_account_or_store, 'notify') as mock:
        entry_or_exit_order_start = timer()
        if position_type == backtrader.Position.LONG_POSITION:
            if order_intent == backtrader.Order.Entry_Order:
                entry_or_exit_order = instrument.buy(**entry_or_exit__dict)
            else:
                assert order_intent == backtrader.Order.Exit_Order

                # To close a position you need to make the inverse operation with same amount
                entry_or_exit_order = instrument.sell(
                    **entry_or_exit__dict)
        else:
            assert position_type == backtrader.Position.SHORT_POSITION

            if order_intent == backtrader.Order.Entry_Order:
                entry_or_exit_order = instrument.sell(
                    **entry_or_exit__dict)
            else:
                assert order_intent == backtrader.Order.Exit_Order

                # To close a position you need to make the inverse operation with same amount
                entry_or_exit_order = instrument.buy(**entry_or_exit__dict)

        _, entry_or_exit_order_minutes, entry_or_exit_order_seconds = \
            get_time_diff(entry_or_exit_order_start)

        if order_intent == backtrader.Order.Entry_Order:
            entry_or_exit_name = "[Entry]"
        else:
            assert order_intent == backtrader.Order.Exit_Order

            entry_or_exit_name = "[Exit]"

        print("HTTP {} Order Took {}m:{:.2f}s".format(
            entry_or_exit_name,
            int(entry_or_exit_order_minutes), entry_or_exit_order_seconds)
        )
        # Test Assertion
        total_time_spent_in_seconds = entry_or_exit_order_minutes * \
            60 + entry_or_exit_order_seconds

    ret_value = (entry_or_exit_order, total_time_spent_in_seconds, mock, )
    return ret_value


def ut_get_partially_filled_order(params) -> tuple:
    # Un-serialize Params
    bt_ccxt_account_or_store = params['bt_ccxt_account_or_store']
    instrument = params['instrument']
    ccxt_order_id = params['ccxt_order_id']

    # Locate the unmodified CCXT order
    unmodified_ccxt_orders = \
        [exchange_ccxt_order
         for exchange_ccxt_order in bt_ccxt_account_or_store.exchange_ccxt_orders
         if ccxt_order_id == exchange_ccxt_order['id']]
    assert len(unmodified_ccxt_orders) == 1

    # Create a copy so that we could modify it locally without affecting original order
    unmodified_ccxt_order = copy.deepcopy(unmodified_ccxt_orders[0])

    if unmodified_ccxt_order['remaining'] is None:
        unmodified_ccxt_order['remaining'] = unmodified_ccxt_order['amount']

    if unmodified_ccxt_order['filled'] is None:
        unmodified_ccxt_order['filled'] = 0.0

    # Validate assumption made
    assert isinstance(
        unmodified_ccxt_order['filled'], float)
    assert isinstance(
        unmodified_ccxt_order['remaining'], float)

    # Increment the qty by one step
    order_increment_qty = instrument.qty_step
    unmodified_ccxt_order['filled'] += order_increment_qty
    unmodified_ccxt_order['remaining'] -= order_increment_qty

    if bt_ccxt_account_or_store.exchange_dropdown_value == BINANCE_EXCHANGE_ID:
        partially_filled__order_status__value = \
            BINANCE__PARTIALLY_FILLED__ORDER_STATUS__VALUE
    elif bt_ccxt_account_or_store.exchange_dropdown_value == BYBIT_EXCHANGE_ID:
        partially_filled__order_status__value = \
            BYBIT__PARTIALLY_FILLED__ORDER_STATUS__VALUE
    else:
        raise NotImplementedError(
            "{} exchange is yet to be supported!!!".format(
                bt_ccxt_account_or_store.exchange_dropdown_value)
        )

    unmodified_ccxt_order[DERIVED__CCXT_ORDER__KEYS[STATUS]] = \
        partially_filled__order_status__value

    # Post-process the CCXT order so that they are consistent across multiple exchanges
    post_process__ccxt_orders__dict = dict(
        bt_ccxt_exchange=bt_ccxt_account_or_store.parent,
        bt_ccxt_account_or_store=bt_ccxt_account_or_store,
        ccxt_orders=[unmodified_ccxt_order],
    )
    post_processed__ccxt_orders = bt_ccxt_account_or_store.post_process__ccxt_orders(
        params=post_process__ccxt_orders__dict)
    post_processed__ccxt_order = post_processed__ccxt_orders[0]

    # Suspend the order in the open_orders queue
    assert len(bt_ccxt_account_or_store.open_orders) == 1
    accepted_order = bt_ccxt_account_or_store.open_orders.pop()

    datafeed = None
    # Exposed simulated so that we could proceed with order without running cerebro
    bt_ccxt_order__dict = dict(
        owner=bt_ccxt_account_or_store,
        exchange_dropdown_value=bt_ccxt_account_or_store.exchange_dropdown_value,
        symbol_id=instrument.symbol_id,
        ccxt_order=post_processed__ccxt_order,
        execution_type=accepted_order.execution_type,
        position_type=accepted_order.position_type,
        ordering_type=accepted_order.ordering_type,
        order_intent=accepted_order.order_intent,
    )
    if datafeed is not None:
        # Assign the datafeed since it exists
        bt_ccxt_order__dict.update(dict(
            datafeed=datafeed,
        ))
    else:
        # Turn on simulated should there is no datafeed
        bt_ccxt_order__dict.update(dict(
            simulated=True,
        ))
    partially_filled_order = BT_CCXT_Order(**bt_ccxt_order__dict)
    ret_value = (partially_filled_order, accepted_order, )
    return ret_value


def ut_get_rejected_order(params):
    # Un-serialize Params
    bt_ccxt_account_or_store = params['bt_ccxt_account_or_store']
    instrument = params['instrument']
    ccxt_order_id = params['ccxt_order_id']
    accepted_order = params['accepted_order']

    # Locate the unmodified CCXT order
    unmodified_ccxt_orders = \
        [exchange_ccxt_order
         for exchange_ccxt_order in bt_ccxt_account_or_store.exchange_ccxt_orders
         if ccxt_order_id == exchange_ccxt_order['id']]
    assert len(unmodified_ccxt_orders) == 1

    # Create a copy so that we could modify it locally without affecting original order
    unmodified_ccxt_order = copy.deepcopy(unmodified_ccxt_orders[0])
    unmodified_ccxt_order[DERIVED__CCXT_ORDER__KEYS[STATUS]
                          ] = CCXT_COMMON_MAPPING_VALUES[REJECTED_VALUE]

    # Post-process the CCXT order so that they are consistent across multiple exchanges
    post_process__ccxt_orders__dict = dict(
        bt_ccxt_exchange=bt_ccxt_account_or_store.parent,
        bt_ccxt_account_or_store=bt_ccxt_account_or_store,
        ccxt_orders=[unmodified_ccxt_order],
    )
    post_processed__ccxt_orders = bt_ccxt_account_or_store.post_process__ccxt_orders(
        params=post_process__ccxt_orders__dict)
    post_processed__ccxt_order = post_processed__ccxt_orders[0]

    # Suspend the order in the open_orders queue
    assert len(bt_ccxt_account_or_store.open_orders) == 0

    datafeed = None
    # Exposed simulated so that we could proceed with order without running cerebro
    bt_ccxt_order__dict = dict(
        owner=bt_ccxt_account_or_store,
        exchange_dropdown_value=bt_ccxt_account_or_store.exchange_dropdown_value,
        symbol_id=instrument.symbol_id,
        ccxt_order=post_processed__ccxt_order,
        execution_type=accepted_order.execution_type,
        position_type=accepted_order.position_type,
        ordering_type=accepted_order.ordering_type,
        order_intent=accepted_order.order_intent,
    )
    if datafeed is not None:
        # Assign the datafeed since it exists
        bt_ccxt_order__dict.update(dict(
            datafeed=datafeed,
        ))
    else:
        # Turn on simulated should there is no datafeed
        bt_ccxt_order__dict.update(dict(
            simulated=True,
        ))
    rejected_order = BT_CCXT_Order(**bt_ccxt_order__dict)
    ret_value = (rejected_order, accepted_order, )
    return ret_value


def ut_get_bt_ccxt_account_or_stores(params) -> list:
    # Un-serialize Params
    exchange_dropdown_values = params['exchange_dropdown_values']
    target__market_types = params['target__market_types']
    construct_standalone_account_or_store__dict = params[
        'construct_standalone_account_or_store__dict']

    # Optional Params
    callback_func__has_calls = params.get('callback_func__has_calls', None)
    ut_assert_not_called = params.get('ut_assert_not_called', None)
    ut_keep_original_ccxt_order = params.get(
        'ut_keep_original_ccxt_order', None)
    ut_clear_opened_bt_status = params.get('ut_clear_opened_bt_status', None)

    # Legality Check
    assert isinstance(exchange_dropdown_values, tuple)
    assert isinstance(target__market_types, tuple)

    # Clone a shallow copy as we cannot pickle '_thread.lock' object
    cloned_construct_standalone_account_or_store__dict = copy.copy(
        construct_standalone_account_or_store__dict)

    bt_ccxt_account_or_stores = []
    for exchange_dropdown_value in exchange_dropdown_values:
        # Construct the components
        market_types = ut_get_valid_market_types(
            exchange_dropdown_value, target__market_types)

        for market_type in market_types:
            construct_standalone_exchange__dict = dict(
                exchange_dropdown_value=exchange_dropdown_value,

                # UT: Disable singleton in exchange so that we could run tests across multiple exchanges
                ut_disable_singleton=True,
            )
            bt_ccxt_exchange = construct_standalone_exchange(
                params=construct_standalone_exchange__dict)

            cloned_construct_standalone_account_or_store__dict.update(dict(
                exchange_dropdown_value=exchange_dropdown_value,
                market_type=market_type,

                # Optional Params
                bt_ccxt_exchange=bt_ccxt_exchange,
                ut_keep_original_ccxt_order=ut_keep_original_ccxt_order,
                ut_clear_opened_bt_status=ut_clear_opened_bt_status,
            ))
            (bt_ccxt_account_or_store, exchange_specific_config,) = \
                construct_standalone_account_or_store(
                    params=cloned_construct_standalone_account_or_store__dict)

            for symbol_id in cloned_construct_standalone_account_or_store__dict['symbols_id']:
                # Patch def notify so that we could perform UT assertion if it is called
                with patch.object(bt_ccxt_account_or_store, 'notify') as mock:
                    construct_standalone_instrument__dict = dict(
                        bt_ccxt_account_or_store=bt_ccxt_account_or_store,
                        market_type=market_type,
                        symbol_id=symbol_id,
                    )
                    construct_standalone_instrument(
                        params=construct_standalone_instrument__dict)
                    instrument = bt_ccxt_account_or_store.get__child(
                        symbol_id)

                    custom__bt_ccxt_feed__dict = dict(
                        timeframe=backtrader.TimeFrame.Ticks,
                        drop_newest=False,
                        ut__halt_if_no_ohlcv=True,
                        # debug=True,
                    )

                    # Validate assumption made
                    assert isinstance(custom__bt_ccxt_feed__dict, dict)

                    # Long datafeed
                    bt_ccxt_feed__dict = dict(
                        exchange=exchange_dropdown_value,
                        name=backtrader.Position.Position_Types[backtrader.Position.LONG_POSITION],
                        dataname=symbol_id,
                        ohlcv_limit=BINANCE_OHLCV_LIMIT,
                        currency=cloned_construct_standalone_account_or_store__dict['wallet_currency'],
                        config=exchange_specific_config,
                        max_retries=MAX_LIVE_EXCHANGE_RETRIES,
                    )
                    bt_ccxt_feed__dict.update(custom__bt_ccxt_feed__dict)
                    long_bb_data = BT_CCXT_Feed(**bt_ccxt_feed__dict)
                    long_bb_data.set__parent(instrument)

                    # Short datafeed
                    bt_ccxt_feed__dict = dict(
                        exchange=exchange_dropdown_value,
                        name=backtrader.Position.Position_Types[backtrader.Position.SHORT_POSITION],
                        dataname=symbol_id,
                        ohlcv_limit=BINANCE_OHLCV_LIMIT,
                        currency=cloned_construct_standalone_account_or_store__dict['wallet_currency'],
                        config=exchange_specific_config,
                        max_retries=MAX_LIVE_EXCHANGE_RETRIES,
                    )
                    bt_ccxt_feed__dict.update(custom__bt_ccxt_feed__dict)
                    short_bb_data = BT_CCXT_Feed(**bt_ccxt_feed__dict)
                    short_bb_data.set__parent(instrument)

                if callback_func__has_calls is not None:
                    identify_calls__dict = dict(
                        bt_ccxt_account_or_store=bt_ccxt_account_or_store,
                        instrument=instrument,
                    )
                    calls = callback_func__has_calls(
                        params=identify_calls__dict)
                    assert isinstance(calls, list)

                    # Confirm bt_ccxt_account_or_store.notify has been called twice
                    mock.assert_has_calls(calls)

                if ut_assert_not_called:
                    mock.assert_not_called()

            bt_ccxt_account_or_stores.append(bt_ccxt_account_or_store)
    return bt_ccxt_account_or_stores
