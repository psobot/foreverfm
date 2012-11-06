import Queue
import multiprocessing
import threading


class BufferedReadQueue(Queue.Queue):
    def __init__(self, lim=None):
        self.raw = multiprocessing.Queue(lim)
        self.__listener = threading.Thread(target=self.listen)
        self.__listener.setDaemon(True)
        self.__listener.start()
        Queue.Queue.__init__(self, lim)

    def listen(self):
        try:
            while True:
                self.put(self.raw.get())
        except:
            pass

    @property
    def buffered(self):
        return self.qsize()
