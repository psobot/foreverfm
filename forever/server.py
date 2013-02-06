"""
Forever.fm Server
by @psobot, Nov 3 2012
"""

import config
import apikeys
import customlog
import logging

import os
import sys
import json
import lame
import copy
import time
import info
import random
import restart
import datetime
import threading
import traceback
import tornado.web
import statistician
import tornado.ioloop
import tornado.template
import tornadio2.server
import multiprocessing
import pyechonest.config

from cube import emit
from mixer import Mixer
from daemon import Daemon
from hotswap import Hotswap
from listeners import Listeners
from assetcompiler import compiled
from sockethandler import SocketHandler
from bufferedqueue import BufferedReadQueue
from monitor import MonitorHandler, MonitorSocket

#   API Key setup
pyechonest.config.ECHO_NEST_API_KEY = apikeys.ECHO_NEST_API_KEY

started_at_timestamp = time.time()
started_at = datetime.datetime.utcnow()

test = 'test' in sys.argv
frontend = 'frontend' in sys.argv
stream = not frontend
SECONDS_PER_FRAME = lame.SAMPLES_PER_FRAME / 44100.0

templates = tornado.template.Loader(config.template_dir)
templates.autoescape = None
first_frame = threading.Semaphore(0)


class MainHandler(tornado.web.RequestHandler):
    mtime = 0
    template = 'index.html'

    def __gen(self):
        debug = self.get_argument('__debug', None)
        if debug is None:
            debug = self.request.host.startswith("localhost")
        else:
            debug = debug in ["True", 1, "on"]
        kwargs = {
            'debug': debug,
            'compiled': compiled,
            'open': len(StreamHandler.relays) > 0 or debug,
            'endpoint': StreamHandler.relay_url() if not debug else "/all.mp3"
        }
        try:
            if os.path.getmtime(config.template_dir + self.template) > self.mtime:
                templates.reset()
                self.mtime = time.time()
            return templates.load(self.template).generate(**kwargs)
        except Exception, e:
            log.error(e)
            tornado.web.RequestHandler.send_error(self, 500)
            return

    def head(self):
        self.__gen()
        self.finish()

    def get(self):
        self.finish(self.__gen())


class InfoHandler(tornado.web.RequestHandler):
    actions = []
    started = None
    samples = 0L
    duration = 0.
    width = 0L

    @classmethod
    def add(self, data):
        if not self.actions:
            self.started = time.time()
        self.samples += data['samples']
        self.duration += data['duration']
        self.width += data['width']

        self.clean()
        log.info("Adding track info. Currently holding info for %d tracks.",
                 len(self.actions))
        self.actions.append(data)
        SocketHandler.on_segment(data)

    @classmethod
    def clean(cls):
        try:
            now = time.time()
            before = len(cls.actions)
            while cls.actions and cls.actions[0]['time'] \
               + cls.actions[0]['duration'] + config.past_played_buffer < now:
                cls.actions.pop(0)
                end = cls.actions[0]['time'] + cls.actions[0]['duration']
                log.info("Removing action that ended at %d (now is %d).",
                         end, now)
            if before - len(cls.actions) > 0:
                log.info("Removed %d actions.", before - len(cls.actions))
        except:
            log.error("Error while cleaning up:\n%s", traceback.format_exc())

    @classmethod
    def stats(cls):
        return {
            "started": cls.started,
            "samples": cls.samples,
            "duration": cls.duration,
            "width": cls.width
        }

    def get(self):
        self.set_header("Content-Type", "application/json")
        try:
            now = self.get_argument('now', None)
            if now:
                now = time.time()
                for _action in self.actions:
                    if _action['time'] < now \
                    and _action['time'] + _action['duration'] > now:
                        action = copy.copy(_action)
                        del action['waveform']
                        self.write(json.dumps({'frame': action, 'now': now},
                                   ensure_ascii=False).encode('utf-8'))
                        return
                self.write(json.dumps([]))
            else:
                self.write(json.dumps(self.actions, ensure_ascii=False).encode('utf-8'))
        except:
            log.error("Could not send info burst:\n%s", traceback.format_exc())
            log.error("Data:\n%s", self.actions)
            self.write(json.dumps([]))


class TimingHandler(tornado.web.RequestHandler):
    def get(self):
        self.set_header("Content-Type", "application/json")
        self.write(json.dumps({"time": time.time() * 1000}, ensure_ascii=False).encode('utf-8'))


