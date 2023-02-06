STAGES_OF_RESEND_NOTIFICATION = 3

PERSISTENT_STORAGE_DIR_NAME = "persistent_storage"
PERSISTENT_STORAGE_ORDER_FILE_NAME = "ccxt_orders_id.csv"
PERSISTENT_STORAGE_CSV_HEADERS = ["Ordering Type", "CCXT Order ID"]
PS_ORDERING_TYPE, PS_CCXT_ORDER_ID = range(len(PERSISTENT_STORAGE_CSV_HEADERS))

DEFAULT__LEVERAGE_IN_PERCENT = 50.0
DEFAULT__INITIAL__CAPITAL_RESERVATION__VALUE = 1.0

DEFAULT_DATE_FORMAT = "%Y-%m-%d"
TIME_FORMAT_WITH_MS_PRECISION = "%H:%M:%S.%f"
DATE_TIME_FORMAT_WITH_MS_PRECISION = DEFAULT_DATE_FORMAT + \
    " " + TIME_FORMAT_WITH_MS_PRECISION
CCXT_DATA_COLUMNS = ["datetime", "open", "high",
                     "low", "close", "volume", "openinterest"]
DATETIME_COL, OPEN_COL, HIGH_COL, LOW_COL, CLOSE_COL, VOLUME_COL, OPEN_INTEREST_COL = range(
    len(CCXT_DATA_COLUMNS))

CCXT_ORDER_TYPES = \
    ('opened_order', 'partially_filled_order', 'closed_order',
     'canceled_order', 'expired_order', 'rejected_order', )
OPENED_ORDER, PARTIALLY_FILLED_ORDER, CLOSED_ORDER, CANCELED_ORDER, EXPIRED_ORDER, REJECTED_ORDER, = \
    range(len(CCXT_ORDER_TYPES))

CCXT_COMMON_MAPPING_VALUES = \
    ('open', 'closed', 'canceled', 'cancelled', 'expired', 'rejected', )
OPEN_VALUE, CLOSED_VALUE, CANCELED_VALUE, CANCELLED_VALUE, EXPIRED_VALUE, REJECTED_VALUE, = \
    range(len(CCXT_COMMON_MAPPING_VALUES))

CCXT_TYPE_KEY = 'type_name'
CCXT_SYMBOL_KEY = 'symbol_name'
CCXT_SIDE_KEY = 'side_name'
CCXT_STATUS_KEY = 'ccxt_status'

LIST_OF_CCXT_KEY_TO_BE_RENAMED = \
    [
        ('type', CCXT_TYPE_KEY),
        ('symbol', CCXT_SYMBOL_KEY),
        ('side', CCXT_SIDE_KEY),
        ('status', CCXT_STATUS_KEY),
    ]

CCXT_ORDER_KEYS__MUST_EXIST = (
    CCXT_TYPE_KEY, CCXT_STATUS_KEY, 'side_name', 'reduce_only')
CCXT_ORDER_KEYS__MUST_BE_IN_FLOAT = (
    'price', 'amount', 'average', 'filled', 'remaining', 'stopPrice', )

DERIVED__CCXT_ORDER__KEYS = \
    ('status', 'ordering_type', 'execution_type',
     'order_intent', 'position_type', 'side', )
STATUS, ORDERING_TYPE, EXECUTION_TYPE, ORDER_INTENT, POSITION_TYPE, SIDE, = range(
    len(DERIVED__CCXT_ORDER__KEYS))

# ----------------------------------------------------------------------------------------------------------------------
# WARNING: Update to the following tuples must be in sync with filter_order__dict_template
PLURAL__CCXT_ORDER__KEYS = \
    ('statuses', 'ordering_types', 'execution_types',
     'order_intents', 'position_types', 'sides', )
STATUSES, ORDERING_TYPES, EXECUTION_TYPES, ORDER_INTENTS, POSITION_TYPES, SIDES, = \
    range(len(PLURAL__CCXT_ORDER__KEYS))
# ----------------------------------------------------------------------------------------------------------------------

DEFAULT_ACCOUNT_ALIAS = "Main"

BT_CCXT__CASH_TRANSFER_WAIT_TIME__IN_SECONDS = 1.0
CASH_DIGITS = 4

MIN_LIVE_EXCHANGE_RETRIES = 5
MAX_LIVE_EXCHANGE_RETRIES = 300

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
    commission_rate=None,

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

filter_order__dict_template = {
    PLURAL__CCXT_ORDER__KEYS[STATUSES]: None,
    PLURAL__CCXT_ORDER__KEYS[ORDERING_TYPES]: None,
    PLURAL__CCXT_ORDER__KEYS[EXECUTION_TYPES]: None,
    PLURAL__CCXT_ORDER__KEYS[ORDER_INTENTS]: None,
    PLURAL__CCXT_ORDER__KEYS[POSITION_TYPES]: None,
    PLURAL__CCXT_ORDER__KEYS[SIDES]: None,
}

risk_limit__dict_template = dict(
    id=None,
    starting_margin=None,
    maintenance_margin_ratio=None,
    max_leverage=None,
    min_position_value=None,
    max_position_value=None,
)
