import Queue
import threading
import sys

__author__ = 'psobot'

class ExceptionThread(threading.Thread):
    def __init__(self, *args, **kwargs):
        threading.Thread.__init__(self, *args, **kwargs)
        self.__status_queue = Queue.Queue()

    def run(self, *args, **kwargs):
        try:
            threading.Thread.run(self)
        except Exception:
            self.__status_queue.put(sys.exc_info())
        self.__status_queue.put(None)

    def join(self, num=None):
        if not self.__status_queue:
            return
        try:
            exc_info = self.__status_queue.get(True, num)
            if exc_info:
                raise exc_info[1], None, exc_info[2]
        except Queue.Empty:
            return
        self.__status_queue = None
