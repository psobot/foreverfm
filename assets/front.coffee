soundManager.setup
  url: '/static/flash/'

class Waveform
  constructor: (@canvas) ->
    @last = +new Date
    @sub = 0
    @images = []
    @context = @canvas.getContext "2d"
    @canvas.width = window.innerWidth
    @draw()

  draw: ->
    now = +new Date
    delta = (now - @last) / 1000
    @last = now
    
    px = @sub + 5 * delta
    left = -1 * parseInt px
    @sub += px + left

    for i in [0...@images.length]
      if left + @images[i].width < 0
        @images.splice(i, 1) 
        i -= 1

    @context.clearRect 0, 0, @canvas.width, @canvas.height

    right = -@sub
    for image in @images
      @context.drawImage image, Math.round(right), 0
      right += image.width

    me = this
    setTimeout((-> me.draw()), 500)
    
  process: (frame) ->
    img = new Image
    me = this
    img.onload = ->
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
