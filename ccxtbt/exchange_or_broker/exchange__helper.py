import os
import pathlib

from ccxtbt.bt_ccxt__specifications import CCXT__MARKET_TYPES, CCXT__MARKET_TYPE__FUTURE, CCXT__MARKET_TYPE__SPOT
from ccxtbt.exchange_or_broker.binance.binance__exchange__specifications import BINANCE_EXCHANGE_ID
from ccxtbt.exchange_or_broker.bybit.bybit__exchange__helper import get_wallet_currency
from ccxtbt.exchange_or_broker.bybit.bybit__exchange__specifications import BYBIT_EXCHANGE_ID
from ccxtbt.exchange_or_broker.exchange__specifications import FUTURES__MAINNET__API_KEY_AND_SECRET_FILE_NAME, \
    FUTURES__TESTNET__API_KEY_AND_SECRET_FILE_NAME, MAINNET__API_KEY_AND_SECRET_FILE_NAME, \
    SPOT__MAINNET__API_KEY_AND_SECRET_FILE_NAME, SPOT__TESTNET__API_KEY_AND_SECRET_FILE_NAME, \
    TESTNET__API_KEY_AND_SECRET_FILE_NAME
from ccxtbt.utils import round_to_nearest_decimal_points


def get_minimum_instrument_quantity(price, instrument):
    minimum_instrument_quantity = instrument.qty_step
    if instrument.min_notional is not None:
        assert isinstance(instrument.min_notional, int) or isinstance(
            instrument.min_notional, float)
        minimum_instrument_quantity = instrument.min_notional / (price or 1.0)
        for _ in range(1000):
            minimum_instrument_quantity = \
                round_to_nearest_decimal_points(
                    minimum_instrument_quantity, instrument.qty_digits, instrument.qty_step)
            cost = price * minimum_instrument_quantity
            if cost > instrument.min_notional:
                break
            else:
                minimum_instrument_quantity += instrument.qty_step

        assert cost > instrument.min_notional, \
            "Cost: {:.{}f} must be greater than minimum notional: {:.{}f}!!!".format(
                cost, instrument.value_digits,
                instrument.min_notional, instrument.value_digits,
            )
        pass

    # Due to requirement to simulate partially filled order, the minimum quantity must be greater than the qty_step
    if minimum_instrument_quantity == instrument.qty_step:
        minimum_instrument_quantity += instrument.qty_step
    return minimum_instrument_quantity


def get_path_to_exchange(exchange_dropdown_value):
    file_path = pathlib.Path(__file__).parent.resolve()
    if exchange_dropdown_value == BINANCE_EXCHANGE_ID or exchange_dropdown_value == BYBIT_EXCHANGE_ID:
        path_to_exchange = os.path.join(file_path, exchange_dropdown_value)
    else:
        raise NotImplementedError()
    return path_to_exchange


def get_api_and_secret_file_path(exchange_dropdown_value, market_type, main_net_toggle_switch_value):
    file_path = pathlib.Path(__file__).parent.resolve()
    if exchange_dropdown_value == BINANCE_EXCHANGE_ID:
        if market_type == CCXT__MARKET_TYPE__SPOT:
            if main_net_toggle_switch_value:
                api_and_secret_file_name = SPOT__MAINNET__API_KEY_AND_SECRET_FILE_NAME
            else:
                api_and_secret_file_name = SPOT__TESTNET__API_KEY_AND_SECRET_FILE_NAME
        elif market_type == CCXT__MARKET_TYPE__FUTURE:
            if main_net_toggle_switch_value:
                api_and_secret_file_name = FUTURES__MAINNET__API_KEY_AND_SECRET_FILE_NAME
            else:
                api_and_secret_file_name = FUTURES__TESTNET__API_KEY_AND_SECRET_FILE_NAME
        else:
            raise NotImplementedError("{} market type is not yet enabled for {} exchange".format(
                CCXT__MARKET_TYPES[market_type],
                exchange_dropdown_value,
            ))
    elif exchange_dropdown_value == BYBIT_EXCHANGE_ID:
        if main_net_toggle_switch_value:
            api_and_secret_file_name = MAINNET__API_KEY_AND_SECRET_FILE_NAME
        else:
            api_and_secret_file_name = TESTNET__API_KEY_AND_SECRET_FILE_NAME
    else:
        raise NotImplementedError(
            "{} exchange is yet to be supported!!!".format(exchange_dropdown_value))
    api_key_and_secret_full_path = os.path.join(
        file_path, exchange_dropdown_value, api_and_secret_file_name)
    assert os.path.exists(api_key_and_secret_full_path), \
        "{} cannot be located!!!".format(api_key_and_secret_full_path)
    return api_key_and_secret_full_path


def get_symbol_id(params):
    exchange_dropdown_value = params['exchange_dropdown_value']
    symbol_name = params['symbol_name']

    assert isinstance(exchange_dropdown_value, str)
    assert isinstance(symbol_name, str)

    if exchange_dropdown_value == BINANCE_EXCHANGE_ID:
        # E.g. ETH/USDT -> ETHUSDT
        symbol_id = symbol_name.replace("/", "")
    elif exchange_dropdown_value == BYBIT_EXCHANGE_ID:
        # E.g. ETH/USDT:USDT -> ETHUSDT
        # We could rely on get_wallet_currency here using symbol_name as param with assumption symbol_name still
        # ends with the wallet_currency
        wallet_currency = get_wallet_currency(symbol_name)
        replaced_symbol_name = symbol_name.replace(
            ":{}".format(wallet_currency), "")
        symbol_id = replaced_symbol_name.replace("/", "")
    else:
        raise NotImplementedError(
            "{} exchange is yet to be supported!!!".format(exchange_dropdown_value))
    return symbol_id
