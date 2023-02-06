import datetime
import inspect
import requests

from pprint import pprint

from ccxtbt.bt_ccxt__specifications import CCXT__MARKET_TYPES, CCXT__MARKET_TYPE__SPOT, CCXT__MARKET_TYPE__FUTURE, \
    MIN_LEVERAGE, \
    symbol_stationary__dict_template
from ccxtbt.exchange_or_broker.binance.binance__exchange__specifications import BINANCE__SPOT__V3__HTTP_ENDPOINT_URL, \
    BINANCE__EXCHANGE_INFO_ENDPOINT, BINANCE__SYMBOL_COMMAND, BINANCE__FUTURES__V1__HTTP_ENDPOINT_URL
from ccxtbt.expansion.bt_ccxt_expansion__classes import Exchange_HTTP_Parser_Per_Symbol
from ccxtbt.utils import legality_check_not_none_obj, get_digits


class Binance_Symbol_Info__HTTP_Parser(Exchange_HTTP_Parser_Per_Symbol):
    def __init__(self, params):
        super().__init__(params)

        # Obtain symbol step size
        if self.market_type == CCXT__MARKET_TYPE__SPOT:
            '''
            Reference: https://binance-docs.github.io/apidocs/spot/en/#exchange-information
            '''
            self.exchange_info_url = "{}/{}?{}={}".format(
                BINANCE__SPOT__V3__HTTP_ENDPOINT_URL,
                BINANCE__EXCHANGE_INFO_ENDPOINT,
                BINANCE__SYMBOL_COMMAND,
                self.symbol_id.upper(),
            )
            '''
            Sample URL: https://api.binance.com/api/v3/exchangeInfo?symbol=ETHUSDT
            '''
            # Attributes according to symbol_stationary__dict_template
            self.min_leverage = int(MIN_LEVERAGE)
            self.leverage_step = None
        elif self.market_type == CCXT__MARKET_TYPE__FUTURE:
            '''
            Reference: https://binance-docs.github.io/apidocs/futures/en/#exchange-information
            '''
            self.exchange_info_url = "{}/{}?{}={}".format(
                BINANCE__FUTURES__V1__HTTP_ENDPOINT_URL,
                BINANCE__EXCHANGE_INFO_ENDPOINT,
                BINANCE__SYMBOL_COMMAND,
                self.symbol_id.upper(),
            )
            '''
            Sample URL: https://fapi.binance.com/fapi/v1/exchangeInfo?symbol=ETHUSDT
            '''
            # Attributes according to symbol_stationary__dict_template
            self.min_leverage = int(MIN_LEVERAGE)
            self.leverage_step = 1
        else:
            raise NotImplementedError("{} market type is not yet enabled for {} exchange".format(
                CCXT__MARKET_TYPES[self.market_type],
                self.exchange_dropdown_value,
            ))

        # Variables
        for key in symbol_stationary__dict_template.keys():
            if hasattr(self, key) == False:
                setattr(self, key, None)

    def run(self):
        symbol_exchange_info = requests.get(self.exchange_info_url).json()

        # Legality Check
        if 'symbols' not in symbol_exchange_info.keys():
            frameinfo = inspect.getframeinfo(inspect.currentframe())
            msg = "{}: {} Line: {}: {}: {}: ".format(
                self.market_type_name,
                frameinfo.function, frameinfo.lineno,
                self.symbol_id,
                datetime.datetime.utcnow().isoformat().replace("T", " ")[:-3],
            )
            print(msg)
            pprint(symbol_exchange_info)
            raise RuntimeError("{}: symbols not found in symbol_exchange_info.keys()!!!".format(
                inspect.currentframe()))

        symbol_dict = None
        for symbol_dict in symbol_exchange_info['symbols']:
            if symbol_dict['symbol'].upper() == self.symbol_id.upper():
                break
        legality_check_not_none_obj(symbol_dict, "symbol_dict")
        assert symbol_dict['symbol'].upper() == self.symbol_id.upper()

        self.tick_size = float(symbol_dict['filters'][0]['tickSize'])
        self.price_digits = get_digits(self.tick_size)
        self.qty_step = float(symbol_dict['filters'][1]['stepSize'])
        self.qty_digits = get_digits(self.qty_step)
        self.min_qty = float(symbol_dict['filters'][1]['minQty'])
        self.max_qty = float(symbol_dict['filters'][1]['maxQty'])
        self.value_digits = int(symbol_dict['baseAssetPrecision'])

        if self.market_type == CCXT__MARKET_TYPE__SPOT:
            self.min_notional = float(symbol_dict['filters'][2]['minNotional'])

            # Required by offline dataset
            # Spot account has no leverage
            self.leverage_step = None
            pass
        elif self.market_type == CCXT__MARKET_TYPE__FUTURE:
            # If min_notional is not doubled up (i.e. same value as Spot), exchange will error out
            self.min_notional = float(
                symbol_dict['filters'][5]['notional']) * 2

            # Required by offline dataset
            self.leverage_step = 1
            pass
        else:
            raise NotImplementedError("{} market type is not yet enabled for {} exchange".format(
                CCXT__MARKET_TYPES[self.market_type],
                self.exchange_dropdown_value,
            ))
        pass
