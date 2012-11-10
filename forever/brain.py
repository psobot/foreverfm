import sys
import tsp
import time
import shlex
import config
import difflib
import logging
import traceback
import soundcloud
from timer import Timer
from random import shuffle
from requests import HTTPError
from operator import itemgetter

log = logging.getLogger(__name__)
test = 'test' in sys.argv
client = soundcloud.Client(client_id=config.SOUNDCLOUD_CLIENT_KEY)

TAG_WEIGHT = config.tag_weight
BPM_WEIGHT = config.bpm_weight
LEN_WEIGHT = config.len_weight
GENRE_WEIGHT = config.genre_weight
SPREAD_WEIGHT = config.spread_weight
NO_BPM_DIFF = config.no_bpm_diff


def getIndexOfId(l, value):
    for pos, t in enumerate(l):
        if t.id == value:
            return pos

    # Matches behavior of list.index
    raise ValueError("list.index(x): x not in list")


def update_weights():
    """
    To prevent us from making a trillion OS calls during TSP solving.
    """
    global TAG_WEIGHT
    global BPM_WEIGHT
    global LEN_WEIGHT
    global GENRE_WEIGHT
    global SPREAD_WEIGHT
    global NO_BPM_DIFF

    TAG_WEIGHT = config.tag_weight
    BPM_WEIGHT = config.bpm_weight
    LEN_WEIGHT = config.len_weight
    GENRE_WEIGHT = config.genre_weight
    SPREAD_WEIGHT = config.spread_weight
    NO_BPM_DIFF = config.no_bpm_diff


class DeduplicatedTrack(object):
    def __init__(self, o):
        self.o = o

    def __eq__(self, other):
        return hash(self) == hash(other)

    def __hash__(self):
        return hash(self.o.title.lower())


def tag_diff(a, b):
    """
    Return the number of tags that are uncommon between the two tracks.
    """
    return TAG_WEIGHT * (len(a._tags | b._tags) - len(a._tags & b._tags))


def bpm_diff(a, b):
    if a.bpm < 200 and b.bpm < 200:
        try:
            return BPM_WEIGHT * abs(a.bpm - b.bpm)
        except TypeError:
            pass
    return BPM_WEIGHT * NO_BPM_DIFF


def len_diff(a, b):
    return abs(a.duration - b.duration) / 100.0


def spread_diff(a, b):
    return SPREAD_WEIGHT * int(a.user['username'] == b.user['username'])


def genre_diff(a, b):
    r = difflib.SequenceMatcher(a=a.genre.lower(), b=b.genre.lower()).ratio()
    return GENRE_WEIGHT * (1.0 - r)


def distance(a, b):
    return bpm_diff(a, b) + len_diff(a, b) + tag_diff(a, b) + genre_diff(a, b) + spread_diff(a, b)


def chunks(l, n):
    for i in xrange(0, len(l), n):
        yield l[i:i + n]


def tags_of(track):
    try:
        return shlex.split(track.tag_list)
    except ValueError:
        return []


def valid(track):
    return (track.streamable or track.downloadable) \
            and track.duration < 360000 \
            and track.duration > 90000


def cull(tracks):
    tracks = filter(valid, tracks)
    tracks = [t.o for t in set([DeduplicatedTrack(t) for t in tracks])]
    for track in tracks:
        track._tags = set(tags_of(track))
    return tracks


def generate():
    try:
        while test:
            tracks = client.get('/tracks', q='sobot', license='cc-by', limit=4)
            for track in tracks:
                if track.title != "Bright Night":
                    yield track.obj

        tracks = []
        last = []
        wait = 2  # seconds
        while True:
            update_weights()

            log.info("Grabbing fresh tracklist from SoundCloud...")
            with Timer() as t:
                while not tracks:
                    try:
                        tracks =  client.get('/tracks', order='hotness', limit=200, offset=0)
                        tracks += client.get('/tracks', order='hotness', limit=200, offset=200)
                    except HTTPError as h:
                        log.warning("Got %s from SoundCloud. Retrying in %2.2f seconds...",
                                    h, wait)
                        time.sleep(wait)

            log.info("Got %d tracks in %2.2fms.", len(tracks), t.ms)

            if last and not any([t.id == last[-1].id for t in tracks]):
                tracks.append(last[-1])
            tracks = cull(tracks)

            log.info("Solving TSP on %d tracks...", len(tracks))
            with Timer() as t:
                tracks = [tracks[i] for i in tsp.solve(tracks, distance, len(tracks) * config.tsp_mult)]
            log.info("Solved TSP in %2.2fms.", t.ms)

            if last:
                i = getIndexOfId(tracks, last[-1].id) + 1
                tracks = tracks[i:] + tracks[:i]

            for track in tracks:
                yield track.obj

            last = tracks
            tracks = []
    except:
        print traceback.format_exc()
        log.critical("%s", traceback.format_exc())


def pprint(track):
    print track['bpm'], track['title'], "by", track['user']['username']

if __name__ == "__main__":
    print "Testing the BRAIN..."
    if "weight" in sys.argv:
        tracks = cull(client.get('/tracks', order='hotness', limit=1000, offset=0))
        shuffle(tracks)
        print "Comparing against", tracks[0].title
        print "\t", tracks[0].tag_list
        print "\t", tracks[0].genre
        print "DIST\tBPM\tLEN\tTAG\tGEN\tSPR\tTITLE"
        for track, dist, bpm, l, tag, genre, spread in sorted([(
            track,
            distance(tracks[0], track),
            bpm_diff(tracks[0], track),
            len_diff(tracks[0], track),
            tag_diff(tracks[0], track),
            genre_diff(tracks[0], track),
            spread_diff(tracks[0], track),
        ) for track in tracks], key=itemgetter(1)):
            print round(dist, 1), "\t", round(bpm, 1), "\t", round(l, 1), "\t", round(tag, 1), "\t", round(genre, 1), "\t", round(spread, 1), "\t", track.title, "\t", track.genre
    else:
        for track in generate():
            pprint(track)
