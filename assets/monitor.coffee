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
    @_name =  $("##{@id} .name")
    @update(@initdata) if @initdata?

  update: (raw) ->
    @data = raw
    @redraw()

  redraw: ->
    @bar.width(((parseInt(@data) / 9187) * 200) + "px")
    @bar.html(@data)
    @_name.toggleClass('active')

listeners = []

update = (id, data) ->
  el = $(document.getElementById(id))
  console.log "Updating #{id}: #{el}"
  $('.url', el).html(data.config.relay_url)
  $('.location', el).html(data.config.relay_location)
  $('.started', el).html(data.started_at)
  $('.started', el).attr('title', (new Date(data.started_at)).toISOString())
  $('.started', el).timeago()
  $('.listeners', el).html(data.listeners)
  $('.bytes_out_month', el).html(getBytesWithUnit data.bytes_out_month)
  $('.bytes_in_month', el).html(getBytesWithUnit data.bytes_in_month)
  $('.peak_bytes_out_month', el).html(getBytesWithUnit data.peaks.bytes_out_month)
  $('.peak_listeners', el).html(data.peaks.listeners)

fetch = (url, id) ->
  $.getJSON url, (data) ->
    update(id, data)
    setTimeout (-> fetch(url, id)), (10 * 1000)

getBytesWithUnit = (bytes) ->
  return  if isNaN(bytes)
  units = [ " bytes", " KB", " MB", " GB", " TB", " PB", " EB", " ZB", " YB" ]
  amountOf2s = Math.floor(Math.log(+bytes) / Math.log(2))
  amountOf2s = 0  if amountOf2s < 1
  i = Math.floor(amountOf2s / 10)
  bytes = +bytes / Math.pow(2, 10 * i)
  bytes = bytes.toFixed(3)  if bytes.toString().length > bytes.toFixed(3).toString().length
  bytes + units[i]

$(document).ready ->
  s = io.connect ":8193/monitor.websocket"
  s.on 'message', (data) ->
    for l in data.listeners
      id = l['X-Forwarded-For'].replace(/\./g, '')
      json = "http://forever.fm:8001/?url=" + l['X-Relay-Addr'] + "&callback=?"
      if document.getElementById(id) == null
        $('.relays').append """
          <div class="relay" id="#{id}">
            <h1 class="url"></h1>  
            <h2 class="location"></h2>
            <div>Started: <span class="started"></span></div>
            <div><span class="listeners"></span> listeners</div>
            <div><span class="bytes_out_month"></span> sent this month</div>
            <div><span class="bytes_in_month"></span> rec'd this month</div>
            <div><br /></div>
            <div><span class="peak_listeners"></span> listeners (at peak)</div>
            <div><span class="peak_bytes_out_month"></span> sent (at peak month)</div>
            <div style="clear: both"></div>
          </div>
        """
        fetch(json, id)

    for k, v of data.queues
      if not (k of Queue.all)
        new Queue k, v
      else
        Queue.all[k].update v
  window._s = s
