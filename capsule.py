#!/usr/bin/env python
# encoding: utf=8

"""
capsule.py

accepts songs on the commandline, order them, beatmatch them, and output an audio file

Created by Tristan Jehan and Jason Sundram.
Heavily modified by Peter Sobot for integration with forever.fm.
"""

import threading
import multiprocessing
from echonest.action import make_stereo
from audio import LocalAudioFile, assemble

from capsule_support import order_tracks, resample_features, \
                            timbre_whiten, initialize, make_transition, terminate, \
                            FADE_OUT, display_actions, is_valid, LOUDNESS_THRESH
import traceback
import time
import logging
import cStringIO
from lame import Lame
import numpy

import soundcloud
client = soundcloud.Client(client_id="6325e96fcef18547e6552c23b4c0788c")

logging.basicConfig(format="%(asctime)s P%(process)-5d (%(levelname)8s) %(module)16s%(lineno)5d: %(uid)32s %(message)s")
log = logging.getLogger(__name__)

import sys
test_mode = 'test' in sys.argv

import gc


class Mixer(multiprocessing.Process):
    def __init__(self, iqueue, oqueues,
                 settings=({},), initial=None,
                 max_play_time=300, transition_time=30,
                 safety_buffer=30, samplerate=44100):
        self.iqueue = iqueue

        self.encoders = []
        if len(oqueues) != len(settings):
            raise ValueError("Differing number of output queues and settings!")

        self.oqueues = oqueues
        self.settings = settings

        self.__track_lock = threading.Lock()
        self.__tracks = []

        self.max_play_time = max_play_time
        self.transition_time = transition_time
        self.safety_buffer = safety_buffer
        self.samplerate = 44100
        self.__stop = False
        self.__first = True

        if isinstance(initial, list):
            self.add_tracks(initial)
        elif isinstance(initial, LocalAudioFile):
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
        #   TODO: Extend me to deal with possible downloadable tracks
        return cStringIO.StringIO(client.get(x['stream_url']).raw_data)

    def analyze(self, x):
        if isinstance(x, list):
            return [self.analyze(y) for y in x]
        if isinstance(x, LocalAudioFile):
            return self.process(x)
        if isinstance(x, tuple):
            return self.analyze(*x)

        log.info("Grabbing stream of %s", x['title'])
        laf = LocalAudioFile(self.get_stream(x), type='mp3')
        setattr(laf, "_metadata", x)
        return self.process(laf)  # TODO: Fix MP3 const

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
        r = make_stereo(track)
        log.info("Done processing %s", track.analysis.pyechonest_track)
        return r

    def __db_2_volume(self, loudness):
        return (1.0 - LOUDNESS_THRESH * (LOUDNESS_THRESH - loudness) / 100.0)

    def loop(self):
        while len(self.tracks) < 2:
            log.info("Waiting for a new track.")
            self.add_track(self.iqueue.get())  # TODO: Extend me to allow multiple tracks.
            log.info("Got a new track.")

        # Initial transition. Should contain 2 instructions: fadein, and playback.
        inter = self.tracks[0].analysis.duration - self.transition_time * 3
        yield initialize(self.tracks[0], inter,
                         self.transition_time, 10)

        while not self.__stop:
            while len(self.tracks) > 1:
                stay_time = min(self.tracks[0].analysis.duration - self.transition_time * 3,
                                self.tracks[1].analysis.duration - self.transition_time * 3)
                yield make_transition(self.tracks[0],
                                      self.tracks[1],
                                      stay_time,
                                      self.transition_time)
                self.tracks = self.tracks[1:]
            log.info("Waiting for a new track.")
            self.add_track(self.iqueue.get())  # TODO: Extend me to allow multiple tracks.
            log.info("Got a new track.")

        # Last chunk. Should contain 1 instruction: fadeout.
        yield terminate(self.tracks[-1], FADE_OUT)

    def run(self):
        for oqueue, settings in zip(self.oqueues, self.settings):
            e = Lame(oqueue=oqueue, **settings)
            self.encoders.append(e)
            e.start()

        try:
            while test_mode:
                import wave
                f = wave.open("test.wav")
                a = numpy.frombuffer(f.readframes(f.getnframes()), dtype=numpy.int16).reshape((-1, 2))
                self.encode(a)

            renderer = display_actions()
            renderer.send(None)
            for i, actions in enumerate(self.loop()):
                for action in actions:
                    log.info(renderer.send(action))
                _a = time.time()
                log.info("Rendering audio data...")
                ADs = [a.render() for a in actions]
                log.info("Rendered in %fs!", time.time() - _a)
                _a = time.time()
                log.info("Assembling audio data...")
                out = assemble(ADs, numChannels=2, sampleRate=self.samplerate)
                log.info("Assembled in %fs!", time.time() - _a)
                del ADs
                gc.collect()
                self.encode(out.data)
        except:
            traceback.print_exc()
            self.stop()
            return

    def encode(self, pcm_data):
        samples = len(pcm_data)
        put_time = time.time()
        for encoder in self.encoders:
            encoder.add_pcm(pcm_data)
        done_time = time.time()
        del pcm_data
        gc.collect()
        if not self.__first:
            delay = max(0, (samples / float(self.samplerate)) \
                            - (done_time - put_time) \
                            - self.safety_buffer)
            time.sleep(delay)
        self.__first = False

    def stop(self):
        self.__stop = True

    @property
    def stopped(self):
        return self.__stop
