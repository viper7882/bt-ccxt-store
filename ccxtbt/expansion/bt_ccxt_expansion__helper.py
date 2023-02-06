import backtrader
import json
import time

from ccxtbt.bt_ccxt__specifications import CCXT__MARKET_TYPES
from ccxtbt.account_or_store.account_or_store__classes import BT_CCXT_Account_or_Store
from ccxtbt.cerebro.cerebro__classes import Enhanced_Cerebro
from ccxtbt.cerebro.cerebro__specifications import LIVE_CEREBRO__DICT
from ccxtbt.datafeed.datafeed__classes import BT_CCXT_Feed
from ccxtbt.exchange_or_broker.binance.binance__exchange__helper import get_binance_commission_rate
from ccxtbt.exchange_or_broker.binance.binance__exchange__specifications import BINANCE_EXCHANGE_ID, \
    BINANCE_OHLCV_LIMIT, BINANCE__PARTIALLY_FILLED__ORDER_STATUS__VALUE
from ccxtbt.exchange_or_broker.bybit.bybit__exchange__helper import get_bybit_commission_rate
from ccxtbt.exchange_or_broker.bybit.bybit__exchange__specifications import BYBIT_EXCHANGE_ID, \
    BYBIT_OHLCV_LIMIT, BYBIT__PARTIALLY_FILLED__ORDER_STATUS__VALUE
from ccxtbt.exchange_or_broker.exchange__classes import BT_CCXT_Exchange
from ccxtbt.exchange_or_broker.exchange__helper import get_api_and_secret_file_path
from ccxtbt.exchange_or_broker.exchange__specifications import CCXT_COMMON_MAPPING_VALUES, MAX_LIVE_EXCHANGE_RETRIES, \
    OPEN_VALUE, CANCELED_VALUE, CLOSED_VALUE, EXPIRED_VALUE, REJECTED_VALUE
from ccxtbt.expansion.bt_ccxt_expansion__classes import FAKE_COMMISSION_INFO, FAKE_EXCHANGE
from ccxtbt.instrument.instrument__classes import BT_CCXT_Instrument
from ccxtbt.order.order__helper import get_filtered_orders
from ccxtbt.order.order__specifications import CANCELED_ORDER, CLOSED_ORDER, EXPIRED_ORDER, OPENED_ORDER, \
    PARTIALLY_FILLED_ORDER, REJECTED_ORDER, CCXT_ORDER_TYPES, CCXT_STATUS_KEY
from ccxtbt.utils import legality_check_not_none_obj


def construct_standalone_exchange(params) -> type(BT_CCXT_Exchange):
    # Un-serialize Params
    exchange_dropdown_value = params['exchange_dropdown_value']

    # Optional Params
    ut_disable_singleton = params.get('ut_disable_singleton', None)

    if ut_disable_singleton:
        '''
        Resetting the singleton to None here so that we could sweep multiple exchanges.
        '''
        BT_CCXT_Exchange._singleton = None

    order_types = {
        backtrader.Order.Market: "market",
        backtrader.Order.Limit: "limit",
    }
    if exchange_dropdown_value == BINANCE_EXCHANGE_ID:
        order_types.update(
            {
                backtrader.Order.StopMarket: "stop_market",
                backtrader.Order.StopLimit: "stop",
            }
        )
    ccxt__order_types__broker_mapping = dict(
        order_types=order_types,
    )

    # CCXT broker_or_exchange mapping consumed by BT-CCXT broker_or_exchange
    # Documentation: https://docs.ccxt.com/en/latest/manual.html#order-structure
    # Common mapping across exchanges
    mappings = {
        CCXT_ORDER_TYPES[OPENED_ORDER]: {
            'key': CCXT_STATUS_KEY,
            'value': CCXT_COMMON_MAPPING_VALUES[OPEN_VALUE],
        },
        CCXT_ORDER_TYPES[CLOSED_ORDER]: {
            'key': CCXT_STATUS_KEY,
            'value': CCXT_COMMON_MAPPING_VALUES[CLOSED_VALUE],
        },
        CCXT_ORDER_TYPES[CANCELED_ORDER]: {
            'key': CCXT_STATUS_KEY,
            'value': CCXT_COMMON_MAPPING_VALUES[CANCELED_VALUE],
        },
        CCXT_ORDER_TYPES[EXPIRED_ORDER]: {
            'key': CCXT_STATUS_KEY,
            'value': CCXT_COMMON_MAPPING_VALUES[EXPIRED_VALUE],
        },
        CCXT_ORDER_TYPES[REJECTED_ORDER]: {
            'key': CCXT_STATUS_KEY,
            'value': CCXT_COMMON_MAPPING_VALUES[REJECTED_VALUE],
        },
    }

    # Exchange specific entries below
    if exchange_dropdown_value == BINANCE_EXCHANGE_ID:
        '''
        Reference: https://binance-docs.github.io/apidocs/futures/en/#public-endpoints-info
        '''
        mappings.update({
            CCXT_ORDER_TYPES[PARTIALLY_FILLED_ORDER]: {
                'key': CCXT_STATUS_KEY,
                'value': BINANCE__PARTIALLY_FILLED__ORDER_STATUS__VALUE,
            },
        })
    elif exchange_dropdown_value == BYBIT_EXCHANGE_ID:
        '''
        Reference: https://bybit-exchange.github.io/docs/futuresV2/linear/#order-status-order_status-stop_order_status
        '''
        mappings.update({
            CCXT_ORDER_TYPES[PARTIALLY_FILLED_ORDER]: {
                'key': CCXT_STATUS_KEY,
                'value': BYBIT__PARTIALLY_FILLED__ORDER_STATUS__VALUE,
            },
        })
    else:
        # Do nothing
        pass

    ccxt__broker_mapping = dict(
        mappings=mappings,
    )
    ccxt__broker_mapping.update(ccxt__order_types__broker_mapping)
    bt_ccxt_exchange = BT_CCXT_Exchange(broker_mapping=ccxt__broker_mapping)
    return bt_ccxt_exchange


