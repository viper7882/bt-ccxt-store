import datetime
import inspect

from time import time as timer

from ccxtbt.bt_ccxt__specifications import CCXT__MARKET_TYPES, CCXT__MARKET_TYPE__FUTURES, CCXT__MARKET_TYPE__SPOT, \
    MIN_LEVERAGE
from ccxtbt.utils import legality_check_not_none_obj


def get_binance_commission_rate(params) -> float:
    '''
    Exchange specific approach to obtain commission rate for market type
    '''
    # INFO: Un-serialized Params
    bt_ccxt_account_or_store = params['bt_ccxt_account_or_store']
    market_type = params['market_type']
    symbol_id = params['symbol_id']

    commission = None
    timestamp = int(datetime.datetime.now().timestamp() * 1000)
    commission_rate__dict = dict(
        timestamp=timestamp,
    )
    if market_type == CCXT__MARKET_TYPE__FUTURES:
        # Reference: https://binance-docs.github.io/apidocs/futures/en/#user-commission-rate-user_data
        commission_rate__dict.update(dict(
            symbol=symbol_id,
        ))
        trading_fee = \
            bt_ccxt_account_or_store.exchange.fapiPrivate_get_commissionrate(
                params=commission_rate__dict)
        commission = \
            max(float(trading_fee['makerCommissionRate']),
                float(trading_fee['takerCommissionRate']))
    elif market_type == CCXT__MARKET_TYPE__SPOT:
        # Reference: https://binance-docs.github.io/apidocs/spot/en/#account-information-user_data
        account_info = \
            bt_ccxt_account_or_store.exchange.private_get_account(
                params=commission_rate__dict)
        key_of_max_value = max(
            account_info['commissionRates'], key=account_info['commissionRates'].get)
        commission = float(account_info['commissionRates'][key_of_max_value])
    else:
        raise NotImplementedError()
    legality_check_not_none_obj(commission, "commission")
    return commission


def get_binance_max_leverage(params) -> int:
    '''
    Exchange specific approach to obtain leverage for symbol
    '''
    # INFO: Un-serialized Params
    bt_ccxt_account_or_store = params['bt_ccxt_account_or_store']
    market_type_name = params['market_type_name']
    symbol_id = params['symbol_id']
    notional_value = params['notional_value']

    assert notional_value >= 0.0

    max_leverage = None
    timestamp = int(datetime.datetime.now().timestamp() * 1000)
    leverage__dict = dict(
        timestamp=timestamp,
    )
    if market_type_name == CCXT__MARKET_TYPES[CCXT__MARKET_TYPE__FUTURES]:
        # Reference: https://binance-docs.github.io/apidocs/futures/en/#user-leverage-rate-user_data
        leverage__dict.update(dict(
            symbol=symbol_id,
        ))
        position_bracket = \
            bt_ccxt_account_or_store.exchange.fapiPrivate_get_leveragebracket(
                params=leverage__dict)

        point_of_reference = position_bracket[0]

        # Validate assumption made
        assert point_of_reference['symbol'] == symbol_id

        for i in range(len(point_of_reference['brackets'])):
            if float(point_of_reference['brackets'][i]['notionalCap']) >= notional_value:
                max_leverage = int(
                    point_of_reference['brackets'][i]['initialLeverage'])
                break
        pass
    elif market_type_name == CCXT__MARKET_TYPES[CCXT__MARKET_TYPE__SPOT]:
        raise NotImplementedError()
    else:
        raise NotImplementedError()
    legality_check_not_none_obj(max_leverage, "max_leverage")
    return max_leverage


def get_binance_leverages(params) -> tuple:
    '''
    Exchange specific approach to obtain leverage for symbol
    '''
    # INFO: Un-serialized Params
    bt_ccxt_account_or_store = params['bt_ccxt_account_or_store']
    market_type_name = params['market_type_name']
    symbol_id = params['symbol_id']

    leverage = None
    max_leverage = None
    timestamp = int(datetime.datetime.now().timestamp() * 1000)
    leverage__dict = dict(
        timestamp=timestamp,
    )
    if market_type_name == CCXT__MARKET_TYPES[CCXT__MARKET_TYPE__FUTURES]:
        # Reference: https://binance-docs.github.io/apidocs/futures/en/#account-information-v2-user_data
        account_info = \
            bt_ccxt_account_or_store.exchange.fapiPrivate_get_account(
                params=leverage__dict)
        for i in range(len(account_info['positions'])):
            if account_info['positions'][i]['symbol'] == symbol_id:
                leverage = int(account_info['positions'][i]['leverage'])
                break
        max_leverage = get_binance_max_leverage(params)
    elif market_type_name == CCXT__MARKET_TYPES[CCXT__MARKET_TYPE__SPOT]:
        leverage = int(MIN_LEVERAGE)
    else:
        raise NotImplementedError()
    legality_check_not_none_obj(leverage, "leverage")
    legality_check_not_none_obj(max_leverage, "max_leverage")
    ret_value = leverage, max_leverage
    return ret_value


def set_binance_leverage(params) -> None:
    '''
    Exchange specific approach to configure leverage for symbol
    '''
    # INFO: Un-serialized Params
    bt_ccxt_account_or_store = params['bt_ccxt_account_or_store']
    market_type_name = params['market_type_name']
    symbol_id = params['symbol_id']
    from_leverage = params['from_leverage']
    to_leverage = params['to_leverage']

    # Legality Check
    assert from_leverage != to_leverage, \
        "from_leverage: {} == to_leverage: {}!!!".format(
            from_leverage, to_leverage)

    timestamp = int(datetime.datetime.now().timestamp() * 1000)
    leverage__dict = dict(
        timestamp=timestamp,
        symbol=symbol_id,
        leverage=to_leverage,
    )
    if market_type_name == CCXT__MARKET_TYPES[CCXT__MARKET_TYPE__FUTURES]:
        # Reference: https://binance-docs.github.io/apidocs/futures/en/#change-initial-leverage-trade
        response = \
            bt_ccxt_account_or_store.exchange.fapiPrivate_post_leverage(
                params=leverage__dict)

        # INFO: Confirmation
        assert response['symbol'] == symbol_id
        assert response['leverage'] == str(to_leverage)

        frameinfo = inspect.getframeinfo(inspect.currentframe())
        msg = "{}: {} Line: {}: INFO: {}: Sync with {}: ".format(
            market_type_name,
            frameinfo.function, frameinfo.lineno,
            symbol_id, bt_ccxt_account_or_store,
        )
        sub_msg = "Adjusted leverage from {} -> {}".format(
            from_leverage,
            to_leverage,
        )
        print(msg + sub_msg)
        pass
    elif market_type_name == CCXT__MARKET_TYPES[CCXT__MARKET_TYPE__SPOT]:
        raise NotImplementedError()
    else:
        raise NotImplementedError()
