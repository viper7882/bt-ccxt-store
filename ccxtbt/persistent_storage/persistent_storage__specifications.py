PERSISTENT_STORAGE_DIR_NAME = "persistent_storage"
PERSISTENT_STORAGE_ORDER_FILE_NAME = "ccxt_orders_id.csv"

PERSISTENT_STORAGE_CSV_HEADERS = ["Ordering Type", "CCXT Order ID"]
PS_ORDERING_TYPE, PS_CCXT_ORDER_ID = range(len(PERSISTENT_STORAGE_CSV_HEADERS))
