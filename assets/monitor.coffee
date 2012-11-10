window.log = ->
  log.history = log.history or []
  log.history.push arguments
  console.log Array::slice.call(arguments)  if @console

$(document).ready ->
  s = io.connect ":8193/monitor.websocket"
  s.on 'message', (data) ->
    window._d = data
    listeners = []
    for listener in data.listeners
      listeners.push("<span><strong>#{k}</strong>: #{v}</span>" for k, v of listener)
    window.log listeners
    html = """
    <div>Current Listeners: #{data.listeners.length}</div>
    <div class='listeners'>#{listeners.join('')}</div>
    <div>#{"<span><strong>#{k}</strong>: #{v}</span>" for k, v of data.queues}</div>
    """
    window.log html
    $('body').html html
