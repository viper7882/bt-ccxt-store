import backtrader
import datetime
import decimal
import inspect
import json
import math
import os
import threading
import traceback
import unittest

from time import time as timer

from ccxtbt.bt_ccxt__specifications import MAX_LIVE_EXCHANGE_RETRIES, VALUE_DIGITS
from ccxtbt.bt_ccxt_account_or_store__classes import BT_CCXT_Account_or_Store
from ccxtbt.bt_ccxt_feed__classes import BT_CCXT_Feed
from ccxtbt.bt_ccxt_instrument__classes import BT_CCXT_Instrument
from ccxtbt.bt_ccxt_order__classes import BT_CCXT_Order
from ccxtbt.bybit_exchange__specifications import BYBIT_EXCHANGE_ID, BYBIT_OHLCV_LIMIT, BYBIT_COMMISSION_PRECISION
from ccxtbt.utils import get_time_diff, legality_check_not_none_obj, truncate

API_KEY_AND_SECRET_FILE_NAME = "testnet__api_key_and_secret.json"

class FAKE_EXCHANGE(object):
    def __init__(self, owner):
        self.owner = owner

    def add_commission_info(self, commission_info):
        self.commission_info = commission_info

    def get_commission_info(self):
        return self.commission_info

    def get_ohlcv_provider__account_or_store(self):
        return self.owner


class FAKE_COMMISSION_INFO(object):
    def __init__(self, params):
        # INFO: Un-serialize Params
        for key, val in params.items():
            setattr(self, key, val)

        if self.symbol_id == "ETHUSDT":
            self.symbol_tick_size = 0.05
            self.price_digits = get_digits(self.symbol_tick_size)
            self.qty_step = 0.01
            self.qty_digits = get_digits(self.qty_step)
        else:
            raise NotImplementedError()

    def get_value_size(self, size, price):
        '''
        Returns the value of size for given a price. For future-like objects it is fixed at size * margin.
        Value size a.k.a. Initial Margin in cryptocurrency.
        Cash will be deducted from (size > 0)/added to (size < 0) this amount.
        '''
        valuesize = 0.0
        if size:
            valuesize = truncate(abs(size) * price, VALUE_DIGITS)
        return valuesize

    def _get_commission_rate(self, size, price, pseudoexec):
        '''
        Calculates the commission of an operation at a given price
            pseudoexec: if True the operation has not yet been executed

            Percentage based commission fee.
            More details at https://www.backtrader.com/docu/user-defined-commissions/commission-schemes-subclassing/.
        '''
        assert isinstance(price, float)
        if ((pseudoexec == False) and (price <= 0.0)):
            raise ValueError("Price: {:.{}f} cannot be zero or negative! Size is {:.{}f}, pseudoexec: {}"
                             .format(price, self.price_digits, size, self.qty_digits, pseudoexec))

        # Order Cost: https://help.bybit.com/hc/en-us/articles/900000169703-Order-Cost-USDT-Contract-
        commission_in_coin_refer = truncate((abs(size) * self.commission) * price, BYBIT_COMMISSION_PRECISION)
        return commission_in_coin_refer

    def get_commission_rate(self, size, price):
        '''Calculates the commission of an operation at a given price
        '''
        return self._get_commission_rate(size, price, pseudoexec=True)

def get_commission_info(params):
    commission_info = FAKE_COMMISSION_INFO(params)
    return commission_info

def get_digits(step_size) -> int:
    if isinstance(step_size, float):
        # Credits: https://stackoverflow.com/questions/6189956/easy-way-of-finding-decimal-places
        number_of_digits = abs(decimal.Decimal(str(step_size)).as_tuple().exponent)
    elif isinstance(step_size, int):
        # Credits: https://stackoverflow.com/questions/2189800/how-to-find-length-of-digits-in-an-integer
        number_of_digits = int(math.log10(step_size)) + 1
    else:
        raise NotImplementedError("{}: Unsupported step_size type: {}".format(
            inspect.currentframe(),
            type(step_size),
        ))
    return number_of_digits


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

def handle_datafeed(datafeed, price):
    datafeed.start()
    datafeed.forward()
    datafeed._load()
    datafeed._tz = None
    datafeed.close[0] = price

def reverse_engineer__ccxt_order(bt_ccxt_order__dict):
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

    # TOOD: Bybit exchange-specific codes
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

    bt_ccxt_order__dict.update(dict(
        execution_type=execution_type,
        ordering_type=ordering_type,
        order_intent=order_intent,
    ))
    return bt_ccxt_order__dict

