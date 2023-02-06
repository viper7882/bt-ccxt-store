import inspect
import multiprocessing
import threading
import time

from backtrader import print_timestamp_checkpoint
from functools import reduce
from time import time as timer

from ccxtbt.cerebro.cerebro__specifications import HTTP_THREAD_TIMEOUT, UPDATE_INTERVAL
from ccxtbt.utils import get_time_diff


def alive_count(lst):
    alive = map(lambda x: 1 if x.is_alive() else 0, lst)
    return reduce(lambda a, b: a + b, alive)


def prep_threads(max_thread=None):
    max_thread = max_thread if max_thread is not None else multiprocessing.cpu_count()
    thread_limiter = threading.BoundedSemaphore(max_thread)
    timeout = HTTP_THREAD_TIMEOUT
    return thread_limiter, timeout


def run_threads(threads, timeout, disable_verbose=None, print_checkpoint=False):
    start = timer()
    if len(threads) > 0:
        for thread in threads:
            thread.start()

        while alive_count(threads) > 0 and timeout > 0.0:
            timeout = timeout - UPDATE_INTERVAL
            time.sleep(UPDATE_INTERVAL)

        for i, thread in enumerate(threads):
            thread_start = timer()
            thread.join()
            if print_checkpoint:
                frameinfo = inspect.getframeinfo(inspect.currentframe())
                print_timestamp_checkpoint(
                    frameinfo.function, frameinfo.lineno,
                    "Thread #{} CP".format(i), thread_start,
                )

    if not disable_verbose:
        _, minutes, seconds = get_time_diff(start)
        frameinfo = inspect.getframeinfo(inspect.currentframe())
        print("{} Line: {}: Took {}m:{:.2f}s".format(
            frameinfo.function, frameinfo.lineno, minutes, seconds)
        )
