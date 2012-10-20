from capsule import Mixer
import Queue
import tornado.web
import tornado.ioloop
import tornado.template
import tornadio2.server
import threading
import logging
from Queue import Empty
from random import shuffle
from lame import Lame
import multiprocessing
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
            delay = sent - cls.last_send
            if True or delay > 0.15:
                log.warning("Time between MP3 packets: %fs", delay)
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
        socket_io_port=8193,
        enabled_protocols=['websocket', 'xhr-multipart', 'xhr-polling', 'jsonp-polling']
    )

    application.listen(8192)
    tornadio2.server.SocketServer(application)


def add_tracks():
    track_queue = multiprocessing.Queue(1)
    pcm_queue = multiprocessing.Queue()

    encoder = Lame(StreamHandler.on_new_frame, oqueue=queue)
    encoder.start()
    sent = 0

    m = Mixer(inqueue=track_queue, outqueue=pcm_queue)
    m.start()

    audio_buffer = []
    try:
        for i in xrange(0, 10):
            tracks = filter(good_track, client.get('/tracks', order='hotness', limit=20, offset=i))
            shuffle(tracks)
            for track in tracks:
                log.info("Grabbing stream of %s", track.title)
                stream = client.get(track.stream_url).raw_data
                log.info("Adding new track.")
                track_queue.put((stream, track.obj))
                sent += 1
                log.info("Added new track.")
                if sent < 2:
                    continue
                if len(audio_buffer) > 1:
                    log.info("Encoding...")
                    encoder.add_pcm(audio_buffer.pop(0))
                    log.info("Encoded!")
                log.info("Waiting for PCM...")
                audio_buffer.append(pcm_queue.get())
    finally:
        pass

if __name__ == "__main__":
    start()
