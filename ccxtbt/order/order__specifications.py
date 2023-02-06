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

CCXT_ORDER_TYPES = \
    ('opened_order', 'partially_filled_order', 'closed_order',
     'canceled_order', 'expired_order', 'rejected_order', )
OPENED_ORDER, PARTIALLY_FILLED_ORDER, CLOSED_ORDER, CANCELED_ORDER, EXPIRED_ORDER, REJECTED_ORDER, = \
    range(len(CCXT_ORDER_TYPES))

DERIVED__CCXT_ORDER__KEYS = \
    ('status', 'ordering_type', 'execution_type',
     'order_intent', 'position_type', 'side', )
STATUS, ORDERING_TYPE, EXECUTION_TYPE, ORDER_INTENT, POSITION_TYPE, SIDE, = range(
    len(DERIVED__CCXT_ORDER__KEYS))

PLURAL__CCXT_ORDER__KEYS = \
    ('statuses', 'ordering_types', 'execution_types',
     'order_intents', 'position_types', 'sides', )
# ----------------------------------------------------------------------------------------------------------------------
# WARNING: Update to the following tuples must be in sync with filter_order__dict_template
STATUSES, ORDERING_TYPES, EXECUTION_TYPES, ORDER_INTENTS, POSITION_TYPES, SIDES, = \
    range(len(PLURAL__CCXT_ORDER__KEYS))

filter_order__dict_template = {
    PLURAL__CCXT_ORDER__KEYS[STATUSES]: None,
    PLURAL__CCXT_ORDER__KEYS[ORDERING_TYPES]: None,
    PLURAL__CCXT_ORDER__KEYS[EXECUTION_TYPES]: None,
    PLURAL__CCXT_ORDER__KEYS[ORDER_INTENTS]: None,
    PLURAL__CCXT_ORDER__KEYS[POSITION_TYPES]: None,
    PLURAL__CCXT_ORDER__KEYS[SIDES]: None,
}
# ----------------------------------------------------------------------------------------------------------------------
