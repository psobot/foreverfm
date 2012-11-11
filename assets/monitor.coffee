window.log = ->
  log.history = log.history or []
  log.history.push arguments
  console.log Array::slice.call(arguments)  if @console

class Queue
  @all: {}

  constructor: (@name, @initdata) ->
    Queue.all[@name] = this

    $('.queues').append """
        <div class="chart" id="chart_#{@name}">
          <div class="name">
            #{@name}
          </div>
          <div class="bar">
            
          </div>
        </div>
      """
    @id = "chart_#{@name}"
    @bar =  $("##{@id} .bar")
    @update(@initdata) if @initdata?

  update: (raw) ->
    @data = raw
    @redraw()

  redraw: ->
    @bar.width(((parseInt(@data) / 9187) * 200) + "px")
    @bar.html(@data)

$(document).ready ->
  s = io.connect ":8193/monitor.websocket"
  s.on 'message', (data) ->
    listeners = []
    for listener in data.listeners
      for k, v of listener
        listeners.push "<span><strong>#{k}</strong>: #{v}</span>"

    $('.listeners').html """
      <div>Current Listeners: #{data.listeners.length}</div>
      #{listeners.join('')}
    """
    for k, v of data.queues
      if not (k of Queue.all)
        new Queue k, v
      else
        Queue.all[k].update v
  window._s = s
