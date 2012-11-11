window.log = ->
  log.history = log.history or []
  log.history.push arguments
  console.log Array::slice.call(arguments)  if @console

$(document).ready ->
  s = io.connect ":8193/monitor.websocket"
  s.on 'message', (data) ->
    listeners = []
    for listener in data.listeners
      for k, v of listener
        listeners.push "<span><strong>#{k}</strong>: #{v}</span>"

    $('body').html """
    <div>Current Listeners: #{data.listeners.length}</div>
    <div class='listeners'>#{listeners.join('')}</div>
    <div>#{"<span><strong>#{k}</strong>: #{v}</span>" for k, v of data.queues}</div>
    """
  window._s = s
