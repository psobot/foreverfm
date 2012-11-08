window.log = ->
  log.history = log.history or []
  log.history.push arguments
  console.log Array::slice.call(arguments)  if @console


soundManager.setup
  url: '/static/flash/'

NUM_TRACKS = 5
MP3_BUFFER = 3  # number of seconds buffered
DONE_TRACKS_LIMIT = 4
MAGIC_REGEX = /(\s*-*\s*((\[|\(|\*|~)[^\)\]]*(mp3|dl|description|free|download|comment|out now|clip|bonus|preview|teaser|in store|follow|radio|prod|full|snip|exclusive|beatport|original mix)+[^\)\]]*(\]|\)|\*|~)|((OUT NOW( ON \w*)?|free|download|preview|teaser|in store|follow|mp3|dl|description|full|snip|exclusive|beatport|original mix).*$))\s*|\[(.*?)\])/i

comma = (x) ->
  if x? then x.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',') else x

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
    matches = @tracks[0].metadata.title.match(/(.*?) by (.*)/i)
    if matches?
      [_, @title, @artist] = matches
      matches = @artist.match(/(.*?)\s+-\s+(.*)/i)
      [_, @artist, other] = matches if matches?
    else
      matches = @tracks[0].metadata.title.match(/(.*?)\s*-\s+(.*)/i)
      if matches?
        [_, @artist, @title] = matches
      else
        @title = @tracks[0].metadata.title
        @artist = @tracks[0].metadata.user.username
    
    matches = @title.match(/([^\[\]]*?)( - ([^\[\]\(\)]*)|(\[.*\]))/i)
    if matches?
      [_, @title, _, other] = matches
    
    #   Remove "Free Download," "Follow Me" and the like
    @title = @title.replace MAGIC_REGEX, ""
    @artist = @artist.replace MAGIC_REGEX, ""

    if @title[0] == '"' and @title[@title.length - 1] == '"'
      @title = @title[1...@title.length - 1].trim()

    @img = if @tracks[0].metadata.artwork_url?
             @tracks[0].metadata.artwork_url
           else
             @tracks[0].metadata.user.avatar_url

    # Stats display
    @playcount   = comma @tracks[0].metadata.playback_count
    @downloads   = comma @tracks[0].metadata.download_count
    @favoritings = comma @tracks[0].metadata.favoritings_count
    @stats = @playcount? and @downloads? and @favoritings

    # Buttons
    @buttons = true
    @nid = @tracks[0].metadata.id
    @download = @tracks[0].metadata.download_url

    @purchaselink = @tracks[0].metadata.purchase_url
    @purchasetext = @tracks[0].metadata.purchase_title
    @purchasetext = "Buy" if not @purchasetext?

    @url = @tracks[0].metadata.permalink_url

  twitter: ->
    text = "Check out this track: #{@url} #{if @playing() then "playing now" else "I found"} on"
    "http://twitter.com/share?text=#{encodeURIComponent(text)}"

  html: (first) ->
    first = false if not first?
    _new = @new
    @new = ''
    """
    <div class='track #{_new} #{if @played() and not first then "hidden" else ""}' id='#{@id}' target="_blank" href="#{@url}">
      <a class="coverart" href="#{@url}" target="_blank"><img src="#{@img}" /></a>
      <div class="text">
        <a class="title" href="#{@url}" target="_blank">#{@title}</a>
        <span class="artist">#{@artist}</span>
      </div>
      <div class='buttons'>
        #{if @id then "<a href='#' data-track='#{@nid}' class='like #{if (SC.favorites? and @nid in SC.favorites) then "" else ""}'>&nbsp;</a>
                       <a href='#{@twitter()}' target='_blank' class='share'>&nbsp;</a>
                      " else ""}
        #{if @download then "<a href='#{@download}' class='download' data-track='#{@nid}'>&nbsp;</a>" else ""}
        #{if @url then "<a href='#{@url}' target='_blank' class='sc'>&nbsp;</a>" else ""}
        #{if @purchaselink and @purchasetext then "<a href='#{@purchaselink}' target='_blank' class='buy'>#{@purchasetext}</a>" else ""}
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
    $(parent).prepend @html(true)
    id = @id
    setTimeout((-> $("##{id}").removeClass 'new hidden'), 100)
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
        setTimeout ->
          $(".hidden", newparent).removeClass('hidden')
          if newparent.children.length > DONE_TRACKS_LIMIT
            end = newparent.children[newparent.children.length - 1]
            $(end).addClass('hidden')
            setTimeout ->
              newparent.removeChild end
            , 1000
        , 100
      , 1400

class Waveform
  speed: 5
  constructor: (@canvas) ->
    @delay = 0
    @offset = $("#menu").outerWidth() + (MP3_BUFFER * @speed)  # Arbitrary - due to MP3 buffering
    @frames = []
    @context = @canvas.getContext "2d"
    @overlap = if navigator.userAgent.match(/chrome/i)? then 0 else 1
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
        @context.drawImage frame.image, right - @overlap, 0
        #if @overlap > 0
          # Clone the last column to prevent visual artifacts on Safari/Firefox
        # @context.putImageData(@context.getImageData(right - @overlap, 0, @overlap, @canvas.height), right, 0)
        right += frame.image.width - @overlap
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

if window.location.toString().search("beta.forever.fm") != -1
  SC.initialize
    client_id: "cd8a7092051937ab1994fa3868edb911"
    redirect_uri: "http://beta.forever.fm/static/sc.html"
else
  SC.initialize
    client_id: "b08793cf5964f5571db86e3ca9e5378f"
    redirect_uri: "http://forever.fm/static/sc.html"


connectedly = (callback, authenticate) ->
  if SC.isConnected()
    callback()
  else
    token = localStorage.getItem "accessToken"
    if token?
      SC.accessToken token
      getFavorites callback
    else if not authenticate? or authenticate
      SC.connect (a) ->
        localStorage.setItem('accessToken', SC.accessToken()) if localStorage?
        getFavorites callback

getFavorites = (callback) ->
  SC.get "/me/favorites/", {limit: 1000}, (favoriteds) ->
    SC.favorites = (track.id for track in favoriteds)
    callback SC.favorites

$(document).ready ->
  w = new Waveform document.getElementById "waveform"
  
  connectedly (favorites) ->
    $("#track_#{id} .like").addClass('selected') for id in favorites
  , false

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
    me = this
    trackid = parseInt $(this).data 'track'
    liked = $(this).hasClass 'selected'
    $(me).toggleClass 'selected'
    connectedly ->
      if liked
        SC.delete "/me/favorites/#{trackid}", (a) ->
          if a.status?
            target = $("#track_#{trackid} .favoritings")
            target.html(comma(parseInt(target.html().replace(',', '')) - 1))
            idx = SC.favorites.indexof(trackid)
            SC.favorites.splice(idx, 1) if idx > -1
          else
            $(me).toggleClass 'selected'
      else
        SC.put "/me/favorites/#{trackid}", (a) ->
          if a.status?
            target = $("#track_#{trackid} .favoritings")
            target.html(comma(parseInt(target.html().replace(',', '')) + 1))
            SC.favorites.push trackid
          else
            $(me).toggleClass 'selected'

  $(document).on "click", 'a.share', (e) ->
    e.preventDefault()
    [w, h] = [500, 250]
    [l, t] = [screen.width / 2 - (w / 2), screen.height / 2 - (h / 2)]
    window.open(this.href, "Twitter", "toolbar=no,location=no,directories=no,status=no,menubar=no,scrollbars=no, resizable=yes,copyhistory=no,height=#{h},width=#{w},top=#{t},left=#{l}")
    $(this).addClass('selected')

  $(document).on "click", 'a.download', (e) ->
    e.preventDefault()
    trackid = $(this).data 'track'
    me = this
    connectedly ->
      $(me).addClass('selected')
      me.href += "?oauth_token=#{SC.accessToken()}"
      window.location = me.href
      target = $("#track_#{trackid} .stats .count.download")
      target.html(comma(parseInt(target.html().replace(',', '')) + 1))


  window._waveform = w
  window._socket = s
