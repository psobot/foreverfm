import time


class Timer(object):
    def __enter__(self):
        self.start = time.clock()
        return self

    def __exit__(self, *args):
        self.end = time.clock()
        self.interval = self.end - self.start
        self.ms = self.interval * 1000


class TimeMethod(object):
    def __init__(self, logmethod):
        self.logmethod = logmethod

    def __call__(self, method):
        def timed(*args, **kw):
            with Timer() as t:
                result = method(*args, **kw)
            self.logmethod('%s took %2.3f ms', method.__name__, t.ms)
            return result

        return timed
