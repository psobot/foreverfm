//  Forever.fm relay server
//  Simple, lightweight, untested.

var http = require('http');
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

var listen = function(callback) {
    req = http.request(options, function (res) {
        if ( res.statusCode != 200 ) {
            console.log("OH NOES: Got a " + res.statusCode + " back.");
        } else {
            callback();
            res.on('data', function (buf) {
                for (l in listeners) listeners[l].write(buf);
            });
        }
    })
    req.end();
}

var run = function() {
    http.createServer(function(request, response) {
        if (request.url == "/all.mp3") {
            response.writeHead(200, {'Content-Type': 'audio/mpeg'});
            response.on('close', function () {
                console.log("Removed listener: " + request.headers['x-real-ip']);
                listeners.splice(listeners.indexOf(response), 1);
            });
            listeners.push(response);
            console.log("Added listener: " + request.headers['x-real-ip']);
            console.log("Now at " + listeners.length + " listeners.");
        } else {
            response.write(JSON.stringify({
                listeners: {
                    count: listeners.length
                }
            }));
            response.end();
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
