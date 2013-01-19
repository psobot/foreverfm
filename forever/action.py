#!/usr/bin/env python
# encoding: utf-8
"""
action.py

Created by Tristan Jehan and Jason Sundram.
"""
import numpy
from numpy import zeros, multiply, float32, mean, copy

from echonest.audio import assemble
from cAction import limit, crossfade, fadein, fadeout, fade
from itertools import izip
import logging

import dirac

log = logging.getLogger(__name__)


def rows(m):
    """returns the # of rows in a numpy matrix"""
    return m.shape[0]


def make_mono(track):
    """Converts stereo tracks to mono; leaves mono tracks alone."""
    if track.data.ndim == 2:
        mono = mean(track.data, 1)
        track.data = mono
        track.numChannels = 1
    return track


def make_stereo(track):
    """If the track is mono, doubles it. otherwise, does nothing."""
    if track.data.ndim == 1:
        stereo = zeros((len(track.data), 2))
        stereo[:, 0] = copy(track.data)
        stereo[:, 1] = copy(track.data)
        track.data = stereo
        track.numChannels = 2
    return track


def render(actions, filename, verbose=True):
    """Calls render on each action in actions, concatenates the results,
    renders an audio file, and returns a path to the file"""
    pieces = [a.render() for a in actions]
    # TODO: allow numChannels and sampleRate to vary.
    out = assemble(pieces, numChannels=2, sampleRate=44100, verbose=verbose)
    return out, out.encode(filename)


class Playback(object):
    """A snippet of the given track with start and duration. Volume leveling
    may be applied."""
    def __init__(self, track, start, duration):
        self.track = track
        self.start = float(start)
        self.duration = float(duration)

    @property
    def samples(self):
        if isinstance(self.duration, float):
            return int(self.duration * 44100)
        return self.duration

    def render(self, chunk_size=None):
        gain = getattr(self.track, 'gain', None)
        if chunk_size is None:
            # self has start and duration, so it is a valid index into track.
            output = self.track[self].data

            # Normalize volume if necessary
            if gain is not None:
                # limit expects a float32 vector
                output = limit(multiply(output, float32(gain)))

            yield output
        else:
            if isinstance(self.start, float):
                start = int(self.start * 44100)
                end = int((self.start + self.duration) * 44100)
            else:
                start, end = self.start, self.end
            for i in xrange(start, end, chunk_size):
                if gain is not None:
                    yield limit(multiply(
                            self.track[i:min(end, i + chunk_size)].data,
                            float32(gain)
                          )).astype(numpy.int16)
                else:
                    yield self.track[i:min(end, i + chunk_size)].data

    def __repr__(self):
        return "<Playback '%s'>" % self.track.analysis.pyechonest_track.title

    def __str__(self):
        try:
            title = self.track.analysis.pyechonest_track.title
        except:
            title = "?"
        args = (self.start, self.start + self.duration,
                self.duration, title)
        return "Playback\t%.3f\t-> %.3f\t (%.3f)\t%s" % args


class Fadeout(Playback):
    def render(self, chunk_size=None):
        gain = getattr(self.track, 'gain', 1.0)
        if chunk_size is None:
            yield fadeout(self.track[self].data, gain)
        else:
            start = int(self.start * 44100)
            end = int((self.start + self.duration) * 44100)
            for i in xrange(start, end, chunk_size):
                e = min(end, i + chunk_size)
                yield (fade(self.track[i:e].data, gain,
                            1.0 - (float(i - start) / (end - start)),
                            1.0 - (float(e - start) / (end - start)))
                            .astype(numpy.int16))

    def __repr__(self):
        return "<Fadeout '%s'>" % self.track.analysis.pyechonest_track.title

    def __str__(self):
        args = (self.start, self.start + self.duration,
                self.duration, self.track.analysis.pyechonest_track.title)
        return "Fade out\t%.3f\t-> %.3f\t (%.3f)\t%s" % args


class Fadein(Playback):
    def render(self, chunk_size=None):
        gain = getattr(self.track, 'gain', 1.0)
        if chunk_size is None:
            output = self.track[self].data
            output = fadein(output, gain)
            yield output
        else:
            start = int(self.start * 44100)
            end = int((self.start + self.duration) * 44100)
            for i in xrange(start, end, chunk_size):
                e = min(end, i + chunk_size)
                yield (fade(self.track[i:e].data, gain,
                            (float(i - start) / (end - start)),
                            (float(e - start) / (end - start)))
                            .astype(numpy.int16))

    def __repr__(self):
        return "<Fadein '%s'>" % self.track.analysis.pyechonest_track.title

    def __str__(self):
        args = (self.start, self.start + self.duration,
                self.duration, self.track.analysis.pyechonest_track.title)
        return "Fade in\t%.3f\t-> %.3f\t (%.3f)\t%s" % args


