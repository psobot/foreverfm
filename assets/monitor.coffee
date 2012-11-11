window.log = ->
  log.history = log.history or []
  log.history.push arguments
  console.log Array::slice.call(arguments)  if @console

class Queue
  @all: {}

  constructor: (@name, @initdata) ->
    Queue.all[@name] = this
    @nowmax = 0
    @allmax = 0
    @t = +new Date
    t = @t
    @data = d3.range(31).map -> { time: t, value: 0 }

    $('.queues').append """
        <div id="chart"></div>
      """
    @initdraw()
    @update(@initdata)

  initdraw: ->
    w = 20
    h = 160
    @w = w
    @h = h
    @x = d3.scale.linear().domain([ 0, 1 ]).range([ 0, @w ])
    x = @x
    @y = d3.scale.linear().domain([ 0, @curmax ]).rangeRound([ 0, @h ])
    y = @y
    @chart = d3.select("div#chart")\
              .append("svg")\
              .attr("class", "chart")\
              .attr("width", @w * @data.length - 1)\
              .attr("height", @h)
    @chart.selectAll("rect")\
         .data(@data).enter()\
         .append("rect").attr("x", (d, i) -> (x(i) - .5))\
         .attr("y", (d) -> (h - y(d.value) - .5))\
         .attr("width", w).attr "height", (d) -> (y d.value)

    @chart.append("line")\
         .attr("x1", 0)\
         .attr("x2", @w * @data.length)\
         .attr("y1", @h - .5)\
         .attr("y2", @h - .5).style "stroke", "#000"

  update: (raw) ->
    @data.shift()
    @data.push(@next(raw))
    @max(raw)
    @redraw()

  next: (value) ->
    result = { time: ++@t, value: value }
    d3.select('div.count p span.current').html(value)
    result

  max: (value) ->
    @curmax = 0
    x = 0
    while x < @data.length
      @nowmax = (if @data[x].value > @nowmax then @data[x].value else @nowmax)
      x = x + 1
    @allmax = (if @nowmax > @allmax then @nowmax else @allmax)
    @y = d3.scale.linear().domain([ 0, @nowmax ]).rangeRound([ 0, @h ])
    d3.select("div.count p span.max").html @allmax

  redraw: ->
    w = @w
    h = @h
    x = @x
    y = @y
    rect = @chart.selectAll("rect").data(@data, (d) -> d.time)
    rect.enter().insert("rect", "line") \
        .attr("x", (d, i) -> (x(i + 1) - .5) ) \
        .attr("y", (d) -> (h - y(d.value) - .5)) \
        .attr("width", w) \
        .attr("height", (d) -> y(d.value)) \
        .transition() \
        .duration(1000) \
        .attr("x", (d, i) -> (x(i) - .5))

    rect.transition() \
        .duration(1000) \
        .attr("x", (d, i) -> (x(i) - .5))

    rect.exit().transition() \
        .duration(1000) \
        .attr("x", (d, i) -> (x(i - 1) - .5)) \
        .remove()


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
