import threading

from abc import abstractmethod

from ccxtbt.utils import legality_check_not_none_obj


class Thread_Skeleton(threading.Thread):
    def __init__(self, params):
        self.params = params
        super().__init__()

        # Un-serialize Params
        for key, val in params.items():
            setattr(self, key, val)

        legality_check_not_none_obj(self.thread_limiter, "self.thread_limiter")

    def run(self):
        self.thread_limiter.acquire()
        try:
            self.limited_thread_run()
        finally:
            self.thread_limiter.release()

    @abstractmethod
    def limited_thread_run(self):
        print("ERROR: This abstract method is not implemented!!!")
