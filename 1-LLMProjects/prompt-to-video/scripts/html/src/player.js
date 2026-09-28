/* player.js - a self-contained animated-deck player for the browser.
 *
 * The deliverable here is the HTML FILE, not a video. It opens in any browser, plays
 * itself, and needs no server, no network and no toolchain. That changes the design in
 * three ways compared with a render-to-mp4 pipeline:
 *
 *   1. It plays on the wall clock, driven by requestAnimationFrame, because a human is
 *      watching it in real time rather than a renderer stepping it frame by frame.
 *   2. It has to survive an arbitrary window size, so the 1280x720 stage is scaled to
 *      fit and letterboxed.
 *   3. It has to obey browser policy, chiefly that AUTOPLAY WITH SOUND IS BLOCKED.
 *      So it autoplays muted and offers an unmute control. See `audio` below.
 *
 * THE SCHEMA IS DELIBERATELY IDENTICAL to the poc-html renderer's. Same scenes, same
 * tracks, same presets, same easings. A deck written for one runs on the other, and
 * this player still exposes seek(), so if an mp4 is ever needed the frame renderer can
 * drive this exact file. Choosing "HTML, not video" here does not close that door.
 *
 * URL parameters
 *   ?autoplay=0   load paused on the first frame
 *   ?loop=1       restart at the end. For a kiosk or a booth screen
 *   ?controls=0   hide the control bar
 *   ?embed=1      autoplay + loop + no controls, for an iframe
 *   ?t=12.5       start at 12.5s
 *   ?muted=0      try to start unmuted. Browsers will usually refuse; see below
 */
