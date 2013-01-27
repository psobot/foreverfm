import sys
import tsp
import time
import shlex
import config
import apikeys
import difflib
import logging
import traceback
import soundcloud
from cube import emit
from timer import Timer
from requests import HTTPError
from database import Database


log = logging.getLogger(__name__)
test = 'test' in sys.argv
client = soundcloud.Client(client_id=apikeys.SOUNDCLOUD_CLIENT_KEY)

#   Turn off the excessive "Starting new HTTPS connection (1): i1.sndcdn.com"
#   logs that happen before every single request:
soundcloud.request.requests.packages.\
        urllib3.connectionpool.log.setLevel(logging.CRITICAL)


def getIndexOfId(l, value):
    for pos, t in enumerate(l):
        if t.id == value:
            return pos

    # Matches behavior of list.index
    raise ValueError("list.index(x): x not in list")


class Criteria(object):
    WEIGHT = 1

    def __init__(self):
        self.update_weight()

    def __call__(self, a, b):
        try:
            d = max(min(self.diff(a, b), 1.0), 0.0)
        except Exception:
            d = None
        if d is not None:
            return (d * self.WEIGHT, self.WEIGHT)
        else:
            return (0, 0)

    def precompute(self, track):
        pass

    def postcompute(self, track):
        pass

    def update_weight(self):
        try:
            self.WEIGHT = getattr(config,
                                  self.__class__.__name__.lower() + "_weight")
        except:
            log.warning("Could not update weight for criteria \"%s\":\n%s",
                        self.__class__.__name__, traceback.format_exc())

    def diff(self, a, b):
        raise NotImplementedError()


class Tag(Criteria):
    def precompute(self, track):
        try:
            track.obj['_tags'] = set(shlex.split(track.tag_list))
        except ValueError:
            track.obj['_tags'] = set()

    def postcompute(self, track):
        del track.obj['_tags']

    def diff(self, a, b):
        """
        Return the number of tags that are uncommon between the two tracks.
        """
        if a._tags and b._tags:
            return (len(a._tags | b._tags) - len(a._tags & b._tags)) / 10.0
        else:
            return None


class Tempo(Criteria):
    def diff(self, a, b):
        a = a.tempo if hasattr(a, 'tempo') else a.bpm
        b = b.tempo if hasattr(b, 'tempo') else b.bpm
        if a < 200 and b < 200:
            return abs(a - b) / 100.0


class Length(Criteria):
    def diff(self, a, b):
        return abs(a.duration - b.duration) / 100.0


class Spread(Criteria):
    def diff(self, a, b):
        return int(a.user['username'] == b.user['username'])


class Genre(Criteria):
    def diff(self, a, b):
        r = difflib.SequenceMatcher(a=a.genre.lower(),
                                    b=b.genre.lower()).ratio()
        return (1.0 - r)


class Danceability(Criteria):
    def diff(self, a, b):
        if hasattr(a, 'danceability') and hasattr(b, 'danceability'):
            return abs(a.danceability - b.danceability)


class Energy(Criteria):
    def diff(self, a, b):
        if hasattr(a, 'energy') and hasattr(b, 'energy'):
            return abs(a.energy - b.energy)


class Loudness(Criteria):
    def diff(self, a, b):
        if hasattr(a, 'loudness') and hasattr(b, 'loudness'):
            return abs(a.loudness - b.loudness) / 10.0


criteria = [Tag(), Tempo(), Length(), Spread(), Genre(), Danceability(), Energy(), Loudness()]


class DeduplicatedTrack(soundcloud.resource.Resource):
    def __init__(self, o):
        self.obj = o.obj

    def __eq__(self, other):
        if self.title.lower() == other.title.lower():
            return True
        return hash(self) == hash(other)

    def __hash__(self):
        #   TODO: This is kind of a hack
        return hash(self.duration)


def distance(a, b):
    values = [c(a, b) for c in criteria]
    return float(sum([n for n, _ in values])) /\
           float(sum([d for _, d in values]))


def chunks(l, n):
    for i in xrange(0, len(l), n):
        yield l[i:i + n]


def valid(track, user_blacklist=set(), tag_blacklist=set()):
    return (track.streamable or track.downloadable) \
            and track.duration < (config.max_track_length * 1000) \
            and track.duration > (config.min_track_length * 1000) \
            and not track.user['username'] in user_blacklist \
            and track._tags.isdisjoint(tag_blacklist)


def cull(tracks):
    u = set(config.blacklist['user'])
    t = set(config.blacklist['tag'])
    for track in tracks:
        for criterion in criteria:
            criterion.precompute(track)
    tracks = filter(lambda x: valid(x, u, t), tracks)
    tracks = list(set([DeduplicatedTrack(t) for t in tracks]))
    return tracks


