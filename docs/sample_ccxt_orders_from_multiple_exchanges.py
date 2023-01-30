# Contents before def _post_process__ccxt_orders has been called

# Binance Active, Limit Order
ccxt_order['id'] = 'xxx'
ccxt_order['datetime'] = '2023-01-29T02:05:18.550Z'
ccxt_order['symbol'] = 'ETH/USDT'
ccxt_order['type'] = 'limit'
ccxt_order['side'] == "buy"
ccxt_order['price'] == 1554.99
ccxt_order['amount'] == 0.007
ccxt_order['average'] == None
ccxt_order['filled'] == 0.0
ccxt_order['remaining'] == 0.007
ccxt_order['status'] == "open"
ccxt_order['stopPrice'] == None
ccxt_order['reduceOnly'] == False

# Bybit Active, Limit Order
ccxt_order['symbol'] = 'ETH/USDT:USDT'
ccxt_order['info']['reduce_only'] == False


# Binance Conditional, Market Order
ccxt_order['id'] = 'xxx'
ccxt_order['datetime'] = '2023-01-29T02:05:18.550Z'
ccxt_order['symbol'] = 'ETH/USDT'
ccxt_order['type'] = 'stop_market'
ccxt_order['side'] == "buy"
ccxt_order['price'] == None
ccxt_order['amount'] == 0.007
ccxt_order['average'] == None
ccxt_order['filled'] == 0.0
ccxt_order['remaining'] == 0.007
ccxt_order['status'] == "open"
ccxt_order['stopPrice'] == 1650.0
ccxt_order['reduceOnly'] == False

# Bybit Conditional, Market Order
ccxt_order['symbol'] = 'ETH/USDT:USDT'
ccxt_order['type'] = 'market'
ccxt_order['stopPrice'] == "1650.0" (should be safe_float)
ccxt_order['filled'] == None
ccxt_order['remaining'] == None

# Binance Conditional, Limit Order
ccxt_order['id'] = 'xxx'
ccxt_order['datetime'] = '2023-01-29T02:05:18.550Z'
ccxt_order['symbol'] = 'ETH/USDT'
ccxt_order['type'] = 'stop'
ccxt_order['side'] == "buy"
ccxt_order['price'] == 1650.0
ccxt_order['amount'] == 0.007
ccxt_order['average'] == None
ccxt_order['filled'] == 0.0
ccxt_order['remaining'] == 0.007
ccxt_order['status'] == "open"
ccxt_order['stopPrice'] == 1650.0
ccxt_order['reduceOnly'] == False

# Bybit Conditional, Limit Order
ccxt_order['symbol'] = 'ETH/USDT:USDT'
ccxt_order['type'] = 'limit'
ccxt_order['info']['reduce_only'] == False
ccxt_order['filled'] == None
ccxt_order['remaining'] == None
