from ccxtbt.bt_ccxt__specifications import VALUE_DIGITS
from ccxtbt.exchange.bybit.bybit__exchange__specifications import BYBIT_COMMISSION_PRECISION
from ccxtbt.utils import get_digits, truncate


class FAKE_EXCHANGE(object):
    def __init__(self, owner):
        self.owner = owner
        self.accounts_or_stores = []

    def get_ohlcv_provider__account_or_store(self):
        return self.owner

    def add__account_or_store(self, account_or_store):
        if account_or_store not in self.accounts_or_stores:
            self.accounts_or_stores.append(account_or_store)


class FAKE_COMMISSION_INFO(object):
    def __init__(self, params):
        # INFO: Un-serialize Params
        for key, val in params.items():
            setattr(self, key, val)

        # Alias
        STANDARD_ATTRIBUTES = ['tick_size',
                               'price_digits', 'qty_step', 'qty_digits']
        for standard_attribute in STANDARD_ATTRIBUTES:
            setattr(self, standard_attribute, getattr(
                self.instrument, standard_attribute))

    def get_value_size(self, size, price):
        '''
        Returns the value of size for given a price. For future-like objects it is fixed at size * margin.
        Value size a.k.a. Initial Margin in cryptocurrency.
        Cash will be deducted from (size > 0)/added to (size < 0) this amount.
        '''
        valuesize = 0.0
        if size:
            valuesize = truncate(
                abs(size) * price, self.instrument.value_digits)
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
                             .format(price, self.instrument.price_digits, size, self.instrument.qty_digits, pseudoexec))

        # Order Cost: https://help.bybit.com/hc/en-us/articles/900000169703-Order-Cost-USDT-Contract-
        commission_in_coin_refer = truncate(
            (abs(size) * self.commission) * price, BYBIT_COMMISSION_PRECISION)
        return commission_in_coin_refer

    def get_commission_rate(self, size, price):
        '''Calculates the commission of an operation at a given price
        '''
        return self._get_commission_rate(size, price, pseudoexec=True)

    def profit_and_loss(self, size, price, new_price):
        '''
        Return actual profit and loss a position has

            size (int): amount to update the position size
                size < 0: A sell operation has taken place
                size > 0: A buy operation has taken place
        '''
        profit_and_loss_amount = 0.0
        if size:
            if new_price and price and new_price != price:
                # Reference: https://help.bybit.com/hc/en-us/articles/900000630066-P-L-calculations-USDT-Contract-
                # INFO: Unrealized P&L
                if size > 0:
                    # Buy operation
                    profit_and_loss_amount = truncate(
                        size * (new_price - price), self.instrument.value_digits)
                else:
                    # Sell operation
                    profit_and_loss_amount = truncate(
                        abs(size) * (price - new_price), self.instrument.value_digits)
        return profit_and_loss_amount
