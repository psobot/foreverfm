"""
Originally created by Tristan Jehan and Jason Sundram.
Heavily modified by Peter Sobot for integration with forever.fm.
"""

from action import Blend, Crossfade
from echonest.audio import assemble, LocalAudioStream
from audio import AudioData

from capsule_support import order_tracks, resample_features, \
                            timbre_whiten, initialize, make_transition, terminate, \
                            FADE_OUT, is_valid, LOUDNESS_THRESH
import os
import gc
import time
import config
import logging
import urllib2
import traceback
import threading
import soundcloud
import multiprocessing
from lame import Lame

client = soundcloud.Client(client_id=config.SOUNDCLOUD_CLIENT_KEY)

log = logging.getLogger(__name__)

import sys
test = 'test' in sys.argv


class Mixer(multiprocessing.Process):
    def __init__(self, iqueue, oqueues, infoqueue,
                 settings=({},), initial=None,
                 max_play_time=300, transition_time=30,
                 samplerate=44100):
        self.iqueue = iqueue
        self.infoqueue = infoqueue

        self.encoders = []
        if len(oqueues) != len(settings):
            raise ValueError("Differing number of output queues and settings!")

        self.oqueues = oqueues
        self.settings = settings

        self.__track_lock = threading.Lock()
        self.__tracks = []

        self.max_play_time = max_play_time
        self.transition_time = transition_time
        self.samplerate = 44100
        self.__stop = False

        if isinstance(initial, list):
            self.add_tracks(initial)
        elif isinstance(initial, AudioData):
            self.add_track(initial)

        multiprocessing.Process.__init__(self)

    @property
    def tracks(self):
        self.__track_lock.acquire()
        tracks = self.__tracks
        self.__track_lock.release()
        return tracks

    @tracks.setter
    def tracks(self, new_val):
        self.__track_lock.acquire()
        self.__tracks = new_val
        self.__track_lock.release()

    @property
    def current_track(self):
        return self.tracks[0]

    def get_stream(self, x):
        fname = os.path.abspath("cache/%d.mp3" % x['id'])
        if os.path.isfile(fname):
            return fname
        else:
            if x['downloadable'] and x['original_format'] == "mp3":
                url = x['download_url']
            else:
                url = x['stream_url']
            url += "?client_id=" + config.SOUNDCLOUD_CLIENT_KEY

            try:
                conn = urllib2.urlopen(url)
            except urllib2.URLError as e:
                log.warning("Encountered URL error while trying to fetch: %s. Retrying...", e)
                conn = urllib2.urlopen(url)

            f = open(fname, 'w')
            f.write(conn.read())
            f.close()
            return fname

    def analyze(self, x):
        if isinstance(x, list):
            return [self.analyze(y) for y in x]
        if isinstance(x, AudioData):
            return self.process(x)
        if isinstance(x, tuple):
            return self.analyze(*x)

        log.info("Grabbing stream of %s", x['title'])
        laf = LocalAudioStream(self.get_stream(x))
        setattr(laf, "_metadata", x)
        return self.process(laf)

    def add_track(self, track):
        log.info("ADDING TRACK IN BACKEND: %s", track['title'])
        self.tracks.append(self.analyze(track))

    def add_tracks(self, tracks):
        self.tracks += order_tracks(self.analyze(tracks))

    def process(self, track):
        if not hasattr(track.analysis.pyechonest_track, "title"):
            setattr(track.analysis.pyechonest_track, "title", track._metadata.get('title', "<unknown>"))
        log.info("Resampling features for %s", track.analysis.pyechonest_track)
        track.resampled = resample_features(track, rate='beats')
        track.resampled['matrix'] = timbre_whiten(track.resampled['matrix'])

        if not is_valid(track, self.transition_time):
            raise ValueError("Track too short!")

        track.gain = self.__db_2_volume(track.analysis.loudness)

        # for compatibility, we make mono tracks stereo
        log.info("Done processing %s", track.analysis.pyechonest_track)
        return track

    def __db_2_volume(self, loudness):
        return (1.0 - LOUDNESS_THRESH * (LOUDNESS_THRESH - loudness) / 100.0)

    def loop(self):
        while len(self.tracks) < 2:
            log.info("Waiting for a new track.")
            track = self.iqueue.get()
            try:
                self.add_track(track)  # TODO: Extend to allow multiple tracks.
                log.info("Got a new track.")
            except Exception, e:
                log.error("Could not add track due to %s! Skipping...", e)

        # Initial transition. Should contain 2 instructions: fadein, and playback.
        inter = self.tracks[0].analysis.duration - self.transition_time * 3
        yield initialize(self.tracks[0], inter, self.transition_time, 10)

        while not self.__stop:
            while len(self.tracks) > 1:
                stay_time = min(self.tracks[0].analysis.duration
                                 - self.transition_time * 3,
                                self.tracks[1].analysis.duration
                                 - self.transition_time * 3)
                yield make_transition(self.tracks[0],
                                      self.tracks[1],
                                      stay_time,
                                      self.transition_time)
                self.tracks[0].finish()
                del self.tracks[0].analysis
                del self.tracks[0]
                gc.collect()
            log.info("Waiting for a new track.")
            try:
                self.add_track(self.iqueue.get())  # TODO: Allow multiple tracks.
                log.info("Got a new track.")
            except ValueError:
                log.warning("Track too short! Trying another.")
            except Exception:
                log.error("Exception while trying to add new track:\n%s",
                          traceback.format_exc())

        # Last chunk. Should contain 1 instruction: fadeout.
        yield terminate(self.tracks[-1], FADE_OUT)

    def run(self):
        for oqueue, settings in zip(self.oqueues, self.settings):
            e = Lame(oqueue=oqueue, **settings)
            self.encoders.append(e)
            e.start()

        try:
            ctime = None
            for i, _actions in enumerate(self.loop()):
                _a = time.time()
                log.info("Rendering audio data...")
                ADs = []
                actions = []
                for a in _actions:
                    try:
                        ADs.append(a.render())
                        actions.append(a)
                    except:
                        log.error("Could not render %s. Skipping.\n%s", a,
                                  traceback.format_exc())
                log.info("Rendered in %fs!", time.time() - _a)
                _a = time.time()
                log.info("Assembling audio data...")
                out = assemble(ADs, numChannels=2, sampleRate=self.samplerate)
                log.info("Assembled in %fs!", time.time() - _a)

                del ADs
                gc.collect()

                if not ctime:
                    ctime = time.time()
                for a in actions:
                    d = {
                        'time': ctime,
                        'action': a.__class__.__name__.split(".")[-1],
                        'duration': a.duration
                    }
                    if isinstance(a, Blend) or isinstance(a, Crossfade):
                        d['tracks'] = [{
                            "metadata": a.t1._metadata,
                            "start": a.l1[0][0],
                            "end": sum(a.l1[-1])
                        }, {
                            "metadata": a.t2._metadata,
                            "start": a.l2[0][0],
                            "end": sum(a.l2[-1])
                        }]
                    else:
                        d['tracks'] = [{
                            "metadata": a.track._metadata,
                            "start": a.start,
                            "end": a.start + a.duration
                        }]
                    self.infoqueue.put(d)
                    ctime += a.duration
                for encoder in self.encoders:
                    encoder.add_pcm(out.data)
                del out.data
                del out
                gc.collect()
        except:
            log.error("Something failed in mixer.run:\n%s",
                      traceback.format_exc())
            self.stop()
            return

    def stop(self):
        self.__stop = True

    @property
    def stopped(self):
        return self.__stop
