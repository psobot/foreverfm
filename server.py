from capsule import Mixer
import Queue
import tornado.web
import tornado.ioloop
import tornado.template
import tornadio2.server
import threading
import logging
from random import shuffle
from operator import attrgetter
import multiprocessing
import soundcloud
import lame
import time

client = soundcloud.Client(client_id="b08793cf5964f5571db86e3ca9e5378f")


def good_track(track):
    return track.streamable and track.duration < 360000 and track.duration > 90000


logging.basicConfig(format="%(asctime)s P%(process)-5d (%(levelname)8s) %(module)16s%(lineno)5d: %(uid)32s %(message)s")
log = logging.getLogger(__name__)

import sys
test_mode = 'test' in sys.argv


frame_seconds = lame.SAMPLES_PER_FRAME / 44100.0


class Listeners(list):
    def __init__(self, queue, name):
        self.__queue = queue
        self.__name = name
        self.__packet = None
        self.__last_send = None
        self.__lag = 0
        list.__init__(self)

    def append(self, listener):
        if self.__packet:
            listener.write(self.__packet)
            listener.flush()
        list.append(self, listener)

    def broadcast(self):
        try:
            self.__broadcast()
            if self.__last_send:
                self.__lag += (time.time() - self.__last_send) - frame_seconds

            if self.__lag > 0:   # TODO: Doesn't this make this "leading?"
                log.warning("Queue %s lagging by %2.2f ms. Compensating...",
                            self.__name, self.__lag * 1000)
                while self.__lag > 0:
                    self.__broadcast()
                    self.__lag -= frame_seconds

            self.__last_send = time.time()
        except Queue.Empty:
            if self.__packet:
                log.warning("Dropping frames! Queue %s is starving!", self.__name)
            pass

    def __broadcast(self):
        self.__packet = self.__queue.get_nowait()
        for listener in self:
            listener.write(self.__packet)
            listener.flush()


class StreamHandler(tornado.web.RequestHandler):
    __subclasses = []
    listeners = []

    @classmethod
    def stream_frames(cls):
        for klass in cls.__subclasses:
            klass.listeners.broadcast()

    @classmethod
    def init_streams(cls, streams):
        routes = []
        for endpoint, name, q in streams:
            klass = type(
                name + "Handler",
                (StreamHandler,),
                {"listeners": Listeners(q, name)}
            )
            cls.__subclasses.append(klass)
            routes.append((endpoint, klass))
        return routes

    @tornado.web.asynchronous
    def get(self):
        log.info("Added new listener at %s", self.request.remote_ip)
        self.set_header("Content-Type", "audio/mpeg")
        self.listeners.append(self)

    def on_finish(self):
        log.info("Removed listener at %s", self.request.remote_ip)
        self.listeners.remove(self)


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


def start():
    track_queue = multiprocessing.Queue(1)
    v2_queue = BufferedReadQueue()

    mixer = Mixer(iqueue=track_queue, oqueues=(v2_queue.raw,))
    mixer.start()

    at = threading.Thread(target=add_tracks, args=(track_queue,))
    at.daemon = True
    at.start()

    class SocketConnection(tornadio2.conn.SocketConnection):
        __endpoints__ = {}

    stream_routes = StreamHandler.init_streams([
        (r"/all.mp3", "All", v2_queue)
    ])

    application = tornado.web.Application(
        tornadio2.TornadioRouter(SocketConnection).apply_routes([
            # Static assets for local development
            (r"/(favicon.ico)", tornado.web.StaticFileHandler, {"path": "static/img/"}),
            (r"/static/(.*)", tornado.web.StaticFileHandler, {"path": "static/"}),
        ] + stream_routes),
        socket_io_port=8193,
        enabled_protocols=['websocket', 'xhr-multipart', 'xhr-polling', 'jsonp-polling']
    )

    frame_sender = tornado.ioloop.PeriodicCallback(
        StreamHandler.stream_frames, frame_seconds * 1000
    )
    frame_sender.start()

    application.listen(8192)
    tornadio2.server.SocketServer(application)


def add_tracks(track_queue):
    sent = 0
    try:
        while test_mode:
            track_queue.put({})

        l = 1000

        offsets = range(0, 4) * l
        shuffle(offsets)
        for i in offsets:
            tracks = client.get('/tracks', order='hotness', limit=l, offset=i)
            tracks = filter(good_track, tracks)
            for track in tracks:
                if track.bpm:
                    print "track", track.title, "has bpm", track.bpm

            for track in sorted(tracks, key=attrgetter('bpm')):
                if track.bpm:
                    print "track", track.title, "has bpm", track.bpm

            shuffle(tracks)

            for track in tracks:
                log.info("Adding new track.")
                track_queue.put(track.obj)
                sent += 1
                log.info("Added new track.")
    finally:
        pass

if __name__ == "__main__":
    start()
