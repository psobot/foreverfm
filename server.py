from capsule import Mixer
import Queue
import tornado.web
import tornado.ioloop
import tornado.template
import tornadio2.server
import threading
import logging
from random import shuffle
import multiprocessing
import soundcloud
import lame

client = soundcloud.Client(client_id="6325e96fcef18547e6552c23b4c0788c")


def good_track(track):
    return track.streamable and track.duration < 360000 and track.duration > 90000


logging.basicConfig(format="%(asctime)s P%(process)-5d (%(levelname)8s) %(module)16s%(lineno)5d: %(uid)32s %(message)s")
log = logging.getLogger(__name__)

import sys
test_mode = 'test' in sys.argv


class Listeners(list):
    def __init__(self, queue, name):
        self.__queue = queue
        self.__name = name
        self.__packet = None
        list.__init__(self)

    def append(self, listener):
        if self.__packet:
            listener.write(self.__packet)
            listener.flush()
        list.append(self, listener)

    def broadcast(self):
        try:
            self.__packet = self.__queue.get_nowait()
            for listener in self:
                listener.write(self.__packet)
                listener.flush()
        except Queue.Empty:
            if self.__packet:
                log.warning("Dropping frames! Queue %s is starving!", self.__name)
            pass


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
        StreamHandler.stream_frames,
        (float(lame.SAMPLES_PER_FRAME) / mixer.samplerate) * 1000
    )
    frame_sender.start()

    application.listen(8192)
    tornadio2.server.SocketServer(application)


def add_tracks(track_queue):
    sent = 0
    try:
        while test_mode:
            track_queue.put({})

        offsets = range(0, 40)
        shuffle(offsets)
        for i in offsets:
            tracks = filter(good_track, client.get('/tracks', order='hotness', limit=20, offset=i))
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
