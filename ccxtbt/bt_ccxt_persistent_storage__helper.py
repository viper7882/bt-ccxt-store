import backtrader
import csv
import inspect
import os

import pandas as pd

from pandas.core.frame import DataFrame
from pandas.io.parsers import TextFileReader
from pathlib import Path

from ccxtbt.bt_ccxt__specifications import CCXT__MARKET_TYPES, PERSISTENT_STORAGE_CSV_HEADERS, \
    PERSISTENT_STORAGE_DIR_NAME, PERSISTENT_STORAGE_ORDER_FILE_NAME, PS_CCXT_ORDER_ID, PS_ORDERING_TYPE
from ccxtbt.utils import legality_check_not_none_obj


def get_persistent_storage_file_path(params) -> str:
    # Un-serialize Params
    exchange_dropdown_value = params['exchange_dropdown_value']
    market_type = params['market_type']
    main_net_toggle_switch_value = params['main_net_toggle_switch_value']
    symbol_id = params['symbol_id']

    # Legality Check
    legality_check_not_none_obj(
        exchange_dropdown_value, "exchange_dropdown_value")
    if market_type not in range(len(CCXT__MARKET_TYPES)):
        raise ValueError("{}: {} market_type must be one of {}!!!".format(
            inspect.currentframe(),
            market_type, range(len(CCXT__MARKET_TYPES))))
    assert isinstance(main_net_toggle_switch_value, bool)
    assert isinstance(symbol_id, str)

    if main_net_toggle_switch_value == True:
        exchange_net_type = backtrader.Broker_or_Exchange_Base.Exchange_Net_Types[
            backtrader.Broker_or_Exchange_Base.MAINNET]
    else:
        exchange_net_type = backtrader.Broker_or_Exchange_Base.Exchange_Net_Types[
            backtrader.Broker_or_Exchange_Base.TESTNET]

    persistent_storage_dir_path = \
        os.path.join(Path(os.path.dirname(os.path.realpath(__file__))), PERSISTENT_STORAGE_DIR_NAME,
                     exchange_dropdown_value, CCXT__MARKET_TYPES[market_type])

    file_name = "{}_{}_{}".format(
        exchange_net_type, symbol_id, PERSISTENT_STORAGE_ORDER_FILE_NAME)
    persistent_storage_file_path = \
        os.path.join(persistent_storage_dir_path, file_name)
    return persistent_storage_file_path


def save_to_persistent_storage(params) -> bool:
    # Un-serialize Params
    csv_headers = params['csv_headers']
    csv_dicts = params['csv_dicts']

    # Optional Params
    mode = params.get('mode', None)

    # Reference: https://www.scaler.com/topics/how-to-create-a-csv-file-in-python/
    assert isinstance(csv_headers, list)
    assert isinstance(csv_dicts, list)

    success = False
    save_to_file_path = get_persistent_storage_file_path(params)
    save_to_dir_path = os.path.dirname(os.path.abspath(save_to_file_path))

    # Make the directory
    if not os.path.exists(save_to_dir_path):
        Path(save_to_dir_path).mkdir(parents=True, exist_ok=True)

    if len(csv_dicts) > 0:
        mode = "a" if mode is None else mode
    else:
        mode = "w" if mode is None else mode

    if not os.path.exists(save_to_file_path):
        mode += "+"

    with open(save_to_file_path, mode, newline='') as file:
        writer = csv.DictWriter(file, fieldnames=csv_headers)

        # Write header only if we are NOT in append mode
        if "a" not in mode:
            writer.writeheader()

        writer.writerows(csv_dicts)
        success = True
        pass
    return success


def read_from_persistent_storage(params) -> None | DataFrame | TextFileReader:
    read_from_file_path = get_persistent_storage_file_path(params)
    read_from_dir_path = os.path.dirname(os.path.abspath(read_from_file_path))

    # Reference: https://www.scaler.com/topics/how-to-create-a-csv-file-in-python/
    dataframe = None
    # Confirm if the directory must exist
    if os.path.exists(read_from_dir_path):
        # Confirm if the file must exist
        if os.path.exists(read_from_file_path):
            try:
                dataframe = pd.read_csv(read_from_file_path)

                # Reference: https://pbpython.com/pandas_dtypes.html
                dataframe[PERSISTENT_STORAGE_CSV_HEADERS[PS_CCXT_ORDER_ID]] = \
                    dataframe[PERSISTENT_STORAGE_CSV_HEADERS[PS_CCXT_ORDER_ID]].astype(
                        str)
                pass
            except pd.errors.EmptyDataError:
                pass
    return dataframe


def delete_from_persistent_storage(params) -> bool:
    # Un-serialize Params
    ordering_type = params['ordering_type']
    ccxt_order_id = params['ccxt_order_id']

    success = False
    dataframe = read_from_persistent_storage(params)

    ordering_type_list = []
    ccxt_orders_id = []
    if dataframe is not None:
        ordering_type_list = dataframe[PERSISTENT_STORAGE_CSV_HEADERS[PS_ORDERING_TYPE]].tolist(
        )
        ccxt_orders_id = dataframe[PERSISTENT_STORAGE_CSV_HEADERS[PS_CCXT_ORDER_ID]].tolist(
        )

    csv_dicts = []

    found_match = False
    for file_ordering_type, file_ccxt_order_id in zip(ordering_type_list, ccxt_orders_id):
        if ordering_type != file_ordering_type or ccxt_order_id != file_ccxt_order_id:
            csv_dict = {
                PERSISTENT_STORAGE_CSV_HEADERS[PS_ORDERING_TYPE]: file_ordering_type,
                PERSISTENT_STORAGE_CSV_HEADERS[PS_CCXT_ORDER_ID]: file_ccxt_order_id,
            }
            csv_dicts.append(csv_dict)
        else:
            found_match = True

    if found_match == False:
        frameinfo = inspect.getframeinfo(inspect.currentframe())
        msg = "{} Line: {}: WARNING: ".format(
            frameinfo.function, frameinfo.lineno,
        )
        sub_msg = "\'{}\' ccxt_order_id of {} ordering type not found in {}".format(
            ccxt_order_id,
            backtrader.Order.Ordering_Types[ordering_type],
            ccxt_orders_id,
        )
        print(msg + sub_msg)

    save_to_persistent_storage__dict = dict(
        csv_headers=PERSISTENT_STORAGE_CSV_HEADERS,
        csv_dicts=csv_dicts,

        # Optional Params
        mode="w",
    )
    save_to_persistent_storage__dict.update(params)
    success = save_to_persistent_storage(
        params=save_to_persistent_storage__dict)
    return success
