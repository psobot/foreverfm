soundManager.setup
  url: '/static/flash/'

NUM_TRACKS = 5
MP3_BUFFER = 3  # number of seconds buffered

class Frame
  constructor: (init, is_new) ->
    for k, v of init
      this[k] = v
    @image = null
    @div = null
    @id = "track_#{@tracks[0].metadata.id}"
    @new = if is_new then 'new' else ''

    # hack for development... don't wanna do this
    while document.getElementById(@id)
      @id += "_"

    @parseMetaData()

  parseMetaData: ->
    matches = @tracks[0].metadata.title.match(/(.*?)\s*-\s*(.*)/i)
    if matches?
      [_, @artist, @title] = matches
    else
      matches = @tracks[0].metadata.title.match(/(.*?) by (.*)/i)
      if matches?
        [_, @title, @artist] = matches
      else
        @title = @tracks[0].metadata.title
        @artist = @tracks[0].metadata.user.username
    
    matches = @title.match(/([^\[\]]*?)( - ([^\[\]\(\)]*)|(\[.*\]))/i)
    if matches?
      [_, @title, _, other] = matches
    
    #   Remove "Free Download," "Follow Me" and the like
    @title = @title.replace /(\s*-*\s*((\[|\()[^\)\]]*(free|download|comment|out now|clip|bonus|preview|teaser|in store|follow)+[^\)\]]*(\]|\))|((OUT NOW( ON \w*)?|free|download|preview|teaser|in store|follow).*$))\s*|\[(.*?)\])/i, ""

    if @title[0] == '"' and @title[@title.length - 1] == '"'
      @title = @title[1...@title.length - 1].trim()

    @img = if @tracks[0].metadata.artwork_url?
             @tracks[0].metadata.artwork_url
           else
             @tracks[0].metadata.user.avatar_url
    @playcount   = @tracks[0].metadata.playback_count
    @downloads   = @tracks[0].metadata.download_count
    @favoritings = @tracks[0].metadata.favoritings_count
    @stats = @playcount? and @downloads? and @favoritings
    @url = @tracks[0].metadata.permalink_url

  html: ->
    """
    <a class='track #{@new}' id='#{@id}' target="_blank" href="#{@url}">
      <div class="coverart"><img src="#{@img}" /></div>
      <div class="text">
        <span class="title">#{@title}</span>
        <span class="artist">#{@artist}</span>
      </div>
      #{if @stats then "
      <div class='stats'>
        <span class='count playback'>#{@playcount}</span>
        <span class='count download'>#{@downloads}</span>
        <span class='count favoritings'>#{@favoritings}</span>
      </div>
      " else ""}
    </div>
    """

  played: ->
    (@time + @duration + MP3_BUFFER) < (+new Date / 1000)

  intendedParent: ->
    document.getElementById( if @played() then "done" else "tracks" )

  render: ->
    return if @action != "Playback"
    return @relayout() if @div?

    console.log "Rendering", @tracks[0].metadata.title, "played?", @played()
    parent = @intendedParent()
    #if $(parent).data('limit') <= parent.children.length
    $(parent).prepend @html()
    id = @id
    setTimeout((-> $("##{id}").removeClass 'new'), 100)
    @div = document.getElementById @id

  relayout: ->
    console.log "Doing relayout of ", @tracks[0].metadata.title, "played?", @played()
    @div = document.getElementById(@id) if not @div.parentNode?
    newparent = document.getElementById( if @played() then "done" else "tracks" )
    if @div.parentNode != newparent
      # TODO: element.addEventListener('webkitAnimationEnd', function(){
      # this.style.webkitAnimationName = '';
      # }, false);
      console.log "Adding #{@tracks[0].metadata.title} to #{newparent.id}"
      @div.parentNode.removeChild @div
      newparent.innerHTML = @html() + newparent.innerHTML

class Waveform
  speed: 5
  constructor: (@canvas) ->
    @delay = 0
    @offset = $("#menu").outerWidth() + (MP3_BUFFER * @speed)  # Arbitrary - due to MP3 buffering
    @frames = []
    @context = @canvas.getContext "2d"
    @canvas.width = window.innerWidth
    @drawloop()

  drawloop: ->
    @draw()
    me = this
    return if @stop?
    setTimeout((-> me.drawloop()), 100)

  draw: ->
    if window.soundManager.sounds.ui360Sound0? && window.soundManager.sounds.ui360Sound0.paused
      @paused_at = +new Date unless @paused_at?
      return
    else if @paused_at?
      @delay += (+new Date - @paused_at)
      delete @paused_at

    if @frames[0]?
      @context.clearRect 0, 0, @canvas.width, @canvas.height
      nowtime = (+new Date - @delay) / 1000
      
      if @frames.length > 1
        for i in [1...@frames.length]
          if @frames[i].time + MP3_BUFFER > nowtime
            frame = @frames[i-1]
            if not @__current_frame? || @__current_frame != frame
              @onCurrentFrameChange @__current_frame, frame
              @__current_frame = frame
            break
      else
        frame = @frames[0]
        if not @__current_frame? || @__current_frame != frame
          @onCurrentFrameChange @__current_frame, frame
          @__current_frame = frame


      left = (nowtime - @frames[0].time) * @speed * -1
      while @offset + left + @frames[0].image.width < 0
        @frames.splice(0, 1)
        return if not @frames[0]?
        left = (nowtime - @frames[0].time) * @speed * -1
      right = @offset + left
      for frame in @frames
        @context.drawImage frame.image, right, 0
        right += frame.image.width

  onNewFrame: (frame) ->
    @frames.push frame
    frame.render()
    
  onCurrentFrameChange: (old, knew) ->
    console.log "Current frame is now:", knew.action, knew.tracks[0].metadata.title
    knew.render()
    old.render() if old?
    
  process: (f, from_socket) ->
    frame = new Frame f, from_socket
    img = new Image
    me = this
    img.onload = ->
      frame.image = this
      me.onNewFrame frame
    img.src = frame.waveform
      

$(document).ready ->
  w = new Waveform document.getElementById "waveform"

  $.getJSON "all.json", (segments) ->
    for segment in segments
      w.process segment

  s = io.connect "/info.websocket"
  s.on 'message', (segment) ->
    w.process segment, true

  window._waveform = w
  window._socket = s
