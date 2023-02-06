import backtrader
import copy
import datetime
import inspect
import gc
import itertools
import multiprocessing
import queue
import threading
import traceback

from backtrader import Strategy, SignalStrategy, WriterFile, linebuffer, indicator, print_timestamp_checkpoint
from backtrader.utils.py3 import (integer_types)
from time import time as timer

from ccxtbt.cerebro.cerebro__specifications import enhanced_cerebro_force_get_data__dict_template, \
    enhanced_cerebro_new_check_data__dict_template
from ccxtbt.parallel_processing.parallel_processing__helper import prep_threads, run_threads
from ccxtbt.parallel_processing.parallel_processing__classes import Thread_Skeleton
from ccxtbt.parallel_processing.parallel_processing__specifications import thread_queue__dict_template
from ccxtbt.utils import legality_check_not_none_obj


class Enhanced_Cerebro_New_Check_Data_Thread(Thread_Skeleton):
    def __init__(self, params):
        super().__init__(params)

        # Return list of dictionary to caller
        self.dret = None

    def limited_thread_run(self):
        try:
            qlapse = datetime.datetime.utcnow() - self.qstart
            self.datafeed.do_qcheck(self.newqcheck, qlapse.total_seconds())
            self.dret = self.datafeed.next(ticks=False)
        except Exception:
            traceback.print_exc()


class Enhanced_Cerebro_Force_Get_Data_Thread(Thread_Skeleton):
    def __init__(self, params):
        super().__init__(params)

        # Return list of dictionary to caller
        self.data_datetime = None

    def limited_thread_run(self):
        try:
            if self.ret:  # dts already contains a valid datetime for this index
                self.data_datetime = self.dts[self.index]
            else:
                # try to get a datafeed by checking with a master
                datafeed = self.datafeeds[self.index]
                # check to force output
                datafeed._check(forcedata=self.dmaster)
                if datafeed.next(datamaster=self.dmaster, ticks=False):  # retry
                    self.data_datetime = datafeed.datetime[0]  # good -> store
        except Exception:
            traceback.print_exc()


