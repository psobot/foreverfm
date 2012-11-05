window.log = ->
  log.history = log.history or []
  log.history.push arguments
  console.log Array::slice.call(arguments)  if @console


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
    @title = @title.replace /(\s*-*\s*((\[|\()[^\)\]]*(mp3|dl|description|free|download|comment|out now|clip|bonus|preview|teaser|in store|follow|radio|prod)+[^\)\]]*(\]|\))|((OUT NOW( ON \w*)?|free|download|preview|teaser|in store|follow|mp3|dl|description).*$))\s*|\[(.*?)\])/i, ""

    if @title[0] == '"' and @title[@title.length - 1] == '"'
      @title = @title[1...@title.length - 1].trim()

    @img = if @tracks[0].metadata.artwork_url?
             @tracks[0].metadata.artwork_url
           else
             @tracks[0].metadata.user.avatar_url

    # Stats display
    @playcount   = @comma @tracks[0].metadata.playback_count
    @downloads   = @comma @tracks[0].metadata.download_count
    @favoritings = @comma @tracks[0].metadata.favoritings_count
    @stats = @playcount? and @downloads? and @favoritings

    # Buttons
    @buttons = true
    @nid = @tracks[0].metadata.id
    @download = @tracks[0].metadata.download_url

    @url = @tracks[0].metadata.permalink_url

  comma: (x) ->
    if x? then x.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',') else x

  twitter: ->
    text = "Check out this track: #{@url} #{if @playing() then "playing now" else "I found"} on"
    "http://twitter.com/share?text=#{encodeURIComponent(text)}"

  html: ->
    _new = @new
    @new = ''
    """
    <div class='track #{_new} #{if @played() then "hidden" else ""}' id='#{@id}' target="_blank" href="#{@url}">
      <a class="coverart" href="#{@url}" target="_blank"><img src="#{@img}" /></a>
      <div class="text">
        <a class="title" href="#{@url}" target="_blank">#{@title}</a>
        <span class="artist">#{@artist}</span>
      </div>
      <div class='buttons'>
        #{if @id then "<a href='#' data-track='#{@nid}' class='like'>&nbsp;</a>
                       <a href='#{@twitter()}' target='_blank' class='share'>&nbsp;</a>
                      " else ""}
        #{if @download then "<a href='#{@download}' class='download'>&nbsp;</a>" else ""}
        #{if @url then "<a href='#{@url}' target='_blank' class='sc'>&nbsp;</a>" else ""}
      </div>
      #{if @stats then "
      <div class='stats'>
        #{if @playcount? and @playcount != '0' then "<span class='count playback'>#{@playcount}</span>" else ""}
        #{if @downloads? and @downloads != '0' then "<span class='count download'>#{@downloads}</span>" else ""}
        #{if @favoritings? and @favoritings != '0' then "<span class='count favoritings'>#{@favoritings}</span>" else ""}
      </div>
      " else ""}
    </div>
    """

  played: ->
    (@time + @duration + MP3_BUFFER) < (+new Date / 1000)

  playing: ->
    ((@time + MP3_BUFFER) < (+new Date / 1000)) and not @played()

  intendedParent: ->
    document.getElementById( if @played() then "done" else "tracks" )

  render: ->
    return if @action != "Playback"
    return @relayout() if @div?

    parent = @intendedParent()
    $(parent).prepend @html()
    id = @id
    setTimeout((-> $("##{id}").removeClass 'new'), 100)
    @div = document.getElementById @id

  relayout: ->
    @div = document.getElementById(@id) if not @div.parentNode?
    newparent = document.getElementById( if @played() then "done" else "tracks" )
    if @div.parentNode != newparent
      neighbour = @div.parentNode.children[@div.parentNode.children.length - 2]
      $(@div).addClass("ending")
      $(neighbour).addClass("next")

      div = @div
      html = @html()
      setTimeout ->
        $(neighbour).removeClass("next")
        div.parentNode.removeChild div
        newparent.innerHTML = html + newparent.innerHTML
        setTimeout((-> $(".hidden", newparent).removeClass("hidden")), 100)
      , 1000

class Waveform
  speed: 5
  constructor: (@canvas) ->
    @delay = 0
    @offset = $("#menu").outerWidth() + (MP3_BUFFER * @speed)  # Arbitrary - due to MP3 buffering
    @frames = []
    @context = @canvas.getContext "2d"
    @layout()
    @drawloop()

  layout: ->
    @canvas.width = window.innerWidth

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

      # Actually draw our waveform here
      for frame in @frames
        @context.drawImage frame.image, right, 0
        right += frame.image.width
      @setPlayerColor()

  __dec2hex: (i) ->
   (i+0x100).toString(16).substr(-2)

  LIGHTENING: 32
  setPlayerColor: ->
    pix = @context.getImageData(@offset, parseInt(@canvas.height / 2), 1, @canvas.height).data
    [r, g, b] = [Math.min(pix[0] + @LIGHTENING, 255),
                 Math.min(pix[1] + @LIGHTENING, 255),
                 Math.min(pix[2] + @LIGHTENING, 255)]
    window.threeSixtyPlayer.config.playRingColor = "##{@__dec2hex(r)}#{@__dec2hex(g)}#{@__dec2hex(b)}"
    window.threeSixtyPlayer.config.backgroundRingColor = window.threeSixtyPlayer.config.playRingColor

  onNewFrame: (frame) ->
    @frames.push frame
    frame.render()
    
  onCurrentFrameChange: (old, knew) ->
    if knew.action == "Crossmatch" or knew.action == "Crossfade"
      setTimeout ->
        knew.render()
        old.render() if old?
      , (knew.duration * 500)
    
  process: (f, from_socket) ->
    frame = new Frame f, from_socket
    img = new Image
    me = this
    img.onload = ->
      frame.image = this
      me.onNewFrame frame
    img.src = frame.waveform

SC.initialize
  client_id: "b08793cf5964f5571db86e3ca9e5378f"
  redirect_uri: "http://beta.forever.fm/static/sc.html"

connectedly = (callback) ->
  if SC.isConnected()
    callback()
  else
    token = localStorage.getItem "accessToken"
    if token?
      SC.accessToken token
      callback()
    else
      SC.connect (a) ->
        localStorage.setItem('accessToken', SC.accessToken()) if localStorage?
        callback(a)

$(document).ready ->
  w = new Waveform document.getElementById "waveform"
  $(window).resize ->
    w.layout()
    w.draw()

  $.getJSON "all.json", (segments) ->
    for segment in segments
      w.process segment

  s = io.connect ":8193/info.websocket"
  s.on 'message', (segment) ->
    w.process segment, true

  $(document).on "click", 'a.like', (e) ->
    e.preventDefault()
    return if $(this).hasClass 'selected'
    me = this
    connectedly ->
      SC.put "/me/favorites/#{$(me).data('track')}", (a) ->
        $(me).addClass('selected') if a.status?

  $(document).on "click", 'a.share', (e) ->
    e.preventDefault()
    [w, h] = [500, 250]
    [l, t] = [screen.width / 2 - (w / 2), screen.height / 2 - (h / 2)]
    window.open(this.href, "Twitter", "toolbar=no,location=no,directories=no,status=no,menubar=no,scrollbars=no, resizable=yes,copyhistory=no,height=#{h},width=#{w},top=#{t},left=#{l}")
    $(this).addClass('selected')

  $(document).on "click", 'a.download', (e) ->
    e.preventDefault()
    me = this
    connectedly ->
      $(me).addClass('selected')
      window.open("#{me.href}?oauth_token=#{SC.accessToken()}", "Download", "")

  window._waveform = w
  window._socket = s
