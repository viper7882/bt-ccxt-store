import copy
import os

HTTP_THREAD_TIMEOUT = 2.0
UPDATE_INTERVAL = 0.1

LIVE_CEREBRO__DICT = dict(
    quicknotify=True,
    maxcpus=os.cpu_count(),
    stdstats=False,
    live=True,
    tradehistory=True,
    runonce=False,
)

common__wecoz_cerebro_data__dict_template = dict(
    # Thread and Queue Params
    thread_limiter=None,
    p2c__inbound_fifo_queue=None,
    c2p__outbound_fifo_queue=None,
)

wecoz_cerebro_new_check_data__dict_template = copy.deepcopy(
    common__wecoz_cerebro_data__dict_template)
wecoz_cerebro_new_check_data__dict_template.update((dict(
    # Program Flow Params
    qstart=None,
    datafeed=None,
    newqcheck=None,
)))

wecoz_cerebro_force_get_data__dict_template = copy.deepcopy(
    common__wecoz_cerebro_data__dict_template)
wecoz_cerebro_force_get_data__dict_template.update((dict(
    # Program Flow Params
    datafeeds=None,
    ret=None,
    index=None,
    dts=None,
    dmaster=None,
)))
