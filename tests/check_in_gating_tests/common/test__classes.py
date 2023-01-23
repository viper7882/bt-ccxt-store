from ccxtbt.bt_ccxt__specifications import VALUE_DIGITS
from ccxtbt.bybit_exchange__specifications import BYBIT_COMMISSION_PRECISION
from ccxtbt.utils import get_digits, truncate


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
        commission_in_coin_refer = truncate(
            (abs(size) * self.commission) * price, BYBIT_COMMISSION_PRECISION)
        return commission_in_coin_refer

    def get_commission_rate(self, size, price):
        '''Calculates the commission of an operation at a given price
        '''
        return self._get_commission_rate(size, price, pseudoexec=True)
