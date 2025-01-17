import datetime
import inspect
import requests

from pprint import pprint

from ccxtbt.bt_ccxt__specifications import CCXT__MARKET_TYPES, CCXT__MARKET_TYPE__SPOT, \
    CCXT__MARKET_TYPE__LINEAR_PERPETUAL_SWAP, \
    MIN_LEVERAGE, symbol_stationary__dict_template
from ccxtbt.exchange_or_broker.bybit.bybit__exchange__specifications import BYBIT__DERIVATIVES_V2_ENDPOINT, \
    BYBIT__SPOT__HTTP_ENDPOINT_URL, BYBIT__SPOT_V3_ENDPOINT, BYBIT__SYMBOLS_COMMAND, \
    BINANCE__USDT__DERIVATIVES__HTTP_ENDPOINT_URL
from ccxtbt.expansion.bt_ccxt_expansion__classes import Exchange_HTTP_Parser_Per_Symbol
from ccxtbt.utils import legality_check_not_none_obj, get_digits


class Bybit_Symbol_Info__HTTP_Parser(Exchange_HTTP_Parser_Per_Symbol):
    def __init__(self, params):
        super().__init__(params)

        # Obtain symbol step size
        if self.market_type == CCXT__MARKET_TYPE__SPOT:
            '''
            Reference: https://bybit-exchange.github.io/docs/spot/v3/#t-getsymbols
            '''
            self.exchange_info_url = "{}/{}/{}".format(
                BYBIT__SPOT__HTTP_ENDPOINT_URL,
                BYBIT__SPOT_V3_ENDPOINT,
                BYBIT__SYMBOLS_COMMAND,
            )
            '''
            Sample URL: https://api.bybit.com/spot/v3/public/symbols
            '''
            # Attributes according to symbol_stationary__dict_template
            self.min_leverage = MIN_LEVERAGE
            self.leverage_step = None
        elif self.market_type == CCXT__MARKET_TYPE__LINEAR_PERPETUAL_SWAP:
            '''
            Reference: https://bybit-exchange.github.io/docs/futuresV2/inverse/#t-querysymbol
            '''
            self.exchange_info_url = "{}/{}/{}".format(
                BINANCE__USDT__DERIVATIVES__HTTP_ENDPOINT_URL,
                BYBIT__DERIVATIVES_V2_ENDPOINT,
                BYBIT__SYMBOLS_COMMAND,
            )
            '''
            Sample URL: https://api.bybit.com/v2/public/symbols
            '''
            # Attributes according to symbol_stationary__dict_template
            self.min_leverage = MIN_LEVERAGE
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

        if self.market_type == CCXT__MARKET_TYPE__SPOT:
            ret_code_key = 'retCode'
        elif self.market_type == CCXT__MARKET_TYPE__LINEAR_PERPETUAL_SWAP:
            ret_code_key = 'ret_code'
        else:
            raise NotImplementedError("{} market type is not yet enabled for {} exchange".format(
                CCXT__MARKET_TYPES[self.market_type],
                self.exchange_dropdown_value,
            ))

        # Legality Check
        if symbol_exchange_info[ret_code_key] != 0:
            frameinfo = inspect.getframeinfo(inspect.currentframe())
            msg = "{}: {} Line: {}: {}: {}: ".format(
                self.market_type_name,
                frameinfo.function, frameinfo.lineno,
                self.symbol_id,
                datetime.datetime.utcnow().isoformat().replace("T", " ")[:-3],
            )
            print(msg)
            pprint(symbol_exchange_info)
            raise RuntimeError("{}: symbols not found in symbol_exchange_info!!!".format(
                inspect.currentframe()))

        if self.market_type == CCXT__MARKET_TYPE__SPOT:
            point_of_reference = symbol_exchange_info['result']['list']
        elif self.market_type == CCXT__MARKET_TYPE__LINEAR_PERPETUAL_SWAP:
            point_of_reference = symbol_exchange_info['result']
        else:
            raise NotImplementedError("{} market type is not yet enabled for {} exchange".format(
                CCXT__MARKET_TYPES[self.market_type],
                self.exchange_dropdown_value,
            ))

        symbol_dict = None
        for symbol_dict in point_of_reference:
            if symbol_dict['name'].upper() == self.symbol_id.upper():
                break
        legality_check_not_none_obj(symbol_dict, "symbol_dict")
        # Confirmation
        assert symbol_dict['name'].upper() == self.symbol_id.upper()

        if self.market_type == CCXT__MARKET_TYPE__SPOT:
            self.tick_size = float(symbol_dict['minPricePrecision'])
            self.price_digits = get_digits(self.tick_size)
            self.qty_step = float(symbol_dict['basePrecision'])
            self.qty_digits = get_digits(self.qty_step)
            self.min_qty = float(symbol_dict['minTradeQty'])
            self.max_qty = float(symbol_dict['maxTradeQty'])

            # Required by offline dataset
            # Spot account has no leverage and risk_limit
            self.leverage_step = None
            pass
        elif self.market_type == CCXT__MARKET_TYPE__LINEAR_PERPETUAL_SWAP:
            self.tick_size = float(
                symbol_dict['price_filter']['tick_size'])
            self.price_digits = get_digits(self.tick_size)
            self.qty_step = float(symbol_dict['lot_size_filter']['qty_step'])
            self.qty_digits = get_digits(self.qty_step)
            self.min_qty = \
                float(symbol_dict['lot_size_filter']['min_trading_qty'])
            self.max_qty = \
                float(symbol_dict['lot_size_filter']['max_trading_qty'])

            # Required by offline dataset
            self.leverage_step = float(
                symbol_dict['leverage_filter']['leverage_step'])
            pass
        else:
            raise NotImplementedError("{} market type is not yet enabled for {} exchange".format(
                CCXT__MARKET_TYPES[self.market_type],
                self.exchange_dropdown_value,
            ))

        # There is no min_notional imposed by Bybit at the moment
        self.min_notional = None
        self.value_digits = max(self.price_digits, self.qty_digits)
        pass
