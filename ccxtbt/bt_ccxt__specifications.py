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

CCXT__MARKET_TYPES = ("spot", "inverse", "linear", "futures", "options", )
CCXT__MARKET_TYPE__SPOT, CCXT__MARKET_TYPE__INVERSE, CCXT__MARKET_TYPE__LINEAR, CCXT__MARKET_TYPE__FUTURES, \
    CCXT__MARKET_TYPE__OPTIONS = range(len(CCXT__MARKET_TYPES))

MAINNET__API_KEY_AND_SECRET_FILE_NAME = "mainnet__api_key_and_secret.json"
TESTNET__API_KEY_AND_SECRET_FILE_NAME = "testnet__api_key_and_secret.json"

SPOT__MAINNET__API_KEY_AND_SECRET_FILE_NAME = "spot__mainnet__api_key_and_secret.json"
SPOT__TESTNET__API_KEY_AND_SECRET_FILE_NAME = "spot__testnet__api_key_and_secret.json"

FUTURES__MAINNET__API_KEY_AND_SECRET_FILE_NAME = SPOT__MAINNET__API_KEY_AND_SECRET_FILE_NAME
FUTURES__TESTNET__API_KEY_AND_SECRET_FILE_NAME = "futures__testnet__api_key_and_secret.json"

symbol_stationary__dict_template = dict(
    symbol_id=None,
    symbol_name=None,

    taker_fee=None,
    maker_fee=None,
    tick_size=None,

    # Leverage
    min_leverage=None,
    leverage_step=None,

    # Risk Limit
    risk_limit=None,  # To be filled with risk_limit__dict_template should it exists

    # Lot size
    lot_size_qty_step=None,
    lot_size_min_qty=None,
    lot_size_max_qty=None,
)

STANDARD_ATTRIBUTES = ['symbol_tick_size',
                       'price_digits', 'qty_step', 'qty_digits']
