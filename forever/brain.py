import sys
import config
import logging
import soundcloud
from random import shuffle

log = logging.getLogger(__name__)
test = 'test' in sys.argv


def good_track(track):
    return track.streamable and track.duration < 360000 and track.duration > 90000


client = soundcloud.Client(client_id=config.SOUNDCLOUD_CLIENT_KEY)


def add_tracks():
    try:
        while test:
            tracks = client.get('/tracks', q='sobot', license='cc-by', limit=4)
            for track in tracks:
                if track.title != "Bright Night":
                    yield track.obj

        l = 1000

        offsets = range(0, 4) * l
        shuffle(offsets)
        for i in offsets:
            tracks = client.get('/tracks', order='hotness', limit=l, offset=i)
            tracks = filter(good_track, tracks)
            shuffle(tracks)

            for track in tracks:
                log.info("Adding new track.")
                yield track.obj
    finally:
        pass
