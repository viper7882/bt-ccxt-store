import backtrader
import datetime
import inspect

from abc import ABC, abstractmethod

from ccxtbt.bt_ccxt__specifications import CCXT__MARKET_TYPES


class Wecoz(object):
    def __init__(self, params):
        # INFO: Un-serialize Params
        for key, val in params.items():
            setattr(self, key, val)

    def check_required_attributes(self, must_have_attributes):
        assert isinstance(must_have_attributes, tuple)
        for must_have_attribute in must_have_attributes:
            if hasattr(self, must_have_attribute) == False:
                msg = "\'{}\' attribute must be defined!!!".format(
                    must_have_attribute)
                raise NotImplementedError(msg)


class Exchange_HTTP_Parser(Wecoz, ABC):
    def __init__(self, params) -> None:
        super().__init__(params)

        # INFO: Ensure creator initialize the following attributes
        must_have_attributes = ('market_type', )
        self.check_required_attributes(must_have_attributes)

        # Legality Check
        if self.market_type not in range(len(CCXT__MARKET_TYPES)):
            raise RuntimeError("{}: {} market_type must be one of {}!!!".format(
                inspect.currentframe(),
                self.market_type, range(len(CCXT__MARKET_TYPES))))

        self.market_type_name = CCXT__MARKET_TYPES[self.market_type]


class Exchange_HTTP_Parser_Per_Symbol(Exchange_HTTP_Parser, ABC):
    def __init__(self, params) -> None:
        super().__init__(params)

        # INFO: Ensure creator initialize the following attributes
        must_have_attributes = ('symbol_id', )
        self.check_required_attributes(must_have_attributes)

        # Legality Check
        assert isinstance(self.symbol_id, str)

    @abstractmethod
    def run(self):
        print("ERROR: This abstract method is not implemented!!!")


class Enhanced_Position(backtrader.Position):
    def __init__(self, size=0.0, price=0.0, date_and_time=None):
        super(Enhanced_Position, self).__init__(
            size=size, price=price, date_and_time=datetime)

        # Enhanced attributes
        # self.position_value = 0.0
        # self.position_take_profit = 0.0
        # self.position_stop_loss = 0.0
        # self.position_trailing_stop = 0.0
        # self.position_margin = 0.0
        # self.unrealized_pnl = 0.0
        # self.unrealized_pnl_in_percent = 0.0
        # self.realised_pnl = 0.0
        # self.leverage = 1.0

    def __repr__(self):
        return str(self)

    def __str__(self):
        items = list()
        items.append('--- Position Begin ---')
        # items.append('- Leverage: {}'.format(self.leverage))
        items.append('- Size: {}'.format(self.size))
        items.append('- Entry Price: {}'.format(self.price))
        # items.append('- Value: {}'.format(self.position_value))
        # items.append('- TP: {}'.format(self.position_take_profit))
        # items.append('- SL: {}'.format(self.position_stop_loss))
        # items.append('- TS: {}'.format(self.position_trailing_stop))
        # items.append('- Margin: {}'.format(self.position_margin))
        # items.append('- Unrealized PNL: {}'.format(self.unrealized_pnl))
        # items.append('- Unrealized PNL in %: {}'.format(self.unrealized_pnl_in_percent))
        # items.append('- Realized PNL: {}'.format(self.unrealized_pnl))
        items.append('- Opened: {}'.format(self.upopened))
        items.append('- Closed: {}'.format(self.upclosed))
        items.append('--- Position End ---')
        ret_value = str('\n'.join(items))
        return ret_value

    def clone(self):
        return Enhanced_Position(size=self.size, price=self.price, date_and_time=self.datetime)

    def pseudoupdate(self, size, price):
        return Enhanced_Position(self.size, self.price, self.datetime).update(size, price)

    def update(self, size, price, dt=datetime.datetime.utcnow()):
        '''
        Updates the current position and returns the updated size, price and
        units used to open/close a position

        Args:
            size (int): amount to update the position size
                size < 0: A sell operation has taken place
                size > 0: A buy operation has taken place

            price (float):
                Must always be positive to ensure consistency

        Returns:
            A tuple (non-named) contaning
               size - new position size
                   Simply the sum of the existing size plus the "size" argument
               price - new position price
                   If a position is increased the new average price will be
                   returned
                   If a position is reduced the price of the remaining size
                   does not change
                   If a position is closed the price is nullified
                   If a position is reversed the price is the price given as
                   argument
               opened - amount of contracts from argument "size" that were used
                   to open/increase a position.
                   A position can be opened from 0 or can be a reversal.
                   If a reversal is performed then opened is less than "size",
                   because part of "size" will have been used to close the
                   existing position
               closed - amount of units from arguments "size" that were used to
                   close/reduce a position

            Both opened and closed carry the same sign as the "size" argument
            because they refer to a part of the "size" argument
        '''
        self.price_orig = self.price
        oldsize = self.size
        self.size += size

        if self.size != 0.0:
            self.datetime = dt  # record datetime update (datetime.datetime)
        else:
            self.datetime = None

        if self.size == 0.0:
            # Update closed existing position
            opened, closed = 0.0, size
            self.price = 0.0
        elif oldsize == 0.0:
            # Update opened a position from 0.0
            opened, closed = size, 0.0
            self.price = price
        elif oldsize > 0.0:  # existing "long" position updated

            if size > 0.0:  # increased position
                opened, closed = size, 0.0
                self.price = (self.price * oldsize + size * price) / self.size

            elif self.size > 0.0:  # reduced position
                opened, closed = 0.0, size
                # self.price = self.price

            else:
                # reversed position form plus to minus
                # Validate assumption made
                assert self.size < 0.0

                opened, closed = self.size, -oldsize
                self.price = price

        else:
            # existing short position updated
            # Validate assumption made
            assert oldsize < 0.0

            if size < 0.0:  # increased position
                opened, closed = size, 0.0
                self.price = (self.price * oldsize + size * price) / self.size

            elif self.size < 0.0:  # reduced position
                opened, closed = 0.0, size
                # self.price = self.price

            else:
                # reversed position from minus to plus
                # Validate assumption made
                assert self.size > 0.0

                opened, closed = self.size, -oldsize
                self.price = price

        self.upopened = opened
        self.upclosed = closed

        return self.size, self.price, opened, closed

    def set(self, size, price):
        super(Enhanced_Position, self).set(size=size, price=price)

        if size != 0.0:
            self.datetime = datetime.datetime.utcnow()
        else:
            self.datetime = None