def construct_standalone_cerebro(params) -> type(Enhanced_Cerebro):
    # Un-serialize Params
    bt_ccxt_exchange = params['bt_ccxt_exchange']

    # Legality Check
    assert type(bt_ccxt_exchange).__name__ == BT_CCXT_Exchange.__name__

    # Reference: https://www.backtrader.com/docu/mixing-timeframes/indicators-mixing-timeframes/
    # data feeds from different timeframes can be mixed in indicators if runonce=False
    cerebro = Enhanced_Cerebro(**LIVE_CEREBRO__DICT)
    cerebro.set_broker_or_exchange(bt_ccxt_exchange)
    return cerebro


def construct_standalone_account_or_store(params) -> tuple:
    # Un-serialize Params
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
    isolated_toggle_switch_value = params['isolated_toggle_switch_value']

    # Optional Params
    account_type = params.get('account_type', None)
    bt_ccxt_exchange = params.get('bt_ccxt_exchange', None)
    ut_keep_original_ccxt_order = params.get(
        'ut_keep_original_ccxt_order', None)
    ut_modify_open_to_ccxt_status = params.get(
        'ut_modify_open_to_ccxt_status', None)

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
            isolated_toggle_switch_value=isolated_toggle_switch_value,
        )

        # Live-specific Params
        account_or_store__dict.update(dict(
            exchange_dropdown_value=exchange_dropdown_value,
            wallet_currency=wallet_currency.upper(),
            retries=MAX_LIVE_EXCHANGE_RETRIES,
            symbols_id=symbols_id,
            account__thread__connectivity__lock=account__thread__connectivity__lock,

            # Optional Params
            ut_keep_original_ccxt_order=ut_keep_original_ccxt_order,
            ut_modify_open_to_ccxt_status=ut_modify_open_to_ccxt_status,
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

    ret_value = (bt_ccxt_account_or_store, exchange_specific_config, )
    return ret_value


def construct_standalone_instrument(params) -> type(BT_CCXT_Instrument):
    # Un-serialize Params
    bt_ccxt_account_or_store = params['bt_ccxt_account_or_store']
    market_type = params['market_type']
    symbol_id = params['symbol_id']

    # Legality Check
    assert type(
        bt_ccxt_account_or_store).__name__ == BT_CCXT_Account_or_Store.__name__, \
        "Expected {} but Observed: {}".format(BT_CCXT_Account_or_Store.__name__, type(
            bt_ccxt_account_or_store).__name__)

    bt_ccxt_instrument__dict = dict(
        symbol_id=symbol_id,
    )
    instrument = BT_CCXT_Instrument(**bt_ccxt_instrument__dict)

    # sync_symbol_positions here
    instrument.set__parent(bt_ccxt_account_or_store)

    commission_rate__dict = dict(
        bt_ccxt_account_or_store=bt_ccxt_account_or_store,
        market_type=market_type,
        symbol_id=symbol_id,
    )
    if bt_ccxt_account_or_store.exchange_dropdown_value == BINANCE_EXCHANGE_ID:
        commission = get_binance_commission_rate(
            params=commission_rate__dict)
    elif bt_ccxt_account_or_store.exchange_dropdown_value == BYBIT_EXCHANGE_ID:
        commission = get_bybit_commission_rate(
            params=commission_rate__dict)
    else:
        raise NotImplementedError(
            "{} exchange is yet to be supported!!!".format(bt_ccxt_account_or_store.exchange_dropdown_value))

    get_commission_info__dict = dict(
        symbol_id=symbol_id,
        isolated_toggle_switch_value=bt_ccxt_account_or_store.isolated_toggle_switch_value,
        leverage_in_percent=bt_ccxt_account_or_store.leverage_in_percent,
        commission=commission,
        instrument=instrument,
    )
    commission_info = FAKE_COMMISSION_INFO(params=get_commission_info__dict)

    instrument.add_commission_info(commission_info)

    # notify here
    bt_ccxt_account_or_store.add__instrument(instrument)
    return instrument


def construct_dual_position_datafeeds(params) -> tuple:
    # Un-serialize Params
    exchange_dropdown_value = params['exchange_dropdown_value']
    instrument = params['instrument']
    bt_ccxt_feed__dict = params['bt_ccxt_feed__dict']
    wallet_currency = params['wallet_currency']

    # Validate assumption made
    assert isinstance(bt_ccxt_feed__dict, dict)

    if exchange_dropdown_value == BINANCE_EXCHANGE_ID:
        ohlcv_limit = BINANCE_OHLCV_LIMIT
    elif exchange_dropdown_value == BYBIT_EXCHANGE_ID:
        ohlcv_limit = BYBIT_OHLCV_LIMIT
    else:
        raise NotImplementedError(
            "{} exchange is yet to be supported!!!".format(exchange_dropdown_value))

    # Long datafeed
    dual_positions__bt_ccxt_feed__dict = dict(
        exchange=exchange_dropdown_value,
        name=backtrader.Position.Position_Types[backtrader.Position.LONG_POSITION],
        dataname=instrument.symbol_id,
        ohlcv_limit=ohlcv_limit,
        currency=wallet_currency,
        max_retries=MAX_LIVE_EXCHANGE_RETRIES,
    )
    dual_positions__bt_ccxt_feed__dict.update(bt_ccxt_feed__dict)
    long_bb_data = BT_CCXT_Feed(**dual_positions__bt_ccxt_feed__dict)
    long_bb_data.set__parent(instrument)

    # Short datafeed
    dual_positions__bt_ccxt_feed__dict = dict(
        exchange=exchange_dropdown_value,
        name=backtrader.Position.Position_Types[backtrader.Position.SHORT_POSITION],
        dataname=instrument.symbol_id,
        ohlcv_limit=ohlcv_limit,
        currency=wallet_currency,
        max_retries=MAX_LIVE_EXCHANGE_RETRIES,
    )
    dual_positions__bt_ccxt_feed__dict.update(bt_ccxt_feed__dict)
    short_bb_data = BT_CCXT_Feed(**dual_positions__bt_ccxt_feed__dict)
    short_bb_data.set__parent(instrument)

    ret_value = (long_bb_data, short_bb_data, )
    return ret_value


def query__entry_or_exit_order(params):
    # Un-serialize Params
    bt_ccxt_account_or_store = params['bt_ccxt_account_or_store']
    instrument = params['instrument']
    filter_order__dict = params['filter_order__dict']

    fetch_opened_orders__dict = dict(
        # CCXT requires the market type name to be specified correctly
        type=CCXT__MARKET_TYPES[bt_ccxt_account_or_store.market_type],

    )
    opened_bt_ccxt_orders = \
        instrument.fetch_opened_orders(since=None,
                                       limit=None,
                                       params=fetch_opened_orders__dict)

    if bt_ccxt_account_or_store.exchange_dropdown_value == BYBIT_EXCHANGE_ID:
        fetch_opened_orders__dict.update(dict(
            stop=True,
        ))
        opened_bt_ccxt_orders += \
            instrument.fetch_opened_orders(since=None,
                                           limit=None,
                                           params=fetch_opened_orders__dict)

    get_filtered_orders__dict = dict(
        filter_order__dict=filter_order__dict,
        orders=opened_bt_ccxt_orders,
    )
    filtered_bt_ccxt_orders = get_filtered_orders(
        params=get_filtered_orders__dict)
    return filtered_bt_ccxt_orders
