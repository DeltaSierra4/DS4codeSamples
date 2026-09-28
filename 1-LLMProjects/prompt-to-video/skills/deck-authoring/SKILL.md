---
name: deck-authoring
description: Use when writing or editing a self-playing HTML deck for this plugin - anything that calls DeckPlayer.create, defines scenes and tracks, or gets packed by build/pack.mjs. Covers the one-timeline model, scene arithmetic, compute tracks, additive composition, the browser autoplay policy, and the six authoring rules that keep a deck seekable. Do NOT use for mp4 work, which is Pillow-drawn and has no timeline of this kind.
---

# Authoring a self-playing HTML deck

The deliverable is **one HTML file**. Someone double-clicks it and it plays. No
mp4, no encoding, no player software, nothing to install.

## The one idea

**Everything visible is a track on one timeline, and the player owns the clock.**

Nothing uses `setTimeout`, nothing uses a CSS `transition`. The player creates
every animation paused, then advances a single clock and seeks all of them
together. That is what makes the scrub bar work, what makes `?t=12.5` work, and
what lets audio take over as master clock without drift.

```js
DeckPlayer.create({
  stage: '.stage', width: 1280, height: 720, fade: 500,
  scenes: [
    { id: 'title', el: '#s1', dur: 6000, tracks: [
      { el: '.eyebrow', preset: 'riseIn',    at: 300,  dur: 800 },
      { el: 'h1 .w',    preset: 'riseIn',    at: 600,  dur: 1000, stagger: 160 },
      { el: '.rule',    preset: 'wipeRight', at: 1400, dur: 900 },
    ]},
  ],
});
```

## Scene arithmetic

`dur` is a scene's own on-screen time, both fades included. Consecutive scenes
cross-dissolve, overlapping by `fade`:

```
start[0]   = 0
start[i+1] = start[i] + dur[i] - overlap[i]
total      = sum(dur) - sum(overlap)
```

With a uniform fade that reduces to `total = sum(dur) - (sceneCount - 1) * fade`.
Eight scenes totalling 93.5s with seven 500ms dissolves land on 90.00s exactly.

**Changing any `dur` changes the total.** If narration cue times were derived
from scene starts, re-derive them. A per-scene `overlap` overrides `fade` and is
clamped to half the shorter scene.

## The six rules

Breaking these produces a deck that looks fine while you watch it and then
misbehaves on the scrub bar, on `?t=`, or under a frame renderer.

- **No CSS `transition`.** Transitions fire on property change in real time and
  cannot be seeked. The scrub bar would lie.
- **No `setTimeout`, `setInterval` or `requestAnimationFrame`** for anything
  visible. The player owns the clock.
- **Anything that is not a CSS property** (text, counters, canvas, SVG dash
  offsets) is a `compute` track: a pure function of progress, called on every
  frame the player draws.
- **No webfonts, no remote images.** The packed file must reach nothing. This is
  why the decks use Georgia and Segoe UI.
- **Two tracks animating one property on one element:** mark the second
  `additive: true`, or it masks the first for the whole timeline. This is the
  one that costs people an hour.
- **No em dashes in visible copy.** Periods, commas, colons.

## Track selectors are scoped, and a miss is silent

A scene's tracks are queried **inside that scene's element**, not against the
document. A selector that matches nothing produces only a
`console.warn('[player] no element matches ...')` — the deck plays, the element
simply never animates, and it looks like a scene that failed to appear.

So: when a scene seems not to render, check the selector before checking the
timing.

## Three browser realities that shape the design

1. **Autoplay with sound is blocked.** Every current browser refuses it without
   a prior user gesture. The deck autoplays **muted** and offers an unmute
   button, and that click is itself the gesture that satisfies the policy. There
   is no way around this and no point trying.
2. **The window is never 1280x720.** The stage is a fixed 1280x720 coordinate
   system that the player centres and scales with a CSS transform, so authored
   pixel positions stay true and text stays vector-crisp at any size.
3. **Anything the file has to fetch is a way for it to break later** — a blocked
   CDN, an offline laptop, a forwarded email carrying only the HTML. The shipped
   file references nothing outside itself, and `build/check.mjs` enforces that
   rather than trusting it.

## Working loop

Authoring needs **no build step**. The source deck loads `./player.js` from
beside it, so save and refresh is the whole loop. Pack only when sending.

```bash
node build/test-player.mjs                                  # 77 checks, no browser
node build/pack.mjs src/my-deck.html ../../output/my-deck.html
node build/check.mjs ../../output/my-deck.html              # exit 0 = safe to send
```

Node 18+, and no npm install. The packer has zero dependencies on purpose: it
has to run on the machine where `npm install` is the thing that fails.

No node on the machine is a stop, not a workaround. `scripts/nodecheck.py` finds
it and `reference/node-setup.md` holds the recovery. Never hand-roll a prompt
about installing it.

Edit the deck in `src/`, never the packed file in `output/`.

## Where things are

| Path | What it is |
|---|---|
| `scripts/html/src/player.js` | The runtime: timeline, clock, controls, scale-to-fit, audio sync. Never edit. |
| `scripts/html/src/example-deck.html` | The deck to copy. 60s, six scenes, compute tracks, additive composition, proportional bars, a staggered cascade. Replace all of its copy: it is deliberately about the plugin, because `scripts/` is distributed. |
| `scripts/html/src/template.html` | Minimal three-scene skeleton. Thinner than the above; prefer the 90s deck. |
| `scripts/html/build/pack.mjs` | Fold everything into one file. |
| `scripts/html/build/check.mjs` | Prove it is self-contained. Run before sending anything. |
| `scripts/html/build/test-player.mjs` | 77 unit tests for the schedule and clock maths. |
| `reference/html-authoring.md` | Presets, track options, the gotchas in full. |
| `reference/html-distribution.md` | Getting it to people: email, SharePoint, embedding, kiosks. |

`src/` and `build/` must stay siblings. `check.mjs` resolves `../src/player.js`
from its own location and silently downgrades its timeline check to a warning if
that path breaks.
