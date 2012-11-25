//  Forever.fm relay server
//  Simple, lightweight, untested.

var http = require('http');
var winston = require('winston');
var daemon = require("daemonize2").setup({
    main: "relay.js",
    name: "relay",
    pidfile: "relay.pid"
});

var options = {
    hostname: "forever.fm",
    path: "/all.mp3",
    headers: {"Connection": "keep-alive"}
};
var port = 8192;
var listeners = [];
var timeout = 1000; // ms

winston.level = 'log';
winston.add(winston.transports.File, { filename: 'relay.log', handleExceptions: true });

var check = function(callback) {
    winston.info("Attempting to connect to generator...");
    check_opts = {'method': 'HEAD'};
    for (var a in options) check_opts[a] = options[a];
    req = http.request(check_opts, function (res) {
        if ( res.statusCode != 200 ) {
            winston.error("OH NOES: Got a " + res.statusCode);
        } else {
            winston.info("Got 200 back from generator!")
            if (typeof callback != "undefined") callback();
        }
    })
    req.end();
}

var listen = function(callback) {
    winston.info("Attempting to listen to generator...");
    req = http.request(options, function (res) {
        if ( res.statusCode != 200 ) {
            winston.error("OH NOES: Got a " + res.statusCode);
            setTimeout(function(){listen(callback)}, timeout);
        } else {
            winston.info("Listening to generator!")
            res.on('data', function (buf) {
                try {
                    for (l in listeners) listeners[l].write(buf);
                } catch (err) {
                    winston.log("Could not send to listeners: " + err);
                }
            });
            res.on('end', function () {
                winston.error("Stream ended! Restarting listener...");
                setTimeout(function(){listen(function(){})}, timeout);
            });
            if (typeof callback != "undefined") callback();
        }
    })
    req.end();
}

var ipof = function(req) {
    var ipAddress;
    var forwardedIpsStr = req.headers['x-forwarded-for']; 
    if (forwardedIpsStr) {
        var forwardedIps = forwardedIpsStr.split(',');
        ipAddress = forwardedIps[0];
    }
    if (!ipAddress) {
        ipAddress = req.connection.remoteAddress;
    }
    return ipAddress;
};

var run = function() {
    winston.info("Starting server.")
    http.createServer(function(request, response) {
        request.ip = ipof(request);
        try {
            if (request.url == "/all.mp3") {
                response.writeHead(200, {'Content-Type': 'audio/mpeg'});
                response.on('close', function () {
                    winston.info("Removed listener: " + request.ip);
                    listeners.splice(listeners.indexOf(response), 1);
                });
                listeners.push(response);
                winston.info("Added listener: " + request.ip);
                winston.info("Now at " + listeners.length + " listeners.");
            } else {
                response.write(JSON.stringify({
                    listeners: {
                        count: listeners.length
                    }
                }));
                response.end();
            }
        } catch (err) {
            winston.error(err);
        }
    }).listen(port);
}

switch (process.argv[2]) {
    case "start":
        check(function() {
            daemon.start();
        });
        break;
    case "stop":
        daemon.stop();
        break;
    default:
        check(function() {
          listen();
          run();
        });
}
