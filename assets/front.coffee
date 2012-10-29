soundManager.setup
  url: '/static/flash/'

class Waveform
  constructor: (@div) ->
    @last = +new Date
    @left = 0
    @draw()

  draw: ->
    now = +new Date
    delta = (now - @last) / 1000
    @last = now
    
    @left -= 5 * delta

    if @div.children.length > 0
      first_width = parseInt @div.children[0].style.width
      if -1 * @left > first_width
        console.log first_width, @div.style.left
        @div.removeChild @div.children[0]
        @left += first_width
    
    @div.style.left = @left + "px"

    me = this
    window.requestAnimationFrame( -> me.draw() )
    

  process: (frame) ->
    @div.innerHTML += """
      <div class="segment"
           data-duration="#{frame.duration}"
           data-start="#{frame.start}"
           style="width: #{frame.width}px;
                  background-image: url(#{frame.waveform});"
      ></div>
    """
    @div.children[@div.children.length - 1].classList.add "move"

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
