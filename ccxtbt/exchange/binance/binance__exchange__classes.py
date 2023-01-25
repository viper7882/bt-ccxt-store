import datetime
import inspect
import requests

from pprint import pprint

from ccxtbt.bt_ccxt_expansion__classes import Exchange_HTTP_Parser_Per_Symbol
from ccxtbt.bt_ccxt__specifications import CCXT__MARKET_TYPE__SPOT, CCXT__MARKET_TYPE__FUTURES, MIN_LEVERAGE, \
    STANDARD_ATTRIBUTES, symbol_stationary__dict_template
from ccxtbt.exchange.binance.binance__exchange__specifications import BINANCE__SPOT__V3__HTTP_ENDPOINT_URL, \
    BINANCE__EXCHANGE_INFO_ENDPOINT, BINANCE__SYMBOL_COMMAND, BINANCE__FUTURES__V1__HTTP_ENDPOINT_URL
from ccxtbt.utils import legality_check_not_none_obj, get_digits


class Binance_Symbol_Info__HTTP_Parser(Exchange_HTTP_Parser_Per_Symbol):
    def __init__(self, params):
        super().__init__(params)

        # INFO: Obtain symbol step size
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
        elif self.market_type == CCXT__MARKET_TYPE__FUTURES:
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
            raise NotImplementedError()

        # Variables
        for key in symbol_stationary__dict_template.keys():
            if hasattr(self, key) == False:
                setattr(self, key, None)

        for standard_attribute in STANDARD_ATTRIBUTES:
            if hasattr(self, standard_attribute) == False:
                setattr(self, standard_attribute, None)

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

        self.symbol_tick_size = float(symbol_dict['filters'][0]['tickSize'])
        self.price_digits = get_digits(self.symbol_tick_size)
        self.qty_step = float(symbol_dict['filters'][1]['stepSize'])
        self.qty_digits = get_digits(self.qty_step)
        self.lot_size_min_qty = float(symbol_dict['filters'][1]['minQty'])
        self.lot_size_max_qty = float(symbol_dict['filters'][1]['maxQty'])

        # Attributes according to symbol_stationary__dict_template
        # Alias
        self.tick_size = self.symbol_tick_size
        self.lot_size_qty_step = self.qty_step
        pass