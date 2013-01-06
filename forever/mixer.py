"""
Based off of `capsule`, by Tristan Jehan and Jason Sundram.
Heavily modified by Peter Sobot for integration with forever.fm.
"""
import os
import gc
import apikeys
import logging
import urllib2
import traceback
import threading
import multiprocessing

from lame import Lame
from timer import Timer
from database import Database, merge

from echonest.audio import LocalAudioStream
from audio import AudioData

from capsule_support import order_tracks, resample_features, \
                            timbre_whiten, initialize, make_transition, terminate, \
                            FADE_OUT, is_valid, LOUDNESS_THRESH

log = logging.getLogger(__name__)

import sys
test = 'test' in sys.argv


def metadata_of(a):
    if hasattr(a, '_metadata'):
        return a._metadata.obj
    if hasattr(a, 'track'):
        return metadata_of(a.track)
    if hasattr(a, 't1') and hasattr(a, 't2'):
        return (metadata_of(a.t1), metadata_of(a.t2))
    raise ValueError("No metadata found!")


def generate_metadata(a):
    d = {
        'action': a.__class__.__name__.split(".")[-1],
        'duration': a.duration,
        'samples': a.samples
    }
    m = metadata_of(a)
    if isinstance(m, tuple):
        m1, m2 = m
        d['tracks'] = [{
            "metadata": m1,
            "start": a.s1,
            "end": a.e1
        }, {
            "metadata": m2,
            "start": a.s2,
            "end": a.e2
        }]
    else:
        d['tracks'] = [{
            "metadata": m,
            "start": a.start,
            "end": a.start + a.duration
        }]
    return d


class Mixer(multiprocessing.Process):
    def __init__(self, iqueue, oqueues, infoqueue,
                 settings=({},), initial=None,
                 max_play_time=300, transition_time=30 if not test else 5,
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
        fname = os.path.abspath("cache/%d.mp3" % x.id)
        if os.path.isfile(fname):
            return fname
        else:
            if x.downloadable and x.original_format == "mp3":
                url = x.download_url
            else:
                url = x.stream_url
            url += "?client_id=" + apikeys.SOUNDCLOUD_CLIENT_KEY

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

        log.info("Grabbing stream...", uid=x.id)
        laf = LocalAudioStream(self.get_stream(x))
        setattr(laf, "_metadata", x)
        Database().ensure(merge(x, laf.analysis))
        return self.process(laf)

    def add_track(self, track):
        self.tracks.append(self.analyze(track))

    def add_tracks(self, tracks):
        self.tracks += order_tracks(self.analyze(tracks))

    def process(self, track):
        if not hasattr(track.analysis.pyechonest_track, "title"):
            setattr(track.analysis.pyechonest_track, "title", track._metadata.title)
        log.info("Resampling features...", uid=track._metadata.id)
        track.resampled = resample_features(track, rate='beats')
        track.resampled['matrix'] = timbre_whiten(track.resampled['matrix'])

        if not is_valid(track, self.transition_time):
            raise ValueError("Track too short!")

        track.gain = self.__db_2_volume(track.analysis.loudness)
        log.info("Done processing.", uid=track._metadata.id)
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
            except Exception:
                log.error("Exception while trying to add new track:\n%s",
                          traceback.format_exc())

        # Initial transition. Should contain 2 instructions: fadein, and playback.
        inter = self.tracks[0].analysis.duration - self.transition_time * 3
        yield initialize(self.tracks[0], inter, self.transition_time, 10)

        while not self.__stop:
            while len(self.tracks) > 1:
                stay_time = min(self.tracks[0].analysis.duration
                                 - self.transition_time * 3,
                                self.tracks[1].analysis.duration
                                 - self.transition_time * 3)
                tra = make_transition(self.tracks[0],
                                      self.tracks[1],
                                      stay_time,
                                      self.transition_time)
                del self.tracks[0].analysis
                gc.collect()
                yield tra
                self.tracks[0].finish()
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

        log.error("Stopping!")
        # Last chunk. Should contain 1 instruction: fadeout.
        yield terminate(self.tracks[-1], FADE_OUT)

    def run(self):
        for oqueue, settings in zip(self.oqueues, self.settings):
            e = Lame(oqueue=oqueue, **settings)
            self.encoders.append(e)
            e.start()

        try:
            self.ctime = None
            for i, actions in enumerate(self.loop()):
                log.info("Rendering audio data for %d actions.", len(actions))
                for a in actions:
                    try:
                        with Timer() as t:
                            #   TODO: Move the "multiple encoding" support into
                            #   LAME itself - it should be able to multiplex the
                            #   streams itself.
                            self.encoders[0].add_pcm(a)
                            self.infoqueue.put(generate_metadata(a))
                        log.info("Rendered in %fs!", t.ms)
                    except:
                        log.error("Could not render %s. Skipping.\n%s", a,
                                  traceback.format_exc())
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
