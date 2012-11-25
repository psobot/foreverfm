import time
import base64
import logging
import scwaveform
from metadata import Metadata

log = logging.getLogger(__name__)


def generate(iq, first_frame):
    log.info("Info generator waiting on first frame...")
    first_frame.acquire()
    stime = time.time()
    log.info("Info generator got first frame! Start time: %2.2f", stime)
    samples = 0L
    while True:
        action = iq.get()
        if 'failed' in action:
            log.error("Sending retraction of data for id %s.", action['id'])
            samples -= action['samples'] - action['effective_length']
            yield action
            continue

        action['time'] = stime + (samples / 44100.0)
        samples += action['samples']

        if len(action['tracks']) == 2:
            m1 = Metadata(action['tracks'][0]['metadata'])
            s1 = action['tracks'][0]['start']
            e1 = action['tracks'][0]['end']

            m2 = Metadata(action['tracks'][1]['metadata'])
            s2 = action['tracks'][1]['start']
            e2 = action['tracks'][1]['end']

            log.info("Processing metadata for %d -> %d, (%2.2fs %2.2fs) -> (%2.2fs, %2.2fs).",
                        m1.id, m2.id, s1, s2, e1, e2, uid=m1.id)

            a = scwaveform.generate([s1, s2], [e1, e2],
                                    [m1.color, m2.color],
                                    [m1.waveform_url, m2.waveform_url],
                                    [m1.duration, m2.duration],
                                    action['duration'])
        else:
            for track in action['tracks']:
                metadata = Metadata(track['metadata'])
                start = track['start']
                end = track['end']

                log.info("Processing metadata, %2.2fs -> %2.2fs.",
                            start, end, uid=metadata.id)
                a = scwaveform.generate(start, end, metadata.color,
                                        metadata.waveform_url,
                                        metadata.duration,
                                        action['duration'])
        action['waveform'] = "data:image/png;base64,%s" % \
                            base64.encodestring(a)
        action['width'] = int(action['duration'] * scwaveform.DEFAULT_SPEED)
        yield action
