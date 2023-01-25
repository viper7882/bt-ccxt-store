import ccxt
import datetime
import inspect

from ccxtbt.bt_ccxt__specifications import CCXT__MARKET_TYPES, CCXT__MARKET_TYPE__LINEAR_PERPETUAL_SWAP, CCXT__MARKET_TYPE__SPOT, \
    MIN_LEVERAGE
from ccxtbt.utils import legality_check_not_none_obj


def get_wallet_currency(symbol_id):
    currency = None
    if symbol_id.endswith("USDT"):
        currency = "USDT"
    elif symbol_id.endswith("USDC"):
        currency = symbol_id.replace("USDC", "")
    elif symbol_id.endswith("USD"):
        currency = symbol_id.replace("USD", "")
    legality_check_not_none_obj(currency, "currency")
    return currency


def get_symbol_name(symbol_id):
    if symbol_id.endswith("USDT"):
        symbol_name = symbol_id.replace("USDT", "/USDT")
    elif symbol_id.endswith("USD"):
        symbol_name = symbol_id.replace("USD", "/USD")
    elif symbol_id.endswith("USDC"):
        symbol_name = symbol_id.replace("USDC", "/USDC")
    else:
        raise RuntimeError("{}: {} is not supported!".format(
            inspect.currentframe(), symbol_id))
    return symbol_name


def get_ccxt_market_symbol_name(market_type, symbol_id) -> str:
    currency = get_wallet_currency(symbol_id)
    symbol_name = get_symbol_name(symbol_id)
    if market_type == CCXT__MARKET_TYPE__LINEAR_PERPETUAL_SWAP:
        ccxt_market_symbol_name = "{}:{}".format(symbol_name, currency)
    else:
        assert market_type == CCXT__MARKET_TYPE__SPOT

        ccxt_market_symbol_name = "{}".format(symbol_name)
    return ccxt_market_symbol_name


def get_bybit_commission_rate(params) -> float:
    '''
    Exchange specific approach to obtain commission rate for market type
    '''
    # INFO: Un-serialized Params
    bt_ccxt_account_or_store = params['bt_ccxt_account_or_store']
    market_type = params['market_type']
    symbol_id = params['symbol_id']

    commission = None
    if market_type == CCXT__MARKET_TYPE__LINEAR_PERPETUAL_SWAP or market_type == CCXT__MARKET_TYPE__SPOT:
        market_type_name = CCXT__MARKET_TYPES[market_type]

        # Load all markets from the exchange
        load_markets__dict = dict(
            type=market_type_name,   # CCXT Market Type
        )
        markets = bt_ccxt_account_or_store.exchange.load_markets(
            params=load_markets__dict)

        ccxt_market_symbol_name = get_ccxt_market_symbol_name(
            market_type, symbol_id)

        # Legality Check
        if ccxt_market_symbol_name not in markets.keys():
            raise ccxt.BadSymbol()

        selected_market = markets[ccxt_market_symbol_name]

        commission = \
            max(float(selected_market['taker']),
                float(selected_market['maker']))
        pass
    else:
        raise NotImplementedError()
    legality_check_not_none_obj(commission, "commission")
    return commission


def get_bybit_max_leverage(params) -> float:
    '''
    Exchange specific approach to obtain leverage for symbol
    '''
    # INFO: Un-serialized Params
    bt_ccxt_account_or_store = params['bt_ccxt_account_or_store']
    market_type = params['market_type']
    symbol_id = params['symbol_id']
    notional_value = params['notional_value']

    assert notional_value >= 0.0

    max_leverage = None
    if market_type == CCXT__MARKET_TYPE__LINEAR_PERPETUAL_SWAP:
        if symbol_id.endswith("USDT"):
            '''
            Reference: https://bybit-exchange.github.io/docs/futuresV2/linear/#t-getrisklimit
            '''
            # response = bt_ccxt_account_or_store.exchange.private_get_public_linear_risk_limit()
            response = bt_ccxt_account_or_store.exchange.public_get_public_linear_risk_limit(
                dict(symbol=symbol_id))

            for i in range(len(response['result'])):
                # Validate assumption made
                assert response['result'][i]['symbol'] == symbol_id

                if float(response['result'][i]['limit']) >= notional_value:
                    max_leverage = float(response['result'][i]['max_leverage'])
                    break
            pass
        elif symbol_id.endswith("USD") or symbol_id.endswith("USDC"):
            '''
            Reference: https://bybit-exchange.github.io/docs/futuresV2/inverse/#t-getrisklimit
            '''
            response = bt_ccxt_account_or_store.exchange.public_get_v2_public_risk_limit_list(
                dict(symbol=symbol_id))
            raise NotImplementedError()
        else:
            raise NotImplementedError()
    elif market_type == CCXT__MARKET_TYPE__SPOT:
        raise NotImplementedError()
    else:
        raise NotImplementedError()
    legality_check_not_none_obj(max_leverage, "max_leverage")
    return max_leverage


