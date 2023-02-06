import backtrader
import copy
import datetime
import inspect
import sys
import threading
import traceback
import unittest

from pprint import pprint
from time import time as timer
from unittest.mock import call, patch

from ccxtbt.bt_ccxt__specifications import CCXT__MARKET_TYPES, CCXT__MARKET_TYPE__FUTURE, \
    CCXT__MARKET_TYPE__LINEAR_PERPETUAL_SWAP, DEFAULT__INITIAL__CAPITAL_RESERVATION__VALUE, \
    DEFAULT__LEVERAGE_IN_PERCENT
from ccxtbt.exchange_or_broker.binance.binance__exchange__specifications import BINANCE_EXCHANGE_ID
from ccxtbt.exchange_or_broker.bybit.bybit__exchange__helper import get_wallet_currency
from ccxtbt.exchange_or_broker.bybit.bybit__exchange__specifications import BYBIT_EXCHANGE_ID
from ccxtbt.expansion.bt_ccxt_expansion__helper import construct_dual_position_datafeeds, \
    construct_standalone_cerebro, query__entry_or_exit_order
from ccxtbt.order.order__specifications import ORDERING_TYPES, STATUSES, EXECUTION_TYPES, ORDER_INTENTS, POSITION_TYPES
from ccxtbt.order.order__specifications import PLURAL__CCXT_ORDER__KEYS, filter_order__dict_template
from ccxtbt.persistent_storage.persistent_storage__helper import read_from_persistent_storage, \
    save_to_persistent_storage
from ccxtbt.persistent_storage.persistent_storage__specifications import PERSISTENT_STORAGE_CSV_HEADERS, \
    PS_CCXT_ORDER_ID, PS_ORDERING_TYPE
from ccxtbt.strategy.strategy__classes import Enhanced_Strategy
from ccxtbt.utils import get_opposite__position_type, get_order_entry_price_and_queue, get_time_diff, \
    legality_check_not_none_obj

from tests.common.test__helper import ut_enter_or_exit_using_limit_or_conditional_order, \
    ut_enter_or_exit_using_market_order, \
    ut_get_bt_ccxt_account_or_stores, ut_get_partially_filled_order, ut_get_rejected_order, ut_get_valid_market_types
from tests.common.test__specifications import MAX__HTTP__REAL_ORDER_WAITING_TIME__IN_SECONDS


