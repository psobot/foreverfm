import Image
import urllib2
import logging
import cStringIO
from timer import Timer


log = logging.getLogger(__name__)
DEFAULT_SPEED = 5  # pixels per second


def generate(s, e, c, u, od, nd, speed=DEFAULT_SPEED):
    buf = cStringIO.StringIO()
    if isinstance(s, list):
        with Timer() as t:
            assert(len(s) == len(e))
            assert(len(s) == len(c))
            assert(len(s) == len(u))
            a = generate_single(s[0], e[0], c[0], u[0], od[0], nd, speed)
            b = generate_single(s[1], e[1], c[1], u[1], od[1], nd, speed)

            assert(a.size == b.size)

            #   Make a linear gradient mask between the two images.
            lr = Image.new('RGBA', a.size)
            lr.putdata([(0, 0, 0, int(255.0 * (1.0 - (float(x) / a.size[0]))))
                        for y in xrange(a.size[1])
                            for x in xrange(a.size[0])])
            b.paste(a, mask=lr.split()[3])
            b.save(buf, format='png')
        log.info("Generated composite waveform in %2.2fms.", t.ms)
        return buf.getvalue()
    else:
        with Timer() as t:
            generate_single(s, e, c, u, od, nd, speed).save(buf, "png")
        log.info("Generated waveform in %2.2fms.", t.ms)
        return buf.getvalue()


def generate_single(start, end, rgb1, url, o_duration, n_duration, speed):
    fp = cStringIO.StringIO(urllib2.urlopen(url).read())
    mask = Image.open(fp).convert("RGBA")

    #   Resize mask to fit...
    cur_speed = (1000.0 * mask.size[0]) / o_duration
    ltrb = (int(start * cur_speed), 0, int(end * cur_speed), mask.size[1])
    mask = mask.crop(ltrb)

    lim = 64
    if all([c < lim for c in rgb1]):
        rgb1 = [int(min(x + lim, 255)) for x in rgb1]
    rgb2 = [max(x - lim, 0) for x in rgb1]

    color = lambda i: \
        tuple([(rgb1[c] +
                int((i * 2.0 / mask.size[1]) *
                    (rgb2[c] - rgb1[c]))
               ) for c in range(3)])

    gradient = Image.new('RGBA', (1, mask.size[1]))
    gradient.putdata([color(i) for i in xrange(mask.size[1])])
    gradient = gradient.resize(mask.size)
    gradient.paste((255, 255, 255, 0), mask=mask.split()[3])

    #   Resize to the required width
    newsize = (int(n_duration * speed), mask.size[1])
    return gradient.resize(newsize)