class Enhanced_Cerebro(backtrader.Cerebro):
    '''Params:

      - ``smart_datafeed_reset`` (default: ``True``)

        Whether to reset the ``datafeeds`` automatically by inspecting the content first
    '''
    params = dict(
        smart_datafeed_reset=True,
        # drop_newest_datafeed=True,
    )

    def __init__(self):
        super().__init__()

        self._pending_order = list()
        self._critical_contents = list()

        self.thread_name = None

    def __getstate__(self):
        '''
        Return state values to be pickled.

        Added to address TypeError: cannot pickle '_thread.lock' object for cerebro during deepcopy.

        WARNING: The content of this function is specifically created targeting def plot() only.

        Credits: https://stackoverflow.com/questions/2345944/exclude-objects-field-from-pickling-in-python
        '''
        return self._exactbars, self.runstrats, self.thread_name,

    def __setstate__(self, state):
        '''
        Restore state from the unpickled state values.

        Added to address TypeError: cannot pickle '_thread.lock' object for cerebro during deepcopy.

        WARNING: The content of this function is specifically created targeting def plot() only.

        Credits: https://stackoverflow.com/questions/2345944/exclude-objects-field-from-pickling-in-python
        '''
        (self._exactbars, self.runstrats, self.thread_name, ) = state

    def add_datafeed(self, datafeed, name):
        '''
        Adds a ``Data Feed`` instance to the mix.

        If ``name`` is not None it will be put into ``datafeed._name`` which is
        meant for decoration/plotting purposes.
        '''
        if self.thread_name is None:
            # Record down the thread name that initializes Cerebro
            current_thread = threading.current_thread()
            self.thread_name = current_thread.name

        legality_check_not_none_obj(name, "name")
        datafeed._name = name

        datafeed._id = next(self._datafeed_id)
        datafeed.setenvironment(self)

        self.datafeeds.append(datafeed)
        self.datafeeds_by_name[datafeed._name] = datafeed
        backend_feed = datafeed.get_backend_datafeed()
        if backend_feed and backend_feed not in self.backend_feeds:
            self.backend_feeds.append(backend_feed)

        if datafeed.is_live():
            self._do_live = True

        return datafeed

    def add_pending_order(self, orders, notify=True):
        self._pending_order.append((orders, notify))

    def update_critical_contents(self, critical_contents, notify=True):
        self._critical_contents.append((critical_contents, notify))

    def reset_datas_and_feeds(self):
        self.backend_feeds.clear()
        self.datafeeds.clear()

    def _runnext(self, runstrats):
        '''
        Actual implementation of run in full next mode. All objects have its
        ``next`` method invoke on each datafeed arrival
        '''
        start = timer()

        print_checkpoint = False

        # # TODO: Debug Use
        # print_checkpoint = True

        datafeeds = sorted(self.datafeeds,
                           key=lambda x: (x._timeframe, x._compression))
        datas1 = datafeeds[1:]
        datafeed0 = datafeeds[0]
        d0ret = True

        rsonly = [i for i, x in enumerate(datafeeds)
                  if x.resampling and not x.replaying]
        onlyresample = len(datafeeds) == len(rsonly)
        noresample = not rsonly

        clonecount = sum(datafeed._clone for datafeed in datafeeds)
        ldatas = len(datafeeds)
        ldatas_noclones = ldatas - clonecount
        dt0 = backtrader.date2num(datetime.datetime.max) - 2  # default at max
        while d0ret or d0ret is None:
            start = timer()
            # if any has live datafeed in the buffer, no datafeed will wait anything
            newqcheck = not any(datafeed.has_live_data()
                                for datafeed in datafeeds)
            if not newqcheck:
                # If no datafeed has reached the live status or all, wait for
                # the next incoming datafeed
                livecount = sum(datafeed._laststatus ==
                                datafeed.LIVE for datafeed in datafeeds)
                newqcheck = not livecount or livecount == ldatas_noclones

            if print_checkpoint:
                print_timestamp_checkpoint(
                    inspect.getframeinfo(inspect.currentframe()).function,
                    inspect.getframeinfo(inspect.currentframe()).lineno,
                    "Cerebro _runnext CP2",
                    start,
                )

            lastret = False
            # Notify anything from the account_or_store even before moving datafeeds
            # because datafeeds may not move due to an error reported by the account_or_store
            self._notify_account_or_store()
            if self._event_stop:  # stop if requested
                return

            if print_checkpoint:
                print_timestamp_checkpoint(
                    inspect.getframeinfo(inspect.currentframe()).function,
                    inspect.getframeinfo(inspect.currentframe()).lineno,
                    "Cerebro _runnext CP3",
                    start,
                )

            self._datafeed_notification()
            if self._event_stop:  # stop if requested
                return

            if print_checkpoint:
                print_timestamp_checkpoint(
                    inspect.getframeinfo(inspect.currentframe()).function,
                    inspect.getframeinfo(inspect.currentframe()).lineno,
                    "Cerebro _runnext CP4",
                    start,
                )

            # record starting time and tell feeds to discount the elapsed time
            # from the qcheck value
            qstart = datetime.datetime.utcnow()

            thread_limiter, timeout = prep_threads()

            thread_and_queue_dicts = []
            for datafeed in datafeeds:
                enhanced_cerebro_new_check_data__dict = copy.deepcopy(
                    enhanced_cerebro_new_check_data__dict_template)

                # Thread and Queue Params
                enhanced_cerebro_new_check_data__dict['thread_limiter'] = thread_limiter
                enhanced_cerebro_new_check_data__dict['p2c__inbound_fifo_queue'] = queue.Queue(
                )
                enhanced_cerebro_new_check_data__dict['c2p__outbound_fifo_queue'] = queue.Queue(
                )

                # Program Flow Params
                enhanced_cerebro_new_check_data__dict['qstart'] = qstart
                enhanced_cerebro_new_check_data__dict['datafeed'] = datafeed
                enhanced_cerebro_new_check_data__dict['newqcheck'] = newqcheck

                thread = Enhanced_Cerebro_New_Check_Data_Thread(
                    enhanced_cerebro_new_check_data__dict)

                thread_and_queue_dict = copy.deepcopy(
                    thread_queue__dict_template)
                thread_and_queue_dict['thread'] = thread
                thread_and_queue_dict['c2p__outbound_fifo_queue'] = \
                    enhanced_cerebro_new_check_data__dict['p2c__inbound_fifo_queue']
                thread_and_queue_dict['p2c__inbound_fifo_queue'] = \
                    enhanced_cerebro_new_check_data__dict['c2p__outbound_fifo_queue']
                thread_and_queue_dicts.append(thread_and_queue_dict)

            threads = [thread_and_queue_dict['thread']
                       for thread_and_queue_dict in thread_and_queue_dicts]
            try:
                run_threads(threads, timeout, disable_verbose=True)
            except Exception:
                traceback.print_exc()
            drets = [x.dret for x in threads]

            if print_checkpoint:
                print_timestamp_checkpoint(
                    inspect.getframeinfo(inspect.currentframe()).function,
                    inspect.getframeinfo(inspect.currentframe()).lineno,
                    "Cerebro _runnext CP5",
                    start,
                )

            d0ret = any((dret for dret in drets))
            if not d0ret and any((dret is None for dret in drets)):
                d0ret = None

            if d0ret:
                dts = []
                for i, ret in enumerate(drets):
                    dts.append(datafeeds[i].datetime[0] if ret else None)

                if print_checkpoint:
                    print_timestamp_checkpoint(
                        inspect.getframeinfo(inspect.currentframe()).function,
                        inspect.getframeinfo(inspect.currentframe()).lineno,
                        "Cerebro _runnext CP5a",
                        start,
                    )

                # Get index to minimum datetime i.e. the eldest datetime
                if onlyresample or noresample:
                    dt0 = min((d for d in dts if d is not None))
                else:
                    dt0 = min((d for i, d in enumerate(dts)
                               if d is not None and i not in rsonly))

                if print_checkpoint:
                    print_timestamp_checkpoint(
                        inspect.getframeinfo(inspect.currentframe()).function,
                        inspect.getframeinfo(inspect.currentframe()).lineno,
                        "Cerebro _runnext CP5b",
                        start,
                    )

                # Date Master is the datafeed that has the eldest datetime
                dmaster = datafeeds[dts.index(dt0)]  # and timemaster
                # Convert float to datetime by def num2date() in feed.py
                self._dtmaster = dmaster.num2date(dt0)
                # Convert float to datetime
                self._udtmaster = backtrader.num2date(dt0)

                # slen = len(runstrats[0])

                # Try to get something for those that didn't return
                thread_limiter, timeout = prep_threads()

                thread_and_queue_dicts = []
                for i, ret in enumerate(drets):
                    enhanced_cerebro_new_check_data__dict = copy.deepcopy(
                        enhanced_cerebro_force_get_data__dict_template)

                    # Thread and Queue Params
                    enhanced_cerebro_new_check_data__dict['thread_limiter'] = thread_limiter
                    enhanced_cerebro_new_check_data__dict['p2c__inbound_fifo_queue'] = queue.Queue(
                    )
                    enhanced_cerebro_new_check_data__dict['c2p__outbound_fifo_queue'] = queue.Queue(
                    )

                    # Program Flow Params
                    enhanced_cerebro_new_check_data__dict['datafeeds'] = datafeeds
                    enhanced_cerebro_new_check_data__dict['ret'] = ret
                    enhanced_cerebro_new_check_data__dict['index'] = i
                    enhanced_cerebro_new_check_data__dict['dts'] = dts
                    enhanced_cerebro_new_check_data__dict['dmaster'] = dmaster

                    thread = Enhanced_Cerebro_Force_Get_Data_Thread(
                        enhanced_cerebro_new_check_data__dict)

                    thread_and_queue_dict = copy.deepcopy(
                        thread_queue__dict_template)
                    thread_and_queue_dict['thread'] = thread
                    thread_and_queue_dict['c2p__outbound_fifo_queue'] = \
                        enhanced_cerebro_new_check_data__dict['p2c__inbound_fifo_queue']
                    thread_and_queue_dict['p2c__inbound_fifo_queue'] = \
                        enhanced_cerebro_new_check_data__dict['c2p__outbound_fifo_queue']
                    thread_and_queue_dicts.append(thread_and_queue_dict)

                threads = [thread_and_queue_dict['thread']
                           for thread_and_queue_dict in thread_and_queue_dicts]
                try:
                    run_threads(threads, timeout,
                                disable_verbose=True)
                except Exception:
                    traceback.print_exc()
                dts = [x.data_datetime for x in threads]

                if print_checkpoint:
                    print_timestamp_checkpoint(
                        inspect.getframeinfo(inspect.currentframe()).function,
                        inspect.getframeinfo(inspect.currentframe()).lineno,
                        "Cerebro _runnext CP5c",
                        start,
                    )

                # The following codes ensure datafeed sync between different granularity_timeframe. For instant,
                #       between 15m and 1h.
                # make sure only those at dmaster level end up delivering
                for i, dti in enumerate(dts):
                    if dti is not None:
                        di = datafeeds[i]
                        rpi = False and di.replaying   # to check behavior
                        if dti > dt0:
                            if not rpi:  # must see all ticks ...
                                di.rewind()  # cannot deliver yet
                            # self._plotfillers[i].append(slen)
                        elif not di.replaying:
                            # Replay forces tick fill, else force here
                            di._tick_fill(force=True)

                        # self._plotfillers2[i].append(slen)  # mark as fill

                if print_checkpoint:
                    print_timestamp_checkpoint(
                        inspect.getframeinfo(inspect.currentframe()).function,
                        inspect.getframeinfo(inspect.currentframe()).lineno,
                        "Cerebro _runnext CP6",
                        start,
                    )

            elif d0ret is None:
                # meant for things like live feeds which may not produce a bar
                # at the moment but need the loop to run for notifications and
                # getting resample and others to produce timely bars
                for datafeed in datafeeds:
                    datafeed._check()

                if print_checkpoint:
                    print_timestamp_checkpoint(
                        inspect.getframeinfo(inspect.currentframe()).function,
                        inspect.getframeinfo(inspect.currentframe()).lineno,
                        "Cerebro _runnext CP8",
                        start,
                    )
            else:
                lastret = datafeed0._last()
                for datafeed in datas1:
                    lastret += datafeed._last(datamaster=datafeed0)

                if print_checkpoint:
                    print_timestamp_checkpoint(
                        inspect.getframeinfo(inspect.currentframe()).function,
                        inspect.getframeinfo(inspect.currentframe()).lineno,
                        "Cerebro _runnext CP9",
                        start,
                    )

                if not lastret:
                    # Only go extra round if something was changed by "lasts"
                    break

            # Datas may have generated a new notification after next
            self._datafeed_notification()
            if self._event_stop:  # stop if requested
                return

            if print_checkpoint:
                print_timestamp_checkpoint(
                    inspect.getframeinfo(inspect.currentframe()).function,
                    inspect.getframeinfo(inspect.currentframe()).lineno,
                    "Cerebro _runnext CP10",
                    start,
                )

            if d0ret or lastret:  # if any bar, check timers before broker_or_exchange
                self._check_timers(runstrats, dt0, cheat=True)
                if self.p.cheat_on_open:
                    for strat in runstrats:
                        strat._next_open()
                        if self._event_stop:  # stop if requested
                            return

            self._account_or_store__notification()
            if self._event_stop:  # stop if requested
                return

            if print_checkpoint:
                print_timestamp_checkpoint(
                    inspect.getframeinfo(inspect.currentframe()).function,
                    inspect.getframeinfo(inspect.currentframe()).lineno,
                    "Cerebro _runnext CP11",
                    start,
                )

            # print("{} Line: {}: DEBUG: d0ret: {} or lastret: {}".format(
            #     inspect.getframeinfo(inspect.currentframe()).function,
            #     inspect.getframeinfo(inspect.currentframe()).lineno,
            #     d0ret, lastret,
            # ))

            # # TODO: Debug Use
            # debug = True
            debug = False
            if d0ret or lastret:  # bars produced by datafeed or filters
                self._check_timers(runstrats, dt0, cheat=False)
                for strat in runstrats:
                    # print("{} Line: {}: d0ret: {} or lastret: {}".format(
                    #     inspect.getframeinfo(inspect.currentframe()).function,
                    #     inspect.getframeinfo(inspect.currentframe()).lineno,
                    #     d0ret, lastret,
                    # ))

                    if hasattr(self._broker_or_exchange, 'get__children'):
                        accounts_or_stores = self._broker_or_exchange.get__children()
                        for account_or_store in accounts_or_stores:
                            instruments = account_or_store.get__children()
                            for instrument in instruments:
                                strat._next(account_or_store,
                                            instrument, debug=debug)

                                # print("{} Line: {}: strat self._event_stop: {}".format(
                                #     inspect.getframeinfo(inspect.currentframe()).function,
                                #     inspect.getframeinfo(inspect.currentframe()).lineno,
                                #     self._event_stop,
                                # ))

                                if self._event_stop:  # stop if requested
                                    return

                                self._next_writers(runstrats)
                    else:
                        # Legacy BackBroker
                        strat._next(None, None, debug=debug)

                        if self._event_stop:  # stop if requested
                            return

                        self._next_writers(runstrats)

            if print_checkpoint:
                print_timestamp_checkpoint(
                    inspect.getframeinfo(inspect.currentframe()).function,
                    inspect.getframeinfo(inspect.currentframe()).lineno,
                    "Cerebro _runnext CP12",
                    start,
                )

            # if self.p.drop_newest_datafeed == True:
            #     for datafeed in datafeeds:
            #         if len(datafeed) >= 1:
            #             # Avoid seeing the under construction bar i.e. provide unified behavior between live and
            #             #       backtest
            #             datafeed.advance()
            pass

        # Last notification chance before stopping
        self._datafeed_notification()
        if self._event_stop:  # stop if requested
            return

        if print_checkpoint:
            print_timestamp_checkpoint(
                inspect.getframeinfo(inspect.currentframe()).function,
                inspect.getframeinfo(inspect.currentframe()).lineno,
                "Cerebro _runnext CP13",
                start,
            )

        self._notify_account_or_store()
        if self._event_stop:  # stop if requested
            return

        if print_checkpoint:
            print_timestamp_checkpoint(
                inspect.getframeinfo(inspect.currentframe()).function,
                inspect.getframeinfo(inspect.currentframe()).lineno,
                "Cerebro _runnext CP14",
                start,
            )
        pass

    def _run_once(self, runstrats):
        '''
        Actual implementation of run in vector mode.

        Strategies are still invoked on a pseudo-event mode in which ``next``
        is called for each datafeed arrival
        '''
        for strat in runstrats:
            strat._once()
            strat.reset()  # strat called next by next - reset lines

        # The default once for strategies does nothing and therefore
        # has not moved forward all datafeeds/indicators/observers that
        # were homed before calling once, Hence no "need" to do it
        # here again, because pointers are at 0
        datafeeds = sorted(self.datafeeds,
                           key=lambda x: (x._timeframe, x._compression))

        while True:
            # Check next incoming date in the datafeeds
            dts = [datafeed.advance_peek() for datafeed in datafeeds]
            dt0 = min(dts)
            if dt0 == float('inf'):
                break  # no datafeed delivers anything

            # Timemaster if needed be
            # dmaster = datafeeds[dts.index(dt0)]  # and timemaster
            # slen = len(runstrats[0])
            for i, dti in enumerate(dts):
                if dti <= dt0:
                    datafeeds[i].advance()
                    # self._plotfillers2[i].append(slen)  # mark as fill
                else:
                    # self._plotfillers[i].append(slen)
                    pass

            self._check_timers(runstrats, dt0, cheat=True)

            if self.p.cheat_on_open:
                for strat in runstrats:
                    strat._oncepost_open()
                    if self._event_stop:  # stop if requested
                        return

            self._broker_or_echange_notification()
            if self._event_stop:  # stop if requested
                return

            self._check_timers(runstrats, dt0, cheat=False)

            for strat in runstrats:
                strat._oncepost(dt0)
                if self._event_stop:  # stop if requested
                    return

                self._next_writers(runstrats)

    def run(self, **kwargs):
        '''The core method to perform backtesting. Any ``kwargs`` passed to it
        will affect the value of the standard parameters ``Cerebro`` was
        instantiated with.

        If ``cerebro`` has not datafeeds the method will immediately bail out.

        It has different return values:

          - For No Optimization: a list contanining instances of the Strategy
            classes added with ``add_strategy``

          - For Optimization: a list of lists which contain instances of the
            Strategy classes added with ``add_strategy``
        '''
        self._event_stop = False  # Stop is requested

        if len(self.datafeeds) == 0:
            raise ValueError("{} Line: {}: ERROR: No datafeed is found in cerebro. If you choose to proceed without "
                             "datafeed, cerebro will not run either below!!!".format(
                                 inspect.getframeinfo(
                                     inspect.currentframe()).function,
                                 inspect.getframeinfo(
                                     inspect.currentframe()).lineno,
                             ))

        if not self.datafeeds:
            return []  # nothing can be run

        pkeys = self.params._getkeys()
        for key, val in kwargs.items():
            if key in pkeys:
                setattr(self.params, key, val)

        # Manage activate/deactivate object cache
        linebuffer.LineActions.cleancache()  # clean cache
        indicator.Indicator.cleancache()  # clean cache

        linebuffer.LineActions.usecache(self.p.objcache)
        indicator.Indicator.usecache(self.p.objcache)

        self._dorunonce = self.p.runonce
        self._dopreload = self.p.preload
        self._exactbars = int(self.p.exactbars)

        if self._exactbars:
            self._dorunonce = False  # something is saving memory, no runonce
            self._dopreload = self._dopreload and self._exactbars < 1

        self._do_replay = self._do_replay or any(
            x.replaying for x in self.datafeeds)
        if self._do_replay:
            # preloading is not supported with replay. full timeframe bars
            # are constructed in realtime
            self._dopreload = False

        if self._do_live or self.p.live:
            # in this case both preload and runonce must be off
            self._dorunonce = False
            self._dopreload = False

        self.runwriters = list()

        # Add the system default writer if requested
        if self.p.writer is True:
            wr = WriterFile()
            self.runwriters.append(wr)

        # Instantiate any other writers
        for wrcls, wrargs, wrkwargs in self.writers:
            wr = wrcls(*wrargs, **wrkwargs)
            self.runwriters.append(wr)

        # Write down if any writer wants the full csv output
        self.writers_csv = any(map(lambda x: x.p.csv, self.runwriters))

        self.runstrats = list()

        if self.signals:  # allow processing of signals
            signalst, sargs, skwargs = self._signal_strat
            if signalst is None:
                # Try to see if the 1st regular strategy is a signal strategy
                try:
                    signalst, sargs, skwargs = self.strategies.pop(0)
                except IndexError:
                    pass  # Nothing there
                else:
                    if not isinstance(signalst, SignalStrategy):
                        # no signal ... reinsert at the beginning
                        self.strategies.insert(0, (signalst, sargs, skwargs))
                        signalst = None  # flag as not presetn

            if signalst is None:  # recheck
                # Still None, create a default one
                signalst, sargs, skwargs = SignalStrategy, tuple(), dict()

            # Add the signal strategy
            self.add_strategy(signalst,
                              _accumulate=self._signal_accumulate,
                              _concurrent=self._signal_concurrent,
                              signals=self.signals,
                              *sargs,
                              **skwargs)

        if not self.strategies:  # Datas are present, add a strategy
            self.add_strategy(Strategy)

        iterstrats = itertools.product(*self.strategies)
        if not self._do_optimization or self.p.maxcpus == 1:
            # If no optimmization is wished ... or 1 core is to be used
            # let's skip process "spawning"
            for iterstrat in iterstrats:
                runstrat = self.run_strategies(iterstrat)
                self.runstrats.append(runstrat)
                if self._do_optimization:
                    for cb in self.optcbs:
                        cb(runstrat)  # callback receives finished strategy
        else:
            if self.p.optdatas and self._dopreload and self._dorunonce:
                for datafeed in self.datafeeds:
                    datafeed.reset()
                    if self._exactbars < 1:  # datafeeds can be full length
                        datafeed.extend(size=self.params.lookahead)
                    datafeed._start()
                    if self._dopreload:
                        datafeed.preload()

            pool = multiprocessing.Pool(self.p.maxcpus or None)
            for r in pool.imap(self, iterstrats):
                self.runstrats.append(r)
                for cb in self.optcbs:
                    cb(r)  # callback receives finished strategy
                    # Force GC to run
                    gc.collect()
                # Force GC to run
                gc.collect()

            pool.close()

            if self.p.optdatas and self._dopreload and self._dorunonce:
                for datafeed in self.datafeeds:
                    datafeed.stop()

        if not self._do_optimization:
            # avoid a list of list for regular cases
            return self.runstrats[0]

        return self.runstrats

    def stop_writers(self, runstrats, instrument):
        cerebroinfo = backtrader.OrderedDict()
        datainfos = backtrader.OrderedDict()

        for i, datafeed in enumerate(self.datafeeds):
            datainfos['Data%d' % i] = datafeed.getwriterinfo(instrument)

        cerebroinfo['Datas'] = datainfos

        stratinfos = dict()
        for strat in runstrats:
            stname = strat.__class__.__name__
            stratinfos[stname] = strat.getwriterinfo(instrument)

        cerebroinfo['Strategies'] = stratinfos

        for writer in self.runwriters:
            writer.writedict(dict(Cerebro=cerebroinfo))
            writer.stop()

    def _account_or_store__notification(self):
        '''
        Internal method which kicks the account_or_store and delivers any account_or_store notification to the strategy
        '''
        if hasattr(self._broker_or_exchange, 'get__children'):
            accounts_or_stores = self._broker_or_exchange.get__children()
            for account_or_store in accounts_or_stores:
                account_or_store.next()

                while True:
                    order = account_or_store.get_notification()
                    if order is None:
                        break

                    owner = order.owner
                    if owner is None:
                        owner = self.runningstrats[0]  # default

                    owner._add_notification(
                        order, quicknotify=self.p.quicknotify)
        else:
            # Legacy BackBroker
            self._broker_or_exchange.next()

            while True:
                order = self._broker_or_exchange.get_notification()
                if order is None:
                    break

                owner = order.owner
                if owner is None:
                    owner = self.runningstrats[0]  # default

                owner._add_notification(order, quicknotify=self.p.quicknotify)

    def run_strategies(self, iterstrat, predata=False):
        '''
        Internal method invoked by ``run``` to run a set of strategies
        '''

        start = timer()
        print_checkpoint = False

        # # TODO: Debug Use
        # print_checkpoint = True

        self._init_stcount()

        self.runningstrats = runstrats = list()

        if print_checkpoint:
            print_timestamp_checkpoint(
                inspect.getframeinfo(inspect.currentframe()).function,
                inspect.getframeinfo(inspect.currentframe()).lineno,
                "CP1",
                start,
            )

        if self.p.cheat_on_open and self.p.broker_coo:
            # try to activate in broker_or_exchange
            if hasattr(self._broker_or_exchange, 'set_coo'):
                self._broker_or_exchange.set_coo(True)

        if self._fhistory is not None:
            self._broker_or_exchange.set_fund_history(self._fhistory)

        for orders, onotify in self._ohistory:
            self._broker_or_exchange.add_order_history(orders, onotify)

        # Quick hack to mimic add_order_history
        for orders, onotify in self._pending_order:
            self._broker_or_exchange.add_pending_order(orders, onotify)

        # Quick hack to mimic add_order_history
        for critical_contents, onotify in self._critical_contents:
            self._broker_or_exchange.update_critical_contents(
                critical_contents, onotify)

        if print_checkpoint:
            print_timestamp_checkpoint(
                inspect.getframeinfo(inspect.currentframe()).function,
                inspect.getframeinfo(inspect.currentframe()).lineno,
                "CP2",
                start,
            )

        for backend_feed in self.backend_feeds:
            backend_feed.start()

        if print_checkpoint:
            print_timestamp_checkpoint(
                inspect.getframeinfo(inspect.currentframe()).function,
                inspect.getframeinfo(inspect.currentframe()).lineno,
                "CP3",
                start,
            )

        if self.writers_csv:
            wheaders = list()
            for datafeed in self.datafeeds:
                if datafeed.csv:
                    wheaders.extend(datafeed.getwriterheaders())

            for writer in self.runwriters:
                if writer.p.csv:
                    writer.addheaders(wheaders)

        # self._plotfillers = [list() for d in self.datafeeds]
        # self._plotfillers2 = [list() for d in self.datafeeds]

        if not predata:
            for datafeed in self.datafeeds:
                if self.p.smart_datafeed_reset == False:
                    datafeed.reset()
                else:
                    if len(datafeed.datetime) == 0:
                        datafeed.reset()
                if self._exactbars < 1:  # datafeeds can be full length
                    datafeed.extend(size=self.params.lookahead)
                datafeed._start()
                if self._dopreload:
                    datafeed.preload()

        if print_checkpoint:
            print_timestamp_checkpoint(
                inspect.getframeinfo(inspect.currentframe()).function,
                inspect.getframeinfo(inspect.currentframe()).lineno,
                "CP4",
                start,
            )

        for stratcls, sargs, skwargs in iterstrat:
            sargs = self.datafeeds + list(sargs)
            try:
                strat = stratcls(*sargs, **skwargs)
            except backtrader.errors.StrategySkipError:
                continue  # do not add strategy to the mix

            if self.p.oldsync:
                strat._oldsync = True  # tell strategy to use old clock update
            if self.p.tradehistory:
                strat.set_tradehistory()
            runstrats.append(strat)

        if print_checkpoint:
            print_timestamp_checkpoint(
                inspect.getframeinfo(inspect.currentframe()).function,
                inspect.getframeinfo(inspect.currentframe()).lineno,
                "CP5",
                start,
            )

        tz = self.p.tz
        if isinstance(tz, integer_types):
            tz = self.datafeeds[tz]._tz
        else:
            tz = backtrader.tzparse(tz)

        if runstrats:
            # loop separated for clarity
            defaultsizer = self.sizers.get(None, (None, None, None))
            for idx, strat in enumerate(runstrats):
                if self.p.stdstats:
                    strat._add_observer(
                        False, backtrader.observers.Broker_or_Exchange)
                    if self.p.oldbuysell:
                        strat._add_observer(
                            True, backtrader.observers.Buy_and_Sell)
                    else:
                        strat._add_observer(True, backtrader.observers.Buy_and_Sell,
                                            barplot=True)

                    if self.p.oldtrades or len(self.datafeeds) == 1:
                        strat._add_observer(False, backtrader.observers.Trades)
                    else:
                        strat._add_observer(
                            False, backtrader.observers.DataTrades)

                for multi, obscls, obsargs, obskwargs in self.observers:
                    strat._add_observer(multi, obscls, *obsargs, **obskwargs)

                for indcls, indargs, indkwargs in self.indicators:
                    strat._add_indicator(indcls, *indargs, **indkwargs)

                for ancls, anargs, ankwargs in self.analyzers:
                    strat._add_analyzer(ancls, *anargs, **ankwargs)

                sizer, sargs, skwargs = self.sizers.get(idx, defaultsizer)
                if sizer is not None:
                    strat._addsizer(sizer, *sargs, **skwargs)

                strat._settz(tz)
                strat._start()

                for writer in self.runwriters:
                    if writer.p.csv:
                        writer.addheaders(strat.getwriterheaders())

            if print_checkpoint:
                print_timestamp_checkpoint(
                    inspect.getframeinfo(inspect.currentframe()).function,
                    inspect.getframeinfo(inspect.currentframe()).lineno,
                    "CP6",
                    start,
                )

            if not predata:
                for strat in runstrats:
                    strat.qbuffer(self._exactbars, replaying=self._do_replay)

            for writer in self.runwriters:
                writer.start()

            if print_checkpoint:
                print_timestamp_checkpoint(
                    inspect.getframeinfo(inspect.currentframe()).function,
                    inspect.getframeinfo(inspect.currentframe()).lineno,
                    "CP7",
                    start,
                )

            # Prepare timers
            self._timers = []
            self._timerscheat = []
            for pre_timer in self._pretimers:
                # preprocess tzdata if needed
                pre_timer.start(self.datafeeds[0])

                if pre_timer.params.cheat:
                    self._timerscheat.append(pre_timer)
                else:
                    self._timers.append(pre_timer)

            if print_checkpoint:
                print_timestamp_checkpoint(
                    inspect.getframeinfo(inspect.currentframe()).function,
                    inspect.getframeinfo(inspect.currentframe()).lineno,
                    "CP8",
                    start,
                )

            if self._dopreload and self._dorunonce:
                if self.p.oldsync:
                    self._runonce_old(runstrats)
                else:
                    self._run_once(runstrats)

                if print_checkpoint:
                    print_timestamp_checkpoint(
                        inspect.getframeinfo(inspect.currentframe()).function,
                        inspect.getframeinfo(inspect.currentframe()).lineno,
                        "CP9",
                        start,
                    )
            else:
                if self.p.oldsync:
                    self._runnext_old(runstrats)
                else:
                    self._runnext(runstrats)

                if print_checkpoint:
                    print_timestamp_checkpoint(
                        inspect.getframeinfo(inspect.currentframe()).function,
                        inspect.getframeinfo(inspect.currentframe()).lineno,
                        "CP10",
                        start,
                    )

            for strat in runstrats:
                strat._stop()

            if print_checkpoint:
                print_timestamp_checkpoint(
                    inspect.getframeinfo(inspect.currentframe()).function,
                    inspect.getframeinfo(inspect.currentframe()).lineno,
                    "CP11",
                    start,
                )

        if hasattr(self._broker_or_exchange, 'get__children'):
            accounts_or_stores = self._broker_or_exchange.get__children()
            for account_or_store in accounts_or_stores:
                account_or_store.stop()
        else:
            # Legacy BackBroker
            self._broker_or_exchange.stop()

        if not predata:
            for datafeed in self.datafeeds:
                datafeed.stop()

        for backend_feed in self.backend_feeds:
            backend_feed.stop()

        if print_checkpoint:
            print_timestamp_checkpoint(
                inspect.getframeinfo(inspect.currentframe()).function,
                inspect.getframeinfo(inspect.currentframe()).lineno,
                "CP12",
                start,
            )

        if self._do_optimization and self.p.optreturn:
            # Results can be optimized
            results = list()
            for strat in runstrats:
                for a in strat.analyzers:
                    a.strategy = None
                    a._parent = None
                    for attrname in dir(a):
                        if attrname.startswith('datafeed'):
                            setattr(a, attrname, None)

                oreturn = backtrader.OptReturn(
                    strat.params, analyzers=strat.analyzers, strategycls=type(strat))
                results.append(oreturn)

            if print_checkpoint:
                print_timestamp_checkpoint(
                    inspect.getframeinfo(inspect.currentframe()).function,
                    inspect.getframeinfo(inspect.currentframe()).lineno,
                    "CP13",
                    start,
                )

            return results

        if print_checkpoint:
            print_timestamp_checkpoint(
                inspect.getframeinfo(inspect.currentframe()).function,
                inspect.getframeinfo(inspect.currentframe()).lineno,
                "CP14",
                start,
            )

        return runstrats

    def stop_running(self, instrument):
        '''If invoked from inside a strategy or anywhere else, including other
        threads the execution will stop as soon as possible.'''
        self._event_stop = True  # signal a stop has been requested
        instrument.set__stop_running()
