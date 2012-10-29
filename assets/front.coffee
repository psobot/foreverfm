soundManager.setup
  url: '/static/flash/'

class Waveform
  speed: 5
  constructor: (@canvas) ->
    @last = +new Date
    @rem = 0
    @left = $("#menu").outerWidth()
    @images = []
    @context = @canvas.getContext "2d"
    @canvas.width = window.innerWidth
    @draw()

  draw: ->
    now = +new Date
    delta = (now - @last) / 1000
    @last = now
    unless window.soundManager.sounds.ui360Sound0? && window.soundManager.sounds.ui360Sound0.paused
      px = (@speed * delta) + @rem
      @rem = px - parseInt(px)
      @left += -1 * parseInt(px)

      removals = []
      for i in [0...@images.length]
        if @left + @images[i].width < 0
          removals.push i
      
      for i in [0...removals]
        @left += @images[removals[i] - i].width
        @images.splice(i, 1)

      @context.clearRect 0, 0, @canvas.width, @canvas.height

      right = @left
      for image in @images
        @context.drawImage image, Math.round(right), 0
        right += image.width

    me = this
    setTimeout((-> me.draw()), 100)
    
  process: (frame) ->
    img = new Image
    me = this
    img.onload = ->
      me.left -= parseInt((+new Date)/1000 - frame.time)
      me.images.push img
    img.src = frame.waveform
      

$(document).ready ->
  w = new Waveform document.getElementById "waveform"

  $.getJSON "all.json", (segments) ->
    for segment in segments
      w.process segment

  s = io.connect "/info.websocket"
  s.on 'message', (segment) ->
    w.process segment

  window._waveform = w
  window._socket = s
