import backtrader
import copy
import inspect
import itertools
import operator

from ccxtbt.utils import legality_check_not_none_obj
from ccxtbt.trade.trade__classes import Enhanced_Trade


class Enhanced_Strategy(backtrader.Strategy):
    params = dict(
        is_backtest=None,
    )

    def __init__(self):
        super().__init__()

        # Legality Check
        assert isinstance(self.p.is_backtest, bool)

        # Derived attributes
        self.instrument = self.datafeed.get__parent()
        self.account_or_store = self.instrument.get__parent()
        self.broker_or_exchange = self.account_or_store.get__parent()

    # --------------------------------------------------------------------------------------------
    # Extension from original
    # --------------------------------------------------------------------------------------------
    def get_position(self, position_type, symbol_id=None, instrument=None, debug=False):
        '''
        Returns the current position for a given instrument.

        A property ``position`` is also available
        '''
        if instrument is None:
            instrument = self.get_instrument(symbol_id=symbol_id)
        return instrument.get_position(position_type, debug=debug)

    def set_position(self, position_type, size, price, symbol_id=None, instrument=None, debug=False):
        '''
        Stores the position for a given datafeed in a given broker_or_exchange.

        If both are None, the main datafeed and the default broker_or_exchange will be used
        '''
        if instrument is None:
            instrument = self.get_instrument(symbol_id=symbol_id)
        instrument.set_position(position_type, size, price, debug=debug)

    # --------------------------------------------------------------------------------------------
    # Customization from original
    # --------------------------------------------------------------------------------------------
    def _next(self, account_or_store, instrument, debug=False):
        self.pre_ind_next(debug=debug)
        super()._next(account_or_store, instrument, debug=debug)

        min_per_status = self._get_min_per_status()

        # # TODO: Debug use
        # dlens = list(map(operator.sub, self._min_periods, map(len, self.datafeeds)))
        # frameinfo = inspect.getframeinfo(inspect.currentframe())
        # msg = "{} Line: {}: {}: {}: _min_periods: {} vs dlens: {}, min_per_status: {}".format(
        #     frameinfo.function, frameinfo.lineno,
        #     self.p.symbol_id,
        #     datetime.datetime.utcnow().isoformat().replace("T", " ")[:-3],
        #     self._min_periods,
        #     dlens,
        #     min_per_status,
        # )
        # print(msg)

        self._next_analyzers(min_per_status)
        self._next_observers(min_per_status)

        self.clear()

    def _get_min_per_status(self):
        # check the min period status connected to datafeeds
        dlens = map(operator.sub, self._min_periods, map(len, self.datafeeds))

        self._min_per_status = min_per_status = max(dlens)
        return min_per_status

    def _notify(self, account_or_store, instrument, qorders=[], qtrades=[]):
        if self.cerebro.p.quicknotify:
            # need to know if quicknotify is on, to not reprocess pendingorders
            # and pendingtrades, which have to exist for things like observers
            # which look into it
            procorders = qorders
            proctrades = qtrades
        else:
            procorders = self._orderspending
            proctrades = self._trades_pending

        for order in procorders:
            if order.execution_type != order.Historical or order.histnotify:
                self.notify_order(order)
            for analyzer in itertools.chain(self.analyzers,
                                            self._slave_analyzers):
                analyzer._notify_order(order)

        for trade in proctrades:
            self.notify_trade(trade)
            for analyzer in itertools.chain(self.analyzers,
                                            self._slave_analyzers):
                analyzer._notify_trade(trade)

        if qorders:
            return  # cash is notified on a regular basis

        cash = instrument.get_cash()
        value = instrument.get_value()
        fundvalue = account_or_store.fundvalue
        fundshares = account_or_store.fundshares

        self.notify_cashvalue(cash, value)
        self.notify_fund(cash, value, fundvalue, fundshares)
        for analyzer in itertools.chain(self.analyzers, self._slave_analyzers):
            analyzer._notify_cashvalue(cash, value)
            analyzer._notify_fund(cash, value, fundvalue, fundshares)

    def pre_ind_next(self, debug):
        '''
        Allow the children class to handle pre-indicator processing if required
        '''
        pass

    def close(self, instrument, position_type=None, size=None, **kwargs):
        '''
        Counters a long/short position closing it

        See the documentation for ``buy`` for an explanation of the parameters

        Note:

          - ``size``: automatically calculated from the existing position if
            not provided (default: ``None``) by the caller

        Returns: the submitted order
        '''
        possize = self.get_position(position_type, **kwargs).size
        size = abs(size if size is not None else possize)

        if possize > 0:
            return self.sell(symbol_id=self.p.symbol_id, position_type=position_type, size=size,
                             instrument=instrument,
                             **kwargs)
        elif possize < 0:
            return self.buy(position_type=position_type, size=size,
                            instrument=instrument,
                            **kwargs)

        return None

    def buy(self, symbol_id=None, datafeed=None, instrument=None, position_type=None,
            size=None, price=None, base_price=None, price_limit=None,
            execution_type=None, valid=None, tradeid=0, oco=None,
            trailing_amount=None, trailing_percent=None,
            parent=None, transmit=True,
            **kwargs):
        if isinstance(datafeed, backtrader.string_types):
            datafeed = self.get_datafeed_by_name(datafeed)

        # Legality Check
        legality_check_not_none_obj(symbol_id, "symbol_id")
        legality_check_not_none_obj(instrument, "instrument")
        legality_check_not_none_obj(position_type, "position_type")

        # Live
        if self.p.is_backtest == False:
            if datafeed is None:
                if size is None:
                    msg = "{} Line: {}: Since both datafeed and size are absent, Buy is skipped!!!".format(
                        inspect.getframeinfo(inspect.currentframe()).function,
                        inspect.getframeinfo(inspect.currentframe()).lineno,
                    )
                    raise RuntimeError(msg)

            if datafeed is not None:
                size = abs(size) if size is not None else self.getsizing(
                    datafeed, instrument, position_type)
                return instrument.buy(
                    self, symbol_id, datafeed,
                    size=size, price=price, price_limit=price_limit,
                    execution_type=execution_type, valid=valid, tradeid=tradeid, oco=oco,
                    trailing_amount=trailing_amount, trailing_percent=trailing_percent,
                    parent=parent, transmit=transmit, position_type=position_type,
                    **kwargs)

        # Backtest
        else:
            datafeed = datafeed if datafeed is not None else self.datafeeds[0]
            size = size if size is not None else self.getsizing(
                datafeed, instrument, position_type)
            if size:
                size = abs(size)
                return instrument.buy(
                    self, symbol_id, datafeed,
                    size=size, price=price, base_price=base_price, price_limit=price_limit,
                    execution_type=execution_type, valid=valid, tradeid=tradeid, oco=oco,
                    trailing_amount=trailing_amount, trailing_percent=trailing_percent,
                    parent=parent, transmit=transmit, position_type=position_type,
                    **kwargs)

        return None

    def sell(self, symbol_id=None, datafeed=None, instrument=None, position_type=None,
             size=None, price=None, base_price=None, price_limit=None,
             execution_type=None, valid=None, tradeid=0, oco=None,
             trailing_amount=None, trailing_percent=None,
             parent=None, transmit=True,
             **kwargs):
        if isinstance(datafeed, backtrader.string_types):
            datafeed = self.get_datafeed_by_name(datafeed)

        # Legality Check
        legality_check_not_none_obj(symbol_id, "symbol_id")
        legality_check_not_none_obj(position_type, "position_type")
        legality_check_not_none_obj(position_type, "position_type")

        # Live
        if self.p.is_backtest == False:
            if datafeed is None:
                if size is None:
                    msg = "{} Line: {}: Since both datafeed and size are absent, Sell is skipped!!!".format(
                        inspect.getframeinfo(inspect.currentframe()).function,
                        inspect.getframeinfo(inspect.currentframe()).lineno,
                    )
                    raise RuntimeError(msg)

            if datafeed is not None:
                size = abs(size) if size is not None else self.getsizing(
                    datafeed, instrument, position_type)

                return instrument.sell(
                    self, symbol_id, datafeed,
                    size=size, price=price, price_limit=price_limit,
                    execution_type=execution_type, valid=valid, tradeid=tradeid, oco=oco,
                    trailing_amount=trailing_amount, trailing_percent=trailing_percent,
                    parent=parent, transmit=transmit, position_type=position_type,
                    **kwargs)

        # Backtest
        else:
            datafeed = datafeed if datafeed is not None else self.datafeeds[0]
            size = size if size is not None else self.getsizing(
                datafeed, instrument, position_type)

            if size:
                return instrument.sell(
                    self, symbol_id, datafeed,
                    size=abs(size), price=price, base_price=base_price, price_limit=price_limit,
                    execution_type=execution_type, valid=valid, tradeid=tradeid, oco=oco,
                    trailing_amount=trailing_amount, trailing_percent=trailing_percent,
                    parent=parent, transmit=transmit, position_type=position_type,
                    **kwargs)

        return None

    def _add_notification(self, order, quicknotify=False):
        if not order.p.simulated:
            self._orderspending.append(order)

        qorders = []
        qtrades = []
        if quicknotify:
            qorders = [order]

        # For partially filled order, even if it goes flow through the trade, there is no execution bit.
        #       Nothing will be done inside def flow_through_trade.

        # Avoid flow_through_trade for Conditional Order that is yet to be triggered
        if not order.executed.size or \
                (order.ordering_type == backtrader.Order.CONDITIONAL_ORDERING_TYPE and order.triggered == False):
            if quicknotify:
                self._notify(qorders=qorders, qtrades=qtrades)
            return

        qtrades = self.flow_through_trade(order, quicknotify, qtrades)
        if quicknotify:
            self._notify(qorders=qorders, qtrades=qtrades)

    def flow_through_trade(self, order, quicknotify, qtrades=[], custom_trade=None) -> list:
        tradedata = order.datafeed._compensate
        if tradedata is None:
            tradedata = order.datafeed

        if custom_trade is None:
            datatrades = self._trades[tradedata][order.tradeid]
            if not datatrades:
                trade = Enhanced_Trade(
                    datafeed=tradedata, tradeid=order.tradeid, historyon=self._tradehistoryon)
                datatrades.append(trade)
            else:
                trade = datatrades[-1]
        else:
            datatrades = []
            # Exercise the custom trade instead
            trade = custom_trade

        for execution_bit in order.executed.iterate_pending():
            if execution_bit is None:
                break

            # # TODO: Debug use
            # frameinfo = inspect.getframeinfo(inspect.currentframe())
            # msg = "{} Line: {}: DEBUG: execution_bit:".format(
            #     frameinfo.function, frameinfo.lineno,
            # )
            # print(msg)
            # dump_obj(execution_bit, "execution_bit")

            if execution_bit.closed:
                # Legality Check
                if execution_bit.price <= 0.0 or abs(execution_bit.closed) == 0.0:
                    raise RuntimeError("{}: order id: {}: Both {:.{}f} x {:.{}f} of must be positive!!!".format(
                        inspect.currentframe(),
                        order.ref,
                        execution_bit.price, self.price_digits,
                        execution_bit.closed, self.qty_digits,
                    ))

                execution_bit__price = execution_bit.price

                proceed_with_trade_update = False
                execution_bit__closed = None
                execution_bit__closed_commission = None
                execution_bit__profit_and_loss_amount = None
                if self.p.is_backtest == False:
                    # Whenever the exchange marks the execution_bit as closed, it means the position is
                    #       completely close. Hence, even if we slice the close orders to multiple orders, by design
                    #       it is guaranteed to close. Therefore, we will have to re-calculate the
                    #       profit_and_loss_amount and closed_commission based on the total closed quantity.
                    if len(trade.history) >= 1:
                        execution_bit__closed = -trade.history[0].event.size
                        execution_bit__closed_commission = \
                            order.commission_info.get_commission_rate(
                                execution_bit__closed, execution_bit__price)
                        execution_bit__profit_and_loss_amount = \
                            order.commission_info.profit_and_loss(-execution_bit__closed,
                                                                  trade.history[0].event.price,
                                                                  execution_bit__price)
                        proceed_with_trade_update = True
                    else:
                        # Unable to strictly apply the following legality rule due to one potential scenario
                        # where Conditional [Entry] Order is sent, bot stopped, exchange triggered the order and
                        # eventually became an opened position. Since the bot stopped during this entire process,
                        # there is no trade history recorded and it is illogical for the bot to produce
                        # trade history based on this complex scenario. Hence, the decision made at the moment of
                        # writing is to discard this trade update.
                        #
                        # raise RuntimeError(
                        #     "{}: order id: {}: Expected >= 1 but observed {} trade history to begin with!!!".format(
                        #         inspect.currentframe(),
                        #         order.ref,
                        #         len(trade.history),
                        #     ))
                        pass
                else:
                    execution_bit__closed = execution_bit.closed
                    execution_bit__closed_commission = execution_bit.closed_commission
                    execution_bit__profit_and_loss_amount = execution_bit.profit_and_loss_amount
                    proceed_with_trade_update = True

                if proceed_with_trade_update == True:
                    legality_check_not_none_obj(
                        execution_bit__closed, "execution_bit__closed")
                    legality_check_not_none_obj(
                        execution_bit__closed_commission, "execution_bit__closed_commission")
                    legality_check_not_none_obj(execution_bit__profit_and_loss_amount,
                                                "execution_bit__profit_and_loss_amount")

                    trade.update(order,
                                 execution_bit__closed,
                                 execution_bit__price,
                                 execution_bit__closed_commission,
                                 execution_bit__profit_and_loss_amount,
                                 commission_info=order.commission_info)

                    if custom_trade is None:
                        if trade.isclosed:
                            self._trades_pending.append(copy.copy(trade))
                            if quicknotify:
                                qtrades.append(trade)

            # Update it if needed
            if execution_bit.opened:
                if trade.isclosed:
                    trade = Enhanced_Trade(datafeed=tradedata, tradeid=order.tradeid,
                                           historyon=self._tradehistoryon)
                    if custom_trade is None:
                        datatrades.append(trade)

                # Legality Check
                if execution_bit.price <= 0.0 or abs(execution_bit.opened) == 0.0:
                    raise RuntimeError("{}: order id: {}: Both {:.{}f} x {:.{}f} of must be positive!!!".format(
                        inspect.currentframe(),
                        order.ref,
                        execution_bit.price, self.price_digits,
                        execution_bit.opened, self.qty_digits,
                    ))

                trade.update(order,
                             execution_bit.opened,
                             execution_bit.price,
                             execution_bit.opened_commission,
                             execution_bit.profit_and_loss_amount,
                             commission_info=order.commission_info)

                if custom_trade is None:
                    # This extra check covers the case in which different tradeid
                    # orders have put the position down to 0 and the next order
                    # "opens" a position but "closes" the trade
                    if trade.isclosed:
                        self._trades_pending.append(copy.copy(trade))
                        if quicknotify:
                            qtrades.append(trade)

            if custom_trade is None:
                if trade.justopened:
                    self._trades_pending.append(copy.copy(trade))
                    if quicknotify:
                        qtrades.append(trade)
        return qtrades

    def getsizing(self, datafeed, instrument, is_buy=True):
        '''
        Return the stake calculated by the sizer instance for the current
        situation
        '''
        legality_check_not_none_obj(instrument, "instrument")
        self._sizer.set(self, instrument)
        sizing = self._sizer.getsizing(datafeed, is_buy=is_buy)
        return sizing

    def getwriterinfo(self, instrument):
        wrinfo = backtrader.AutoOrderedDict()

        wrinfo['Params'] = self.p._getkwargs()

        sections = [
            ['Indicators', self.getindicators_lines()],
            ['Observers', self.getobservers()]
        ]

        for sectname, sectitems in sections:
            sinfo = wrinfo[sectname]
            for item in sectitems:
                itname = item.__class__.__name__
                sinfo[itname].Lines = item.lines.getlinealiases() or None
                sinfo[itname].Params = item.p._getkwargs() or None

        ainfo = wrinfo.Analyzers

        # Internal Value Analyzer
        ainfo.Value.Begin = instrument.starting_cash
        ainfo.Value.End = instrument.get_value()

        # no slave analyzers for writer
        for aname, analyzer in self.analyzers.getitems():
            ainfo[aname].Params = analyzer.p._getkwargs() or None
            ainfo[aname].Analysis = analyzer.get_analysis()

        return wrinfo
