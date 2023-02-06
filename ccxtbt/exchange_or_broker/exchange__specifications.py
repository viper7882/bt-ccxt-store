MIN_LIVE_EXCHANGE_RETRIES = 5
MAX_LIVE_EXCHANGE_RETRIES = 300

MAINNET__API_KEY_AND_SECRET_FILE_NAME = "mainnet__api_key_and_secret.json"
TESTNET__API_KEY_AND_SECRET_FILE_NAME = "testnet__api_key_and_secret.json"

SPOT__MAINNET__API_KEY_AND_SECRET_FILE_NAME = "spot__mainnet__api_key_and_secret.json"
SPOT__TESTNET__API_KEY_AND_SECRET_FILE_NAME = "spot__testnet__api_key_and_secret.json"

FUTURES__MAINNET__API_KEY_AND_SECRET_FILE_NAME = SPOT__MAINNET__API_KEY_AND_SECRET_FILE_NAME
FUTURES__TESTNET__API_KEY_AND_SECRET_FILE_NAME = "futures__testnet__api_key_and_secret.json"

CCXT_COMMON_MAPPING_VALUES = \
    ('open', 'closed', 'canceled', 'cancelled', 'expired', 'rejected', )
OPEN_VALUE, CLOSED_VALUE, CANCELED_VALUE, CANCELLED_VALUE, EXPIRED_VALUE, REJECTED_VALUE, = \
    range(len(CCXT_COMMON_MAPPING_VALUES))
