import inspect
import os

from pathlib import Path

from ccxtbt.bt_ccxt__specifications import CCXT__MARKET_TYPES, PERSISTENT_STORAGE_DIR_NAME, PERSISTENT_STORAGE_ORDER_FILE_NAME
from ccxtbt.utils import legality_check_not_none_obj


def get_persistent_storage_file_path(params) -> str:
    # Un-serialized Params
    exchange_dropdown_value = params['exchange_dropdown_value']
    market_type = params['market_type']

    # Legality Check
    legality_check_not_none_obj(
        exchange_dropdown_value, "exchange_dropdown_value")
    if market_type not in range(len(CCXT__MARKET_TYPES)):
        raise ValueError("{}: {} market_type must be one of {}!!!".format(
            inspect.currentframe(),
            market_type, range(len(CCXT__MARKET_TYPES))))

    persistent_storage_dir_path = \
        os.path.join(Path(os.path.dirname(os.path.realpath(__file__))), PERSISTENT_STORAGE_DIR_NAME,
                     exchange_dropdown_value, CCXT__MARKET_TYPES[market_type])
    persistent_storage_file_path = \
        os.path.join(persistent_storage_dir_path,
                     PERSISTENT_STORAGE_ORDER_FILE_NAME)
    return persistent_storage_file_path


def save_to_persistent_storage(params) -> bool:
    # Un-serialized Params
    ccxt_orders_id = params['ccxt_orders_id']

    assert isinstance(ccxt_orders_id, list)

    success = False
    save_to_file_path = get_persistent_storage_file_path(params)
    save_to_dir_path = os.path.dirname(os.path.abspath(save_to_file_path))

    # Make the directory
    if not os.path.exists(save_to_dir_path):
        Path(save_to_dir_path).mkdir(parents=True, exist_ok=True)

    if len(ccxt_orders_id) > 0:
        mode = "a+"
    else:
        mode = "w+"

    with open(save_to_file_path, mode) as file:
        if len(ccxt_orders_id) > 0:
            file.writelines("\n".join(ccxt_orders_id))
        else:
            file.write("")
        success = True
        pass
    return success


def read_from_persistent_storage(params) -> list:
    read_from_file_path = get_persistent_storage_file_path(params)
    read_from_dir_path = os.path.dirname(os.path.abspath(read_from_file_path))

    ccxt_orders_id = []
    # Confirm if the directory must exist
    if os.path.exists(read_from_dir_path):
        # Confirm if the file must exist
        if os.path.exists(read_from_file_path):
            with open(read_from_file_path, "r") as file:
                ccxt_orders_id = file.readlines()
    return ccxt_orders_id


def delete_from_persistent_storage(params) -> bool:
    # Un-serialized Params
    ccxt_order_id = params['ccxt_order_id']

    ccxt_orders_id = read_from_persistent_storage(params)
    assert ccxt_order_id in ccxt_orders_id, "Expected: {} exists in {}!!!".format(
        ccxt_order_id, ccxt_orders_id)
    ccxt_orders_id.remove(ccxt_order_id)

    save_to_persistent_storage__dict = dict(
        ccxt_orders_id=ccxt_orders_id,
    )
    save_to_persistent_storage__dict.update(params)
    success = save_to_persistent_storage(
        params=save_to_persistent_storage__dict)
    return success