class Bybit__bt_ccxt_account_or_store__TestCases(unittest.TestCase):
    def setUp(self):
        try:
            self.bt_ccxt_account_or_store = None

            self.main_net_toggle_switch_value = False
            self.exchange_dropdown_value = BYBIT_EXCHANGE_ID
            self.isolated_toggle_switch_value = False

            # INFO: Bybit exchange-specific value
            account_type = "CONTRACT"

            initial__capital_reservation__value = 0.0
            is_ohlcv_provider = False
            enable_rate_limit = True
            account__thread__connectivity__lock = threading.Lock()
            self.symbol_id = "ETHUSDT"
            symbol_tick_size = 0.05
            price_digits = get_digits(symbol_tick_size)
            symbols_id = [self.symbol_id]

            assert os.path.exists(API_KEY_AND_SECRET_FILE_NAME)

            with open(API_KEY_AND_SECRET_FILE_NAME, "r") as file_to_read:
                json_data = json.load(file_to_read)
                api_key = json_data['key']
                api_secret = json_data['secret']
                account_alias__dropdown_value = json_data['account_alias__dropdown_value']

                exchange_specific_config = {
                    'apiKey': api_key,
                    'secret': api_secret,
                    'nonce': lambda: str(int(time.time() * 1000)),
                    'enableRateLimit': enable_rate_limit,
                    # 'rateLimit': 1100, # in ms
                    'account_alias': account_alias__dropdown_value,
                    'account_type': account_type,
                }

                account_or_store__dict = dict(
                    main_net_toggle_switch_value=self.main_net_toggle_switch_value,
                    config=exchange_specific_config,
                    initial__capital_reservation__value=initial__capital_reservation__value,
                    is_ohlcv_provider=is_ohlcv_provider,
                )

                wallet_currency = get_wallet_currency(self.symbol_id)
                # INFO: Live-specific Params
                account_or_store__dict.update(dict(
                    exchange_dropdown_value=self.exchange_dropdown_value,
                    wallet_currency=wallet_currency.upper(),
                    retries=MAX_LIVE_EXCHANGE_RETRIES,
                    symbols_id=symbols_id,
                    account__thread__connectivity__lock=account__thread__connectivity__lock,

                    # # TODO: Debug Use
                    # debug=True,
                ))

                self.bt_ccxt_account_or_store = BT_CCXT_Account_or_Store(**account_or_store__dict)

                commission = 0.006
                leverage_in_percent = 50.0
                get_commission_info__dict = dict(
                    symbol_id=self.symbol_id,
                    isolated_toggle_switch_value=self.isolated_toggle_switch_value,
                    leverage_in_percent=leverage_in_percent,
                    commission=commission,
                )
                commission_info = get_commission_info(params=get_commission_info__dict)
                fake_exchange = FAKE_EXCHANGE(owner=self.bt_ccxt_account_or_store)
                fake_exchange.add_commission_info(commission_info)
                self.bt_ccxt_account_or_store.set__parent(fake_exchange)

            legality_check_not_none_obj(self.bt_ccxt_account_or_store, "self.bt_ccxt_account_or_store")

            bt_ccxt_instrument__dict = dict(
                symbol_id=self.symbol_id,
            )
            instrument = BT_CCXT_Instrument(**bt_ccxt_instrument__dict)
            instrument.set__parent(self.bt_ccxt_account_or_store)
            self.bt_ccxt_account_or_store.add__instrument(instrument)

            # INFO: Create Long and Short datafeeds
            convert_to_heikin_ashi = False
            drop_newest = True
            historical = False
            granularity_compression = 1
            granularity_timeframe = backtrader.TimeFrame.Minutes

            # TODO: User to fill in the entry prices here
            self.primary_entry_price = 1193.55
            self.hedging_entry_price = 1195.4

            start_date = datetime.datetime.utcnow() - datetime.timedelta(minutes=granularity_compression + 1)

            datafeed__dict = dict(
                dataname=self.symbol_id,
                timeframe=granularity_timeframe,
                compression=granularity_compression,
                ohlcv_limit=BYBIT_OHLCV_LIMIT,

                convert_to_heikin_ashi=convert_to_heikin_ashi,
                symbol_tick_size=symbol_tick_size,
                price_digits=price_digits,

                fromdate=start_date,
                drop_newest=drop_newest,

                # INFO: If historical is True, the strategy will not enter into next()
                historical=historical,

                # # TODO: Debug Use
                # debug=True,
            )
            datafeed__dict.update(dict(
                name="Long",
            ))
            self.long_bb_data = BT_CCXT_Feed(**datafeed__dict)
            self.long_bb_data.set__parent(instrument)
            handle_datafeed(self.long_bb_data, price=self.hedging_entry_price)

            datafeed__dict.update(dict(
                name="Short",
            ))
            self.short_bb_data = BT_CCXT_Feed(**datafeed__dict)
            self.short_bb_data.set__parent(instrument)
            handle_datafeed(self.short_bb_data, price=self.primary_entry_price)

            primary_entry__ccxt_order = \
            {
                "info": {
                    "order_id": "41992e55-3ed8-4ea0-80f6-085a36e73d86",
                    "last_exec_price": "1193.55",
                    "cum_exec_qty": "1.03",
                    "cum_exec_value": "1229.3565",
                    "cum_exec_fee": "0.7376139",
                    "user_id": "660978",
                    "symbol": "ETHUSDT",
                    "side": "Sell",
                    "order_type": "Limit",
                    "time_in_force": "GoodTillCancel",
                    "order_status": "Filled",
                    "tp_trigger_by": "UNKNOWN",
                    "sl_trigger_by": "UNKNOWN",
                    "price": "1193.55",
                    "qty": "1.03",
                    "order_link_id": "",
                    "reduce_only": False,
                    "close_on_trigger": False,
                    "take_profit": "0",
                    "stop_loss": "0",
                    "created_time": "2022-12-28T11:55:13Z",
                    "updated_time": "2022-12-28T11:55:13Z"
                },
                "id": "41992e55-3ed8-4ea0-80f6-085a36e73d86",
                "clientOrderId": None,
                "timestamp": 1672228513000,
                "datetime": "2022-12-28T11:55:13.000Z",
                "lastTradeTimestamp": 1672228513000,
                "symbol": "ETH/USDT:USDT",
                "type": "limit",
                "timeInForce": "GTC",
                "postOnly": False,
                "side": "sell",
                "price": 1193.55,
                "stopPrice": None,
                "amount": 1.03,
                "cost": 1229.3565,
                "average": 1193.55,
                "filled": 1.03,
                "remaining": 0.0,
                "status": "closed",
                "fee": {
                    "cost": 0.7376139,
                    "currency": "USDT"
                },
                "trades": [],
                "fees": [
                    {
                        "cost": 0.7376139,
                        "currency": "USDT"
                    }
                ]
            }

            bt_ccxt_order__dict = dict(
                owner=self,
                position_type=backtrader.Position.SHORT_POSITION,
                datafeed=self.short_bb_data,
                ccxt_order=primary_entry__ccxt_order,
                symbol_id=self.symbol_id,
            )
            bt_ccxt_order__dict = reverse_engineer__ccxt_order(bt_ccxt_order__dict)
            self.primary_entry_order = BT_CCXT_Order(**bt_ccxt_order__dict)

            hedging_entry__ccxt_order = \
            {
                "info": {
                    "stop_order_id": "823f4c52-2be2-4fb2-9231-fd3281733e5f",
                    "trigger_price": "1195.4",
                    "base_price": "1193.55",
                    "trigger_by": "LastPrice",
                    "user_id": "660978",
                    "symbol": "ETHUSDT",
                    "side": "Buy",
                    "order_type": "Limit",
                    "time_in_force": "GoodTillCancel",
                    "order_status": "Filled",
                    "tp_trigger_by": "UNKNOWN",
                    "sl_trigger_by": "UNKNOWN",
                    "price": "1195.4",
                    "qty": "1.78",
                    "order_link_id": "",
                    "reduce_only": False,
                    "close_on_trigger": False,
                    "take_profit": "0",
                    "stop_loss": "0",
                    "created_time": "2022-12-28T11:55:14Z",
                    "updated_time": "2022-12-28T14:50:47Z"
                },
                "id": "823f4c52-2be2-4fb2-9231-fd3281733e5f",
                "clientOrderId": None,
                "timestamp": 1672228514000,
                "datetime": "2022-12-28T11:55:14.000Z",
                "lastTradeTimestamp": 1672239047000,
                "symbol": "ETH/USDT:USDT",
                "type": "limit",
                "timeInForce": "GTC",
                "postOnly": False,
                "side": "buy",
                "price": 1195.4,
                "stopPrice": "1195.4",
                "amount": 1.78,
                "cost": None,
                "average": None,
                "filled": None,
                "remaining": None,
                "status": "closed",
                "fee": None,
                "trades": [],
                "fees": []
            }

            bt_ccxt_order__dict = dict(
                owner=self,
                position_type=backtrader.Position.LONG_POSITION,
                datafeed=self.long_bb_data,
                ccxt_order=hedging_entry__ccxt_order,
                symbol_id=self.symbol_id,
            )
            bt_ccxt_order__dict = reverse_engineer__ccxt_order(bt_ccxt_order__dict)
            self.hedging_entry_order = BT_CCXT_Order(**bt_ccxt_order__dict)

        except Exception:
            traceback.print_exc()
    @unittest.skip("Only run if required")
    def test_01__fetch__primary_order(self):
        start = timer()
        try:
            primary_entry_order_id = "41992e55-3ed8-4ea0-80f6-085a36e73d86"
            ccxt_order = \
                self.bt_ccxt_account_or_store.fetch_ccxt_order(self.symbol_id,
                                                               order_id=primary_entry_order_id,
                                                               stop_order_id=None)

            frameinfo = inspect.getframeinfo(inspect.currentframe())
            msg = "{} Line: {}: INFO: ".format(
                frameinfo.function, frameinfo.lineno,
            )
            sub_msg = "ccxt_order:"
            print(msg + sub_msg)
            print(json.dumps(ccxt_order, indent=self.bt_ccxt_account_or_store.indent))

            pass
        except Exception:
            traceback.print_exc()

        _, minutes, seconds = get_time_diff(start)
        frameinfo = inspect.getframeinfo(inspect.currentframe())
        print("{} Line: {}: Took {}m:{:.2f}s".format(frameinfo.function, frameinfo.lineno,
                                                     int(minutes), seconds))

    @unittest.skip("Only run if required")
    def test_02__fetch__hedging_order(self):
        start = timer()
        try:
            hedging_entry_order_id = "823f4c52-2be2-4fb2-9231-fd3281733e5f"
            ccxt_order = \
                self.bt_ccxt_account_or_store.fetch_ccxt_order(self.symbol_id,
                                                               order_id=None,
                                                               stop_order_id=hedging_entry_order_id)

            frameinfo = inspect.getframeinfo(inspect.currentframe())
            msg = "{} Line: {}: INFO: ".format(
                frameinfo.function, frameinfo.lineno,
            )
            sub_msg = "ccxt_order:"
            print(msg + sub_msg)
            print(json.dumps(ccxt_order, indent=self.bt_ccxt_account_or_store.indent))

            pass
        except Exception:
            traceback.print_exc()

        _, minutes, seconds = get_time_diff(start)
        frameinfo = inspect.getframeinfo(inspect.currentframe())
        print("{} Line: {}: Took {}m:{:.2f}s".format(frameinfo.function, frameinfo.lineno,
                                                     int(minutes), seconds))

    @unittest.skip("Ready for regression")
    def test_10__execute__primary_order(self):
        start = timer()
        try:
            current_price = self.primary_entry_price
            self.bt_ccxt_account_or_store.execute(self.primary_entry_order, current_price)
            pass
        except Exception:
            traceback.print_exc()

        _, minutes, seconds = get_time_diff(start)
        frameinfo = inspect.getframeinfo(inspect.currentframe())
        print("{} Line: {}: Took {}m:{:.2f}s".format(frameinfo.function, frameinfo.lineno,
                                                     int(minutes), seconds))

    # @unittest.skip("Ready for regression")
    def test_11__execute__primary_order_and_then_hedging_order(self):
        start = timer()
        try:
            current_price = self.hedging_entry_price
            self.bt_ccxt_account_or_store.execute(self.primary_entry_order, current_price)
            self.bt_ccxt_account_or_store.execute(self.hedging_entry_order, current_price)
            pass
        except Exception:
            traceback.print_exc()

        _, minutes, seconds = get_time_diff(start)
        frameinfo = inspect.getframeinfo(inspect.currentframe())
        print("{} Line: {}: Took {}m:{:.2f}s".format(frameinfo.function, frameinfo.lineno,
                                                     int(minutes), seconds))


if __name__ == '__main__':
    unittest.main()
