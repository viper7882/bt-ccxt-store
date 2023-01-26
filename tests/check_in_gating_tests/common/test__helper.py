import inspect

import backtrader
import json
import time

from ccxtbt.bt_ccxt__specifications import CCXT__MARKET_TYPES, CCXT__MARKET_TYPE__FUTURE, \
    CCXT__MARKET_TYPE__LINEAR_PERPETUAL_SWAP, MAX_LIVE_EXCHANGE_RETRIES
from ccxtbt.bt_ccxt_exchange__classes import BT_CCXT_Exchange
from ccxtbt.bt_ccxt_account_or_store__classes import BT_CCXT_Account_or_Store
from ccxtbt.bt_ccxt_instrument__classes import BT_CCXT_Instrument

from check_in_gating_tests.common.test__classes import FAKE_COMMISSION_INFO, FAKE_EXCHANGE

from ccxtbt.exchange.binance.binance__exchange__helper import get_binance_commission_rate
from ccxtbt.exchange.binance.binance__exchange__specifications import BINANCE_EXCHANGE_ID

from ccxtbt.exchange.bybit.bybit__exchange__helper import get_bybit_commission_rate
from ccxtbt.exchange.bybit.bybit__exchange__specifications import BYBIT_EXCHANGE_ID

from ccxtbt.exchange.exchange__helper import get_api_and_secret_file_path

from ccxtbt.utils import legality_check_not_none_obj


def ut_get_commission_info(params):
    commission_info = FAKE_COMMISSION_INFO(params)
    return commission_info


def ut_handle_datafeed(datafeed, price=None):
    datafeed.start()
    datafeed.forward()
    datafeed._load()
    datafeed._tz = None
    if price is not None:
        datafeed.close[0] = price


def reverse_engineer__ccxt_order(exchange, bt_ccxt_order__dict):
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

    if str(exchange).lower() == BINANCE_EXCHANGE_ID:
        raise NotImplementedError(
            "{} exchange is yet to be supported!!!".format(str(exchange).lower()))
    elif str(exchange).lower() == BYBIT_EXCHANGE_ID:
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
            "{} exchange is yet to be supported!!!".format(str(exchange).lower()))

    bt_ccxt_order__dict.update(dict(
        execution_type=execution_type,
        ordering_type=ordering_type,
        order_intent=order_intent,
    ))
    return bt_ccxt_order__dict


def ut__construct_standalone_exchange(params) -> object:
    # INFO: Un-serialized Params
    exchange_dropdown_value = params['exchange_dropdown_value']

    order_types = {
        backtrader.Order.Market: "market",
        backtrader.Order.Limit: "limit",
    }
    if exchange_dropdown_value == BINANCE_EXCHANGE_ID:
        order_types.update(
            {
                backtrader.Order.StopMarket: "stop market",
                backtrader.Order.StopLimit: "stop",
            }
        )
    ccxt__order_types__broker_mapping = dict(
        order_types=order_types,
    )

    # INFO: CCXT broker_or_exchange mapping consumed by BT-CCXT broker_or_exchange
    # Documentation: https://docs.ccxt.com/en/latest/manual.html#order-structure
    mappings = dict(
        opened_order={
            'key': "status",
            'value': "open",
        },
        closed_order={
            'key': "status",
            'value': "closed",
        },
        canceled_order={
            'key': "status",
            'value': "canceled",
        },
        expired_order={
            'key': "status",
            'value': "expired",
        },
        rejected_order={
            'key': "status",
            'value': "rejected",
        },
    )

    if exchange_dropdown_value == BINANCE_EXCHANGE_ID:
        mappings.update(
            partially_filled_order={
                'key': "status",
                'value': "PARTIALLY_FILLED",
            },
        )
    elif exchange_dropdown_value == BYBIT_EXCHANGE_ID:
        mappings.update(
            partially_filled_order={
                'key': "status",
                'value': "PartiallyFilled",
            },
        )

    ccxt__broker_mapping = dict(
        mappings=mappings,
    )
    ccxt__broker_mapping.update(ccxt__order_types__broker_mapping)
    bt_ccxt_exchange = BT_CCXT_Exchange(broker_mapping=ccxt__broker_mapping)
    return bt_ccxt_exchange


