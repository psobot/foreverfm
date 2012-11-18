import hashlib
import config
import MySQLdb


class cursor():
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        self.conn = MySQLdb.connect(config.db_host, config.db_user, config.db_pass, self.db, use_unicode=True)
        self.cur = self.conn.cursor()
        return self.cur

    def __exit__(self, type, value, tb):
        self.cur.close()
        if tb is None:
            self.conn.commit()
        else:
            self.conn.rollback()
        self.conn.close()
        self.conn = None


def merge(sc, echonest_analysis):
    e = echonest_analysis.pyechonest_track
    t = Track(
        sc.id,
        sc.title,
        e.audio_md5,
        sc.duration,
        e.key,
        e.mode,
        e.time_signature,
        e.danceability,
        e.energy,
        e.loudness,
        e.tempo,
        hashlib.sha1(e.echoprintstring).hexdigest(),
    )
    for k, v in t.__dict__.iteritems():
        if k != 'title':  # Remove title, as it contains a lot of unicode that we want to ignore.
            sc.obj[k] = v
    return sc


class Track(object):
    def __init__(self,
                 id,
                 title,
                 md5,
                 duration,
                 key,
                 mode,
                 time_signature,
                 danceability,
                 energy,
                 loudness,
                 tempo,
                 fingerprint,
                 **kwargs):
        self.id, self.title, self.md5, self.duration, \
        self.key, self.mode, self.time_signature, \
        self.danceability, self.energy, self.loudness, \
        self.tempo, self.fingerprint = id, title, md5, duration, key, mode, \
        time_signature, danceability, energy, loudness, tempo, fingerprint


class Database(object):
    def __init__(self, db="foreverfm"):
        self.db = db

    def __find(self, sc):
        with cursor(self.db) as c:
            c.execute("SELECT * FROM tracks WHERE id = %s", [sc.id])
            row = c.fetchone()
            if row:
                return Track(*row)
            else:
                return None

    def has(self, sc):
        return self.__find(sc) is not None

    def merge(self, sc):
        track = self.__find(sc)
        if track:
            for k, v in track.__dict__.iteritems():
                sc.obj[k] = v
        return sc

    def insert(self, t):
        with cursor(self.db) as c:
            c.execute(
                "INSERT INTO tracks VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (t.id, t.title, t.md5, t.duration, t.key, t.mode,
                 t.time_signature, t.danceability, t.energy, t.loudness,
                 t.tempo, t.fingerprint)
            )

    def ensure(self, t):
        with cursor(self.db) as c:
            c.execute(
                "REPLACE INTO tracks VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (t.id, t.title, t.md5, t.duration, t.key, t.mode,
                 t.time_signature, t.danceability, t.energy, t.loudness,
                 t.tempo, t.fingerprint)
            )

    def is_duplicate(self, t):
        with cursor(self.db) as c:
            c.execute("""
                SELECT COUNT(*)
                FROM tracks t1
                LEFT JOIN tracks t2 ON (t1.fingerprint = t2.fingerprint
                                        OR t2.md5 = t2.md5) AND t1.id != t2.id
                WHERE t1.id = %s
            """, [t.id])
            r = c.fetchone()
            if r is None:
                return None
            else:
                return r[0] > 0
