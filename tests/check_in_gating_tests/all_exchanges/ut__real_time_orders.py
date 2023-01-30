import backtrader
import copy
import datetime
import inspect
import threading
import traceback
import unittest

from pprint import pprint
from time import time as timer
from unittest.mock import Mock, MagicMock, patch, create_autospec, call

from ccxtbt.bt_ccxt_feed__classes import BT_CCXT_Feed
from ccxtbt.bt_ccxt_order__helper import get_filtered_orders
from ccxtbt.bt_ccxt__specifications import MIN_LIVE_EXCHANGE_RETRIES, STATUSES, CCXT__MARKET_TYPES, \
    CCXT__MARKET_TYPE__FUTURE, \
    CCXT__MARKET_TYPE__LINEAR_PERPETUAL_SWAP, CCXT__MARKET_TYPE__SPOT, \
    DEFAULT__INITIAL__CAPITAL_RESERVATION__VALUE, DEFAULT__LEVERAGE_IN_PERCENT, EXECUTION_TYPES, \
    MAX_LIVE_EXCHANGE_RETRIES, \
    ORDERING_TYPES, ORDER_INTENTS, PLURAL__CCXT_ORDER__KEYS, POSITION_TYPES, filter_order__dict_template
from ccxtbt.exchange.binance.binance__exchange__specifications import BINANCE_EXCHANGE_ID, BINANCE_OHLCV_LIMIT
from ccxtbt.exchange.bybit.bybit__exchange__helper import get_wallet_currency
from ccxtbt.exchange.bybit.bybit__exchange__specifications import BYBIT_EXCHANGE_ID
from ccxtbt.exchange.exchange__helper import get_minimum_instrument_quantity
from ccxtbt.utils import get_opposite__position_type, get_order_entry_price_and_queue, get_time_diff

from check_in_gating_tests.common.test__helper import ut_get_valid_market_types
from ccxtbt.bt_ccxt_expansion__helper import construct_standalone_account_or_store, construct_standalone_exchange, \
    construct_standalone_instrument
from check_in_gating_tests.common.test__specifications import MAX__HTTP__REAL_ORDER_WAITING_TIME__IN_SECONDS


