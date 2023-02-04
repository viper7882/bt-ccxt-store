import backtrader
import copy
import datetime
import inspect
import threading
import traceback
import unittest

from pprint import pprint
from time import time as timer
from unittest.mock import patch, call

from ccxtbt.bt_ccxt_expansion__helper import query__entry_or_exit_order
from ccxtbt.bt_ccxt_persistent_storage__helper import read_from_persistent_storage, save_to_persistent_storage
from ccxtbt.bt_ccxt__specifications import MIN_LIVE_EXCHANGE_RETRIES, ORDERING_TYPES, STATUSES, CCXT__MARKET_TYPES, \
    CCXT__MARKET_TYPE__FUTURE, \
    CCXT__MARKET_TYPE__LINEAR_PERPETUAL_SWAP, DEFAULT__INITIAL__CAPITAL_RESERVATION__VALUE, \
    DEFAULT__LEVERAGE_IN_PERCENT, EXECUTION_TYPES, \
    ORDER_INTENTS, PLURAL__CCXT_ORDER__KEYS, POSITION_TYPES, filter_order__dict_template
from ccxtbt.exchange.binance.binance__exchange__specifications import BINANCE_EXCHANGE_ID
from ccxtbt.exchange.bybit.bybit__exchange__helper import get_wallet_currency
from ccxtbt.exchange.bybit.bybit__exchange__specifications import BYBIT_EXCHANGE_ID
from ccxtbt.utils import get_opposite__position_type, get_order_entry_price_and_queue, get_order_exit_price_and_queue, \
    get_time_diff, legality_check_not_none_obj

from check_in_gating_tests.common.test__helper import ut_enter_or_exit_using_limit_or_conditional_order, \
    ut_enter_or_exit_using_market_order, ut_get_bt_ccxt_account_or_stores, ut_get_partially_filled_order, \
    ut_get_rejected_order
from check_in_gating_tests.common.test__specifications import MAX__HTTP__REAL_ORDER_WAITING_TIME__IN_SECONDS