class StreamHandler(tornado.web.RequestHandler):
    relays = []
    listeners = []

    @classmethod
    def relay_url(cls):
        if len(cls.relays) == 1:
            return cls.relays[0].url
        elif len(cls.relays) > 1:
            choices = [relay for relay in cls.relays for _ in xrange(0, relay.weight)]
            return random.choice(choices).url
        else:
            return ""

    @classmethod
    def stream_frames(cls):
        try:
            cls.relays.broadcast()
        except:
            log.error("Could not broadcast due to: \n%s", traceback.format_exc())

    @classmethod
    def check(cls):
        #   TODO: This should do HTTP requests to ensure that all relays are
        #   still up
        pass

    def head(self):
        try:
            ip = self.request.headers.get('X-Real-Ip', self.request.remote_ip)
            ua = self.request.headers.get('User-Agent', None)
            if ua == config.relay_ua or len(self.relays) == 0:
                log.info("Got HEAD for relay at %s.", ip)
                self.set_header("Content-Type", "audio/mpeg")
                self.finish()
            else:
                if not self.relays:
                    tornado.web.RequestHandler.send_error(self, 503)
                else:
                    relay = self.relay_url()
                    log.info("Redirected new listener %s to %s", ip, relay)
                    self.redirect(relay)
        except:
            log.error("Error in stream.head:\n%s", traceback.format_exc())
            tornado.web.RequestHandler.send_error(self, 500)

    @tornado.web.asynchronous
    def get(self):
        try:
            ip = self.request.headers.get('X-Real-Ip', self.request.remote_ip)
            ua = self.request.headers.get('User-Agent', None)
            if ua == config.relay_ua:
                url = self.request.headers['X-Relay-Addr']
                if not url.startswith('http://'):
                    url = "http://" + url
                port = self.request.headers['X-Relay-Port']
                self.weight = int(self.request.headers.get('X-Relay-Weight', 1))
                log.info("Added new relay at %s:%s with weight %d.", url, port, self.weight)
                self.set_header("Content-Type", "audio/mpeg")
                self.url = "%s:%s/all.mp3" % (url, port)
                self.relays.append(self)
                emit("relays", {"count": len(self.relays)})
            else:
                if self.request.host.startswith("localhost"):
                    log.info("Added new debug listener at %s.", ip)
                    self.set_header("Content-Type", "audio/mpeg")
                    self.relays.append(self)
                elif not self.relays:
                    tornado.web.RequestHandler.send_error(self, 503)
                else:
                    relay = self.relay_url()
                    log.info("Redirected new listener %s to %s", ip, relay)
                    self.redirect(relay)
        except:
            log.error("Error in stream.get:\n%s", traceback.format_exc())
            tornado.web.RequestHandler.send_error(self, 500)

    def on_finish(self):
        if self in self.relays:
            self.relays.remove(self)
            ip = self.request.headers.get('X-Real-Ip', self.request.remote_ip)
            log.info("Removed relay at %s with weight %d.", ip, self.weight)
            emit("relays", {"count": len(self.relays)})


class SocketConnection(tornadio2.conn.SocketConnection):
    __endpoints__ = {
        "/info.websocket": SocketHandler,   #TODO: Rename
        "/monitor.websocket": MonitorSocket
    }


if __name__ == "__main__":
    Daemon()

    for handler in logging.root.handlers:
        logging.root.removeHandler(handler)
    logging.root.addHandler(customlog.MultiprocessingStreamHandler())

    log = logging.getLogger(config.log_name)
    log.info("Starting %s...", config.app_name)

    track_queue = multiprocessing.Queue(1)
    log.info("Initializing read queue to hold %2.2f seconds of audio.",
             config.frontend_buffer)
    v2_queue = BufferedReadQueue(int(config.frontend_buffer / SECONDS_PER_FRAME))
    info_queue = multiprocessing.Queue()

    mixer = Mixer(iqueue=track_queue,
                  oqueues=(v2_queue.raw,),
                  infoqueue=info_queue)
    mixer.start()

    if stream:
        import brain
        Hotswap(track_queue.put, brain).start()
    Hotswap(InfoHandler.add, info, 'generate', info_queue, first_frame).start()
    Hotswap(MonitorSocket.update,
            statistician, 'generate',
            lambda: StreamHandler.relays,
            InfoHandler.stats,
            mp3_queue=v2_queue).start()

    tornado.ioloop.PeriodicCallback(
        lambda: restart.check('restart.txt',
                              started_at_timestamp,
                              len(StreamHandler.relays)),
        config.restart_timeout * 1000
    ).start()
    tornado.ioloop.PeriodicCallback(InfoHandler.clean, 5 * 1000).start()
    tornado.ioloop.PeriodicCallback(StreamHandler.check, 10 * 1000).start()

    StreamHandler.relays = Listeners(v2_queue, "All", first_frame)

    application = tornado.web.Application(
        tornadio2.TornadioRouter(SocketConnection).apply_routes([
            # Static assets for local development
            (r"/(favicon.ico)", tornado.web.StaticFileHandler, {"path": "static/img/"}),
            (r"/static/(.*)", tornado.web.StaticFileHandler, {"path": "static/"}),

            (r"/timing.json", TimingHandler),

            (r"/all.json", InfoHandler),
            (r"/all.mp3", StreamHandler),

            (r"/monitor", MonitorHandler),
            (r"/", MainHandler),
        ]),
        socket_io_port=config.socket_port,
        enabled_protocols=['websocket', 'xhr-multipart', 'xhr-polling', 'jsonp-polling']
    )

    frame_sender = tornado.ioloop.PeriodicCallback(
        StreamHandler.stream_frames, SECONDS_PER_FRAME * 1000
    )
    frame_sender.start()

    application.listen(config.http_port)
    tornadio2.server.SocketServer(application)