(function (global) {
  'use strict';

  // ---------------------------------------------------------------- easings

  var EASE = {
    linear: 'linear',
    out: 'cubic-bezier(.22,.61,.36,1)',
    in: 'cubic-bezier(.55,.06,.68,.19)',
    inOut: 'cubic-bezier(.65,0,.35,1)',
    outExpo: 'cubic-bezier(.16,1,.3,1)',
    outBack: 'cubic-bezier(.34,1.4,.64,1)',
    outSoft: 'cubic-bezier(.25,.46,.45,.94)',
  };

  // JS twins, for compute tracks, which the player interpolates itself.
  var EASE_FN = {
    linear: function (p) { return p; },
    out: function (p) { return 1 - Math.pow(1 - p, 3); },
    in: function (p) { return p * p * p; },
    inOut: function (p) { return p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2; },
    outExpo: function (p) { return p >= 1 ? 1 : 1 - Math.pow(2, -10 * p); },
    outBack: function (p) { var c = 1.70158, c3 = c + 1; return 1 + c3 * Math.pow(p - 1, 3) + c * Math.pow(p - 1, 2); },
    outSoft: function (p) { return 1 - Math.pow(1 - p, 2); },
  };

  var PRESETS = {
    riseIn:    { dur: 850, ease: 'outExpo', keyframes: [{ opacity: 0, transform: 'translateY(26px)' }, { opacity: 1, transform: 'translateY(0)' }] },
    riseOut:   { dur: 550, ease: 'in',      keyframes: [{ opacity: 1, transform: 'translateY(0)' }, { opacity: 0, transform: 'translateY(-18px)' }] },
    fadeIn:    { dur: 700, ease: 'out',     keyframes: [{ opacity: 0 }, { opacity: 1 }] },
    fadeOut:   { dur: 500, ease: 'out',     keyframes: [{ opacity: 1 }, { opacity: 0 }] },
    slideInL:  { dur: 900, ease: 'outExpo', keyframes: [{ opacity: 0, transform: 'translateX(-40px)' }, { opacity: 1, transform: 'translateX(0)' }] },
    slideInR:  { dur: 900, ease: 'outExpo', keyframes: [{ opacity: 0, transform: 'translateX(40px)' }, { opacity: 1, transform: 'translateX(0)' }] },
    popIn:     { dur: 700, ease: 'outBack', keyframes: [{ opacity: 0, transform: 'scale(.86)' }, { opacity: 1, transform: 'scale(1)' }] },
    wipeRight: { dur: 900, ease: 'outExpo', keyframes: [{ transform: 'scaleX(0)' }, { transform: 'scaleX(1)' }] },
    wipeDown:  { dur: 800, ease: 'outExpo', keyframes: [{ transform: 'scaleY(0)' }, { transform: 'scaleY(1)' }] },
    growWidth: { dur: 1100, ease: 'outExpo', keyframes: [{ width: '0%' }, { width: '100%' }] },
    drift:     { dur: 6000, ease: 'linear', keyframes: [{ transform: 'scale(1.04)' }, { transform: 'scale(1.12)' }] },
  };

  // ---------------------------------------------------------------- schedule

  /**
   * Turn a declarative scene list into absolute-time animation descriptors.
   * Pure: no DOM, no side effects. Unit tested in build/test-player.mjs.
   *
   *     start[0]   = 0
   *     start[i+1] = start[i] + dur[i] - overlap[i]
   *     total      = sum(dur) - sum(overlap)
   *
   * `dur` is a scene's own on-screen time, both fades included. Consecutive scenes
   * cross-dissolve, overlapping by `fade`, so both are partly visible through the
   * boundary rather than dipping to the backdrop between them.
   */
  function buildSchedule(scenes, opts) {
    opts = opts || {};
    var fade = num(opts.fade, 500);
    var fadeFirstIn = opts.fadeFirstIn !== false;
    var fadeLastOut = opts.fadeLastOut !== false;

    if (!Array.isArray(scenes) || !scenes.length) throw new Error('buildSchedule: no scenes');

    var problems = [];
    var n = scenes.length;

    var overlaps = [];
    for (var i = 0; i < n - 1; i++) {
      var want = num(scenes[i + 1].overlap, fade);
      var cap = Math.min(scenes[i].dur, scenes[i + 1].dur) / 2;
      if (want > cap) {
        problems.push('overlap ' + want + 'ms between "' + sid(scenes[i], i) + '" and "' + sid(scenes[i + 1], i + 1) +
          '" is more than half the shorter scene; clamped to ' + Math.floor(cap) + 'ms');
        want = Math.floor(cap);
      }
      overlaps.push(want);
    }

    var out = { fade: fade, durationMs: 0, scenes: [], tracks: [], computes: [], problems: problems, overlaps: overlaps };
    var t = 0;

    scenes.forEach(function (sc, i) {
      var id = sid(sc, i);
      if (!(num(sc.dur, 0) > 0)) problems.push('scene "' + id + '" has no positive dur');
      if (!sc.el) problems.push('scene "' + id + '" has no el selector');

      var dur = num(sc.dur, 0);
      var fIn = i === 0 ? (fadeFirstIn ? fade : 0) : overlaps[i - 1];
      var fOut = i === n - 1 ? (fadeLastOut ? fade : 0) : overlaps[i];
      if (fIn + fOut > dur) problems.push('scene "' + id + '" is ' + dur + 'ms but its fades total ' + (fIn + fOut) + 'ms');

      out.scenes.push({ id: id, el: sc.el, start: t, dur: dur, end: t + dur, fadeIn: fIn, fadeOut: fOut, label: sc.label || null });

      out.tracks.push({
        el: sc.el, scene: id, kind: 'scene',
        keyframes: envelope(fIn, fOut, dur),
        timing: { delay: t, duration: dur, easing: EASE.linear, fill: 'both', composite: 'replace' },
      });

      (sc.tracks || []).forEach(function (tr, k) {
        var label = 'scene "' + id + '" track ' + k + ' (' + (tr.el || '?') + ')';
        var preset = tr.preset ? PRESETS[tr.preset] : null;
        if (tr.preset && !preset) { problems.push(label + ': unknown preset "' + tr.preset + '"'); return; }

        var kf = tr.keyframes || (preset && preset.keyframes);
        var isCompute = typeof tr.compute === 'function';
        if (!kf && !isCompute) { problems.push(label + ': needs a preset, keyframes, or compute'); return; }

        var d = num(tr.dur, preset ? preset.dur : 800);
        var easeName = tr.ease || (preset && preset.ease) || 'out';
        if (!EASE[easeName]) { problems.push(label + ': unknown ease "' + easeName + '"'); return; }

        var at = num(tr.at, 0);
        var stagger = num(tr.stagger, 0);
        if (at < 0) problems.push(label + ': at is negative');
        if (at + d > dur) problems.push(label + ': ends at ' + (at + d) + 'ms, past the scene\'s ' + dur + 'ms' + (stagger ? ' (before stagger)' : ''));

        if (isCompute) {
          out.computes.push({
            el: tr.el, scene: id, start: t + at, duration: d, ease: easeName,
            from: num(tr.from, 0), to: num(tr.to, 1), fn: tr.compute,
          });
        } else {
          // `additive: true` -> composite 'add'.
          //
          // Every track fills both ways, and the Web Animations API resolves conflicts by
          // creation order, so a LATER transform track masks an earlier one for the whole
          // timeline, not just its own window. An entrance followed by a slow drift on the
          // same element therefore silently loses the entrance unless the drift is additive,
          // whose neutral value composites to nothing outside its window.
          out.tracks.push({
            el: tr.el, scene: id, kind: 'element', stagger: stagger,
            keyframes: kf,
            timing: {
              delay: t + at, duration: d, easing: EASE[easeName], fill: 'both',
              composite: tr.additive ? 'add' : (tr.composite || 'replace'),
            },
          });
        }
      });

      t += dur - (i < n - 1 ? overlaps[i] : 0);
    });

    out.durationMs = out.scenes[n - 1].end;
    return out;
  }

  function envelope(fadeIn, fadeOut, dur) {
    var kf = [];
    var upTo = dur > 0 ? Math.min(1, fadeIn / dur) : 0;
    var downFrom = dur > 0 ? Math.max(upTo, 1 - fadeOut / dur) : 1;
    if (fadeIn > 0) kf.push({ opacity: 0, offset: 0 });
    kf.push({ opacity: 1, offset: round4(upTo) });
    kf.push({ opacity: 1, offset: round4(downFrom) });
    if (fadeOut > 0) kf.push({ opacity: 0, offset: 1 });
    if (kf.length > 1 && kf[0].offset === kf[1].offset && kf[0].opacity === kf[1].opacity) kf.shift();
    return kf;
  }

  /**
   * Rewrite keyframes for prefers-reduced-motion: SETTLE AT THE FINAL GEOMETRY, keep
   * only the opacity change. Nothing slides, scales, grows or travels; things fade in
   * where they end up. That is the distinction the media query is actually about.
   *
   * Settling rather than deleting matters. Simply removing the animated property leaves
   * the element at whatever the stylesheet says, and the stylesheet says the START
   * state, because the animation was supposed to move it. A growing bar declared
   * `width: 0` would animate nothing and stay invisible, which is not "reduced motion",
   * it is a broken deck. Taking the last keyframe's values for every keyframe shows the
   * finished result instead.
   */
  function stripTransforms(keyframes) {
    if (!keyframes.length) return keyframes;
    var last = keyframes[keyframes.length - 1];
    var settled = {};
    for (var key in last) if (key !== 'opacity' && key !== 'offset') settled[key] = last[key];
    return keyframes.map(function (k) {
      var o = {};
      for (var s in settled) o[s] = settled[s];
      if (k.offset !== undefined) o.offset = k.offset;
      o.opacity = k.opacity !== undefined ? k.opacity : 1;
      return o;
    });
  }

  function num(v, d) { return typeof v === 'number' && isFinite(v) ? v : d; }
  function sid(sc, i) { return sc.id || sc.el || ('scene' + (i + 1)); }
  function round4(n) { return Math.round(n * 10000) / 10000; }
  function clamp(n, a, b) { return n < a ? a : n > b ? b : n; }
  function clock(ms) {
    var s = Math.max(0, Math.round(ms / 1000));
    return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
  }

  // ---------------------------------------------------------------- player

  function create(config) {
    if (typeof document === 'undefined') throw new Error('create() needs a DOM. In Node, use buildSchedule().');

    var params = new URLSearchParams(global.location ? global.location.search : '');
    var embed = params.get('embed') === '1';
    var opt = {
      autoplay: params.get('autoplay') !== '0',
      loop: embed || params.get('loop') === '1',
      controls: !embed && params.get('controls') !== '0',
      startMuted: params.get('muted') !== '0',
      startAt: params.has('t') ? parseFloat(params.get('t')) * 1000 : 0,
    };

    var reduceMotion = typeof matchMedia === 'function' &&
      matchMedia('(prefers-reduced-motion: reduce)').matches;

    var schedule = buildSchedule(config.scenes, config);
    if (schedule.problems.length) {
      console.warn('[player] ' + schedule.problems.length + ' schedule problem(s):');
      schedule.problems.forEach(function (p) { console.warn('  - ' + p); });
    }

    var stage = document.querySelector(config.stage || '.stage');
    if (!stage) throw new Error('No stage element matches "' + (config.stage || '.stage') + '"');
    var W = num(config.width, 1280), H = num(config.height, 720);

    // ---- scale the fixed stage to fit whatever window it lands in ----------
    // A transform scale keeps text vector-crisp at any size, which a width/height
    // rescale of the layout would not, and keeps the deck's coordinate system fixed
    // so authored pixel positions stay true.
    function fit() {
      var s = Math.min(global.innerWidth / W, global.innerHeight / H);
      stage.style.transform = 'translate(-50%, -50%) scale(' + s + ')';
    }
    fit();
    global.addEventListener('resize', fit);

    // ---- attach the timeline ----------------------------------------------
    document.querySelectorAll('[data-draw]').forEach(function (p) {
      if (typeof p.getTotalLength === 'function') {
        var len = p.getTotalLength();
        p.style.setProperty('--len', len);
        p.style.strokeDasharray = len;
        p.style.strokeDashoffset = len;
      }
    });

    var animations = [];
    var computes = [];

    schedule.tracks.forEach(function (tr) {
      var scope = tr.kind === 'scene' ? document : sceneEl(tr.scene);
      var els = Array.prototype.slice.call((scope || document).querySelectorAll(tr.el));
      if (!els.length) { console.warn('[player] no element matches "' + tr.el + '" in ' + tr.scene); return; }
      var kf = (reduceMotion && tr.kind === 'element') ? stripTransforms(tr.keyframes) : tr.keyframes;
      els.forEach(function (el, idx) {
        var anim = el.animate(kf, {
          delay: tr.timing.delay + (tr.stagger || 0) * (reduceMotion ? 0 : idx),
          duration: reduceMotion && tr.kind === 'element' ? Math.min(tr.timing.duration, 250) : tr.timing.duration,
          easing: tr.timing.easing,
          fill: tr.timing.fill,
          composite: tr.timing.composite,
        });
        anim.pause();
        anim.currentTime = 0;
        animations.push(anim);
      });
    });

    schedule.computes.forEach(function (c) {
      var scope = sceneEl(c.scene) || document;
      Array.prototype.slice.call(scope.querySelectorAll(c.el)).forEach(function (el) {
        computes.push({ el: el, start: c.start, duration: c.duration, ease: EASE_FN[c.ease] || EASE_FN.out, from: c.from, to: c.to, fn: c.fn });
      });
    });

    // Any CSS @keyframes animation written with animation-play-state: paused joins the
    // timeline too, so a deck can use either mechanism.
    if (typeof document.getAnimations === 'function') {
      document.getAnimations().forEach(function (a) {
        if (animations.indexOf(a) === -1) {
          try { a.pause(); a.currentTime = 0; animations.push(a); } catch (e) { /* not seekable */ }
        }
      });
    }

    function sceneEl(id) {
      for (var i = 0; i < schedule.scenes.length; i++) {
        if (schedule.scenes[i].id === id) return document.querySelector(schedule.scenes[i].el);
      }
      return null;
    }

    // ---- audio -------------------------------------------------------------
    // AUTOPLAY WITH SOUND IS BLOCKED by every current browser without a prior user
    // gesture. Fighting that is not an option, so the deck autoplays MUTED and offers
    // an unmute control, which is itself the gesture that satisfies the policy.
    //
    // When audio is present and audible it becomes the master clock. Two independent
    // clocks, rAF and the audio hardware, drift apart over a couple of minutes; slaving
    // the timeline to audio.currentTime is what real video players do and it removes
    // the problem rather than compensating for it.
    var audio = null;
    var hasAudio = false;

    // Re-queried rather than captured once. The element can legitimately appear after
    // this script has run: a build tool appends it, or someone hand-places it lower in
    // the body. Capturing null at create() time and never looking again means the audio
    // is in the file and unreachable, which presents as "the sound does not work" with
    // nothing obviously wrong anywhere.
    function findAudio() {
      var el = document.querySelector('audio[data-narration]');
      if (el !== audio) { audio = el; if (audio) audio.muted = true; }
      hasAudio = !!(audio && (audio.currentSrc || audio.src || audio.querySelector('source')));
      if (player) player.hasAudio = hasAudio;
      if (ui && ui.syncAudio) ui.syncAudio();
      return hasAudio;
    }

    // ---- clock -------------------------------------------------------------
    var t = clamp(opt.startAt, 0, schedule.durationMs);
    var playing = false;
    var rafId = null;
    var lastTs = 0;
    var ended = false;

    function seek(ms) {
      t = clamp(ms, 0, schedule.durationMs);
      for (var i = 0; i < animations.length; i++) {
        try { animations[i].currentTime = t; } catch (e) { /* dropped */ }
      }
      for (var j = 0; j < computes.length; j++) {
        var c = computes[j];
        var p = c.duration > 0 ? clamp((t - c.start) / c.duration, 0, 1) : (t >= c.start ? 1 : 0);
        c.fn(c.from + (c.to - c.from) * c.ease(p), c.el, p);
      }
      player.currentTime = t;
      if (ui) ui.paint();
      return t;
    }

    function frame(ts) {
      if (!playing) return;
      if (hasAudio && audio && !audio.paused && !audio.muted) {
        // audio is master
        t = audio.currentTime * 1000;
      } else {
        var dt = lastTs ? ts - lastTs : 0;
        // Clamp the delta. requestAnimationFrame stops while a tab is backgrounded, so
        // without this the first frame after returning would jump by however long the
        // user was away. Clamping makes a hidden tab behave as a pause.
        t += clamp(dt, 0, 250);
      }
      lastTs = ts;

      if (t >= schedule.durationMs) {
        seek(schedule.durationMs);
        if (opt.loop) { restart(); return; }
        playing = false; ended = true; rafId = null;
        if (audio) audio.pause();
        if (ui) ui.paint();
        return;
      }
      seek(t);
      rafId = requestAnimationFrame(frame);
    }

    function play() {
      if (playing) return;
      if (ended || t >= schedule.durationMs) { t = 0; ended = false; }
      playing = true;
      lastTs = 0;
      if (hasAudio && audio) {
        try { audio.currentTime = t / 1000; } catch (e) { /* not seekable yet */ }
        var pr = audio.play();
        if (pr && pr.catch) pr.catch(function () { /* blocked; the timeline plays on regardless */ });
      }
      rafId = requestAnimationFrame(frame);
      if (ui) ui.paint();
    }

    function pause() {
      playing = false;
      if (rafId) { cancelAnimationFrame(rafId); rafId = null; }
      if (audio) audio.pause();
      if (ui) ui.paint();
    }

    function toggle() { playing ? pause() : play(); }
    function restart() { ended = false; t = 0; lastTs = 0; seek(0); if (!playing) play(); else if (audio) { try { audio.currentTime = 0; } catch (e) {} } }

    function setMuted(m) {
      if (!audio) return;
      audio.muted = m;
      if (!m && playing) {
        try { audio.currentTime = t / 1000; } catch (e) {}
        var pr = audio.play();
        if (pr && pr.catch) pr.catch(function () {});
      }
      if (ui) ui.paint();
    }

    var player = {
      version: 1,
      schedule: schedule,
      durationMs: schedule.durationMs,
      currentTime: t,
      reduceMotion: reduceMotion,
      hasAudio: hasAudio,
      stage: stage,
      seek: seek, play: play, pause: pause, toggle: toggle, restart: restart,
      setMuted: setMuted,
      isPlaying: function () { return playing; },
      isMuted: function () { return !audio || audio.muted; },
      ready: false,
    };

    var ui = opt.controls ? mountControls(player, opt) : null;

    findAudio();
    // And once more after the document has finished parsing, which is when an element
    // placed below this script actually exists.
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', findAudio, { once: true });
    }

    seek(t);

    // System fonts resolve immediately, but a deck that embeds one still needs a beat.
    // Cap the wait: a font that never arrives must not stop the deck from playing.
    var fontWait = (typeof document.fonts !== 'undefined' && document.fonts.ready)
      ? Promise.race([document.fonts.ready, new Promise(function (r) { setTimeout(r, num(config.fontTimeout, 2000)); })])
      : Promise.resolve();

    fontWait.then(function () {
      findAudio();
      seek(player.currentTime);
      player.ready = true;
      document.documentElement.setAttribute('data-deck-ready', '1');
      if (opt.autoplay) play();
    });

    global.__deck = player;
    return player;
  }

  // ---------------------------------------------------------------- controls

  // Injected rather than shipped as a stylesheet, so a deck needs no CSS of its own for
  // the chrome and the packer has one less file to inline.
  var PLAYER_CSS =
    '.deck-controls{position:fixed;left:50%;bottom:22px;transform:translateX(-50%);z-index:9999;' +
    'display:flex;align-items:center;gap:12px;padding:9px 14px;border-radius:14px;' +
    'background:rgba(10,14,18,.72);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);' +
    'box-shadow:0 8px 30px rgba(0,0,0,.35);color:#fff;' +
    'font:500 12.5px/1 system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;' +
    'opacity:1;transition:opacity .35s ease}' +
    '.deck-controls.hidden{opacity:0;pointer-events:none}' +
    '.deck-controls button{all:unset;cursor:pointer;width:30px;height:30px;border-radius:9px;' +
    'display:flex;align-items:center;justify-content:center;font-size:12px;color:#fff;' +
    'background:rgba(255,255,255,.11)}' +
    '.deck-controls button:hover{background:rgba(255,255,255,.2)}' +
    '.deck-controls button:focus-visible{outline:2px solid #eb8c00;outline-offset:2px}' +
    '.deck-controls [data-time]{font-variant-numeric:tabular-nums;opacity:.8;min-width:74px;text-align:center}' +
    '.deck-scrub{position:relative;width:min(38vw,420px);height:16px;cursor:pointer;display:flex;align-items:center}' +
    '.deck-scrub:focus-visible{outline:2px solid #eb8c00;outline-offset:2px;border-radius:4px}' +
    '.deck-scrub::before{content:"";position:absolute;left:0;right:0;height:4px;border-radius:3px;background:rgba(255,255,255,.2)}' +
    '.deck-scrub i{position:absolute;left:0;height:4px;border-radius:3px;background:linear-gradient(90deg,#d04a02,#eb8c00);width:0}' +
    '.deck-scrub b{position:absolute;left:0;right:0;height:16px}' +
    '.deck-scrub u{position:absolute;top:5px;width:2px;height:6px;background:rgba(255,255,255,.55);border-radius:1px}' +
    'body.deck-idle{cursor:none}' +
    '@media print{.deck-controls{display:none}}';

  function injectStyles() {
    if (document.getElementById('deck-player-css')) return;
    var s = document.createElement('style');
    s.id = 'deck-player-css';
    s.textContent = PLAYER_CSS;
    document.head.appendChild(s);
  }

  function mountControls(player, opt) {
    injectStyles();
    var bar = document.createElement('div');
    bar.className = 'deck-controls';
    bar.setAttribute('role', 'group');
    bar.setAttribute('aria-label', 'Playback controls');
    bar.innerHTML =
      '<button data-act="toggle" aria-label="Play or pause">&#9654;</button>' +
      '<button data-act="restart" aria-label="Restart">&#8635;</button>' +
      '<div data-scrub class="deck-scrub" role="slider" tabindex="0" aria-label="Seek"><i></i><b></b></div>' +
      '<span data-time>0:00 / 0:00</span>' +
      // Always built, hidden until an audio element is actually found. Building it
      // conditionally means a track that appears later can never get a control.
      '<button data-act="mute" aria-label="Unmute" hidden>&#128263;</button>' +
      '<button data-act="full" aria-label="Fullscreen">&#9974;</button>';
    document.body.appendChild(bar);

    var btnToggle = bar.querySelector('[data-act="toggle"]');
    var btnMute = bar.querySelector('[data-act="mute"]');
    var scrub = bar.querySelector('[data-scrub]');
    var fill = scrub.querySelector('i');
    var marks = scrub.querySelector('b');
    var time = bar.querySelector('[data-time]');

    // Scene markers, so the bar shows the structure of the piece.
    marks.innerHTML = player.schedule.scenes.slice(1).map(function (s) {
      return '<u style="left:' + (s.start / player.durationMs * 100).toFixed(3) + '%"></u>';
    }).join('');

    bar.addEventListener('click', function (e) {
      var b = e.target.closest('[data-act]');
      if (!b) return;
      var act = b.getAttribute('data-act');
      if (act === 'toggle') player.toggle();
      else if (act === 'restart') player.restart();
      else if (act === 'mute') player.setMuted(!player.isMuted());
      else if (act === 'full') {
        if (document.fullscreenElement) document.exitFullscreen();
        else document.documentElement.requestFullscreen().catch(function () {});
      }
    });

    function scrubTo(e) {
      var r = scrub.getBoundingClientRect();
      var p = clamp((e.clientX - r.left) / r.width, 0, 1);
      player.seek(p * player.durationMs);
    }
    var dragging = false;
    scrub.addEventListener('pointerdown', function (e) { dragging = true; scrub.setPointerCapture(e.pointerId); player.pause(); scrubTo(e); });
    scrub.addEventListener('pointermove', function (e) { if (dragging) scrubTo(e); });
    scrub.addEventListener('pointerup', function (e) { dragging = false; scrub.releasePointerCapture(e.pointerId); });

    document.addEventListener('keydown', function (e) {
      if (e.target && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
      var k = e.key;
      if (k === ' ' || k === 'k') { e.preventDefault(); player.toggle(); }
      else if (k === 'ArrowRight') { player.pause(); player.seek(player.currentTime + (e.shiftKey ? 5000 : 1000)); }
      else if (k === 'ArrowLeft') { player.pause(); player.seek(player.currentTime - (e.shiftKey ? 5000 : 1000)); }
      else if (k === 'Home' || k === '0') { player.restart(); }
      else if (k === 'm' && player.hasAudio) { player.setMuted(!player.isMuted()); }
      else if (k === 'f') { if (document.fullscreenElement) document.exitFullscreen(); else document.documentElement.requestFullscreen().catch(function () {}); }
    });

    // Auto-hide, like a video player. Never while paused, so the controls are findable.
    var hideTimer = null;
    function wake() {
      bar.classList.remove('hidden');
      document.body.classList.remove('deck-idle');
      clearTimeout(hideTimer);
      hideTimer = setTimeout(function () {
        if (player.isPlaying()) { bar.classList.add('hidden'); document.body.classList.add('deck-idle'); }
      }, 2600);
    }
    ['pointermove', 'pointerdown', 'keydown'].forEach(function (ev) { document.addEventListener(ev, wake); });
    wake();

    return {
      syncAudio: function () {
        btnMute.hidden = !player.hasAudio;
      },
      paint: function () {
        var d = player.durationMs || 1;
        fill.style.width = (player.currentTime / d * 100).toFixed(3) + '%';
        time.textContent = clock(player.currentTime) + ' / ' + clock(d);
        btnToggle.innerHTML = player.isPlaying() ? '&#10074;&#10074;' : '&#9654;';
        scrub.setAttribute('aria-valuenow', Math.round(player.currentTime / 1000));
        scrub.setAttribute('aria-valuemax', Math.round(d / 1000));
        btnMute.hidden = !player.hasAudio;
        btnMute.innerHTML = player.isMuted() ? '&#128263;' : '&#128266;';
        btnMute.setAttribute('aria-label', player.isMuted() ? 'Unmute narration' : 'Mute narration');
        if (!player.isPlaying()) wake();
      },
    };
  }

  // ---------------------------------------------------------------- exports

  var api = {
    create: create,
    buildSchedule: buildSchedule,
    stripTransforms: stripTransforms,
    PRESETS: PRESETS, EASE: EASE, EASE_FN: EASE_FN,
    fmt: {
      int: function (n) { return String(Math.round(n)); },
      comma: function (n) { return Math.round(n).toLocaleString('en-US'); },
      money: function (n) { return '$' + Math.round(n).toLocaleString('en-US'); },
      moneyK: function (n) { return '$' + Math.round(n / 1000) + 'K'; },
    },
    countTo: function (format) {
      var f = format || api.fmt.int;
      return function (value, el) { el.textContent = f(value); };
    },
    drawLine: function () {
      return function (value, el) {
        var len = Number(el.style.getPropertyValue('--len')) || 0;
        el.style.strokeDashoffset = String(len * (1 - value));
      };
    },
    setVar: function (name, suffix) {
      return function (value, el) { el.style.setProperty(name, value + (suffix || '')); };
    },
    clock: clock,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  global.DeckPlayer = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