class Edit(object):
    """Refer to a snippet of audio"""
    def __init__(self, track, start, duration):
        self.track = track
        self.start = float(start)
        self.duration = float(duration)

    def __str__(self):
        args = (self.start, self.start + self.duration,
                self.duration, self.track.analysis.pyechonest_track.title)
        return "Edit\t%.3f\t-> %.3f\t (%.3f)\t%s" % args

    def get(self):
        return self.track[self]

    @property
    def end(self):
        return self.start + self.duration


class Crossfade(object):
    """Crossfades between two tracks, at the start points specified,
    for the given duration"""
    def __init__(self, tracks, starts, duration, mode='linear'):
        self.t1, self.t2 = [Edit(t, s, duration) for t, s in zip(tracks, starts)]
        self.s1, self.s2 = starts
        self.e1, self.e2 = [s + self.t1.duration for s in starts]
        self.duration = self.t1.duration
        self.mode = mode

    @property
    def samples(self):
        if isinstance(self.duration, float):
            return int(self.duration * 44100)
        return self.duration

    def render(self, chunk_size=None):
        #   For now, only support stereo tracks
        assert self.t1.track.data.ndim == 2
        assert self.t2.track.data.ndim == 2
        if chunk_size is None:
            yield crossfade(self.t1.data, self.t2.data, self.mode)
        else:
            start = int(self.s1 * 44100)
            end = int((self.s1 + self.duration) * 44100)
            for i in xrange(start, end, chunk_size):
                e = min(end, i + chunk_size)
                yield (crossfade(self.t1.track[i:e].data,
                                 self.t2.track[i:e].data, self.mode,
                                 self.samples, i - start).astype(numpy.int16))

    def __repr__(self):
        args = (self.t1.track.analysis.pyechonest_track.title, self.t2.track.analysis.pyechonest_track.title)
        return "<Crossfade '%s' and '%s'>" % args

    def __str__(self):
        args = (self.t1.start, self.t2.start + self.duration, self.duration,
                self.t1.track.analysis.pyechonest_track.title, self.t2.track.analysis.pyechonest_track.title)
        return "Crossfade\t%.3f\t-> %.3f\t (%.3f)\t%s -> %s" % args


class Jump(Crossfade):
    """Move from one point """
    def __init__(self, track, source, target, duration):
        self.track = track
        self.t1, self.t2 = (Edit(track, source, duration),
                            Edit(track, target - duration, duration))
        self.duration = float(duration)
        self.mode = 'equal_power'
        self.CROSSFADE_COEFF = 0.6

    @property
    def source(self):
        return self.t1.start

    @property
    def target(self):
        return self.t2.end

    def __repr__(self):
        return "<Jump '%s'>" % (self.t1.track.analysis.pyechonest_track.title)

    def __str__(self):
        args = (self.t1.start, self.t2.end, self.duration,
                self.t1.track.analysis.pyechonest_track.title)
        return "Jump\t\t%.3f\t-> %.3f\t (%.3f)\t%s" % args


class Blend(object):
    """Mix together two lists of beats"""
    def __init__(self, tracks, lists):
        self.t1, self.t2 = tracks
        self.l1, self.l2 = lists
        self.s1, self.s2 = self.l1[0][0], self.l2[0][0]
        self.e1, self.e2 = sum(self.l1[-1]), sum(self.l2[-1])
        assert(len(self.l1) == len(self.l2))

        self.calculate_durations()

    def calculate_durations(self):
        zipped = zip(self.l1, self.l2)
        self.durations = [(d1 + d2) / 2.0 for ((s1, d1), (s2, d2)) in zipped]
        self.duration = sum(self.durations)

    def render(self):
        # use self.durations already computed
        # build 2 AudioQuantums
        # call Mix
        pass

    def __repr__(self):
        args = (self.t1.analysis.pyechonest_track.title, self.t2.analysis.pyechonest_track.title)
        return "<Blend '%s' and '%s'>" % args

    def __str__(self):
        # start and end for each of these lists.
        s1, e1 = self.l1[0][0], sum(self.l1[-1])
        s2, e2 = self.l2[0][0], sum(self.l2[-1])
        n1, n2 = self.t1.analysis.pyechonest_track.title, self.t2.analysis.pyechonest_track.title  # names
        args = (s1, s2, e1, e2, self.duration, n1, n2)
        return "Blend [%.3f, %.3f] -> [%.3f, %.3f] (%.3f)\t%s + %s" % args