def get_immediate_tracks(db):
    try:
        success = False
        for track in open(config.immediate_track_list):
            try:
                res = client.get('/tracks/%d' % int(track))
                for criterion in criteria:
                    criterion.precompute(res)
                res = db.merge(res)
                for criterion in criteria:
                    criterion.postcompute(res)
                success = True
                yield res
            except Exception as e:
                log.warning("Couldn't add immediate track \"%s\" due to %s!",
                            track, e)
        if success:
            tracklist = open(config.immediate_track_list, 'w')
            tracklist.write("")
            tracklist.close()
    except Exception as e:
        log.error("Got %s when trying to fetch immediate tracks!", e)
        yield []


def get_force_mix_tracks(db):
    try:
        for track in open(config.force_mix_track_list):
            try:
                res = client.get('/tracks/%d' % int(track))
                for criterion in criteria:
                    criterion.precompute(res)
                res = db.merge(res)
                yield res
            except Exception as e:
                log.warning("Couldn't add forced track \"%s\" due to %s!",
                            track, e)
    except Exception as e:
        log.error("Got %s when trying to fetch forced tracks!", e)
        yield []


def generate():
    try:
        tracks = []
        last = []
        wait = 2  # seconds
        d = Database()
        while test:
            yield d.merge(client.get('/tracks/73783917'))

        while True:
            log.info("Grabbing fresh tracklist from SoundCloud...")
            with Timer() as t:
                while not tracks:
                    try:
                        tracks =  client.get('/tracks', order='hotness', limit=200, offset=0)
                        tracks += client.get('/tracks', order='hotness', limit=200, offset=200)
                    except Exception as e:
                        log.warning("Got %s from SoundCloud. Retrying in %2.2f seconds...",
                                    e, wait)
                        time.sleep(wait)

            log.info("Got %d tracks in %2.2fms.", len(tracks), t.ms)
            emit('tracks_fetch', {"count": len(tracks), "ms": t.ms})

            if last and not any([t.id == last[-1].id for t in tracks]):
                tracks.append(last[-1])
            tracks = cull(tracks)

            tracks += list(get_force_mix_tracks(d))

            try:
                tracks = [d.merge(t) for t in tracks]
            except:
                log.warning("Could not merge tracks with DB due to:\n%s", traceback.format_exc())

            log.info("Solving TSP on %d tracks...", len(tracks))
            with Timer() as t:
                tracks = [tracks[i] for i in tsp.solve(tracks, distance, len(tracks) * config.tsp_mult)]
            log.info("Solved TSP in %2.2fms.", t.ms)
            emit('tsp_solve', {"count": len(tracks), "ms": t.ms})

            for track in tracks:
                for criterion in criteria:
                    criterion.postcompute(track)

            if last:
                i = getIndexOfId(tracks, last[-1].id) + 1
                tracks = tracks[i:] + tracks[:i]

            for track in tracks:
                for priority in get_immediate_tracks(d):
                    emit('decide_priority')
                    yield priority
                emit('decide_normal')
                yield track

            last = tracks
            tracks = []
    except:
        print traceback.format_exc()
        log.critical("%s", traceback.format_exc())


def print_table(tracks):
    print "delta",
    for criterion in criteria:
        print "\t%s\t" % criterion.__class__.__name__,
    print "\tBPM\tTitle"

    for i in xrange(1, len(tracks)):
        print "%2.2f" % distance(tracks[i], tracks[i - 1]),
        for criterion in criteria:
            print "\t%2.1f/%2.1f" % criterion(tracks[i], tracks[i - 1]),
        print "\t%2.1f" % ((tracks[i].tempo if hasattr(tracks[i], 'tempo') else tracks[i].bpm) or 0),
        print "\t", tracks[i].title, "by", tracks[i].user['username']

if __name__ == "__main__":
    print "Testing the BRAIN..."
    d = Database()
    o = None
    while not o:
        try:
            o  = client.get('/tracks', order='hotness', limit=200)
            o += client.get('/tracks', order='hotness', limit=200, offset=200)
        except HTTPError as e:
            print "Error from SC. (%s) Trying again..." % e
            pass
    tracks = cull([d.merge(t) for t in o])

    print "Solving TSP on %d tracks..." % len(tracks)

    with Timer() as t:
        tracks = [tracks[i] for i in tsp.solve(tracks, distance, len(tracks) * config.tsp_mult)]
    print "Solved TSP in %2.2fms." % t.ms
    #   TODO:   Use standard deviation to find the limit of deviation
    #           for tempo difference in tracks. I.e.: Any tracks that don't
    #           fit next to their neighbours should be removed, then TSP re-run.

    print_table(tracks)
