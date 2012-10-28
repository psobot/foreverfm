soundManager.setup
  url: '/static/flash/'

class Waveform
  constructor: (@div) ->


  process: (frame) ->
    console.log frame
    $(@div).append """
      <div class="segment" style="width: #{frame.width}px; background-image: url(#{frame.waveform});" />
    """

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
