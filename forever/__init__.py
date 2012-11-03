import logging
try:
    from customlog import CustomLog
    logging.setLoggerClass(CustomLog)
except OSError:
    print "Could not instantiate logger class!"
