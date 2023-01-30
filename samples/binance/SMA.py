import backtrader as bt
from datetime import datetime, timedelta
import json

from ccxtbt.bt_ccxt_account_or_store__classes import BT_CCXT_Account_or_Store
from ccxtbt.bt_ccxt__specifications import CANCELED_ORDER, CCXT_ORDER_TYPES, CLOSED_ORDER


class TestStrategy(bt.Strategy):

    def __init__(self):

        self.sma = bt.indicators.SMA(self.data, period=21)

    def next(self):

        # Get cash and balance
        # New broker method that will let you get the cash and balance for
        # any wallet. It also means we can disable the getcash() and getvalue()
        # rest calls before and after next which slows things down.

        # NOTE: If you try to get the wallet balance from a wallet you have
        # never funded, a KeyError will be raised! Change LTC below as approriate
        if self.live_data:
            cash, value = self.broker_or_exchange.get_wallet_balance('BNB')
        else:
            # Avoid checking the balance during a backfill. Otherwise, it will
            # Slow things down.
            cash = 'NA'

        for datafeed in self.datafeeds:

            print('{} - {} | Cash {} | O: {} H: {} L: {} C: {} V:{} SMA:{}'.format(data.datetime.datetime(),
                                                                                   datafeed._name, cash, data.open[0], data.high[
                                                                                       0], data.low[0], data.close[0], data.volume[0],
                                                                                   self.sma[0]))

    def datafeed_notification(self, datafeed, status, *args, **kwargs):
        dn = datafeed._name
        dt = datetime.now()
        msg = 'Data Status: {}'.format(datafeed._getstatusname(status))
        print(dt, dn, msg)
        if data._getstatusname(status) == 'LIVE':
            self.live_data = True
        else:
            self.live_data = False


with open('./samples/params.json', 'r') as f:
    params = json.load(f)

cerebro = bt.Cerebro(quicknotify=True)


# Add the strategy
cerebro.add_strategy(TestStrategy)

# Create our store
config = {'apiKey': params["binance"]["apikey"],
          'secret': params["binance"]["secret"],
          'enableRateLimit': True,
          }


# IMPORTANT NOTE - Kraken (and some other exchanges) will not return any values
# for get cash or value if You have never held any BNB coins in your account.
# So switch BNB to a coin you have funded previously if you get errors
store = BT_CCXT_Account_or_Store(
    exchange='binance', currency='BNB', config=config, retries=5, debug=False)


# Get the broker and pass any kwargs if needed.
# ----------------------------------------------
# Broker mappings have been added since some exchanges expect different values
# to the defaults. Case in point, Kraken vs Bitmex. NOTE: Broker mappings are not
# required if the broker uses the same values as the defaults in BT_CCXT_Exchange.
broker_mapping = {
    'order_types': {
        bt.Order.Market: 'market',
        bt.Order.Limit: 'limit',
        bt.Order.StopMarket: 'stop-loss',  # stop-loss for kraken, stop for bitmex
        bt.Order.StopLimit: 'stop limit'
    },
    'mappings': {
        CCXT_ORDER_TYPES[CLOSED_ORDER]: {
            'key': 'status',
            'value': 'closed'
        },
        CCXT_ORDER_TYPES[CANCELED_ORDER]: {
            'key': 'result',
            'value': 1}
    }
}

broker = store.get_broker_or_exchange(broker_mapping=broker_mapping)
cerebro.set_broker_or_exchange(broker)

# Get our data
# Drop newest will prevent us from loading partial data from incomplete candles
hist_start_date = datetime.utcnow() - timedelta(minutes=50)
data = store.getdata(dataname='BNB/USDT', name="BNBUSDT",
                     timeframe=bt.TimeFrame.Minutes, fromdate=hist_start_date,
                     compression=1, ohlcv_limit=50, drop_newest=True)  # , historical=True)

# Add the feed
cerebro.add_datafeed(data)

# Run the strategy
cerebro.run()
