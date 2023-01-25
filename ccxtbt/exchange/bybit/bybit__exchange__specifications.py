BYBIT_EXCHANGE_ID = "bybit"
BYBIT_OHLCV_LIMIT = 200
BYBIT_COMMISSION_PRECISION = 4

# Reference: https://bybit-exchange.github.io/docs/inverse/#t-websocketauthentication
# Reference: https://bybit-exchange.github.io/docs/testnet/inverse/#t-authentication
bybit_testnet_websocket_endpoints = (
    "wss://stream-testnet.bybit.com/realtime", )
bybit_mainnet_websocket_endpoints = ("wss://stream.bybit.com/realtime",
                                     "wss://stream.bytick.com/realtime", )

bybit_mainnet_urls = ("https://api.bybit.com", "https://api.bytick.com", )
bybit_testnet_urls = ("https://api-testnet.bybit.com",
                      "https://api-testnet.bytick.com", )

From_or_To_Account_Types = (
    "CONTRACT", "SPOT", "INVESTMENT", "OPTION", "UNIFIED", )
CONTRACT__Account_Type, SPOT__Account_Type, INVESTMENT__Account_Type, OPTION__Account_Type, UNIFIED__Account_Type, = \
    range(len(From_or_To_Account_Types))

BYBIT__SPOT__WS_STREAM = "wss://stream.bybit.com/spot/public/v3"
'''
Sample output:
{"topic":"trade.BTCUSDT","ts":1672501573024,"type":"snapshot","data":{"v":"2290000000035488024","t":1672501573022,"p":"16596.02","q":"0.003396","m":false,"type":"0"}}
'''
BYBIT__SPOT__HTTP_ENDPOINT_URL = bybit_mainnet_urls[0]

BYBIT__FUTURES__WS_STREAM = "wss://stream.bybit.com/realtime_public"
'''
Sample output:
{"topic":"trade.BTCUSDT","data":[{"symbol":"BTCUSDT","tick_direction":"ZeroPlusTick","price":"16604.50","size":0.001,"timestamp":"2022-12-31T15:46:11.000Z","trade_time_ms":"1672501571614","side":"Buy","trade_id":"2a96c191-ac19-5e45-a914-3f1cad88615b","is_block_trade":"false"}]}
'''

BYBIT__USDT__DERIVATIVES__WS_STREAM = "wss://stream.bybit.com/contract/usdt/public/v3"
'''
Sample output:
{"topic":"publicTrade.BTCUSDT","type":"snapshot","ts":1672501571616,"data":[{"T":1672501571614,"s":"BTCUSDT","S":"Buy","v":"0.001","p":"16604.50","L":"ZeroPlusTick","i":"2a96c191-ac19-5e45-a914-3f1cad88615b","BT":false}]}
'''
BINANCE__USDT__DERIVATIVES__HTTP_ENDPOINT_URL = bybit_mainnet_urls[0]

BYBIT__SPOT_V3_ENDPOINT = "spot/v3"
BYBIT__DERIVATIVES_V2_ENDPOINT = "v2"

BYBIT__SYMBOLS_COMMAND = "public/symbols"


BYBIT__WS_STREAM_COMMAND = "subscribe"
BYBIT__SPOT__CLUSTER_TRADE = "trade"
BYBIT__FUTURES__CLUSTER_TRADE = BYBIT__SPOT__CLUSTER_TRADE
BYBIT__DERIVATIVES__CLUSTER_PUBLIC_TRADE = "publicTrade"

'''
Reference: https://bybit-exchange.github.io/docs/futuresV2/linear/#t-switchpositionmode
'''
BYBIT__DERIVATIVES__DEFAULT_POSITION_MODE = "BothSide"