class Crossmatch(Blend):
    quality = 0

    """Makes a beat-matched crossfade between the two input tracks."""
    def calculate_durations(self):
        c, dec = 1.0, 1.0 / float(len(self.l1) + 1)
        self.durations = []
        for ((s1, d1), (s2, d2)) in zip(self.l1, self.l2):
            c -= dec
            self.durations.append(c * d1 + (1 - c) * d2)
        self.duration = sum(self.durations)

    @property
    def samples(self):
        if not hasattr(self, '__samples'):
            durs = []
            for l in [self.l1, self.l2]:
                rates = []
                o = 0
                signal_start = int(l[0][0] * 44100)
                for i in xrange(len(l)):
                    rate = (int(l[i][0] * 44100) - signal_start,
                            self.durations[i] / l[i][1])
                    rates.append(rate)
                for (s1, r1), (s2, r2) in zip(rates, rates[1:]):
                    o += int((s2 - s1) * r1)
                end = int((sum(l[-1]) - l[0][0]) * 44100)
                o += int((end - rates[-1][0]) * rates[-1][1])
                durs += [o]
            self.__samples = min(durs)
        return self.__samples

    def g(self, d, gain, rate):
        s = 44100
        if gain is not None:
            return limit(multiply(dirac.timeScale(d, rate, s, self.quality),
                         float32(gain)))
        else:
            return dirac.timeScale(d, rate, s, self.quality)

    def stretch(self, t, l):
        """t is a track, l is a list"""
        gain = getattr(t, 'gain', None)
        signal_start = int(l[0][0] * t.sampleRate)
        rates = []
        for i in xrange(len(l)):
            rate = (int(l[i][0] * t.sampleRate) - signal_start,
                    self.durations[i] / l[i][1])
            rates.append(rate)

        #   In case the for loop never runs due to too few elements.
        e = int(rates[-1][0] + signal_start)

        for i, ((s1, r1), (s2, r2)) in enumerate(izip(rates, rates[1:])):
            s = int(s1 + signal_start)
            e = int(s2 + signal_start)
            yield self.g(t[s:e].data, gain, r1)

        end = signal_start + int((sum(l[-1]) - l[0][0]) * t.sampleRate)
        yield self.g(t[e:end].data, gain, r2)

    def __buffered(self, t, l, c):
        buf = None
        for chunk in self.stretch(t, l):
            if buf is not None:
                chunk = numpy.append(buf, chunk, 0)
                buf = None
            if len(chunk) > c:
                steps = range(0, len(chunk), c)
                for s, e in izip(steps, steps[1:]):
                    yield chunk[s:e]
                buf = chunk[e:]
            elif len(chunk) < c:
                buf = chunk
            else:
                yield chunk
        if buf is not None and len(buf):
            yield buf

    def __limited(self, t, l, c, limit=None):
        if limit is None:
            limit = self.samples
        for i, chunk in enumerate(self.__buffered(t, l, c)):
            if (i * c) + len(chunk) > limit:
                yield chunk[0:limit - (i * c)]
                return
            else:
                yield chunk

    def render(self, chunk_size=None):
        stretch1, stretch2 = self.__limited(self.t1, self.l1, chunk_size),\
                             self.__limited(self.t2, self.l2, chunk_size)
        total = 0
        for i, (a, b) in enumerate(izip(stretch1, stretch2)):
            o = min(len(a), len(b))
            total += o
            yield crossfade(a[:o], b[:o], '', self.samples, i * chunk_size)\
                    .astype(numpy.int16)

        leftover = self.samples - total
        if leftover > 0:
            log.warning("Leftover samples (%d) when crossmatching.", leftover)

    def __repr__(self):
        try:
            args = (self.t1.analysis.pyechonest_track.title,
                    self.t2.analysis.pyechonest_track.title)
        except:
            args = ("?", "?")
        return "<Crossmatch '%s' and '%s'>" % args

    def __str__(self):
        # start and end for each of these lists.
        s1, e1 = self.l1[0][0], sum(self.l1[-1])
        s2, e2 = self.l2[0][0], sum(self.l2[-1])
        try:
            n1, n2 = self.t1.analysis.pyechonest_track.title, self.t2.analysis.pyechonest_track.title   # names
        except:
            n1, n2 = "?", "?"
        args = (s1, e2, self.duration, n1, n2)
        return "Crossmatch\t%.3f\t-> %.3f\t (%.3f)\t%s -> %s" % args


def humanize_time(secs):
    """Turns seconds into a string of the form HH:MM:SS,
    or MM:SS if less than one hour."""
    mins, secs = divmod(secs, 60)
    hours, mins = divmod(mins, 60)
    if 0 < hours:
        return '%02d:%02d:%02d' % (hours, mins, secs)

    return '%02d:%02d' % (mins, secs)


def display_actions(actions):
    total = 0
    print
    for a in actions:
        print "%s\t  %s" % (humanize_time(total), unicode(a))
        total += a.duration
    print
