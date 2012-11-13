CREATE TABLE `tracks` (
  `id` int(11) unsigned NOT NULL,
  `title` varchar(256) NOT NULL DEFAULT '',
  `md5` char(32) DEFAULT '',
  `duration` float NOT NULL,
  `key` tinyint(4) DEFAULT NULL,
  `mode` tinyint(4) DEFAULT NULL,
  `time_signature` tinyint(4) DEFAULT NULL,
  `danceability` float DEFAULT NULL,
  `energy` float DEFAULT NULL,
  `loudness` float DEFAULT NULL,
  `tempo` float DEFAULT NULL,
  `fingerprint` char(40) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `md5` (`md5`),
  KEY `fingerprint` (`fingerprint`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;
