BINANCE_EXCHANGE_ID = "binance"
BINANCE_OHLCV_LIMIT = 1000
BINANCE_COMMISSION_PRECISION = 8

# Reference: https://binance-docs.github.io/apidocs/spot/en/#api-key-setup
# Reference: https://binance-docs.github.io/apidocs/spot/en/#general-info
binance_mainnet_urls = ("https://api.binance.com", "https://api1.binance.com", "https://api2.binance.com",
                        "https://api3.binance.com", )

# Reference: https://testnet.binance.vision/
binance_testnet_urls = ("https://testnet.binance.vision/api", )

BINANCE__SPOT__SINGLE_WS_STREAM = "wss://stream.binance.com:9443/ws"
BINANCE__SPOT__MULTIPLE_WS_STREAM = "wss://stream.binance.com:9443/stream?streams"
BINANCE__SPOT__V3__HTTP_ENDPOINT_URL = "{}/api/v3".format(
    binance_mainnet_urls[0])
'''
Sample output:
{"e":"trade","E":1672339883321,"s":"ETHUSDT","t":1048851391,"p":"1197.06000000","q":"0.05400000","b":12087564073,"a":12087563306,"T":1672339883321,"m":false,"M":true}
'''

BINANCE__FUTURES__SINGLE_WS_STREAM = "wss://fstream.binance.com/ws"
BINANCE__FUTURES__MULTIPLE_WS_STREAM = "wss://fstream.binance.com/stream?streams"
BINANCE__FUTURES__V1__HTTP_ENDPOINT_URL = "https://fapi.binance.com/fapi/v1"
'''
Sample output:
{"e":"aggTrade","E":1672532700840,"a":1558619352,"s":"BTCUSDT","p":"16531.80","q":"0.021","f":3166759076,"l":3166759076,"T":1672532700685,"m":true}
'''


BINANCE_SPOT_AND_FUTURES_QTY_DIGITS = 8

# Max limit set by Binance is unknown (tested with 10000 and it is still working)
BINANCE_SPOT__ORDERBOOK_DEPTH_LIMIT = 2000

# Hard limit set by Binance
BINANCE_FUTURES__ORDERBOOK_DEPTH_LIMIT = 1000

BINANCE__SUBSCRIBE_WS_STREAM_COMMAND = "SUBSCRIBE"
BINANCE__SPOT__CLUSTER_TRADE = "trade"
BINANCE__FUTURES__CLUSTER_AGG_TRADE = "aggTrade"
BINANCE__EXCHANGE_INFO_ENDPOINT = "exchangeInfo"
BINANCE__SPOT__COMMISSION_RATE_ENDPOINT = "account"
BINANCE__SYMBOL_COMMAND = "symbol"
BINANCE__SPOT__ORDERBOOK_DEPTH = "depth"
BINANCE__SPOT__ORDERBOOK_DEPTH_UPDATE = "depthUpdate"
BINANCE__FUTURES__ORDERBOOK_DEPTH = BINANCE__SPOT__ORDERBOOK_DEPTH
BINANCE__FUTURES__ORDERBOOK_DEPTH_UPDATE = BINANCE__SPOT__ORDERBOOK_DEPTH_UPDATE
BINANCE__FUTURES__COMMISSION_RATE_ENDPOINT = "commissionRate"

BINANCE__FUTURES__DEFAULT_DUAL_POSITION_MODE = True

BINANCE__PARTIALLY_FILLED__ORDER_STATUS__VALUE = "partially_filled"
