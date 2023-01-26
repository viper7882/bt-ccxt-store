DEFAULT_DATE_FORMAT = "%Y-%m-%d"
TIME_FORMAT_WITH_MS_PRECISION = "%H:%M:%S.%f"
DATE_TIME_FORMAT_WITH_MS_PRECISION = DEFAULT_DATE_FORMAT + \
    " " + TIME_FORMAT_WITH_MS_PRECISION
CCXT_DATA_COLUMNS = ["datetime", "open", "high",
                     "low", "close", "volume", "openinterest"]
DATETIME_COL, OPEN_COL, HIGH_COL, LOW_COL, CLOSE_COL, VOLUME_COL, OPEN_INTEREST_COL = range(
    len(CCXT_DATA_COLUMNS))

DEFAULT_ACCOUNT_ALIAS = "Main"

BT_CCXT__CASH_TRANSFER_WAIT_TIME__IN_SECONDS = 1.0
CASH_DIGITS = 4
MAX_LIVE_EXCHANGE_RETRIES = 5
VALUE_DIGITS = 4

MIN_LEVERAGE = 1.0

MIN_TYPICAL_PERCENTAGE = 0.0
MAX_TYPICAL_PERCENTAGE = 100.0
TYPICAL_PERCENTAGE_STEP = 0.1

MIN_LEVERAGE_IN_PERCENT = MIN_TYPICAL_PERCENTAGE
MAX_LEVERAGE_IN_PERCENT = MAX_TYPICAL_PERCENTAGE
PERCENTAGE_LEVERAGE_STEP = 5

# Reference: https://github.com/ccxt/ccxt/wiki/Manual#market-structure
CCXT__MARKET_TYPES = ("spot", "margin", "inverse",
                      "swap", "future", "option", )
CCXT__MARKET_TYPE__SPOT, CCXT__MARKET_TYPE__MARGIN, CCXT__MARKET_TYPE__INVERSE, \
    CCXT__MARKET_TYPE__LINEAR_PERPETUAL_SWAP, CCXT__MARKET_TYPE__FUTURE, CCXT__MARKET_TYPE__OPTION = \
    range(len(CCXT__MARKET_TYPES))

MAINNET__API_KEY_AND_SECRET_FILE_NAME = "mainnet__api_key_and_secret.json"
TESTNET__API_KEY_AND_SECRET_FILE_NAME = "testnet__api_key_and_secret.json"

SPOT__MAINNET__API_KEY_AND_SECRET_FILE_NAME = "spot__mainnet__api_key_and_secret.json"
SPOT__TESTNET__API_KEY_AND_SECRET_FILE_NAME = "spot__testnet__api_key_and_secret.json"

FUTURES__MAINNET__API_KEY_AND_SECRET_FILE_NAME = SPOT__MAINNET__API_KEY_AND_SECRET_FILE_NAME
FUTURES__TESTNET__API_KEY_AND_SECRET_FILE_NAME = "futures__testnet__api_key_and_secret.json"

symbol_stationary__dict_template = dict(
    symbol_id=None,
    symbol_name=None,

    # Transaction Fee
    taker_fee=None,
    maker_fee=None,

    # Price
    tick_size=None,
    price_digits=None,

    # Lot size
    qty_step=None,
    min_qty=None,
    max_qty=None,
    qty_digits=None,

    # Cost/Value
    min_notional=None,
    value_digits=None,

    # Leverage
    min_leverage=None,
    leverage_step=None,

    # Risk Limit
    risk_limit=None,  # To be filled with risk_limit__dict_template should it exists
)