def ut__construct_standalone_account_or_store(params) -> tuple:
    # INFO: Un-serialized Params
    exchange_dropdown_value = params['exchange_dropdown_value']
    main_net_toggle_switch_value = params['main_net_toggle_switch_value']
    market_type = params['market_type']
    symbols_id = params['symbols_id']
    enable_rate_limit = params['enable_rate_limit']
    initial__capital_reservation__value = params['initial__capital_reservation__value']
    is_ohlcv_provider = params['is_ohlcv_provider']
    account__thread__connectivity__lock = params['account__thread__connectivity__lock']
    leverage_in_percent = params['leverage_in_percent']
    wallet_currency = params['wallet_currency']

    # INFO: Optional Params
    account_type = params.get('account_type', None)
    bt_ccxt_exchange = params.get('bt_ccxt_exchange', None)

    market_type_name = CCXT__MARKET_TYPES[market_type]

    api_and_secret_file_path__dict = dict(
        exchange_dropdown_value=exchange_dropdown_value,
        market_type=market_type,
        main_net_toggle_switch_value=main_net_toggle_switch_value,
    )
    api_key_and_secret_full_path = get_api_and_secret_file_path(
        **api_and_secret_file_path__dict)

    bt_ccxt_account_or_store = None
    with open(api_key_and_secret_full_path, "r") as file_to_read:
        json_data = json.load(file_to_read)
        api_key = json_data['key']
        api_secret = json_data['secret']
        account_alias__dropdown_value = json_data['account_alias__dropdown_value']

        exchange_specific_config = dict(
            apiKey=api_key,
            secret=api_secret,
            nonce=lambda: str(int(time.time() * 1000)),
            enableRateLimit=enable_rate_limit,
            type=market_type_name,

            account_alias=account_alias__dropdown_value,
            account_type=account_type,
            market_type=market_type,
        )

        account_or_store__dict = dict(
            main_net_toggle_switch_value=main_net_toggle_switch_value,
            config=exchange_specific_config,
            initial__capital_reservation__value=initial__capital_reservation__value,
            is_ohlcv_provider=is_ohlcv_provider,
            leverage_in_percent=leverage_in_percent,
        )

        # INFO: Live-specific Params
        account_or_store__dict.update(dict(
            exchange_dropdown_value=exchange_dropdown_value,
            wallet_currency=wallet_currency.upper(),
            retries=MAX_LIVE_EXCHANGE_RETRIES,
            symbols_id=symbols_id,
            account__thread__connectivity__lock=account__thread__connectivity__lock,
            # debug=True,
        ))

        bt_ccxt_account_or_store = BT_CCXT_Account_or_Store(
            **account_or_store__dict)
    legality_check_not_none_obj(
        bt_ccxt_account_or_store, "bt_ccxt_account_or_store")

    if bt_ccxt_exchange is None:
        bt_ccxt_exchange = FAKE_EXCHANGE(owner=bt_ccxt_account_or_store)
    else:
        assert type(bt_ccxt_exchange).__name__ == BT_CCXT_Exchange.__name__
    bt_ccxt_account_or_store.set__parent(bt_ccxt_exchange)
    bt_ccxt_exchange.add__account_or_store(bt_ccxt_account_or_store)

    ret_value = bt_ccxt_account_or_store, exchange_specific_config
    return ret_value


def ut__construct_standalone_instrument(params) -> object:
    # INFO: Un-serialized Params
    bt_ccxt_account_or_store = params['bt_ccxt_account_or_store']
    market_type = params['market_type']
    symbol_id = params['symbol_id']
    leverage_in_percent = params['leverage_in_percent']
    isolated_toggle_switch_value = params['isolated_toggle_switch_value']

    # Legality Check
    assert type(
        bt_ccxt_account_or_store).__name__ == BT_CCXT_Account_or_Store.__name__

    bt_ccxt_instrument__dict = dict(
        symbol_id=symbol_id,
    )
    instrument = BT_CCXT_Instrument(**bt_ccxt_instrument__dict)
    instrument.set__parent(bt_ccxt_account_or_store)

    commission_rate__dict = dict(
        bt_ccxt_account_or_store=bt_ccxt_account_or_store,
        market_type=market_type,
        symbol_id=symbol_id,
    )
    if str(bt_ccxt_account_or_store.exchange).lower() == BINANCE_EXCHANGE_ID:
        commission = get_binance_commission_rate(
            params=commission_rate__dict)
    elif str(bt_ccxt_account_or_store.exchange).lower() == BYBIT_EXCHANGE_ID:
        commission = get_bybit_commission_rate(
            params=commission_rate__dict)
    else:
        raise NotImplementedError()

    get_commission_info__dict = dict(
        symbol_id=symbol_id,
        isolated_toggle_switch_value=isolated_toggle_switch_value,
        leverage_in_percent=leverage_in_percent,
        commission=commission,
        instrument=instrument,
    )
    commission_info = \
        ut_get_commission_info(params=get_commission_info__dict)

    instrument.add_commission_info(commission_info)

    bt_ccxt_account_or_store.add__instrument(instrument)
    return instrument


def ut_get_valid_market_types(exchange_dropdown_value, target__market_types):
    assert isinstance(exchange_dropdown_value, str)
    assert isinstance(target__market_types, list)

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
