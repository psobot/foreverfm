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

winston.add(winston.transports.File, { filename: 'relay.log', handleExceptions: true });

var listen = function(callback) {
    req = http.request(options, function (res) {
        if ( res.statusCode != 200 ) {
            winston.error("OH NOES: Got a " + res.statusCode + " back.");
        } else {
            res.on('data', function (buf) {
                for (l in listeners) listeners[l].write(buf);
            });
            callback();
        }
    })
    req.end();
}

var run = function() {
    http.createServer(function(request, response) {
        try {
            if (request.url == "/all.mp3") {
                response.writeHead(200, {'Content-Type': 'audio/mpeg'});
                response.on('close', function () {
                    winston.log("Removed listener: " + request.headers['x-real-ip']);
                    listeners.splice(listeners.indexOf(response), 1);
                });
                listeners.push(response);
                winston.log("Added listener: " + request.headers['x-real-ip']);
                winston.log("Now at " + listeners.length + " listeners.");
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
        listen(function() {
            daemon.start();
        });
        break;
    case "stop":
        daemon.stop();
        break;
    default:
        listen(function() { run(); });
}
