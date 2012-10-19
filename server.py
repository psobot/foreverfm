from capsule import Mixer
import Queue
import tornado.web
import tornado.ioloop
import tornado.template
import tornadio2.server
import threading
import logging
from random import shuffle

import cStringIO
import soundcloud
client = soundcloud.Client(client_id="6325e96fcef18547e6552c23b4c0788c")

prime_limit = 2

import time


def good_track(track):
    return track.streamable and track.duration < 360000 and track.duration > 90000


queue = Queue.Queue()


logging.basicConfig(format="%(asctime)s P%(process)-5d (%(levelname)8s) %(module)16s%(lineno)5d: %(uid)32s %(message)s")
log = logging.getLogger(__name__)


class StreamHandler(tornado.web.RequestHandler):
    listeners = []
    frame = None
    last_send = time.time()

    @classmethod
    def on_new_frame(cls, *args, **kwargs):
        tornado.ioloop.IOLoop.instance().add_callback(lambda: cls.stream_frames(*args, **kwargs))

    @classmethod
    def stream_frames(cls, done):
        while not queue.empty():
            frame = queue.get_nowait()
            for listener in cls.listeners:
                listener.write(frame)
                listener.flush()
            sent = time.time()
            log.info("Time between MP3 packets: %fs", (sent - cls.last_send))
            cls.last_send = sent

    @tornado.web.asynchronous
    def get(self):
        self.set_header("Content-Type", "audio/mpeg")
        if self.frame:
            self.write(self.frame)
        self.flush()
        self.listeners.append(self)


def start():
    at = threading.Thread(target=add_tracks)
    at.daemon = True
    at.start()

    class SocketConnection(tornadio2.conn.SocketConnection):
        __endpoints__ = {}

    application = tornado.web.Application(
        tornadio2.TornadioRouter(SocketConnection).apply_routes([
            # Static assets for local development
            (r"/(favicon.ico)", tornado.web.StaticFileHandler, {"path": "static/img/"}),
            (r"/static/(.*)", tornado.web.StaticFileHandler, {"path": "static/"}),

            # Main stream
            (r"/stream.mp3", StreamHandler)]),
        socket_io_port=8192,
        enabled_protocols=['websocket', 'xhr-multipart', 'xhr-polling', 'jsonp-polling']
    )

    application.listen(8888)
    tornadio2.server.SocketServer(application)


def add_tracks():
    m = Mixer(queue=queue, callback=StreamHandler.on_new_frame)
    m.start()
    try:
        for i in xrange(0, 10):
            tracks = filter(good_track, client.get('/tracks', order='hotness', limit=10, offset=i))
            shuffle(tracks)
            for track in tracks:
                if m.stopped:
                    log.info("Processing thread dead - stopping")
                    raise RuntimeError()
                if len(m.tracks) < prime_limit:
                    log.info("Not waiting for ready - filling track buffer up to %d", prime_limit)
                else:
                    log.info("Waiting for ready...")
                    m.ready.acquire()
                log.info("Grabbing stream of %s", track.title)
                stream = cStringIO.StringIO(client.get(track.stream_url).raw_data)
                log.info("Adding new track.")
                m.add_track(stream, track)

    finally:
        pass
        #m.stop()

if __name__ == "__main__":
    start()