def get_bybit_leverages(params) -> tuple:
    '''
    Exchange specific approach to obtain leverage for symbol
    '''
    # INFO: Un-serialized Params
    bt_ccxt_account_or_store = params['bt_ccxt_account_or_store']
    market_type = params['market_type']
    symbol_id = params['symbol_id']

    leverage = None
    max_leverage = None
    if market_type == CCXT__MARKET_TYPE__LINEAR_PERPETUAL_SWAP:
        response = bt_ccxt_account_or_store.exchange.fetch_positions(
            symbols=[symbol_id], params={'type': CCXT__MARKET_TYPES[market_type]})
        if isinstance(response, list):
            position_leverages = []
            for item in response:
                position_leverages.append(float(item['info']['leverage']))
            leverage = sum(position_leverages) / \
                (len(position_leverages) or 1.0)
        else:
            leverage = float(response['info']['leverage'])
            pass

        max_leverage = get_bybit_max_leverage(params)
    elif market_type == CCXT__MARKET_TYPE__SPOT:
        leverage = MIN_LEVERAGE
    else:
        raise NotImplementedError()
    legality_check_not_none_obj(leverage, "leverage")
    legality_check_not_none_obj(max_leverage, "max_leverage")
    ret_value = leverage, max_leverage
    return ret_value


def set_bybit_leverage(params) -> None:
    '''
    Exchange specific approach to configure leverage for symbol
    '''
    # INFO: Un-serialized Params
    bt_ccxt_account_or_store = params['bt_ccxt_account_or_store']
    market_type = params['market_type']
    symbol_id = params['symbol_id']
    from_leverage = params['from_leverage']
    to_leverage = params['to_leverage']

    # Legality Check
    assert from_leverage != to_leverage, \
        "from_leverage: {} == to_leverage: {}!!!".format(
            from_leverage, to_leverage)

    if market_type == CCXT__MARKET_TYPE__LINEAR_PERPETUAL_SWAP:
        if symbol_id.endswith("USDT"):
            '''
            Reference: https://bybit-exchange.github.io/docs/linear/#t-setleverage
            '''
            response = bt_ccxt_account_or_store.exchange.private_post_private_linear_position_set_leverage(dict(
                symbol=symbol_id,
                buy_leverage=to_leverage,
                sell_leverage=to_leverage,
            ))

            # INFO: Confirmation
            assert response and response['ret_code'] == "0"
        elif symbol_id.endswith("USD") or symbol_id.endswith("USDC"):
            # INFO: leverage should be intended for inverse perpetual
            '''
            Reference: https://bybit-exchange.github.io/docs/inverse/#t-setleverage
            '''
            response = bt_ccxt_account_or_store.exchange.v2_private_post_position_leverage_save(dict(
                symbol=symbol_id,
                leverage=to_leverage,
                leverage_only=True,
            ))
            # INFO: Confirmation
            assert response and response['ret_code'] == "0"
        else:
            raise NotImplementedError()

        frameinfo = inspect.getframeinfo(inspect.currentframe())
        msg = "{}: {} Line: {}: INFO: {}: Sync with {}: ".format(
            CCXT__MARKET_TYPES[market_type],
            frameinfo.function, frameinfo.lineno,
            symbol_id, str(bt_ccxt_account_or_store.exchange).lower(),
        )
        sub_msg = "Adjusted leverage from {} -> {}".format(
            from_leverage,
            to_leverage,
        )
        print(msg + sub_msg)
        pass
    elif market_type == CCXT__MARKET_TYPE__SPOT:
        raise NotImplementedError()
    else:
        raise NotImplementedError()