class Strategy_And_Datafeed__TestCases(unittest.TestCase):
    def setUp(self):
        try:
            self.exchange_dropdown_values = (
                BINANCE_EXCHANGE_ID, BYBIT_EXCHANGE_ID, )

            self.target__market_types = \
                (CCXT__MARKET_TYPE__FUTURE, CCXT__MARKET_TYPE__LINEAR_PERPETUAL_SWAP, )

            self.main_net_toggle_switch_value = False
            self.isolated_toggle_switch_value = False

            self.leverage_in_percent = DEFAULT__LEVERAGE_IN_PERCENT
            self.initial__capital_reservation__value = DEFAULT__INITIAL__CAPITAL_RESERVATION__VALUE

            # For UT, simplifying the flow by setting Testnet as OHLCV provider here so that we do not need a dedicated
            # OHLCV provider
            self.is_ohlcv_provider = True
            self.enable_rate_limit = True

            self.account__thread__connectivity__lock = threading.Lock()
            self.exchange_account__lock = threading.Lock()
            self.symbols_id = ["ETHUSDT", ]
            self.wallet_currency = get_wallet_currency(self.symbols_id[0])

            self.dual_position_types = (
                backtrader.Position.LONG_POSITION, backtrader.Position.SHORT_POSITION,)

            self.minute_delta = 5
            assert self.minute_delta > 1
            self.latest_utc_dt = datetime.datetime.utcnow()

            self.construct_standalone_account_or_store__dict = dict(
                main_net_toggle_switch_value=self.main_net_toggle_switch_value,
                isolated_toggle_switch_value=self.isolated_toggle_switch_value,
                leverage_in_percent=self.leverage_in_percent,
                symbols_id=self.symbols_id,
                enable_rate_limit=self.enable_rate_limit,
                initial__capital_reservation__value=self.initial__capital_reservation__value,
                is_ohlcv_provider=self.is_ohlcv_provider,
                account__thread__connectivity__lock=self.account__thread__connectivity__lock,
                wallet_currency=self.wallet_currency,
            )

            get_bt_ccxt_account_or_stores__dict = dict(
                exchange_dropdown_values=self.exchange_dropdown_values,
                target__market_types=self.target__market_types,
                construct_standalone_account_or_store__dict=self.construct_standalone_account_or_store__dict,

                # Optional Params
                ut_keep_original_ccxt_order=True,
            )
            self.bt_ccxt_account_or_stores = \
                ut_get_bt_ccxt_account_or_stores(
                    params=get_bt_ccxt_account_or_stores__dict)

            for exchange_dropdown_value in self.exchange_dropdown_values:
                market_types = ut_get_valid_market_types(
                    exchange_dropdown_value, self.target__market_types)
                for market_type in market_types:
                    for symbol_id in self.symbols_id:
                        csv_dicts = []
                        # Reset persistent storage
                        save_to_persistent_storage__dict = dict(
                            csv_headers=PERSISTENT_STORAGE_CSV_HEADERS,
                            csv_dicts=csv_dicts,
                            exchange_dropdown_value=exchange_dropdown_value,
                            market_type=market_type,
                            main_net_toggle_switch_value=self.main_net_toggle_switch_value,
                            symbol_id=symbol_id,

                            # Optional Params
                            mode="w",
                        )
                        save_to_persistent_storage(
                            params=save_to_persistent_storage__dict)
            pass

            # Legality Check
            assert self.main_net_toggle_switch_value == False, \
                "{} is created to ONLY work in Testnet!!!".format(
                    type(self).__name__)

            # Confirm there is no opened position and/or no opened [Entry] orders
            self.tearDown()
        except Exception:
            traceback.print_exc()

    def tearDown(self):
        try:
            bt_ccxt_account_or_stores = self.bt_ccxt_account_or_stores
            symbols_id = self.symbols_id

            position_types = (backtrader.Position.LONG_POSITION,
                              backtrader.Position.SHORT_POSITION, )

            entry_ordering_types = (backtrader.Order.ACTIVE_ORDERING_TYPE,
                                    backtrader.Order.CONDITIONAL_ORDERING_TYPE, )

            # Run the tests using default bt_ccxt_account_or_stores instances
            for bt_ccxt_account_or_store in bt_ccxt_account_or_stores:
                for symbol_id in symbols_id:
                    instrument = bt_ccxt_account_or_store.get__child(symbol_id)

                    for position_type in position_types:
                        position = instrument.get_position(position_type)

                        # Confirm there is no opened position
                        self.assertEqual(position.price, 0.0)

                        for entry_ordering_type in entry_ordering_types:
                            if entry_ordering_type == backtrader.Order.ACTIVE_ORDERING_TYPE:
                                execution_type = backtrader.Order.Limit
                            else:
                                assert entry_ordering_type == backtrader.Order.CONDITIONAL_ORDERING_TYPE

                                if bt_ccxt_account_or_store.exchange_dropdown_value == BYBIT_EXCHANGE_ID:
                                    execution_type = backtrader.Order.Limit
                                else:
                                    execution_type = backtrader.Order.StopLimit

                            # Confirm there is no [Entry] order in exchange
                            # Look for [Entry] orders
                            filter_order__dict = copy.deepcopy(
                                filter_order__dict_template)
                            filter_order__dict[PLURAL__CCXT_ORDER__KEYS[STATUSES]] = \
                                [backtrader.Order.Accepted]
                            filter_order__dict[PLURAL__CCXT_ORDER__KEYS[ORDERING_TYPES]] = \
                                [entry_ordering_type]
                            filter_order__dict[PLURAL__CCXT_ORDER__KEYS[EXECUTION_TYPES]] = \
                                [execution_type]
                            filter_order__dict[PLURAL__CCXT_ORDER__KEYS[ORDER_INTENTS]] = \
                                [backtrader.Order.Entry_Order]
                            filter_order__dict[PLURAL__CCXT_ORDER__KEYS[POSITION_TYPES]] = \
                                [position_type]

                            query__entry_or_exit_order__dict = dict(
                                bt_ccxt_account_or_store=bt_ccxt_account_or_store,
                                instrument=instrument,
                                filter_order__dict=filter_order__dict,
                            )
                            opened_bt_ccxt_orders = \
                                query__entry_or_exit_order(
                                    params=query__entry_or_exit_order__dict)

                            self.assertEqual(len(opened_bt_ccxt_orders), 0)
            pass
        except Exception:
            traceback.print_exc()

    @unittest.skip("Only run if required")
    def test_01__Dry_Run(self):
        start = timer()
        try:
            pass
        except Exception:
            traceback.print_exc()

        _, minutes, seconds = get_time_diff(start)
        frameinfo = inspect.getframeinfo(inspect.currentframe())
        print("{} Line: {}: Took {}m:{:.2f}s".format(frameinfo.function, frameinfo.lineno,
                                                     int(minutes), seconds))

    # @unittest.skip("To be enabled")
    # @unittest.skip("Ready for regression")
    def test_10__strategy__no_position__ticks_datafeed__empty_strategy(self):
        start = timer()
        try:
            bt_ccxt_account_or_stores = self.bt_ccxt_account_or_stores
            symbols_id = self.symbols_id
            wallet_currency = self.wallet_currency
            dual_position_types = self.dual_position_types

            class UT_Strategy(Enhanced_Strategy):
                def __init__(self):
                    super().__init__()
                    pass

                def next(self):
                    print("Successful run strategy ^_^")
                    self.cerebro.stop_running(self.instrument)
                    pass

            # Run the tests
            for bt_ccxt_account_or_store in bt_ccxt_account_or_stores:
                for symbol_id in symbols_id:
                    instrument = bt_ccxt_account_or_store.get__child(symbol_id)

                    number_of_empty_positions = 0
                    for dual_position_type in dual_position_types:
                        position = instrument.get_position(dual_position_type)

                        # If there is no opened position
                        if position.price == 0.0:
                            number_of_empty_positions += 1

                    # If there is no opened positions
                    if number_of_empty_positions == 2:
                        construct_standalone_cerebro__dict = dict(
                            bt_ccxt_exchange=bt_ccxt_account_or_store.parent,
                        )
                        cerebro = construct_standalone_cerebro(
                            params=construct_standalone_cerebro__dict)

                        bt_ccxt_feed__dict = dict(
                            timeframe=backtrader.TimeFrame.Ticks,
                            drop_newest=False,
                            ut__halt_if_no_ohlcv=True,
                            # debug=True,
                        )

                        construct_dual_position_datafeeds_dict = dict(
                            exchange_dropdown_value=bt_ccxt_account_or_store.exchange_dropdown_value,
                            instrument=instrument,
                            bt_ccxt_feed__dict=bt_ccxt_feed__dict,
                            wallet_currency=wallet_currency,
                        )
                        (long_bb_data, short_bb_data,) = \
                            construct_dual_position_datafeeds(
                                params=construct_dual_position_datafeeds_dict)
                        cerebro.add_datafeed(long_bb_data, name="long_bb_data")
                        cerebro.add_datafeed(
                            short_bb_data, name="short_bb_data")

                        cerebro__strategy__params = dict(
                            is_backtest=False,
                        )
                        cerebro.add_strategy(
                            UT_Strategy, **cerebro__strategy__params)
                        cerebro.run()
                    else:
                        msg = "{}: {}: WARNING: {}: ".format(
                            bt_ccxt_account_or_store.exchange_dropdown_value,
                            CCXT__MARKET_TYPES[bt_ccxt_account_or_store.market_type],
                            instrument.symbol_id,
                        )
                        sub_msg = "Unable to detect empty positions. Please retry"
                        print(msg + sub_msg)
        except Exception:
            traceback.print_exc()

        _, minutes, seconds = get_time_diff(start)
        frameinfo = inspect.getframeinfo(inspect.currentframe())
        print("{} Line: {}: Took {}m:{:.2f}s".format(frameinfo.function, frameinfo.lineno,
                                                     int(minutes), seconds))

    # @unittest.skip("To be enabled")
    # @unittest.skip("Ready for regression")
    def test_20__strategy__dual_positions__ticks_datafeed__open_and_cancel__entry_order(self):
        start = timer()
        try:
            bt_ccxt_account_or_stores = self.bt_ccxt_account_or_stores
            symbols_id = self.symbols_id
            wallet_currency = self.wallet_currency
            dual_position_types = self.dual_position_types

            position_types = (backtrader.Position.LONG_POSITION,
                              backtrader.Position.SHORT_POSITION,)

            entry_ordering_types = (backtrader.Order.ACTIVE_ORDERING_TYPE,
                                    backtrader.Order.CONDITIONAL_ORDERING_TYPE,)

            class UT_Strategy(Enhanced_Strategy):
                params = dict(
                    position_types=None,
                    entry_ordering_types=None,
                )

                def __init__(self):
                    super().__init__()

                    # Legality Check
                    assert isinstance(self.p.position_types, tuple)
                    assert isinstance(self.p.entry_ordering_types, tuple)
                    pass

                def next(self):
                    for position_type in self.p.position_types:
                        for entry_ordering_type in self.p.entry_ordering_types:
                            if entry_ordering_type == backtrader.Order.ACTIVE_ORDERING_TYPE:
                                execution_type = backtrader.Order.Limit
                            else:
                                assert entry_ordering_type == backtrader.Order.CONDITIONAL_ORDERING_TYPE

                                if self.account_or_store.exchange_dropdown_value == BYBIT_EXCHANGE_ID:
                                    execution_type = backtrader.Order.Limit
                                else:
                                    execution_type = backtrader.Order.StopLimit

                            # Confirm there is no [Entry] order in exchange
                            # Look for [Entry] orders
                            filter_order__dict = copy.deepcopy(
                                filter_order__dict_template)
                            filter_order__dict[PLURAL__CCXT_ORDER__KEYS[STATUSES]] = \
                                [backtrader.Order.Accepted]
                            filter_order__dict[PLURAL__CCXT_ORDER__KEYS[ORDERING_TYPES]] = \
                                [entry_ordering_type]
                            filter_order__dict[PLURAL__CCXT_ORDER__KEYS[EXECUTION_TYPES]] = \
                                [execution_type]
                            filter_order__dict[PLURAL__CCXT_ORDER__KEYS[ORDER_INTENTS]] = \
                                [backtrader.Order.Entry_Order]
                            filter_order__dict[PLURAL__CCXT_ORDER__KEYS[POSITION_TYPES]] = \
                                [position_type]

                            query__entry_or_exit_order__dict = dict(
                                bt_ccxt_account_or_store=self.account_or_store,
                                instrument=self.instrument,
                                filter_order__dict=filter_order__dict,
                            )
                            opened_bt_ccxt_orders = \
                                query__entry_or_exit_order(
                                    params=query__entry_or_exit_order__dict)

                            if len(opened_bt_ccxt_orders) == 0:
                                # ----------------------------------------------------------------------------------
                                # [Entry] Order
                                # ----------------------------------------------------------------------------------
                                if self.account_or_store.exchange_dropdown_value == BINANCE_EXCHANGE_ID:
                                    offset = 100
                                else:
                                    # In the event if the exchange supported greater than this value, go ahead and
                                    # add another IF statement above
                                    offset = 24

                                (ask, bid,) = \
                                    self.instrument.get_orderbook_price_by_offset(
                                        offset)

                                if entry_ordering_type == backtrader.Order.ACTIVE_ORDERING_TYPE:
                                    entry_price = \
                                        get_order_entry_price_and_queue(
                                            position_type, ask, bid)
                                else:
                                    assert entry_ordering_type == backtrader.Order.CONDITIONAL_ORDERING_TYPE

                                    # Hedging Conditional Order requires entry price as if from opposite position
                                    opposite__position_type = \
                                        get_opposite__position_type(
                                            position_type)
                                    entry_price = \
                                        get_order_entry_price_and_queue(
                                            opposite__position_type, ask, bid)

                                limit_or_conditional_order__dict = dict(
                                    bt_ccxt_account_or_store=self.account_or_store,
                                    instrument=self.instrument,
                                    position_type=position_type,
                                    order_intent=backtrader.Order.Entry_Order,
                                    execution_type=execution_type,
                                    ordering_type=entry_ordering_type,
                                    price=entry_price,
                                )
                                (entry_order, total_time_spent_in_seconds, mock,) = \
                                    ut_enter_or_exit_using_limit_or_conditional_order(
                                        params=limit_or_conditional_order__dict)

                                debugger_running = sys.gettrace() is not None
                                if debugger_running == False:
                                    assert total_time_spent_in_seconds <= MAX__HTTP__REAL_ORDER_WAITING_TIME__IN_SECONDS

                                # Confirm self.account_or_store.notify has been called once (Submitted)
                                calls = \
                                    [call(entry_order)]
                                mock.assert_has_calls(calls)

                                # Confirm the last status
                                assert entry_order.status_name == backtrader.Order.Status[
                                    backtrader.Order.Accepted]
                                assert entry_order.status == backtrader.Order.Accepted

                                # Verify [Entry] order is captured in Persistent Storage
                                read_from_persistent_storage__dict = dict(
                                    exchange_dropdown_value=self.account_or_store.exchange_dropdown_value,
                                    market_type=self.account_or_store.market_type,
                                    main_net_toggle_switch_value=self.account_or_store.main_net_toggle_switch_value,
                                    symbol_id=self.instrument.symbol_id,
                                )
                                dataframe = \
                                    read_from_persistent_storage(
                                        params=read_from_persistent_storage__dict)
                                legality_check_not_none_obj(
                                    dataframe, "dataframe")
                                ccxt_orders_id = \
                                    dataframe[PERSISTENT_STORAGE_CSV_HEADERS[PS_CCXT_ORDER_ID]].tolist(
                                    )

                                # Test Assertion
                                assert len(ccxt_orders_id) == 1
                                assert entry_order.ccxt_id in ccxt_orders_id

                                # ----------------------------------------------------------------------------------
                                # Partially Filled [Entry] Order
                                # ----------------------------------------------------------------------------------
                                get_partially_filled_order__dict = dict(
                                    bt_ccxt_account_or_store=self.account_or_store,
                                    instrument=self.instrument,
                                    ccxt_order_id=entry_order.ccxt_id,
                                )
                                (partially_filled_order, accepted_order,) = \
                                    ut_get_partially_filled_order(
                                        params=get_partially_filled_order__dict)

                                # Test assertion
                                assert partially_filled_order.status_name == \
                                    backtrader.Order.Status[backtrader.Order.Submitted]
                                assert partially_filled_order.status == backtrader.Order.Submitted
                                assert partially_filled_order.partially_filled_earlier == False
                                assert self.account_or_store.partially_filled_earlier == None

                                # Swap with the simulated partially_filled_order
                                self.account_or_store.open_orders.append(
                                    partially_filled_order)

                                # Patch def notify so that we could perform UT assertion if it is called
                                with patch.object(self.account_or_store, 'notify') as mock:
                                    self.account_or_store.next(
                                        ut_provided__new_ccxt_order=True)

                                # Confirm self.account_or_store.notify has been called once (Partial)
                                calls = \
                                    [call(partially_filled_order)]
                                mock.assert_has_calls(calls)

                                # Test assertion
                                assert partially_filled_order.status_name == \
                                    backtrader.Order.Status[backtrader.Order.Partial]
                                assert partially_filled_order.status == backtrader.Order.Partial
                                assert partially_filled_order.partially_filled_earlier == True
                                assert self.account_or_store.partially_filled_earlier == True

                                # Verify partially_filled [Entry] order is captured in Persistent Storage
                                read_from_persistent_storage__dict = dict(
                                    exchange_dropdown_value=self.account_or_store.exchange_dropdown_value,
                                    market_type=self.account_or_store.market_type,
                                    main_net_toggle_switch_value=self.account_or_store.main_net_toggle_switch_value,
                                    symbol_id=self.instrument.symbol_id,
                                )
                                dataframe = \
                                    read_from_persistent_storage(
                                        params=read_from_persistent_storage__dict)
                                legality_check_not_none_obj(
                                    dataframe, "dataframe")
                                ccxt_orders_id = \
                                    dataframe[PERSISTENT_STORAGE_CSV_HEADERS[PS_CCXT_ORDER_ID]].tolist(
                                    )

                                # Test Assertion
                                assert len(ccxt_orders_id) == 1
                                assert partially_filled_order.ccxt_id in ccxt_orders_id

                                # Clean up
                                self.account_or_store.open_orders.pop()
                                pass

                                # ----------------------------------------------------------------------------------
                                # Rejected [Entry] Order
                                # ----------------------------------------------------------------------------------
                                get_rejected_order__dict = dict(
                                    bt_ccxt_account_or_store=self.account_or_store,
                                    instrument=self.instrument,
                                    ccxt_order_id=entry_order.ccxt_id,
                                    accepted_order=accepted_order,
                                )
                                (rejected_order, accepted_order,) = \
                                    ut_get_rejected_order(
                                        params=get_rejected_order__dict)

                                # Test assertion
                                assert rejected_order.status_name == backtrader.Order.Status[
                                    backtrader.Order.Submitted]
                                assert rejected_order.status == backtrader.Order.Submitted

                                # Swap with the simulated rejected_order
                                self.account_or_store.open_orders.append(
                                    rejected_order)

                                # Patch def notify so that we could perform UT assertion if it is called
                                with patch.object(self.account_or_store, 'notify') as mock:
                                    self.account_or_store.next(
                                        ut_provided__new_ccxt_order=True)

                                # Confirm self.account_or_store.notify has been called once (Rejected)
                                calls = \
                                    [call(rejected_order)]
                                mock.assert_has_calls(calls)

                                # We could confirm the last status of rejected order here is due to rejected_order
                                # is injected from this test case
                                # Test assertion
                                assert rejected_order.status_name == backtrader.Order.Status[
                                    backtrader.Order.Rejected]
                                assert rejected_order.status == backtrader.Order.Rejected

                                # Verify rejected [Entry] order is NOT captured in Persistent Storage
                                read_from_persistent_storage__dict = dict(
                                    exchange_dropdown_value=self.account_or_store.exchange_dropdown_value,
                                    market_type=self.account_or_store.market_type,
                                    main_net_toggle_switch_value=self.account_or_store.main_net_toggle_switch_value,
                                    symbol_id=self.instrument.symbol_id,
                                )
                                dataframe = \
                                    read_from_persistent_storage(
                                        params=read_from_persistent_storage__dict)
                                legality_check_not_none_obj(
                                    dataframe, "dataframe")
                                ccxt_orders_id = \
                                    dataframe[PERSISTENT_STORAGE_CSV_HEADERS[PS_CCXT_ORDER_ID]].tolist(
                                    )

                                # Test Assertion
                                assert len(ccxt_orders_id) == 0
                                assert rejected_order.ccxt_id not in ccxt_orders_id

                                # Restore the accepted order earlier
                                self.account_or_store.open_orders.append(
                                    accepted_order)

                                # Since we expected the rejected order will remove ccxt_order_id from
                                # persistent storage, we will have to restore the accepted_order's ccxt_order_id
                                csv_dicts = []
                                csv_dict = {
                                    PERSISTENT_STORAGE_CSV_HEADERS[PS_ORDERING_TYPE]: accepted_order.ordering_type,
                                    PERSISTENT_STORAGE_CSV_HEADERS[PS_CCXT_ORDER_ID]: accepted_order.ccxt_id,
                                }
                                csv_dicts.append(csv_dict)

                                save_to_persistent_storage__dict = dict(
                                    csv_headers=PERSISTENT_STORAGE_CSV_HEADERS,
                                    csv_dicts=csv_dicts,
                                    exchange_dropdown_value=self.account_or_store.exchange_dropdown_value,
                                    market_type=self.account_or_store.market_type,
                                    main_net_toggle_switch_value=self.account_or_store.main_net_toggle_switch_value,
                                    symbol_id=self.instrument.symbol_id,
                                )
                                save_to_persistent_storage(
                                    params=save_to_persistent_storage__dict)
                                pass

                                # ----------------------------------------------------------------------------------
                                # Cancel [Entry] Order
                                # ----------------------------------------------------------------------------------
                                frameinfo = inspect.getframeinfo(
                                    inspect.currentframe())
                                msg = "{}: {}: {} Line: {}: INFO: {}: ".format(
                                    self.account_or_store.exchange_dropdown_value,
                                    CCXT__MARKET_TYPES[self.account_or_store.market_type],
                                    frameinfo.function, frameinfo.lineno,
                                    self.instrument.symbol_id,
                                )
                                sub_msg = "{}: type: {}, entry_order:".format(
                                    backtrader.Order.Ordering_Types[entry_ordering_type],
                                    type(entry_order),
                                )
                                print(msg + sub_msg)
                                pprint(str(entry_order))

                                # [Entry] Order for cancellation must come from open_orders
                                # Look for opened [Entry] orders
                                opened_bt_ccxt_orders = self.instrument.get_open_orders()

                                # Test Assertion
                                assert len(opened_bt_ccxt_orders) == 1

                                # Alias
                                order_for_cancellation = opened_bt_ccxt_orders[0]

                                assert order_for_cancellation.status_name == \
                                    backtrader.Order.Status[backtrader.Order.Accepted]
                                assert order_for_cancellation.status == backtrader.Order.Accepted

                                # Patch def notify so that we could perform UT assertion if it is called
                                with patch.object(self.account_or_store, 'notify') as mock:
                                    cancelled_order_start = timer()

                                    # Cancel the opened position
                                    success = \
                                        self.instrument.cancel(
                                            order_for_cancellation)
                                    assert success

                                    _, cancelled_order_minutes, cancelled_order_seconds = \
                                        get_time_diff(
                                            cancelled_order_start)
                                    print("HTTP [Cancel] Order Took {}m:{:.2f}s".format(
                                        int(cancelled_order_minutes), cancelled_order_seconds)
                                    )

                                    debugger_running = sys.gettrace() is not None
                                    if debugger_running == False:
                                        # Test Assertion
                                        total_time_spent_in_seconds = \
                                            cancelled_order_minutes * 60 + cancelled_order_seconds
                                        assert total_time_spent_in_seconds <= \
                                            MAX__HTTP__REAL_ORDER_WAITING_TIME__IN_SECONDS

                                # Confirm self.account_or_store.notify has been called once (Cancelled)
                                calls = [call(order_for_cancellation)]
                                mock.assert_has_calls(calls)

                                # For Canceled Order, since it has been removed in next(), there is no way to
                                # confirm the last status here
                                pass

                                # Verify canceled [Entry] order is NOT captured in Persistent Storage
                                read_from_persistent_storage__dict = dict(
                                    exchange_dropdown_value=self.account_or_store.exchange_dropdown_value,
                                    market_type=self.account_or_store.market_type,
                                    main_net_toggle_switch_value=self.account_or_store.main_net_toggle_switch_value,
                                    symbol_id=self.instrument.symbol_id,
                                )
                                dataframe = \
                                    read_from_persistent_storage(
                                        params=read_from_persistent_storage__dict)
                                legality_check_not_none_obj(
                                    dataframe, "dataframe")
                                ccxt_orders_id = \
                                    dataframe[PERSISTENT_STORAGE_CSV_HEADERS[PS_CCXT_ORDER_ID]].tolist(
                                    )

                                # Test Assertion
                                assert len(ccxt_orders_id) == 0
                                assert order_for_cancellation.ccxt_id not in ccxt_orders_id

                                # To confirm there is no opened order in queue
                                # Look for [Entry] orders
                                filter_order__dict = \
                                    copy.deepcopy(
                                        filter_order__dict_template)
                                filter_order__dict[PLURAL__CCXT_ORDER__KEYS[STATUSES]] = \
                                    [backtrader.Order.Accepted]
                                filter_order__dict[PLURAL__CCXT_ORDER__KEYS[ORDERING_TYPES]] = \
                                    [entry_ordering_type]
                                filter_order__dict[PLURAL__CCXT_ORDER__KEYS[EXECUTION_TYPES]] = \
                                    [execution_type]
                                filter_order__dict[PLURAL__CCXT_ORDER__KEYS[ORDER_INTENTS]] = \
                                    [backtrader.Order.Entry_Order]
                                filter_order__dict[PLURAL__CCXT_ORDER__KEYS[POSITION_TYPES]] = \
                                    [position_type]

                                query__entry_or_exit_order__dict = dict(
                                    bt_ccxt_account_or_store=self.account_or_store,
                                    instrument=self.instrument,
                                    filter_order__dict=filter_order__dict,
                                )
                                opened_bt_ccxt_orders = \
                                    query__entry_or_exit_order(
                                        params=query__entry_or_exit_order__dict)

                                # Test Assertion
                                assert len(opened_bt_ccxt_orders) == 0
                            else:
                                frameinfo = inspect.getframeinfo(
                                    inspect.currentframe())
                                msg = "{}: {}: {} Line: {}: WARNING: {}: ".format(
                                    self.account_or_store.exchange_dropdown_value,
                                    CCXT__MARKET_TYPES[self.account_or_store.market_type],
                                    frameinfo.function, frameinfo.lineno,
                                    self.instrument.symbol_id,
                                )
                                sub_msg = "{} {} {} order(s) found for {} position".format(
                                    len(opened_bt_ccxt_orders),
                                    backtrader.Order.Ordering_Types[entry_ordering_type],
                                    backtrader.Order.Execution_Types[execution_type],
                                    backtrader.Position.Position_Types[position_type],
                                )
                                print(msg + sub_msg)
                                pass
                    self.cerebro.stop_running(self.instrument)
                    pass

            # Run the tests
            for bt_ccxt_account_or_store in bt_ccxt_account_or_stores:
                for symbol_id in symbols_id:
                    instrument = bt_ccxt_account_or_store.get__child(symbol_id)

                    number_of_empty_positions = 0
                    for dual_position_type in dual_position_types:
                        position = instrument.get_position(dual_position_type)

                        # If there is no opened position
                        if position.price == 0.0:
                            number_of_empty_positions += 1

                    # If there is no opened positions
                    if number_of_empty_positions == 2:
                        for dual_position_type in dual_position_types:
                            # ----------------------------------------------------------------------------------------
                            # Enter using Market Order
                            # ----------------------------------------------------------------------------------------
                            ut_enter_or_exit_using_market_order__dict = dict(
                                bt_ccxt_account_or_store=bt_ccxt_account_or_store,
                                instrument=instrument,
                                position_type=dual_position_type,
                                order_intent=backtrader.Order.Entry_Order,
                            )
                            (entry_order, total_time_spent_in_seconds, mock, ) = \
                                ut_enter_or_exit_using_market_order(
                                    params=ut_enter_or_exit_using_market_order__dict)

                            # Minimum confirmation as the [Entry] Market Order should already have done the coverage
                            self.assertEqual(
                                entry_order.status_name,
                                backtrader.Order.Status[backtrader.Order.Completed])
                            self.assertEqual(
                                entry_order.status, backtrader.Order.Completed)

                            frameinfo = inspect.getframeinfo(
                                inspect.currentframe())
                            msg = "{}: {}: {} Line: {}: INFO: {}: ".format(
                                bt_ccxt_account_or_store.exchange_dropdown_value,
                                CCXT__MARKET_TYPES[bt_ccxt_account_or_store.market_type],
                                frameinfo.function, frameinfo.lineno,
                                instrument.symbol_id,
                            )
                            sub_msg = "{}: type: {}, entry_order:".format(
                                backtrader.Order.Ordering_Types[backtrader.Order.ACTIVE_ORDERING_TYPE],
                                type(entry_order),
                            )
                            print(msg + sub_msg)
                            pprint(str(entry_order))
                    else:
                        msg = "{}: {}: WARNING: {}: ".format(
                            bt_ccxt_account_or_store.exchange_dropdown_value,
                            CCXT__MARKET_TYPES[bt_ccxt_account_or_store.market_type],
                            instrument.symbol_id,
                        )
                        sub_msg = "Unable to detect empty positions. Please retry"
                        print(msg + sub_msg)

                    number_of_opened_positions = 0
                    for dual_position_type in dual_position_types:
                        position = instrument.get_position(dual_position_type)

                        # If there is opened position
                        if position.price != 0.0:
                            number_of_opened_positions += 1

                    # If we are in dual positions
                    if number_of_opened_positions == 2:
                        construct_standalone_cerebro__dict = dict(
                            bt_ccxt_exchange=bt_ccxt_account_or_store.parent,
                        )
                        cerebro = construct_standalone_cerebro(
                            params=construct_standalone_cerebro__dict)

                        bt_ccxt_feed__dict = dict(
                            timeframe=backtrader.TimeFrame.Ticks,
                            drop_newest=False,
                            ut__halt_if_no_ohlcv=True,
                            # debug=True,
                        )

                        construct_dual_position_datafeeds_dict = dict(
                            exchange_dropdown_value=bt_ccxt_account_or_store.exchange_dropdown_value,
                            instrument=instrument,
                            bt_ccxt_feed__dict=bt_ccxt_feed__dict,
                            wallet_currency=wallet_currency,
                        )
                        (long_bb_data, short_bb_data,) = \
                            construct_dual_position_datafeeds(
                                params=construct_dual_position_datafeeds_dict)
                        cerebro.add_datafeed(long_bb_data, name="long_bb_data")
                        cerebro.add_datafeed(
                            short_bb_data, name="short_bb_data")

                        cerebro__strategy__params = dict(
                            is_backtest=False,
                            position_types=position_types,
                            entry_ordering_types=entry_ordering_types,
                        )
                        cerebro.add_strategy(
                            UT_Strategy, **cerebro__strategy__params)
                        cerebro.run()

                        for dual_position_type in dual_position_types:
                            # ------------------------------------------------------------------------------------------
                            # Close using Market Order
                            # ------------------------------------------------------------------------------------------
                            position = instrument.get_position(
                                dual_position_type)

                            # If there is opened position
                            if position.price != 0.0:
                                # To close a position you need to make the inverse operation with same amount
                                ut_enter_or_exit_using_market_order__dict = dict(
                                    bt_ccxt_account_or_store=bt_ccxt_account_or_store,
                                    instrument=instrument,
                                    position_type=dual_position_type,
                                    order_intent=backtrader.Order.Exit_Order,

                                    # Optional Params
                                    size=abs(position.size),
                                )
                                (exit_order, total_time_spent_in_seconds, mock, ) = \
                                    ut_enter_or_exit_using_market_order(
                                        params=ut_enter_or_exit_using_market_order__dict)

                                # Minimum confirmation as the [Exit] Market Order should already have done the coverage
                                self.assertEqual(
                                    exit_order.status_name,
                                    backtrader.Order.Status[backtrader.Order.Completed])
                                self.assertEqual(
                                    exit_order.status, backtrader.Order.Completed)

                                frameinfo = inspect.getframeinfo(
                                    inspect.currentframe())
                                msg = "{}: {}: {} Line: {}: INFO: {}: ".format(
                                    bt_ccxt_account_or_store.exchange_dropdown_value,
                                    CCXT__MARKET_TYPES[bt_ccxt_account_or_store.market_type],
                                    frameinfo.function, frameinfo.lineno,
                                    instrument.symbol_id,
                                )
                                sub_msg = "{}: type: {}, exit_order:".format(
                                    backtrader.Order.Ordering_Types[backtrader.Order.ACTIVE_ORDERING_TYPE],
                                    type(exit_order),
                                )
                                print(msg + sub_msg)
                                pprint(str(exit_order))
                    else:
                        msg = "{}: {}: WARNING: {}: ".format(
                            bt_ccxt_account_or_store.exchange_dropdown_value,
                            CCXT__MARKET_TYPES[bt_ccxt_account_or_store.market_type],
                            instrument.symbol_id,
                        )
                        sub_msg = "Unable to detect dual positions. Please retry"
                        print(msg + sub_msg)
                    pass

                    number_of_empty_positions = 0
                    for dual_position_type in dual_position_types:
                        position = instrument.get_position(dual_position_type)

                        # If there is no opened position
                        if position.price == 0.0:
                            number_of_empty_positions += 1

                    # If there is no opened positions
                    assert number_of_empty_positions == 2
        except Exception:
            traceback.print_exc()

        _, minutes, seconds = get_time_diff(start)
        frameinfo = inspect.getframeinfo(inspect.currentframe())
        print("{} Line: {}: Took {}m:{:.2f}s".format(frameinfo.function, frameinfo.lineno,
                                                     int(minutes), seconds))


if __name__ == '__main__':
    unittest.main()