class Real_Time_Orders_and_Performance_Check__TestCases(unittest.TestCase):
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

            self.is_ohlcv_provider = False
            self.enable_rate_limit = True

            self.account__thread__connectivity__lock = threading.Lock()
            self.exchange_account__lock = threading.Lock()
            self.symbols_id = ["ETHUSDT", ]
            self.wallet_currency = get_wallet_currency(self.symbols_id[0])

            self.minute_delta = 5
            assert self.minute_delta > 1
            self.latest_utc_dt = datetime.datetime.utcnow()
            self.prev_datetime = \
                self.latest_utc_dt - \
                datetime.timedelta(minutes=self.minute_delta)

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

                # Optional Params
                ut_keep_original_ccxt_order=True,
            )

            get_bt_ccxt_account_or_stores__dict = dict(
                exchange_dropdown_values=self.exchange_dropdown_values,
                target__market_types=self.target__market_types,
                construct_standalone_account_or_store__dict=self.construct_standalone_account_or_store__dict,
            )
            self.bt_ccxt_account_or_stores = \
                ut_get_bt_ccxt_account_or_stores(
                    params=get_bt_ccxt_account_or_stores__dict)

            for exchange_dropdown_value in self.exchange_dropdown_values:
                for market_type in self.target__market_types:
                    for symbol_id in self.symbols_id:
                        # Reset persistent storage
                        save_to_persistent_storage__dict = dict(
                            ccxt_orders_id=[],
                            exchange_dropdown_value=exchange_dropdown_value,
                            market_type=market_type,
                            main_net_toggle_switch_value=self.main_net_toggle_switch_value,
                            symbol_id=symbol_id,
                        )
                        save_to_persistent_storage(
                            params=save_to_persistent_storage__dict)
            pass

            # Legality Check
            assert self.main_net_toggle_switch_value == False, \
                "{} is created to ONLY work in Testnet!!!".format(
                    type(self).__name__)
        except Exception:
            traceback.print_exc()

    def tearDown(self):
        try:
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
    def test_10__strategy_less__entry_and_exit__using_market_order(self):
        start = timer()
        try:
            bt_ccxt_account_or_stores = self.bt_ccxt_account_or_stores
            symbols_id = self.symbols_id

            position_types = (backtrader.Position.LONG_POSITION,
                              backtrader.Position.SHORT_POSITION, )

            exit_ordering_type = entry_ordering_type = backtrader.Order.ACTIVE_ORDERING_TYPE

            # Run the tests
            for bt_ccxt_account_or_store in bt_ccxt_account_or_stores:
                for symbol_id in symbols_id:
                    instrument = bt_ccxt_account_or_store.get__child(symbol_id)

                    for position_type in position_types:
                        position = instrument.get_position(position_type)

                        instrument.sync_symbol_positions()
                        new_position = instrument.get_position(position_type)
                        assert new_position.price == position.price and new_position.size == position.size, \
                            "Expected: {} vs Actual: {}".format(
                                new_position, position)

                        # If there is no opened position
                        if position.price == 0.0:
                            # ------------------------------------------------------------------------------------------
                            # Enter using Market Order
                            # ------------------------------------------------------------------------------------------
                            ut_enter_or_exit_using_market_order__dict = dict(
                                bt_ccxt_account_or_store=bt_ccxt_account_or_store,
                                instrument=instrument,
                                position_type=position_type,
                                order_intent=backtrader.Order.Entry_Order,
                            )
                            (entry_order, total_time_spent_in_seconds, mock, ) = \
                                ut_enter_or_exit_using_market_order(
                                    params=ut_enter_or_exit_using_market_order__dict)
                            self.assertTrue(
                                total_time_spent_in_seconds <= MAX__HTTP__REAL_ORDER_WAITING_TIME__IN_SECONDS)

                            # Confirm bt_ccxt_account_or_store.notify has been called twice (Submitted + Completed)
                            submitted_entry_order = entry_order.clone()
                            submitted_entry_order.submit()
                            calls = \
                                [call(submitted_entry_order),
                                 call(entry_order)]
                            mock.assert_has_calls(calls)

                            # Confirm the last status
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
                                backtrader.Order.Ordering_Types[entry_ordering_type],
                                type(entry_order),
                            )
                            print(msg + sub_msg)
                            pprint(str(entry_order))

                            position = instrument.get_position(position_type)

                            instrument.sync_symbol_positions()
                            new_position = instrument.get_position(
                                position_type)
                            assert new_position.price == position.price and new_position.size == position.size, \
                                "Expected: {} vs Actual: {}".format(
                                    new_position, position)

                            # Test Assertion
                            self.assertTrue(
                                position.price > 0.0, "position.price: {}".format(position.price))

                            if position_type == backtrader.Position.LONG_POSITION:
                                self.assertTrue(
                                    position.size > 0.0, "position.size: {}".format(position.size))
                            else:
                                assert position_type == backtrader.Position.SHORT_POSITION

                                self.assertTrue(
                                    position.size < 0.0, "position.size: {}".format(position.size))

                            # Verify [Entry] Market Order is NOT captured in Persistent Storage eventually
                            read_from_persistent_storage__dict = dict(
                                exchange_dropdown_value=bt_ccxt_account_or_store.exchange_dropdown_value,
                                market_type=bt_ccxt_account_or_store.market_type,
                                main_net_toggle_switch_value=bt_ccxt_account_or_store.main_net_toggle_switch_value,
                                symbol_id=instrument.symbol_id,
                            )
                            ccxt_orders_id = \
                                read_from_persistent_storage(
                                    params=read_from_persistent_storage__dict)

                            # Test Assertion
                            self.assertEqual(len(ccxt_orders_id), 0)
                            self.assertTrue(
                                entry_order.ccxt_id not in ccxt_orders_id)
                        else:
                            msg = "{}: {}: WARNING: {}: ".format(
                                bt_ccxt_account_or_store.exchange_dropdown_value,
                                CCXT__MARKET_TYPES[bt_ccxt_account_or_store.market_type],
                                instrument.symbol_id,
                            )
                            sub_msg = "{}: Position: {} has Price: {:.{}f} x Qty: {:.{}f}. " \
                                      "Unable to open new [Entry] order. Please close the position and retry".format(
                                          backtrader.Order.Ordering_Types[entry_ordering_type],
                                          backtrader.Position.Position_Types[position_type],
                                          position.price, instrument.price_digits,
                                          position.size, instrument.qty_digits,
                                      )
                            print(msg + sub_msg)

                        position = instrument.get_position(position_type)

                        instrument.sync_symbol_positions()
                        new_position = instrument.get_position(position_type)
                        assert new_position.price == position.price and new_position.size == position.size, \
                            "Expected: {} vs Actual: {}".format(
                                new_position, position)

                        # If there is an opened position
                        if position.price > 0.0:
                            # ------------------------------------------------------------------------------------------
                            # Close using Market Order
                            # ------------------------------------------------------------------------------------------
                            # To close a position you need to make the inverse operation with same amount
                            ut_enter_or_exit_using_market_order__dict = dict(
                                bt_ccxt_account_or_store=bt_ccxt_account_or_store,
                                instrument=instrument,
                                position_type=position_type,
                                order_intent=backtrader.Order.Exit_Order,

                                # Optional Params
                                size=abs(position.size),
                            )
                            (exit_order, total_time_spent_in_seconds, mock, ) = \
                                ut_enter_or_exit_using_market_order(
                                    params=ut_enter_or_exit_using_market_order__dict)
                            self.assertTrue(
                                total_time_spent_in_seconds <= MAX__HTTP__REAL_ORDER_WAITING_TIME__IN_SECONDS)

                            # Confirm bt_ccxt_account_or_store.notify has been called twice (Submitted + Completed)
                            submitted_exit_order = exit_order.clone()
                            submitted_exit_order.submit()
                            calls = \
                                [call(submitted_exit_order), call(exit_order)]
                            mock.assert_has_calls(calls)

                            # Confirm the last status
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
                                backtrader.Order.Ordering_Types[exit_ordering_type],
                                type(exit_order),
                            )
                            print(msg + sub_msg)
                            pprint(str(exit_order))

                            position = instrument.get_position(position_type)

                            instrument.sync_symbol_positions()
                            new_position = instrument.get_position(
                                position_type)
                            assert new_position.price == position.price and new_position.size == position.size, \
                                "Expected: {} vs Actual: {}".format(
                                    new_position, position)

                            # Test Assertion
                            self.assertTrue(
                                position.price == 0.0, "position.price: {}".format(position.price))
                            self.assertTrue(
                                position.size == 0.0, "position.size: {}".format(position.size))
                        else:
                            msg = "{}: {}: WARNING: {}: ".format(
                                bt_ccxt_account_or_store.exchange_dropdown_value,
                                CCXT__MARKET_TYPES[bt_ccxt_account_or_store.market_type],
                                instrument.symbol_id,
                            )
                            sub_msg = "{}: Position: {} has Price: {:.{}f} x Qty: {:.{}f}. " \
                                      "Unable to close position. Please open a position and retry".format(
                                          backtrader.Order.Ordering_Types[exit_ordering_type],
                                          backtrader.Position.Position_Types[position_type],
                                          position.price, instrument.price_digits,
                                          position.size, instrument.qty_digits,
                                      )
                            print(msg + sub_msg)
                        pass
            pass
        except Exception:
            traceback.print_exc()

        _, minutes, seconds = get_time_diff(start)
        frameinfo = inspect.getframeinfo(inspect.currentframe())
        print("{} Line: {}: Took {}m:{:.2f}s".format(frameinfo.function, frameinfo.lineno,
                                                     int(minutes), seconds))

    # @unittest.skip("To be enabled")
    # @unittest.skip("Ready for regression")
    def test_20__strategy_less__both_positions__open_and_cancel__entry_order(self):
        start = timer()
        try:
            bt_ccxt_account_or_stores = self.bt_ccxt_account_or_stores
            symbols_id = self.symbols_id

            position_types = (backtrader.Position.LONG_POSITION,
                              backtrader.Position.SHORT_POSITION, )

            entry_ordering_types = (backtrader.Order.ACTIVE_ORDERING_TYPE,
                                    backtrader.Order.CONDITIONAL_ORDERING_TYPE, )

            # Run the tests
            for bt_ccxt_account_or_store in bt_ccxt_account_or_stores:
                for symbol_id in symbols_id:
                    instrument = bt_ccxt_account_or_store.get__child(symbol_id)

                    for position_type in position_types:
                        for entry_ordering_type in entry_ordering_types:
                            if entry_ordering_type == backtrader.Order.ACTIVE_ORDERING_TYPE:
                                execution_type = backtrader.Order.Limit
                            else:
                                assert entry_ordering_type == backtrader.Order.CONDITIONAL_ORDERING_TYPE

                                if bt_ccxt_account_or_store.exchange_dropdown_value == BYBIT_EXCHANGE_ID:
                                    execution_type = backtrader.Order.Limit
                                else:
                                    execution_type = backtrader.Order.StopLimit

                            position = instrument.get_position(position_type)

                            instrument.sync_symbol_positions()
                            new_position = instrument.get_position(
                                position_type)
                            assert new_position.price == position.price and new_position.size == position.size, \
                                "Expected: {} vs Actual: {}".format(
                                    new_position, position)

                            # If there is no opened position
                            if position.price == 0.0:
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

                                if len(opened_bt_ccxt_orders) == 0:
                                    # ----------------------------------------------------------------------------------
                                    # [Entry] Order
                                    # ----------------------------------------------------------------------------------
                                    if bt_ccxt_account_or_store.exchange_dropdown_value == BINANCE_EXCHANGE_ID:
                                        offset = 100
                                    else:
                                        # In the event if the exchange supported greater than this value, go ahead and
                                        # add another IF statement above
                                        offset = 24

                                    (ask, bid, ) = \
                                        instrument.get_orderbook_price_by_offset(
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
                                        bt_ccxt_account_or_store=bt_ccxt_account_or_store,
                                        instrument=instrument,
                                        position_type=position_type,
                                        order_intent=backtrader.Order.Entry_Order,
                                        execution_type=execution_type,
                                        ordering_type=entry_ordering_type,
                                        price=entry_price,
                                    )
                                    (entry_order, total_time_spent_in_seconds, mock, ) = \
                                        ut_enter_or_exit_using_limit_or_conditional_order(
                                            params=limit_or_conditional_order__dict)
                                    self.assertTrue(
                                        total_time_spent_in_seconds <=
                                        MAX__HTTP__REAL_ORDER_WAITING_TIME__IN_SECONDS)

                                    # Confirm bt_ccxt_account_or_store.notify has been called once (Submitted)
                                    calls = \
                                        [call(entry_order)]
                                    mock.assert_has_calls(calls)

                                    # Confirm the last status
                                    self.assertEqual(
                                        entry_order.status_name,
                                        backtrader.Order.Status[backtrader.Order.Accepted])
                                    self.assertEqual(
                                        entry_order.status, backtrader.Order.Accepted)

                                    # Verify [Entry] order is captured in Persistent Storage
                                    read_from_persistent_storage__dict = dict(
                                        exchange_dropdown_value=bt_ccxt_account_or_store.exchange_dropdown_value,
                                        market_type=bt_ccxt_account_or_store.market_type,
                                        main_net_toggle_switch_value=bt_ccxt_account_or_store.main_net_toggle_switch_value,
                                        symbol_id=instrument.symbol_id,
                                    )
                                    ccxt_orders_id = \
                                        read_from_persistent_storage(
                                            params=read_from_persistent_storage__dict)

                                    # Test Assertion
                                    self.assertEqual(len(ccxt_orders_id), 1)
                                    self.assertTrue(
                                        entry_order.ccxt_id in ccxt_orders_id)

                                    # ----------------------------------------------------------------------------------
                                    # Partially Filled [Entry] Order
                                    # ----------------------------------------------------------------------------------
                                    get_partially_filled_order__dict = dict(
                                        bt_ccxt_account_or_store=bt_ccxt_account_or_store,
                                        instrument=instrument,
                                        ccxt_order_id=entry_order.ccxt_id,
                                    )
                                    (partially_filled_order, accepted_order, ) = \
                                        ut_get_partially_filled_order(
                                            params=get_partially_filled_order__dict)

                                    # Test assertion
                                    self.assertEqual(
                                        partially_filled_order.status_name,
                                        backtrader.Order.Status[backtrader.Order.Submitted])
                                    self.assertEqual(
                                        partially_filled_order.status, backtrader.Order.Submitted)
                                    self.assertEqual(
                                        partially_filled_order.partially_filled_earlier, False)
                                    self.assertEqual(
                                        bt_ccxt_account_or_store.partially_filled_earlier, None)

                                    # Swap with the simulated partially_filled_order
                                    bt_ccxt_account_or_store.open_orders.append(
                                        partially_filled_order)

                                    # Patch def notify so that we could perform UT assertion if it is called
                                    with patch.object(bt_ccxt_account_or_store, 'notify') as mock:
                                        bt_ccxt_account_or_store.next(
                                            ut_provided__new_ccxt_order=True)

                                    # Confirm bt_ccxt_account_or_store.notify has been called once (Partial)
                                    calls = \
                                        [call(partially_filled_order)]
                                    mock.assert_has_calls(calls)

                                    # Test assertion
                                    self.assertEqual(
                                        partially_filled_order.status_name,
                                        backtrader.Order.Status[backtrader.Order.Partial])
                                    self.assertEqual(
                                        partially_filled_order.status, backtrader.Order.Partial)
                                    self.assertEqual(
                                        partially_filled_order.partially_filled_earlier, True)
                                    self.assertEqual(
                                        bt_ccxt_account_or_store.partially_filled_earlier, True)

                                    # Verify partially_filled [Entry] order is captured in Persistent Storage
                                    read_from_persistent_storage__dict = dict(
                                        exchange_dropdown_value=bt_ccxt_account_or_store.exchange_dropdown_value,
                                        market_type=bt_ccxt_account_or_store.market_type,
                                        main_net_toggle_switch_value=bt_ccxt_account_or_store.main_net_toggle_switch_value,
                                        symbol_id=instrument.symbol_id,
                                    )
                                    ccxt_orders_id = \
                                        read_from_persistent_storage(
                                            params=read_from_persistent_storage__dict)

                                    # Test Assertion
                                    self.assertEqual(len(ccxt_orders_id), 1)
                                    self.assertTrue(
                                        partially_filled_order.ccxt_id in ccxt_orders_id)

                                    # Clean up
                                    bt_ccxt_account_or_store.open_orders.pop()
                                    pass

                                    # ----------------------------------------------------------------------------------
                                    # Rejected [Entry] Order
                                    # ----------------------------------------------------------------------------------
                                    get_rejected_order__dict = dict(
                                        bt_ccxt_account_or_store=bt_ccxt_account_or_store,
                                        instrument=instrument,
                                        ccxt_order_id=entry_order.ccxt_id,
                                        accepted_order=accepted_order,
                                    )
                                    (rejected_order, accepted_order, ) = \
                                        ut_get_rejected_order(
                                            params=get_rejected_order__dict)

                                    # Test assertion
                                    self.assertEqual(
                                        rejected_order.status_name, backtrader.Order.Status[backtrader.Order.Submitted])
                                    self.assertEqual(
                                        rejected_order.status, backtrader.Order.Submitted)

                                    # Swap with the simulated rejected_order
                                    bt_ccxt_account_or_store.open_orders.append(
                                        rejected_order)

                                    # Patch def notify so that we could perform UT assertion if it is called
                                    with patch.object(bt_ccxt_account_or_store, 'notify') as mock:
                                        bt_ccxt_account_or_store.next(
                                            ut_provided__new_ccxt_order=True)

                                    # Confirm bt_ccxt_account_or_store.notify has been called once (Rejected)
                                    calls = \
                                        [call(rejected_order)]
                                    mock.assert_has_calls(calls)

                                    # We could confirm the last status of rejected order here is due to rejected_order
                                    # is injected from this test case
                                    # Test assertion
                                    self.assertEqual(
                                        rejected_order.status_name, backtrader.Order.Status[backtrader.Order.Rejected])
                                    self.assertEqual(
                                        rejected_order.status, backtrader.Order.Rejected)

                                    # Verify rejected [Entry] order is NOT captured in Persistent Storage
                                    read_from_persistent_storage__dict = dict(
                                        exchange_dropdown_value=bt_ccxt_account_or_store.exchange_dropdown_value,
                                        market_type=bt_ccxt_account_or_store.market_type,
                                        main_net_toggle_switch_value=bt_ccxt_account_or_store.main_net_toggle_switch_value,
                                        symbol_id=instrument.symbol_id,
                                    )
                                    ccxt_orders_id = \
                                        read_from_persistent_storage(
                                            params=read_from_persistent_storage__dict)

                                    # Test Assertion
                                    self.assertEqual(len(ccxt_orders_id), 0)
                                    self.assertTrue(
                                        rejected_order.ccxt_id not in ccxt_orders_id)

                                    # Restore the accepted order earlier
                                    bt_ccxt_account_or_store.open_orders.append(
                                        accepted_order)

                                    # Since we expected the rejected order will remove ccxt_order_id from
                                    # persistent storage, we will have to restore the accepted_order's ccxt_order_id
                                    ccxt_order_id = accepted_order.ccxt_id
                                    save_to_persistent_storage__dict = dict(
                                        ccxt_orders_id=[ccxt_order_id],
                                        exchange_dropdown_value=bt_ccxt_account_or_store.exchange_dropdown_value,
                                        market_type=bt_ccxt_account_or_store.market_type,
                                        main_net_toggle_switch_value=bt_ccxt_account_or_store.main_net_toggle_switch_value,
                                        symbol_id=instrument.symbol_id,
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
                                        bt_ccxt_account_or_store.exchange_dropdown_value,
                                        CCXT__MARKET_TYPES[bt_ccxt_account_or_store.market_type],
                                        frameinfo.function, frameinfo.lineno,
                                        instrument.symbol_id,
                                    )
                                    sub_msg = "{}: type: {}, entry_order:".format(
                                        backtrader.Order.Ordering_Types[entry_ordering_type],
                                        type(entry_order),
                                    )
                                    print(msg + sub_msg)
                                    pprint(str(entry_order))

                                    # [Entry] Order for cancellation must come from open_orders
                                    # Look for opened [Entry] orders
                                    opened_bt_ccxt_orders = instrument.get_open_orders()

                                    # Test Assertion
                                    self.assertEqual(
                                        len(opened_bt_ccxt_orders), 1)

                                    # Alias
                                    order_for_cancellation = opened_bt_ccxt_orders[0]

                                    self.assertEqual(
                                        order_for_cancellation.status_name,
                                        backtrader.Order.Status[backtrader.Order.Accepted])
                                    self.assertEqual(
                                        order_for_cancellation.status, backtrader.Order.Accepted)

                                    position = \
                                        instrument.get_position(position_type)

                                    instrument.sync_symbol_positions()
                                    new_position = instrument.get_position(
                                        position_type)
                                    assert new_position.price == position.price and \
                                        new_position.size == position.size, \
                                        "Expected: {} vs Actual: {}".format(
                                            new_position, position)

                                    # Test Assertion
                                    self.assertTrue(
                                        position.price == 0.0, "position.price: {}".format(position.price))
                                    self.assertTrue(
                                        position.size == 0.0, "position.size: {}".format(position.size))

                                    # Patch def notify so that we could perform UT assertion if it is called
                                    with patch.object(bt_ccxt_account_or_store, 'notify') as mock:
                                        cancelled_order_start = timer()

                                        for _ in range(MIN_LIVE_EXCHANGE_RETRIES):
                                            # Cancel the opened position
                                            success = \
                                                instrument.cancel(
                                                    order_for_cancellation)
                                            if success == True:
                                                break

                                        _, cancelled_order_minutes, cancelled_order_seconds = \
                                            get_time_diff(
                                                cancelled_order_start)
                                        print("HTTP [Cancel] Order Took {}m:{:.2f}s".format(
                                            int(cancelled_order_minutes), cancelled_order_seconds)
                                        )

                                        # Test Assertion
                                        total_time_spent_in_seconds = \
                                            cancelled_order_minutes * 60 + cancelled_order_seconds
                                        self.assertTrue(
                                            total_time_spent_in_seconds <=
                                            MAX__HTTP__REAL_ORDER_WAITING_TIME__IN_SECONDS)

                                    # Confirm bt_ccxt_account_or_store.notify has been called once (Cancelled)
                                    calls = [call(order_for_cancellation)]
                                    mock.assert_has_calls(calls)

                                    # For Canceled Order, since it has been removed in next(), there is no way to
                                    # confirm the last status here
                                    pass

                                    # Verify canceled [Entry] order is NOT captured in Persistent Storage
                                    read_from_persistent_storage__dict = dict(
                                        exchange_dropdown_value=bt_ccxt_account_or_store.exchange_dropdown_value,
                                        market_type=bt_ccxt_account_or_store.market_type,
                                        main_net_toggle_switch_value=bt_ccxt_account_or_store.main_net_toggle_switch_value,
                                        symbol_id=instrument.symbol_id,
                                    )
                                    ccxt_orders_id = \
                                        read_from_persistent_storage(
                                            params=read_from_persistent_storage__dict)

                                    # Test Assertion
                                    self.assertEqual(len(ccxt_orders_id), 0)
                                    self.assertTrue(
                                        order_for_cancellation.ccxt_id not in ccxt_orders_id)

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
                                        bt_ccxt_account_or_store=bt_ccxt_account_or_store,
                                        instrument=instrument,
                                        filter_order__dict=filter_order__dict,
                                    )
                                    opened_bt_ccxt_orders = \
                                        query__entry_or_exit_order(
                                            params=query__entry_or_exit_order__dict)

                                    # Test Assertion
                                    self.assertEqual(
                                        len(opened_bt_ccxt_orders), 0)
                                else:
                                    frameinfo = inspect.getframeinfo(
                                        inspect.currentframe())
                                    msg = "{}: {}: {} Line: {}: WARNING: {}: ".format(
                                        bt_ccxt_account_or_store.exchange_dropdown_value,
                                        CCXT__MARKET_TYPES[bt_ccxt_account_or_store.market_type],
                                        frameinfo.function, frameinfo.lineno,
                                        instrument.symbol_id,
                                    )
                                    sub_msg = "{} {} {} order(s) found for {} position".format(
                                        len(opened_bt_ccxt_orders),
                                        backtrader.Order.Ordering_Types[entry_ordering_type],
                                        backtrader.Order.Execution_Types[execution_type],
                                        backtrader.Position.Position_Types[position_type],
                                    )
                                    print(msg + sub_msg)
                                    pass
                            else:
                                msg = "{}: {}: WARNING: {}: ".format(
                                    bt_ccxt_account_or_store.exchange_dropdown_value,
                                    CCXT__MARKET_TYPES[bt_ccxt_account_or_store.market_type],
                                    instrument.symbol_id,
                                )
                                sub_msg = "{}: Position: {} has Price: {:.{}f} x Qty: {:.{}f}. " \
                                          "Unable to open new [Entry] order. " \
                                          "Please close the position and retry".format(
                                              backtrader.Order.Ordering_Types[entry_ordering_type],
                                              backtrader.Position.Position_Types[position_type],
                                              position.price, instrument.price_digits,
                                              position.size, instrument.qty_digits,
                                          )
                                print(msg + sub_msg)
                            pass
            pass
        except Exception:
            traceback.print_exc()

        _, minutes, seconds = get_time_diff(start)
        frameinfo = inspect.getframeinfo(inspect.currentframe())
        print("{} Line: {}: Took {}m:{:.2f}s".format(frameinfo.function, frameinfo.lineno,
                                                     int(minutes), seconds))

    # @unittest.skip("To be enabled")
    # @unittest.skip("Ready for regression")

    def test_30__strategy_less__exit__using_limit_and_conditional_order(self):
        start = timer()
        try:
            bt_ccxt_account_or_stores = self.bt_ccxt_account_or_stores
            symbols_id = self.symbols_id

            position_types = (backtrader.Position.LONG_POSITION,
                              backtrader.Position.SHORT_POSITION, )

            entry_ordering_type = backtrader.Order.ACTIVE_ORDERING_TYPE

            exit_ordering_types = (backtrader.Order.ACTIVE_ORDERING_TYPE,
                                   backtrader.Order.CONDITIONAL_ORDERING_TYPE, )

            # Run the tests
            for bt_ccxt_account_or_store in bt_ccxt_account_or_stores:
                for symbol_id in symbols_id:
                    instrument = bt_ccxt_account_or_store.get__child(symbol_id)

                    for position_type in position_types:
                        for exit_ordering_type in exit_ordering_types:
                            position = instrument.get_position(position_type)

                            instrument.sync_symbol_positions()
                            new_position = instrument.get_position(
                                position_type)
                            assert new_position.price == position.price and new_position.size == position.size, \
                                "Expected: {} vs Actual: {}".format(
                                    new_position, position)

                            # If there is no opened position
                            if position.price == 0.0:
                                # --------------------------------------------------------------------------------------
                                # Enter using Marker Order
                                # --------------------------------------------------------------------------------------
                                ut_enter_or_exit_using_market_order__dict = dict(
                                    bt_ccxt_account_or_store=bt_ccxt_account_or_store,
                                    instrument=instrument,
                                    position_type=position_type,
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
                                    backtrader.Order.Ordering_Types[entry_ordering_type],
                                    type(entry_order),
                                )
                                print(msg + sub_msg)
                                pprint(str(entry_order))

                                position = instrument.get_position(
                                    position_type)

                                instrument.sync_symbol_positions()
                                new_position = instrument.get_position(
                                    position_type)
                                assert new_position.price == position.price and new_position.size == position.size, \
                                    "Expected: {} vs Actual: {}".format(
                                        new_position, position)

                                # Test Assertion
                                self.assertTrue(
                                    position.price > 0.0, "position.price: {}".format(position.price))

                                if position_type == backtrader.Position.LONG_POSITION:
                                    self.assertTrue(
                                        position.size > 0.0, "position.size: {}".format(position.size))
                                else:
                                    assert position_type == backtrader.Position.SHORT_POSITION

                                    self.assertTrue(
                                        position.size < 0.0, "position.size: {}".format(position.size))
                            else:
                                msg = "{}: {}: WARNING: {}: ".format(
                                    bt_ccxt_account_or_store.exchange_dropdown_value,
                                    CCXT__MARKET_TYPES[bt_ccxt_account_or_store.market_type],
                                    instrument.symbol_id,
                                )
                                sub_msg = "{}: Position: {} has Price: {:.{}f} x Qty: {:.{}f}. " \
                                          "Unable to open new [Entry] order. " \
                                          "Please close the position and retry".format(
                                              backtrader.Order.Ordering_Types[entry_ordering_type],
                                              backtrader.Position.Position_Types[position_type],
                                              position.price, instrument.price_digits,
                                              position.size, instrument.qty_digits,
                                          )
                                print(msg + sub_msg)

                            instrument.sync_symbol_positions()
                            new_position = instrument.get_position(
                                position_type)
                            assert new_position.price == position.price and new_position.size == position.size, \
                                "Expected: {} vs Actual: {}".format(
                                    new_position, position)

                            # If there is an opened position
                            if position.price > 0.0:
                                # --------------------------------------------------------------------------------------
                                # Close using Active Order or Conditional Order
                                # --------------------------------------------------------------------------------------
                                if exit_ordering_type == backtrader.Order.ACTIVE_ORDERING_TYPE:
                                    execution_type = backtrader.Order.Limit
                                else:
                                    assert exit_ordering_type == backtrader.Order.CONDITIONAL_ORDERING_TYPE

                                    if bt_ccxt_account_or_store.exchange_dropdown_value == BYBIT_EXCHANGE_ID:
                                        execution_type = backtrader.Order.Limit
                                    else:
                                        execution_type = backtrader.Order.StopLimit

                                position = instrument.get_position(
                                    position_type)

                                # Confirm there is no [Exit] order in exchange
                                # Look for [Exit] orders
                                filter_order__dict = copy.deepcopy(
                                    filter_order__dict_template)
                                filter_order__dict[PLURAL__CCXT_ORDER__KEYS[STATUSES]] = \
                                    [backtrader.Order.Accepted]
                                filter_order__dict[PLURAL__CCXT_ORDER__KEYS[ORDERING_TYPES]] = \
                                    [exit_ordering_type]
                                filter_order__dict[PLURAL__CCXT_ORDER__KEYS[EXECUTION_TYPES]] = \
                                    [execution_type]
                                filter_order__dict[PLURAL__CCXT_ORDER__KEYS[ORDER_INTENTS]] = \
                                    [backtrader.Order.Exit_Order]
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

                                if len(opened_bt_ccxt_orders) == 0:
                                    # ----------------------------------------------------------------------------------
                                    # [Exit] Order
                                    # ----------------------------------------------------------------------------------
                                    if bt_ccxt_account_or_store.exchange_dropdown_value == BINANCE_EXCHANGE_ID:
                                        offset = 100
                                    else:
                                        # In the event if the exchange supported greater than this value, go ahead and
                                        # add another IF statement above
                                        offset = 24

                                    (ask, bid, ) = \
                                        instrument.get_orderbook_price_by_offset(
                                            offset)

                                    if exit_ordering_type == backtrader.Order.ACTIVE_ORDERING_TYPE:
                                        exit_price = \
                                            get_order_exit_price_and_queue(
                                                position_type, ask, bid)
                                    else:
                                        assert exit_ordering_type == backtrader.Order.CONDITIONAL_ORDERING_TYPE

                                        # Hedging Conditional Order requires exit price as if from opposite position
                                        opposite__position_type = \
                                            get_opposite__position_type(
                                                position_type)
                                        exit_price = \
                                            get_order_exit_price_and_queue(
                                                opposite__position_type, ask, bid)

                                    # Test assertion
                                    self.assertTrue(abs(position.size) > 0.0)
                                    size = abs(position.size)

                                    limit_or_conditional_order__dict = dict(
                                        bt_ccxt_account_or_store=bt_ccxt_account_or_store,
                                        instrument=instrument,
                                        position_type=position_type,
                                        order_intent=backtrader.Order.Exit_Order,
                                        execution_type=execution_type,
                                        ordering_type=exit_ordering_type,
                                        price=exit_price,

                                        # Optional Params
                                        size=size,
                                    )
                                    (exit_order, total_time_spent_in_seconds, mock, ) = \
                                        ut_enter_or_exit_using_limit_or_conditional_order(
                                            params=limit_or_conditional_order__dict)
                                    self.assertTrue(
                                        total_time_spent_in_seconds <=
                                        MAX__HTTP__REAL_ORDER_WAITING_TIME__IN_SECONDS)

                                    # Confirm bt_ccxt_account_or_store.notify has been called once (Submitted)
                                    calls = \
                                        [call(exit_order)]
                                    mock.assert_has_calls(calls)

                                    # Confirm the last status
                                    self.assertEqual(
                                        exit_order.status_name,
                                        backtrader.Order.Status[backtrader.Order.Accepted])
                                    self.assertEqual(
                                        exit_order.status, backtrader.Order.Accepted)

                                    # ----------------------------------------------------------------------------------
                                    # Cancel [Exit] Order
                                    # ----------------------------------------------------------------------------------
                                    frameinfo = inspect.getframeinfo(
                                        inspect.currentframe())
                                    msg = "{}: {}: {} Line: {}: INFO: {}: ".format(
                                        bt_ccxt_account_or_store.exchange_dropdown_value,
                                        CCXT__MARKET_TYPES[bt_ccxt_account_or_store.market_type],
                                        frameinfo.function, frameinfo.lineno,
                                        instrument.symbol_id,
                                    )
                                    sub_msg = "{}: type: {}, exit_order:".format(
                                        backtrader.Order.Ordering_Types[exit_ordering_type],
                                        type(exit_order),
                                    )
                                    print(msg + sub_msg)
                                    pprint(str(exit_order))

                                    # Look for opened [Exit] orders
                                    opened_bt_ccxt_orders = instrument.get_open_orders()

                                    # Test Assertion
                                    self.assertEqual(
                                        len(opened_bt_ccxt_orders), 1)

                                    # Alias
                                    order_for_cancellation = opened_bt_ccxt_orders[0]

                                    position = \
                                        instrument.get_position(position_type)

                                    instrument.sync_symbol_positions()
                                    new_position = instrument.get_position(
                                        position_type)
                                    assert new_position.price == position.price and \
                                        new_position.size == position.size, \
                                        "Expected: {} vs Actual: {}".format(
                                            new_position, position)

                                    # Test Assertion
                                    self.assertTrue(
                                        position.price != 0.0, "position.price: {}".format(position.price))
                                    self.assertTrue(
                                        position.size != 0.0, "position.size: {}".format(position.size))

                                    for _ in range(MIN_LIVE_EXCHANGE_RETRIES):
                                        # Cancel the opened position
                                        success = instrument.cancel(
                                            order_for_cancellation)
                                        if success == True:
                                            break

                                    # For Canceled Order, since it has been removed in next(), there is no way to
                                    # confirm the last status here
                                    pass
                                else:
                                    frameinfo = inspect.getframeinfo(
                                        inspect.currentframe())
                                    msg = "{}: {}: {} Line: {}: WARNING: {}: ".format(
                                        bt_ccxt_account_or_store.exchange_dropdown_value,
                                        CCXT__MARKET_TYPES[bt_ccxt_account_or_store.market_type],
                                        frameinfo.function, frameinfo.lineno,
                                        instrument.symbol_id,
                                    )
                                    sub_msg = "{} {} {} order(s) found for {} position".format(
                                        len(opened_bt_ccxt_orders),
                                        backtrader.Order.Ordering_Types[exit_ordering_type],
                                        backtrader.Order.Execution_Types[execution_type],
                                        backtrader.Position.Position_Types[position_type],
                                    )
                                    print(msg + sub_msg)
                                    pass

                                # --------------------------------------------------------------------------------------
                                # Close using Market Order
                                # --------------------------------------------------------------------------------------
                                # To close a position you need to make the inverse operation with same amount
                                ut_enter_or_exit_using_market_order__dict = dict(
                                    bt_ccxt_account_or_store=bt_ccxt_account_or_store,
                                    instrument=instrument,
                                    position_type=position_type,
                                    order_intent=backtrader.Order.Exit_Order,

                                    # Optional Params
                                    size=abs(position.size),
                                )
                                (exit_order, total_time_spent_in_seconds, mock, ) = \
                                    ut_enter_or_exit_using_market_order(
                                        params=ut_enter_or_exit_using_market_order__dict)

                                # Minimum confirmation on the last status
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
                                    backtrader.Order.Ordering_Types[exit_ordering_type],
                                    type(exit_order),
                                )
                                print(msg + sub_msg)
                                pprint(str(exit_order))

                                position = instrument.get_position(
                                    position_type)

                                instrument.sync_symbol_positions()
                                new_position = instrument.get_position(
                                    position_type)
                                assert new_position.price == position.price and new_position.size == position.size, \
                                    "Expected: {} vs Actual: {}".format(
                                        new_position, position)

                                # Test Assertion
                                self.assertTrue(
                                    position.price == 0.0, "position.price: {}".format(position.price))
                                self.assertTrue(
                                    position.size == 0.0, "position.size: {}".format(position.size))
                            else:
                                msg = "{}: {}: WARNING: {}: ".format(
                                    bt_ccxt_account_or_store.exchange_dropdown_value,
                                    CCXT__MARKET_TYPES[bt_ccxt_account_or_store.market_type],
                                    instrument.symbol_id,
                                )
                                sub_msg = "{}: Position: {} has Price: {:.{}f} x Qty: {:.{}f}. " \
                                          "Unable to close position. Please open a position and retry".format(
                                              backtrader.Order.Ordering_Types[entry_ordering_type],
                                              backtrader.Position.Position_Types[position_type],
                                              position.price, instrument.price_digits,
                                              position.size, instrument.qty_digits,
                                          )
                                print(msg + sub_msg)
                            pass
            pass
        except Exception:
            traceback.print_exc()

        _, minutes, seconds = get_time_diff(start)
        frameinfo = inspect.getframeinfo(inspect.currentframe())
        print("{} Line: {}: Took {}m:{:.2f}s".format(frameinfo.function, frameinfo.lineno,
                                                     int(minutes), seconds))

    # @unittest.skip("To be enabled")
    # @unittest.skip("Ready for regression")
    def test_40__strategy_less__both_positions__open_and_cancel__entry_order(self):
        start = timer()
        try:
            bt_ccxt_account_or_stores = self.bt_ccxt_account_or_stores
            symbols_id = self.symbols_id

            dual_position_types = (backtrader.Position.LONG_POSITION,
                                   backtrader.Position.SHORT_POSITION,)

            position_types = (backtrader.Position.LONG_POSITION,
                              backtrader.Position.SHORT_POSITION,)

            entry_ordering_types = (backtrader.Order.ACTIVE_ORDERING_TYPE,
                                    backtrader.Order.CONDITIONAL_ORDERING_TYPE,)

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
                                position_type=dual_position_type,
                                instrument=instrument,
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

                    number_of_opened_positions = 0
                    for dual_position_type in dual_position_types:
                        position = instrument.get_position(dual_position_type)

                        # If there is opened position
                        if position.price != 0.0:
                            number_of_opened_positions += 1

                    # If we are in dual positions
                    if number_of_opened_positions == 2:
                        for position_type in position_types:
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

                                if len(opened_bt_ccxt_orders) == 0:
                                    # ----------------------------------------------------------------------------------
                                    # [Entry] Order
                                    # ----------------------------------------------------------------------------------
                                    if bt_ccxt_account_or_store.exchange_dropdown_value == BINANCE_EXCHANGE_ID:
                                        offset = 100
                                    else:
                                        # In the event if the exchange supported greater than this value, go ahead and
                                        # add another IF statement above
                                        offset = 24

                                    (ask, bid,) = \
                                        instrument.get_orderbook_price_by_offset(
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
                                        bt_ccxt_account_or_store=bt_ccxt_account_or_store,
                                        instrument=instrument,
                                        position_type=position_type,
                                        order_intent=backtrader.Order.Entry_Order,
                                        execution_type=execution_type,
                                        ordering_type=entry_ordering_type,
                                        price=entry_price,
                                    )
                                    (entry_order, total_time_spent_in_seconds, mock,) = \
                                        ut_enter_or_exit_using_limit_or_conditional_order(
                                            params=limit_or_conditional_order__dict)
                                    self.assertTrue(
                                        total_time_spent_in_seconds <=
                                        MAX__HTTP__REAL_ORDER_WAITING_TIME__IN_SECONDS)

                                    # Confirm bt_ccxt_account_or_store.notify has been called once (Submitted)
                                    calls = \
                                        [call(entry_order)]
                                    mock.assert_has_calls(calls)

                                    # Confirm the last status
                                    self.assertEqual(
                                        entry_order.status_name,
                                        backtrader.Order.Status[backtrader.Order.Accepted])
                                    self.assertEqual(
                                        entry_order.status, backtrader.Order.Accepted)

                                    # Verify [Entry] order is captured in Persistent Storage
                                    read_from_persistent_storage__dict = dict(
                                        exchange_dropdown_value=bt_ccxt_account_or_store.exchange_dropdown_value,
                                        market_type=bt_ccxt_account_or_store.market_type,
                                        main_net_toggle_switch_value=bt_ccxt_account_or_store.main_net_toggle_switch_value,
                                        symbol_id=instrument.symbol_id,
                                    )
                                    ccxt_orders_id = \
                                        read_from_persistent_storage(
                                            params=read_from_persistent_storage__dict)

                                    # Test Assertion
                                    self.assertEqual(len(ccxt_orders_id), 1)
                                    self.assertTrue(
                                        entry_order.ccxt_id in ccxt_orders_id)

                                    # ----------------------------------------------------------------------------------
                                    # Partially Filled [Entry] Order
                                    # ----------------------------------------------------------------------------------
                                    get_partially_filled_order__dict = dict(
                                        bt_ccxt_account_or_store=bt_ccxt_account_or_store,
                                        instrument=instrument,
                                        ccxt_order_id=entry_order.ccxt_id,
                                    )
                                    (partially_filled_order, accepted_order,) = \
                                        ut_get_partially_filled_order(
                                            params=get_partially_filled_order__dict)

                                    # Test assertion
                                    self.assertEqual(
                                        partially_filled_order.status_name,
                                        backtrader.Order.Status[backtrader.Order.Submitted])
                                    self.assertEqual(
                                        partially_filled_order.status, backtrader.Order.Submitted)
                                    self.assertEqual(
                                        partially_filled_order.partially_filled_earlier, False)
                                    self.assertEqual(
                                        bt_ccxt_account_or_store.partially_filled_earlier, None)

                                    # Swap with the simulated partially_filled_order
                                    bt_ccxt_account_or_store.open_orders.append(
                                        partially_filled_order)

                                    # Patch def notify so that we could perform UT assertion if it is called
                                    with patch.object(bt_ccxt_account_or_store, 'notify') as mock:
                                        bt_ccxt_account_or_store.next(
                                            ut_provided__new_ccxt_order=True)

                                    # Confirm bt_ccxt_account_or_store.notify has been called once (Partial)
                                    calls = \
                                        [call(partially_filled_order)]
                                    mock.assert_has_calls(calls)

                                    # Test assertion
                                    self.assertEqual(
                                        partially_filled_order.status_name,
                                        backtrader.Order.Status[backtrader.Order.Partial])
                                    self.assertEqual(
                                        partially_filled_order.status, backtrader.Order.Partial)
                                    self.assertEqual(
                                        partially_filled_order.partially_filled_earlier, True)
                                    self.assertEqual(
                                        bt_ccxt_account_or_store.partially_filled_earlier, True)

                                    # Verify partially_filled [Entry] order is captured in Persistent Storage
                                    read_from_persistent_storage__dict = dict(
                                        exchange_dropdown_value=bt_ccxt_account_or_store.exchange_dropdown_value,
                                        market_type=bt_ccxt_account_or_store.market_type,
                                        main_net_toggle_switch_value=bt_ccxt_account_or_store.main_net_toggle_switch_value,
                                        symbol_id=instrument.symbol_id,
                                    )
                                    ccxt_orders_id = \
                                        read_from_persistent_storage(
                                            params=read_from_persistent_storage__dict)

                                    # Test Assertion
                                    self.assertEqual(len(ccxt_orders_id), 1)
                                    self.assertTrue(
                                        partially_filled_order.ccxt_id in ccxt_orders_id)

                                    # Clean up
                                    bt_ccxt_account_or_store.open_orders.pop()
                                    pass

                                    # ----------------------------------------------------------------------------------
                                    # Rejected [Entry] Order
                                    # ----------------------------------------------------------------------------------
                                    get_rejected_order__dict = dict(
                                        bt_ccxt_account_or_store=bt_ccxt_account_or_store,
                                        instrument=instrument,
                                        ccxt_order_id=entry_order.ccxt_id,
                                        accepted_order=accepted_order,
                                    )
                                    (rejected_order, accepted_order,) = \
                                        ut_get_rejected_order(
                                            params=get_rejected_order__dict)

                                    # Test assertion
                                    self.assertEqual(
                                        rejected_order.status_name, backtrader.Order.Status[backtrader.Order.Submitted])
                                    self.assertEqual(
                                        rejected_order.status, backtrader.Order.Submitted)

                                    # Swap with the simulated rejected_order
                                    bt_ccxt_account_or_store.open_orders.append(
                                        rejected_order)

                                    # Patch def notify so that we could perform UT assertion if it is called
                                    with patch.object(bt_ccxt_account_or_store, 'notify') as mock:
                                        bt_ccxt_account_or_store.next(
                                            ut_provided__new_ccxt_order=True)

                                    # Confirm bt_ccxt_account_or_store.notify has been called once (Rejected)
                                    calls = \
                                        [call(rejected_order)]
                                    mock.assert_has_calls(calls)

                                    # We could confirm the last status of rejected order here is due to rejected_order
                                    # is injected from this test case
                                    # Test assertion
                                    self.assertEqual(
                                        rejected_order.status_name, backtrader.Order.Status[backtrader.Order.Rejected])
                                    self.assertEqual(
                                        rejected_order.status, backtrader.Order.Rejected)

                                    # Verify rejected [Entry] order is NOT captured in Persistent Storage
                                    read_from_persistent_storage__dict = dict(
                                        exchange_dropdown_value=bt_ccxt_account_or_store.exchange_dropdown_value,
                                        market_type=bt_ccxt_account_or_store.market_type,
                                        main_net_toggle_switch_value=bt_ccxt_account_or_store.main_net_toggle_switch_value,
                                        symbol_id=instrument.symbol_id,
                                    )
                                    ccxt_orders_id = \
                                        read_from_persistent_storage(
                                            params=read_from_persistent_storage__dict)

                                    # Test Assertion
                                    self.assertEqual(len(ccxt_orders_id), 0)
                                    self.assertTrue(
                                        rejected_order.ccxt_id not in ccxt_orders_id)

                                    # Restore the accepted order earlier
                                    bt_ccxt_account_or_store.open_orders.append(
                                        accepted_order)

                                    # Since we expected the rejected order will remove ccxt_order_id from
                                    # persistent storage, we will have to restore the accepted_order's ccxt_order_id
                                    ccxt_order_id = accepted_order.ccxt_id
                                    save_to_persistent_storage__dict = dict(
                                        ccxt_orders_id=[ccxt_order_id],
                                        exchange_dropdown_value=bt_ccxt_account_or_store.exchange_dropdown_value,
                                        market_type=bt_ccxt_account_or_store.market_type,
                                        main_net_toggle_switch_value=bt_ccxt_account_or_store.main_net_toggle_switch_value,
                                        symbol_id=instrument.symbol_id,
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
                                        bt_ccxt_account_or_store.exchange_dropdown_value,
                                        CCXT__MARKET_TYPES[bt_ccxt_account_or_store.market_type],
                                        frameinfo.function, frameinfo.lineno,
                                        instrument.symbol_id,
                                    )
                                    sub_msg = "{}: type: {}, entry_order:".format(
                                        backtrader.Order.Ordering_Types[entry_ordering_type],
                                        type(entry_order),
                                    )
                                    print(msg + sub_msg)
                                    pprint(str(entry_order))

                                    # [Entry] Order for cancellation must come from open_orders
                                    # Look for opened [Entry] orders
                                    opened_bt_ccxt_orders = instrument.get_open_orders()

                                    # Test Assertion
                                    self.assertEqual(
                                        len(opened_bt_ccxt_orders), 1)

                                    # Alias
                                    order_for_cancellation = opened_bt_ccxt_orders[0]

                                    self.assertEqual(
                                        order_for_cancellation.status_name,
                                        backtrader.Order.Status[backtrader.Order.Accepted])
                                    self.assertEqual(
                                        order_for_cancellation.status, backtrader.Order.Accepted)

                                    # Patch def notify so that we could perform UT assertion if it is called
                                    with patch.object(bt_ccxt_account_or_store, 'notify') as mock:
                                        cancelled_order_start = timer()

                                        for _ in range(MIN_LIVE_EXCHANGE_RETRIES):
                                            # Cancel the opened position
                                            success = \
                                                instrument.cancel(
                                                    order_for_cancellation)
                                            if success == True:
                                                break

                                        _, cancelled_order_minutes, cancelled_order_seconds = \
                                            get_time_diff(
                                                cancelled_order_start)
                                        print("HTTP [Cancel] Order Took {}m:{:.2f}s".format(
                                            int(cancelled_order_minutes), cancelled_order_seconds)
                                        )

                                        # Test Assertion
                                        total_time_spent_in_seconds = \
                                            cancelled_order_minutes * 60 + cancelled_order_seconds
                                        self.assertTrue(
                                            total_time_spent_in_seconds <=
                                            MAX__HTTP__REAL_ORDER_WAITING_TIME__IN_SECONDS)

                                    # Confirm bt_ccxt_account_or_store.notify has been called once (Cancelled)
                                    calls = [call(order_for_cancellation)]
                                    mock.assert_has_calls(calls)

                                    # For Canceled Order, since it has been removed in next(), there is no way to
                                    # confirm the last status here
                                    pass

                                    # Verify canceled [Entry] order is NOT captured in Persistent Storage
                                    read_from_persistent_storage__dict = dict(
                                        exchange_dropdown_value=bt_ccxt_account_or_store.exchange_dropdown_value,
                                        market_type=bt_ccxt_account_or_store.market_type,
                                        main_net_toggle_switch_value=bt_ccxt_account_or_store.main_net_toggle_switch_value,
                                        symbol_id=instrument.symbol_id,
                                    )
                                    ccxt_orders_id = \
                                        read_from_persistent_storage(
                                            params=read_from_persistent_storage__dict)

                                    # Test Assertion
                                    self.assertEqual(len(ccxt_orders_id), 0)
                                    self.assertTrue(
                                        order_for_cancellation.ccxt_id not in ccxt_orders_id)

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
                                        bt_ccxt_account_or_store=bt_ccxt_account_or_store,
                                        instrument=instrument,
                                        filter_order__dict=filter_order__dict,
                                    )
                                    opened_bt_ccxt_orders = \
                                        query__entry_or_exit_order(
                                            params=query__entry_or_exit_order__dict)

                                    # Test Assertion
                                    self.assertEqual(
                                        len(opened_bt_ccxt_orders), 0)
                                else:
                                    frameinfo = inspect.getframeinfo(
                                        inspect.currentframe())
                                    msg = "{}: {}: {} Line: {}: WARNING: {}: ".format(
                                        bt_ccxt_account_or_store.exchange_dropdown_value,
                                        CCXT__MARKET_TYPES[bt_ccxt_account_or_store.market_type],
                                        frameinfo.function, frameinfo.lineno,
                                        instrument.symbol_id,
                                    )
                                    sub_msg = "{} {} {} order(s) found for {} position".format(
                                        len(opened_bt_ccxt_orders),
                                        backtrader.Order.Ordering_Types[entry_ordering_type],
                                        backtrader.Order.Execution_Types[execution_type],
                                        backtrader.Position.Position_Types[position_type],
                                    )
                                    print(msg + sub_msg)
                                    pass
                    else:
                        msg = "{}: {}: WARNING: {}: ".format(
                            bt_ccxt_account_or_store.exchange_dropdown_value,
                            CCXT__MARKET_TYPES[bt_ccxt_account_or_store.market_type],
                            instrument.symbol_id,
                        )
                        sub_msg = "Unable to detect dual positions. Please retry"
                        print(msg + sub_msg)
                    pass
        except Exception:
            traceback.print_exc()

        _, minutes, seconds = get_time_diff(start)
        frameinfo = inspect.getframeinfo(inspect.currentframe())
        print("{} Line: {}: Took {}m:{:.2f}s".format(frameinfo.function, frameinfo.lineno,
                                                     int(minutes), seconds))

    # @unittest.skip("To be enabled")
    # @unittest.skip("Ready for regression")
    def test_50__strategy_less__power_cycle(self):
        start = timer()
        try:
            exchange_dropdown_values = self.exchange_dropdown_values
            target__market_types = self.target__market_types
            construct_standalone_account_or_store__dict = self.construct_standalone_account_or_store__dict
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

                            if len(opened_bt_ccxt_orders) == 0:
                                # ----------------------------------------------------------------------------------
                                # [Entry] Order
                                # ----------------------------------------------------------------------------------
                                if bt_ccxt_account_or_store.exchange_dropdown_value == BINANCE_EXCHANGE_ID:
                                    offset = 100
                                else:
                                    # In the event if the exchange supported greater than this value, go ahead and
                                    # add another IF statement above
                                    offset = 24

                                (ask, bid,) = \
                                    instrument.get_orderbook_price_by_offset(
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
                                    bt_ccxt_account_or_store=bt_ccxt_account_or_store,
                                    instrument=instrument,
                                    position_type=position_type,
                                    order_intent=backtrader.Order.Entry_Order,
                                    execution_type=execution_type,
                                    ordering_type=entry_ordering_type,
                                    price=entry_price,
                                )
                                (entry_order, total_time_spent_in_seconds, mock,) = \
                                    ut_enter_or_exit_using_limit_or_conditional_order(
                                        params=limit_or_conditional_order__dict)
                                self.assertTrue(
                                    total_time_spent_in_seconds <=
                                    MAX__HTTP__REAL_ORDER_WAITING_TIME__IN_SECONDS)

                                # Confirm bt_ccxt_account_or_store.notify has been called once (Submitted)
                                calls = \
                                    [call(entry_order)]
                                mock.assert_has_calls(calls)

                                # Confirm the last status
                                self.assertEqual(
                                    entry_order.status_name,
                                    backtrader.Order.Status[backtrader.Order.Accepted])
                                self.assertEqual(
                                    entry_order.status, backtrader.Order.Accepted)

                                # Verify [Entry] order is captured in Persistent Storage
                                read_from_persistent_storage__dict = dict(
                                    exchange_dropdown_value=bt_ccxt_account_or_store.exchange_dropdown_value,
                                    market_type=bt_ccxt_account_or_store.market_type,
                                    main_net_toggle_switch_value=bt_ccxt_account_or_store.main_net_toggle_switch_value,
                                    symbol_id=instrument.symbol_id,
                                )
                                ccxt_orders_id = \
                                    read_from_persistent_storage(
                                        params=read_from_persistent_storage__dict)

                                # Test Assertion
                                self.assertTrue(
                                    entry_order.ccxt_id in ccxt_orders_id)

            # Run the tests using new bt_ccxt_account_or_stores instances
            def callback_func__identify_calls(params):
                # Un-serialize Params
                bt_ccxt_account_or_store = params['bt_ccxt_account_or_store']
                instrument = params['instrument']

                entry_orders = \
                    [open_order for open_order in bt_ccxt_account_or_store.open_orders
                     if open_order.symbol_id == instrument.symbol_id]

                # Confirm bt_ccxt_account_or_store.notify has been called once for each order
                calls = []
                for entry_order in entry_orders:
                    calls.append(call(entry_order))
                return calls

            get_bt_ccxt_account_or_stores__dict = dict(
                exchange_dropdown_values=exchange_dropdown_values,
                target__market_types=target__market_types,
                construct_standalone_account_or_store__dict=construct_standalone_account_or_store__dict,

                # Optional Params
                callback_func__has_calls=callback_func__identify_calls,
            )
            accepted__bt_ccxt_account_or_stores = \
                ut_get_bt_ccxt_account_or_stores(
                    params=get_bt_ccxt_account_or_stores__dict)

            for accepted__bt_ccxt_account_or_store in accepted__bt_ccxt_account_or_stores:
                for symbol_id in symbols_id:
                    instrument = accepted__bt_ccxt_account_or_store.get__child(
                        symbol_id)

                    for position_type in position_types:
                        for entry_ordering_type in entry_ordering_types:
                            if entry_ordering_type == backtrader.Order.ACTIVE_ORDERING_TYPE:
                                execution_type = backtrader.Order.Limit
                            else:
                                assert entry_ordering_type == backtrader.Order.CONDITIONAL_ORDERING_TYPE

                                if accepted__bt_ccxt_account_or_store.exchange_dropdown_value == BYBIT_EXCHANGE_ID:
                                    execution_type = backtrader.Order.Limit
                                else:
                                    execution_type = backtrader.Order.StopLimit

                            # Confirm there is one [Entry] order in exchange
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
                                bt_ccxt_account_or_store=accepted__bt_ccxt_account_or_store,
                                instrument=instrument,
                                filter_order__dict=filter_order__dict,
                            )
                            opened_bt_ccxt_orders = \
                                query__entry_or_exit_order(
                                    params=query__entry_or_exit_order__dict)

                            if len(opened_bt_ccxt_orders) == 1:
                                # Alias
                                opened_bt_ccxt_order = opened_bt_ccxt_orders[0]

                                # ----------------------------------------------------------------------------------
                                # Cancel [Entry] Order
                                # ----------------------------------------------------------------------------------
                                # [Entry] Order for cancellation must come from open_orders
                                entry_order = None
                                open_orders = instrument.get_open_orders()
                                for open_order in open_orders:
                                    if opened_bt_ccxt_order.ccxt_id == open_order.ccxt_id:
                                        entry_order = open_order
                                        break
                                legality_check_not_none_obj(
                                    entry_order, "entry_order")

                                frameinfo = inspect.getframeinfo(
                                    inspect.currentframe())
                                msg = "{}: {}: {} Line: {}: INFO: {}: ".format(
                                    accepted__bt_ccxt_account_or_store.exchange_dropdown_value,
                                    CCXT__MARKET_TYPES[accepted__bt_ccxt_account_or_store.market_type],
                                    frameinfo.function, frameinfo.lineno,
                                    instrument.symbol_id,
                                )
                                sub_msg = "{}: type: {}, entry_order:".format(
                                    backtrader.Order.Ordering_Types[entry_ordering_type],
                                    type(entry_order),
                                )
                                print(msg + sub_msg)
                                pprint(str(entry_order))

                                # Alias
                                order_for_cancellation = entry_order

                                self.assertEqual(
                                    order_for_cancellation.status_name,
                                    backtrader.Order.Status[backtrader.Order.Accepted])
                                self.assertEqual(
                                    order_for_cancellation.status, backtrader.Order.Accepted)

                                # Patch def notify so that we could perform UT assertion if it is called
                                with patch.object(accepted__bt_ccxt_account_or_store, 'notify') as mock:
                                    cancelled_order_start = timer()

                                    for _ in range(MIN_LIVE_EXCHANGE_RETRIES):
                                        # Cancel the opened position
                                        success = \
                                            instrument.cancel(
                                                order_for_cancellation)
                                        if success == True:
                                            break

                                    _, cancelled_order_minutes, cancelled_order_seconds = \
                                        get_time_diff(
                                            cancelled_order_start)
                                    print("HTTP [Cancel] Order Took {}m:{:.2f}s".format(
                                        int(cancelled_order_minutes), cancelled_order_seconds)
                                    )

                                    # Test Assertion
                                    total_time_spent_in_seconds = \
                                        cancelled_order_minutes * 60 + cancelled_order_seconds
                                    self.assertTrue(
                                        total_time_spent_in_seconds <=
                                        MAX__HTTP__REAL_ORDER_WAITING_TIME__IN_SECONDS)

                                # Confirm accepted__bt_ccxt_account_or_store.notify has been called once (Cancelled)
                                calls = [call(order_for_cancellation)]
                                mock.assert_has_calls(calls)

                                # For Canceled Order, since it has been removed in next(), there is no way to
                                # confirm the last status here
                                pass

                                # Verify canceled [Entry] order is NOT captured in Persistent Storage
                                read_from_persistent_storage__dict = dict(
                                    exchange_dropdown_value=accepted__bt_ccxt_account_or_store.exchange_dropdown_value,
                                    market_type=accepted__bt_ccxt_account_or_store.market_type,
                                    main_net_toggle_switch_value=accepted__bt_ccxt_account_or_store.main_net_toggle_switch_value,
                                    symbol_id=instrument.symbol_id,
                                )
                                ccxt_orders_id = \
                                    read_from_persistent_storage(
                                        params=read_from_persistent_storage__dict)

                                # Test Assertion
                                self.assertTrue(
                                    order_for_cancellation.ccxt_id not in ccxt_orders_id)

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
                                    bt_ccxt_account_or_store=accepted__bt_ccxt_account_or_store,
                                    instrument=instrument,
                                    filter_order__dict=filter_order__dict,
                                )
                                opened_bt_ccxt_orders = \
                                    query__entry_or_exit_order(
                                        params=query__entry_or_exit_order__dict)

                                # Test Assertion
                                self.assertEqual(
                                    len(opened_bt_ccxt_orders), 0)
                            else:
                                frameinfo = inspect.getframeinfo(
                                    inspect.currentframe())
                                msg = "{}: {}: {} Line: {}: WARNING: {}: ".format(
                                    accepted__bt_ccxt_account_or_store.exchange_dropdown_value,
                                    CCXT__MARKET_TYPES[accepted__bt_ccxt_account_or_store.market_type],
                                    frameinfo.function, frameinfo.lineno,
                                    instrument.symbol_id,
                                )
                                sub_msg = "{} {} {} order(s) found for {} position".format(
                                    len(opened_bt_ccxt_orders),
                                    backtrader.Order.Ordering_Types[entry_ordering_type],
                                    backtrader.Order.Execution_Types[execution_type],
                                    backtrader.Position.Position_Types[position_type],
                                )
                                print(msg + sub_msg)
                                pass
        except Exception:
            traceback.print_exc()

        _, minutes, seconds = get_time_diff(start)
        frameinfo = inspect.getframeinfo(inspect.currentframe())
        print("{} Line: {}: Took {}m:{:.2f}s".format(frameinfo.function, frameinfo.lineno,
                                                     int(minutes), seconds))

    # @unittest.skip("To be enabled")
    # @unittest.skip("Ready for regression")

    def test_51__strategy_less__power_cycle__non_accepted_ccxt_order(self):
        start = timer()
        try:
            exchange_dropdown_values = self.exchange_dropdown_values
            target__market_types = self.target__market_types
            construct_standalone_account_or_store__dict = self.construct_standalone_account_or_store__dict
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

                            if len(opened_bt_ccxt_orders) == 0:
                                # ----------------------------------------------------------------------------------
                                # [Entry] Order
                                # ----------------------------------------------------------------------------------
                                if bt_ccxt_account_or_store.exchange_dropdown_value == BINANCE_EXCHANGE_ID:
                                    offset = 100
                                else:
                                    # In the event if the exchange supported greater than this value, go ahead and
                                    # add another IF statement above
                                    offset = 24

                                (ask, bid,) = \
                                    instrument.get_orderbook_price_by_offset(
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
                                    bt_ccxt_account_or_store=bt_ccxt_account_or_store,
                                    instrument=instrument,
                                    position_type=position_type,
                                    order_intent=backtrader.Order.Entry_Order,
                                    execution_type=execution_type,
                                    ordering_type=entry_ordering_type,
                                    price=entry_price,
                                )
                                (entry_order, total_time_spent_in_seconds, mock,) = \
                                    ut_enter_or_exit_using_limit_or_conditional_order(
                                        params=limit_or_conditional_order__dict)
                                self.assertTrue(
                                    total_time_spent_in_seconds <=
                                    MAX__HTTP__REAL_ORDER_WAITING_TIME__IN_SECONDS)

                                # Confirm bt_ccxt_account_or_store.notify has been called once (Submitted)
                                calls = \
                                    [call(entry_order)]
                                mock.assert_has_calls(calls)

                                # Confirm the last status
                                self.assertEqual(
                                    entry_order.status_name,
                                    backtrader.Order.Status[backtrader.Order.Accepted])
                                self.assertEqual(
                                    entry_order.status, backtrader.Order.Accepted)

                                # Verify [Entry] order is captured in Persistent Storage
                                read_from_persistent_storage__dict = dict(
                                    exchange_dropdown_value=bt_ccxt_account_or_store.exchange_dropdown_value,
                                    market_type=bt_ccxt_account_or_store.market_type,
                                    main_net_toggle_switch_value=bt_ccxt_account_or_store.main_net_toggle_switch_value,
                                    symbol_id=instrument.symbol_id,
                                )
                                ccxt_orders_id = \
                                    read_from_persistent_storage(
                                        params=read_from_persistent_storage__dict)

                                # Test Assertion
                                self.assertTrue(
                                    entry_order.ccxt_id in ccxt_orders_id)

            # Run the tests using new bt_ccxt_account_or_stores instances
            get_bt_ccxt_account_or_stores__dict = dict(
                exchange_dropdown_values=exchange_dropdown_values,
                target__market_types=target__market_types,
                construct_standalone_account_or_store__dict=construct_standalone_account_or_store__dict,

                # Optional Params
                ut_assert_not_called=True,
                ut_keep_original_ccxt_order=True,
                ut_clear_opened_bt_status=True,
            )
            non_accepted__bt_ccxt_account_or_stores = \
                ut_get_bt_ccxt_account_or_stores(
                    params=get_bt_ccxt_account_or_stores__dict)

            for non_accepted__bt_ccxt_account_or_store in non_accepted__bt_ccxt_account_or_stores:
                for symbol_id in symbols_id:
                    instrument = non_accepted__bt_ccxt_account_or_store.get__child(
                        symbol_id)

                    # Verify [Entry] order is NO longer present in Persistent Storage
                    read_from_persistent_storage__dict = dict(
                        exchange_dropdown_value=non_accepted__bt_ccxt_account_or_store.exchange_dropdown_value,
                        market_type=non_accepted__bt_ccxt_account_or_store.market_type,
                        main_net_toggle_switch_value=non_accepted__bt_ccxt_account_or_store.main_net_toggle_switch_value,
                        symbol_id=instrument.symbol_id,
                    )
                    ccxt_orders_id = \
                        read_from_persistent_storage(
                            params=read_from_persistent_storage__dict)

                    # Test assertion
                    self.assertEqual(len(ccxt_orders_id), 0)

            for non_accepted__bt_ccxt_account_or_store in non_accepted__bt_ccxt_account_or_stores:
                for symbol_id in symbols_id:
                    instrument = non_accepted__bt_ccxt_account_or_store.get__child(
                        symbol_id)

                    for position_type in position_types:
                        for entry_ordering_type in entry_ordering_types:
                            if entry_ordering_type == backtrader.Order.ACTIVE_ORDERING_TYPE:
                                execution_type = backtrader.Order.Limit
                            else:
                                assert entry_ordering_type == backtrader.Order.CONDITIONAL_ORDERING_TYPE

                                if non_accepted__bt_ccxt_account_or_store.exchange_dropdown_value == BYBIT_EXCHANGE_ID:
                                    execution_type = backtrader.Order.Limit
                                else:
                                    execution_type = backtrader.Order.StopLimit

                            # Confirm there is one [Entry] order in exchange
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
                                bt_ccxt_account_or_store=non_accepted__bt_ccxt_account_or_store,
                                instrument=instrument,
                                filter_order__dict=filter_order__dict,
                            )
                            opened_bt_ccxt_orders = \
                                query__entry_or_exit_order(
                                    params=query__entry_or_exit_order__dict)

                            if len(opened_bt_ccxt_orders) == 1:
                                # Alias
                                opened_bt_ccxt_order = opened_bt_ccxt_orders[0]

                                # ----------------------------------------------------------------------------------
                                # Cancel [Entry] Order
                                # ----------------------------------------------------------------------------------
                                # [Entry] Order for cancellation must come from open_orders
                                # Locate the opened BT CCXT order
                                unmodified_bt_ccxt_orders = \
                                    [bt_ccxt_order for bt_ccxt_order in
                                     non_accepted__bt_ccxt_account_or_store.bt_ccxt_orders
                                     if opened_bt_ccxt_order.ccxt_id == bt_ccxt_order.ccxt_id]

                                # Test assertion
                                self.assertEqual(
                                    len(unmodified_bt_ccxt_orders), 1)

                                entry_order = unmodified_bt_ccxt_orders[0]
                                non_accepted__bt_ccxt_account_or_store.open_orders.append(
                                    entry_order)

                                frameinfo = inspect.getframeinfo(
                                    inspect.currentframe())
                                msg = "{}: {}: {} Line: {}: INFO: {}: ".format(
                                    non_accepted__bt_ccxt_account_or_store.exchange_dropdown_value,
                                    CCXT__MARKET_TYPES[non_accepted__bt_ccxt_account_or_store.market_type],
                                    frameinfo.function, frameinfo.lineno,
                                    instrument.symbol_id,
                                )
                                sub_msg = "{}: type: {}, entry_order:".format(
                                    backtrader.Order.Ordering_Types[entry_ordering_type],
                                    type(entry_order),
                                )
                                print(msg + sub_msg)
                                pprint(str(entry_order))

                                # Alias
                                order_for_cancellation = entry_order

                                self.assertEqual(
                                    order_for_cancellation.status_name,
                                    backtrader.Order.Status[backtrader.Order.Submitted])
                                self.assertEqual(
                                    order_for_cancellation.status, backtrader.Order.Submitted)

                                # Patch def notify so that we could perform UT assertion if it is called
                                with patch.object(non_accepted__bt_ccxt_account_or_store, 'notify') as mock:
                                    cancelled_order_start = timer()

                                    for _ in range(MIN_LIVE_EXCHANGE_RETRIES):
                                        # Cancel the opened position
                                        success = \
                                            instrument.cancel(
                                                order_for_cancellation)
                                        if success == True:
                                            break

                                    _, cancelled_order_minutes, cancelled_order_seconds = \
                                        get_time_diff(
                                            cancelled_order_start)
                                    print("HTTP [Cancel] Order Took {}m:{:.2f}s".format(
                                        int(cancelled_order_minutes), cancelled_order_seconds)
                                    )

                                    # Test Assertion
                                    total_time_spent_in_seconds = \
                                        cancelled_order_minutes * 60 + cancelled_order_seconds
                                    self.assertTrue(
                                        total_time_spent_in_seconds <=
                                        MAX__HTTP__REAL_ORDER_WAITING_TIME__IN_SECONDS)

                                # Confirm non_accepted__bt_ccxt_account_or_store.notify has been called once (Cancelled)
                                calls = [call(order_for_cancellation)]
                                mock.assert_has_calls(calls)

                                # For Canceled Order, since it has been removed in next(), there is no way to
                                # confirm the last status here
                                pass

                                # Verify canceled [Entry] order is NOT captured in Persistent Storage
                                read_from_persistent_storage__dict = dict(
                                    exchange_dropdown_value=non_accepted__bt_ccxt_account_or_store.exchange_dropdown_value,
                                    market_type=non_accepted__bt_ccxt_account_or_store.market_type,
                                    main_net_toggle_switch_value=non_accepted__bt_ccxt_account_or_store.main_net_toggle_switch_value,
                                    symbol_id=instrument.symbol_id,
                                )
                                ccxt_orders_id = \
                                    read_from_persistent_storage(
                                        params=read_from_persistent_storage__dict)

                                # Test Assertion
                                self.assertTrue(
                                    order_for_cancellation.ccxt_id not in ccxt_orders_id)

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
                                    bt_ccxt_account_or_store=non_accepted__bt_ccxt_account_or_store,
                                    instrument=instrument,
                                    filter_order__dict=filter_order__dict,
                                )
                                opened_bt_ccxt_orders = \
                                    query__entry_or_exit_order(
                                        params=query__entry_or_exit_order__dict)

                                # Test Assertion
                                self.assertEqual(
                                    len(opened_bt_ccxt_orders), 0)
                            else:
                                frameinfo = inspect.getframeinfo(
                                    inspect.currentframe())
                                msg = "{}: {}: {} Line: {}: WARNING: {}: ".format(
                                    non_accepted__bt_ccxt_account_or_store.exchange_dropdown_value,
                                    CCXT__MARKET_TYPES[non_accepted__bt_ccxt_account_or_store.market_type],
                                    frameinfo.function, frameinfo.lineno,
                                    instrument.symbol_id,
                                )
                                sub_msg = "{} {} {} order(s) found for {} position".format(
                                    len(opened_bt_ccxt_orders),
                                    backtrader.Order.Ordering_Types[entry_ordering_type],
                                    backtrader.Order.Execution_Types[execution_type],
                                    backtrader.Position.Position_Types[position_type],
                                )
                                print(msg + sub_msg)
                                pass
        except Exception:
            traceback.print_exc()

        _, minutes, seconds = get_time_diff(start)
        frameinfo = inspect.getframeinfo(inspect.currentframe())
        print("{} Line: {}: Took {}m:{:.2f}s".format(frameinfo.function, frameinfo.lineno,
                                                     int(minutes), seconds))


if __name__ == '__main__':
    unittest.main()
