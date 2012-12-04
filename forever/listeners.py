import time
import lame
import Queue
import config
import logging

LAG_LIMIT = config.lag_limit
log = logging.getLogger(config.log_name)


class Listeners(list):
    def __init__(self, queue, name, semaphore):
        self.queue = queue
        self.__name = name
        self.__packet = None
        self.__last_send = None
        self.__lag = 0
        self.__semaphore = semaphore
        list.__init__(self)

    def append(self, listener):
        if self.__packet:
            listener.write(self.__packet)
            listener.flush()
        list.append(self, listener)

    def broadcast(self):
        try:
            if self.__lag > LAG_LIMIT:
                log.error("Lag (%s) exceeds limit - dropping frames!",
                          self.__lag)
                self.__lag = 0

            self.__broadcast()
            if self.__last_send:
                self.__lag += int((time.time() - self.__last_send) * 44100)\
                                - lame.SAMPLES_PER_FRAME
            else:
                log.info("Sending first frame for %s.", self.__name)
                self.__semaphore.release()

            if self.__lag > 0:
                log.warning("Queue %s lag detected. (%2.2f ms)",
                            self.__name, (self.__lag * 1000.0 / 44100.0))
                while self.__lag > 0 and not self.queue.empty():
                    self.__broadcast()
                    self.__lag -= lame.SAMPLES_PER_FRAME
                log.warning("Queue %s lag compensated. Leading by %2.2f ms.",
                            self.__name, (self.__lag *  -1000.0 / 44100.0))

            self.__last_send = time.time()
        except Queue.Empty:
            if self.__packet and not self.__starving:
                self.__starving = True
                log.warning("Dropping frames! Queue %s is starving!", self.__name)

    def __broadcast(self):
        self.__packet = self.queue.get_nowait()
        self.__starving = False
        for i, listener in enumerate(list(self)):
            if listener.request.connection.stream.closed():
                try:
                    listener.finish()
                except (AssertionError, IOError, RuntimeError):
                    self.remove(listener)
            else:
                listener.write(self.__packet)
                listener.flush()
