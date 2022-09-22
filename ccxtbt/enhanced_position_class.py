import backtrader


class Enhanced_Position(backtrader.Position):
    def __init__(self, size=0.0, price=0.0):
        super(Enhanced_Position, self).__init__(size=size, price=price)

        # Enhanced attributes
        # self.position_value = 0.0
        # self.position_take_profit = 0.0
        # self.position_stop_loss = 0.0
        # self.position_trailing_stop = 0.0
        # self.position_margin = 0.0
        # self.unrealised_pnl = 0.0
        # self.unrealised_pnl_in_percent = 0.0
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
        # items.append('- Unrealized PNL: {}'.format(self.unrealised_pnl))
        # items.append('- Unrealized PNL in %: {}'.format(self.unrealised_pnl_in_percent))
        # items.append('- Realized PNL: {}'.format(self.unrealised_pnl))
        items.append('- Opened: {}'.format(self.upopened))
        items.append('- Closed: {}'.format(self.upclosed))
        items.append('--- Position End ---')
        ret_value = str('\n'.join(items))
        return ret_value

    def clone(self):
        return Enhanced_Position(size=self.size, price=self.price)

    def pseudoupdate(self, size, price):
        return Enhanced_Position(self.size, self.price).update(size, price)

    def set(self, size, price):
        super(Enhanced_Position, self).set(size=size, price=price)
