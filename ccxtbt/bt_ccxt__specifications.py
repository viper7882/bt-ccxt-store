DEFAULT__LEVERAGE_IN_PERCENT = 50.0
DEFAULT__INITIAL__CAPITAL_RESERVATION__VALUE = 1.0

DEFAULT_DATE_FORMAT = "%Y-%m-%d"
TIME_FORMAT_WITH_MS_PRECISION = "%H:%M:%S.%f"
DATE_TIME_FORMAT_WITH_MS_PRECISION = DEFAULT_DATE_FORMAT + \
    " " + TIME_FORMAT_WITH_MS_PRECISION

CASH_DIGITS = 4
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

risk_limit__dict_template = dict(
    id=None,
    starting_margin=None,
    maintenance_margin_ratio=None,
    max_leverage=None,
    min_position_value=None,
    max_position_value=None,
)