class Real_Time_Orders_and_Performance_Check__TestCases(unittest.TestCase):
    def setUp(self):
        try:
            self.exchange_dropdown_values = (
                BINANCE_EXCHANGE_ID, BYBIT_EXCHANGE_ID, )

            target__market_types = \
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

            self.bt_ccxt_account_or_stores = []

            for exchange_dropdown_value in self.exchange_dropdown_values:
                symbols_id = self.symbols_id
                enable_rate_limit = self.enable_rate_limit
                initial__capital_reservation__value = self.initial__capital_reservation__value
                is_ohlcv_provider = self.is_ohlcv_provider
                account__thread__connectivity__lock = self.account__thread__connectivity__lock
                leverage_in_percent = self.leverage_in_percent
                main_net_toggle_switch_value = self.main_net_toggle_switch_value
                isolated_toggle_switch_value = self.isolated_toggle_switch_value
                wallet_currency = self.wallet_currency

                # Construct the components
                market_types = ut_get_valid_market_types(
                    exchange_dropdown_value, target__market_types)
                for market_type in market_types:
                    construct_standalone_exchange__dict = dict(
                        exchange_dropdown_value=exchange_dropdown_value,
                    )
                    bt_ccxt_exchange = construct_standalone_exchange(
                        params=construct_standalone_exchange__dict)

                    construct_standalone_account_or_store__dict = dict(
                        exchange_dropdown_value=exchange_dropdown_value,
                        main_net_toggle_switch_value=main_net_toggle_switch_value,
                        isolated_toggle_switch_value=isolated_toggle_switch_value,
                        leverage_in_percent=leverage_in_percent,
                        market_type=market_type,
                        symbols_id=symbols_id,
                        enable_rate_limit=enable_rate_limit,
                        initial__capital_reservation__value=initial__capital_reservation__value,
                        is_ohlcv_provider=is_ohlcv_provider,
                        account__thread__connectivity__lock=account__thread__connectivity__lock,
                        wallet_currency=wallet_currency,

                        # Optional Params
                        bt_ccxt_exchange=bt_ccxt_exchange,
                    )
                    (bt_ccxt_account_or_store, exchange_specific_config, ) = \
                        construct_standalone_account_or_store(
                            params=construct_standalone_account_or_store__dict)

                    for symbol_id in symbols_id:
                        construct_standalone_instrument__dict = dict(
                            bt_ccxt_account_or_store=bt_ccxt_account_or_store,
                            market_type=market_type,
                            symbol_id=symbol_id,
                        )
                        construct_standalone_instrument(
                            params=construct_standalone_instrument__dict)
                        instrument = bt_ccxt_account_or_store.get__child(
                            symbol_id)

                        custom__bt_ccxt_feed__dict = dict(
                            timeframe=backtrader.TimeFrame.Ticks,
                            drop_newest=False,
                            ut__halt_if_no_ohlcv=True,
                            # debug=True,
                        )

                        # Validate assumption made
                        assert isinstance(custom__bt_ccxt_feed__dict, dict)

                        # Long datafeed
                        bt_ccxt_feed__dict = dict(
                            exchange=exchange_dropdown_value,
                            name=backtrader.Position.Position_Types[backtrader.Position.LONG_POSITION],
                            dataname=symbol_id,
                            ohlcv_limit=BINANCE_OHLCV_LIMIT,
                            currency=wallet_currency,
                            config=exchange_specific_config,
                            max_retries=MAX_LIVE_EXCHANGE_RETRIES,
                        )
                        bt_ccxt_feed__dict.update(custom__bt_ccxt_feed__dict)
                        self.long_bb_data = BT_CCXT_Feed(**bt_ccxt_feed__dict)
                        self.long_bb_data.set__parent(instrument)

                        # Short datafeed
                        bt_ccxt_feed__dict = dict(
                            exchange=exchange_dropdown_value,
                            name=backtrader.Position.Position_Types[backtrader.Position.SHORT_POSITION],
                            dataname=symbol_id,
                            ohlcv_limit=BINANCE_OHLCV_LIMIT,
                            currency=wallet_currency,
                            config=exchange_specific_config,
                            max_retries=MAX_LIVE_EXCHANGE_RETRIES,
                        )
                        bt_ccxt_feed__dict.update(custom__bt_ccxt_feed__dict)
                        self.short_bb_data = BT_CCXT_Feed(**bt_ccxt_feed__dict)
                        self.short_bb_data.set__parent(instrument)

                    self.bt_ccxt_account_or_stores.append(
                        bt_ccxt_account_or_store)
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
                            offset = 0
                            (nearest_ask, nearest_bid,) = \
                                instrument.get_orderbook_price_by_offset(
                                    offset)

                            price = \
                                get_order_entry_price_and_queue(
                                    position_type, nearest_ask, nearest_bid)
                            size = \
                                get_minimum_instrument_quantity(
                                    price, instrument)

                            entry__dict = dict(
                                owner=self,
                                symbol_id=symbol_id,
                                size=size,
                                execution_type=backtrader.Order.Market,
                                ordering_type=entry_ordering_type,
                                order_intent=backtrader.Order.Entry_Order,
                                position_type=position_type,

                                # CCXT requires the market type name to be specified correctly
                                type=CCXT__MARKET_TYPES[bt_ccxt_account_or_store.market_type],
                            )

                            # Patch def notify so that we could perform UT assertion if it is called
                            with patch.object(bt_ccxt_account_or_store, 'notify') as mock:
                                entry_order_start = timer()
                                if position_type == backtrader.Position.LONG_POSITION:
                                    entry_order = instrument.buy(**entry__dict)
                                else:
                                    assert position_type == backtrader.Position.SHORT_POSITION

                                    entry_order = instrument.sell(
                                        **entry__dict)

                                _, entry_order_minutes, entry_order_seconds = \
                                    get_time_diff(entry_order_start)
                                print("HTTP [Entry] Order Took {}m:{:.2f}s".format(
                                    int(entry_order_minutes), entry_order_seconds)
                                )
                                # Test Assertion
                                total_time_spent_in_seconds = entry_order_minutes * 60 + entry_order_seconds
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

                        # Close using Market Order
                        position = instrument.get_position(position_type)

                        instrument.sync_symbol_positions()
                        new_position = instrument.get_position(position_type)
                        assert new_position.price == position.price and new_position.size == position.size, \
                            "Expected: {} vs Actual: {}".format(
                                new_position, position)

                        # If there is an opened position
                        if position.price > 0.0:
                            # To close a position you need to make the inverse operation with same amount
                            exit__dict = dict(
                                owner=self,
                                symbol_id=symbol_id,
                                size=abs(position.size),
                                execution_type=backtrader.Order.Market,
                                ordering_type=exit_ordering_type,
                                order_intent=backtrader.Order.Exit_Order,
                                position_type=position_type,

                                # CCXT requires the market type name to be specified correctly
                                type=CCXT__MARKET_TYPES[bt_ccxt_account_or_store.market_type],
                            )

                            # Patch def notify so that we could perform UT assertion if it is called
                            with patch.object(bt_ccxt_account_or_store, 'notify') as mock:
                                exit_order_start = timer()

                                if position_type == backtrader.Position.LONG_POSITION:
                                    exit_order = instrument.sell(**exit__dict)
                                else:
                                    assert position_type == backtrader.Position.SHORT_POSITION

                                    exit_order = instrument.buy(**exit__dict)
                                _, exit_order_minutes, exit_order_seconds = \
                                    get_time_diff(exit_order_start)
                                print("HTTP [Exit] Order Took {}m:{:.2f}s".format(
                                    int(exit_order_minutes), exit_order_seconds)
                                )
                                # Test Assertion
                                total_time_spent_in_seconds = exit_order_minutes * 60 + exit_order_seconds
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
                                fetch_opened_orders__dict = dict(
                                    # CCXT requires the market type name to be specified correctly
                                    type=CCXT__MARKET_TYPES[bt_ccxt_account_or_store.market_type],

                                )
                                opened_ccxt_orders = \
                                    instrument.fetch_opened_orders(since=None,
                                                                   limit=None,
                                                                   params=fetch_opened_orders__dict)

                                if bt_ccxt_account_or_store.exchange_dropdown_value == BYBIT_EXCHANGE_ID:
                                    fetch_opened_orders__dict.update(dict(
                                        stop=True,
                                    ))
                                    opened_ccxt_orders += \
                                        instrument.fetch_opened_orders(since=None,
                                                                       limit=None,
                                                                       params=fetch_opened_orders__dict)

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

                                get_filtered_orders__dict = dict(
                                    filter_order__dict=filter_order__dict,
                                    orders=opened_ccxt_orders,
                                )
                                opened_ccxt_orders = \
                                    get_filtered_orders(
                                        params=get_filtered_orders__dict)

                                if len(opened_ccxt_orders) == 0:
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

                                    size = \
                                        get_minimum_instrument_quantity(
                                            entry_price, instrument)

                                    entry__dict = dict(
                                        owner=self,
                                        symbol_id=symbol_id,
                                        price=entry_price,
                                        size=size,
                                        execution_type=execution_type,
                                        ordering_type=entry_ordering_type,
                                        order_intent=backtrader.Order.Entry_Order,
                                        position_type=position_type,

                                        # CCXT requires the market type name to be specified correctly
                                        type=CCXT__MARKET_TYPES[bt_ccxt_account_or_store.market_type],
                                    )
                                    if entry_ordering_type == backtrader.Order.CONDITIONAL_ORDERING_TYPE:
                                        entry__dict.update(dict(
                                            stopPrice=entry_price,
                                        ))
                                        if bt_ccxt_account_or_store.exchange_dropdown_value == BYBIT_EXCHANGE_ID:
                                            offset = 0
                                            (nearest_ask, nearest_bid,) = \
                                                instrument.get_orderbook_price_by_offset(
                                                    offset)

                                            base_price = \
                                                get_order_entry_price_and_queue(
                                                    position_type, nearest_ask, nearest_bid)

                                            # Bybit requires to configure base price
                                            entry__dict.update(dict(
                                                base_price=base_price,
                                            ))

                                    # Patch def notify so that we could perform UT assertion if it is called
                                    with patch.object(bt_ccxt_account_or_store, 'notify') as mock:
                                        entry_order_start = timer()
                                        if position_type == backtrader.Position.LONG_POSITION:
                                            entry_order = instrument.buy(
                                                **entry__dict)
                                        else:
                                            assert position_type == backtrader.Position.SHORT_POSITION

                                            entry_order = instrument.sell(
                                                **entry__dict)
                                        _, entry_order_minutes, entry_order_seconds = \
                                            get_time_diff(entry_order_start)
                                        print("HTTP [Entry] Order Took {}m:{:.2f}s".format(
                                            int(entry_order_minutes), entry_order_seconds)
                                        )
                                        # Test Assertion
                                        total_time_spent_in_seconds = entry_order_minutes * 60 + entry_order_seconds
                                        self.assertTrue(
                                            total_time_spent_in_seconds <=
                                            MAX__HTTP__REAL_ORDER_WAITING_TIME__IN_SECONDS)

                                    # Confirm bt_ccxt_account_or_store.notify has been called once (Submitted)
                                    calls = \
                                        [call(entry_order)]
                                    mock.assert_has_calls(calls)

                                    # Confirm the last status
                                    self.assertEqual(
                                        entry_order.status, backtrader.Order.Accepted)

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

                                    # TODO: Check if the entry order is stored into persistent storage

                                    fetch_opened_orders__dict = dict(
                                        # CCXT requires the market type name to be specified correctly
                                        type=CCXT__MARKET_TYPES[bt_ccxt_account_or_store.market_type],

                                    )
                                    opened_ccxt_orders = \
                                        instrument.fetch_opened_orders(since=None,
                                                                       limit=None,
                                                                       params=fetch_opened_orders__dict)

                                    if bt_ccxt_account_or_store.exchange_dropdown_value == BYBIT_EXCHANGE_ID:
                                        fetch_opened_orders__dict.update(dict(
                                            stop=True,
                                        ))
                                        opened_ccxt_orders += \
                                            instrument.fetch_opened_orders(since=None,
                                                                           limit=None,
                                                                           params=fetch_opened_orders__dict)

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

                                    get_filtered_orders__dict = dict(
                                        filter_order__dict=filter_order__dict,
                                        orders=opened_ccxt_orders,
                                    )
                                    opened_ccxt_orders = \
                                        get_filtered_orders(
                                            params=get_filtered_orders__dict)

                                    # Test Assertion
                                    self.assertEqual(
                                        len(opened_ccxt_orders), 1)

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
                                            # Cancel the opened order
                                            success = instrument.cancel(
                                                opened_ccxt_orders[0])
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
                                    calls = [call(opened_ccxt_orders[0])]
                                    mock.assert_has_calls(calls)

                                    # Confirm the last status
                                    self.assertEqual(
                                        opened_ccxt_orders[0].status, backtrader.Order.Canceled)
                                    pass

                                    # To confirm there is no opened order in queue
                                    fetch_opened_orders__dict = dict(
                                        # CCXT requires the market type name to be specified correctly
                                        type=CCXT__MARKET_TYPES[bt_ccxt_account_or_store.market_type],

                                    )
                                    opened_ccxt_orders = \
                                        instrument.fetch_opened_orders(since=None,
                                                                       limit=None,
                                                                       params=fetch_opened_orders__dict)

                                    if bt_ccxt_account_or_store.exchange_dropdown_value == BYBIT_EXCHANGE_ID:
                                        fetch_opened_orders__dict.update(dict(
                                            stop=True,
                                        ))
                                        opened_ccxt_orders += \
                                            instrument.fetch_opened_orders(since=None,
                                                                           limit=None,
                                                                           params=fetch_opened_orders__dict)

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

                                    get_filtered_orders__dict = dict(
                                        filter_order__dict=filter_order__dict,
                                        orders=opened_ccxt_orders,
                                    )
                                    opened_ccxt_orders = \
                                        get_filtered_orders(
                                            params=get_filtered_orders__dict)

                                    # Test Assertion
                                    self.assertEqual(
                                        len(opened_ccxt_orders), 0)

                                    # TODO: Check if the entry order is removed from persistent storage
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
                                        len(opened_ccxt_orders),
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


if __name__ == '__main__':
    unittest.main()
