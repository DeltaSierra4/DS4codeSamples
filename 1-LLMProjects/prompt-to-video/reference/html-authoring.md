# Authoring a deck

Everything you can put in a scene. Shared with `../poc-html`, so a deck moves between the two.

---

## The shape of a deck

Markup, then one call.

```html
<div class="stage">
  <section class="scene" id="s1"> ... </section>
  <section class="scene" id="s2"> ... </section>
</div>

<script src="player.js"></script>
<script>
  var P = DeckPlayer;
  DeckPlayer.create({ stage: '.stage', fade: 500, scenes: [ /* ... */ ] });
</script>
```

Scenes stack absolutely inside a fixed 1280x720 stage. The player owns their `opacity`; leave it
at `0` in CSS and never animate it there.

Author with no build step: open the file in a browser, edit, refresh. Pack only when you are done.

---

## Scene options

| Key | Meaning |
|---|---|
| `id` | Short, filename-safe. Shows up in logs and audio slots. |
| `el` | Selector for the scene container. Track selectors are queried inside it. |
| `dur` | The scene's own on-screen time, **both fades included**. |
| `overlap` | Override the cross-dissolve into *this* scene. |
| `label` | Human name, for the scrub bar. |
| `tracks` | The animations. |

```
start[0]   = 0
start[i+1] = start[i] + dur[i] - overlap[i]
total      = sum(dur) - sum(overlap)
```

Five 6s scenes with 500ms fades is 28s, not 30s. An overlap wider than half the shorter scene is
clamped, with a warning in the console.

`fadeFirstIn: false` opens fully opaque; `fadeLastOut: false` ends on the last frame rather than
fading out.

---

## Track options

| Key | Meaning |
|---|---|
| `el` | Selector, queried **inside the scene**. Matching several elements is normal. |
| `preset` | Named motion. Supplies keyframes, duration and easing; each overridable. |
| `keyframes` | Web Animations keyframes instead of a preset. |
| `compute` | A function of progress, for anything that is not a CSS property. |
| `at` | Start in ms, **relative to the scene**. |
| `dur` | Duration in ms. |
| `ease` | An easing name. |
| `stagger` | Extra delay per matched element. |
| `additive` | `composite: 'add'`. Required for a second track on the same property. |
| `from` / `to` | Value range for a `compute` track. Defaults 0 and 1. |

---

## Presets

| Name | What it does | Default dur / ease |
|---|---|---|
| `riseIn` | Fade up while sliding up 26px. The workhorse. | 850 / outExpo |
| `riseOut` | Fade down while sliding up 18px. | 550 / in |
| `fadeIn` / `fadeOut` | Opacity only. | 700 / out, 500 / out |
| `slideInL` / `slideInR` | Fade up from 40px left or right. | 900 / outExpo |
| `popIn` | Fade up from 0.86 scale. Buttons, badges, totals. | 700 / outBack |
| `wipeRight` | `scaleX` 0 to 1. Needs `transform-origin: left center`. | 900 / outExpo |
| `wipeDown` | `scaleY` 0 to 1. Needs `transform-origin: top center`. | 800 / outExpo |
| `growWidth` | `width` 0% to 100%. Bars and meters. | 1100 / outExpo |
| `drift` | Slow Ken Burns, scale 1.04 to 1.12. | 6000 / linear |

Easings: `linear`, `out`, `in`, `inOut`, `outExpo`, `outBack`, `outSoft`. `outExpo` for entrances,
`inOut` for anything that returns, `linear` only for continuous drift.

---

## Compute tracks

For anything the Web Animations API cannot interpolate. Called on every frame the player draws,
with the eased value and the element. Must be a pure function of its input, which is what keeps
scrubbing and `?t=` correct.

```js
// count a number up
{ el: '#n', compute: P.countTo(P.fmt.comma), from: 0, to: 1250, at: 600, dur: 1800, ease: 'outExpo' }

// custom format
{ el: '#m', compute: function (v, el) { el.textContent = '$' + Math.round(v) + 'K'; },
  from: 0, to: 40, at: 1500, dur: 2000, ease: 'outExpo' }

// draw an SVG path. Put data-draw on the path; the player measures it and sets --len.
{ el: '#route', compute: P.drawLine(), from: 0, to: 1, at: 1700, dur: 2100, ease: 'outSoft' }

// drive a CSS custom property
{ el: '.dial', compute: P.setVar('--angle', 'deg'), from: 0, to: 270, at: 400, dur: 1200 }
```

Formatters on `P.fmt`: `int`, `comma`, `money`, `moneyK`.

Before its window a compute holds `from`; after it, `to`. Set the element's initial text to match
`from`, or the first frames show whatever the markup says.

---

## The gotcha that costs an hour

**Two tracks animating the same property on the same element: the second wins, from t=0.**

Every track fills both ways, and the Web Animations API resolves conflicts by creation order. So a
later `transform` track masks an earlier one across the *whole* timeline, not just its own window.
An entrance followed by a slow drift silently loses the entrance.

```js
{ el: '.cta', preset: 'popIn', at: 1100, dur: 800 },
{ el: '.cta', additive: true, ease: 'inOut', at: 2000, dur: 3400,
  keyframes: [{ transform: 'scale(1)' }, { transform: 'scale(1.035)' }, { transform: 'scale(1)' }] },
```

Additive composition adds onto what is underneath and contributes nothing outside its own window.

---

## Things that break the timeline

Each renders fine while you watch it and then misbehaves on the scrub bar, on `?t=`, or under a
frame renderer.

| Do not | Because | Instead |
|---|---|---|
| CSS `transition` | Fires on property change in real time; seeking does not touch it | a track |
| `setTimeout` / `setInterval` | Wall clock, independent of the player's clock | a track or a compute |
| `requestAnimationFrame` loops | Same | a compute; it already runs every frame |
| CSS `@keyframes` without `animation-play-state: paused` | Runs on its own | pause it; the player picks it up |
| `<video>` or GIFs | Play on their own clock | tracks, or seek the video from a compute |
| `Date.now()` in visible output | Different every viewing | pass the value in |
| Webfonts, remote images | The packed file must fetch nothing | system fonts, or embed them |

---

## Layout and quality

- Author at **1280x720**. The player scales the stage with a CSS transform, so it stays crisp at
  any window size and authored pixel positions stay true.
- Keep the grain overlay from the template. Large flat gradients band on cheap panels and in
  screenshots; the grain hides it for almost nothing.
- Design for **Georgia and Segoe UI**. Do not port sizes from a Poppins or Lora layout without
  retuning: Georgia runs wider and heavier, so display sizes come down and letter-spacing goes
  slightly negative.
- Text below about 15px at 1280 wide is hard to read once the stage is scaled down on a laptop.
- **No em dashes in visible copy.** Periods, commas, colons.

---

## Accessibility

- Keep the visually hidden transcript current. Scenes are transparent until their turn, so a
  screen reader needs the whole script in one readable block.
- Keep the `<noscript>` block factual: date, place, link.
- `prefers-reduced-motion` is handled by the player. Elements **settle at their final geometry**
  and only opacity changes, rather than the animated property being removed. That distinction
  matters: removing it would leave a `width: 0` bar invisible forever, which is a broken deck, not
  reduced motion.

---

## Workflow

1. Open the source in a browser. Edit, save, refresh.
2. Space to play, arrows to scrub, `f` for fullscreen. The controls are the preview.
3. `node build/test-player.mjs` after touching `player.js`. Instant, no browser.
4. `node build/pack.mjs src/my-deck.html dist/my-deck.html`
5. `node build/check.mjs dist/my-deck.html` — exit 0 means safe to send.
6. Open the **packed** file once before sending. Packing is where a deck stops matching its
   source, and it takes five seconds to rule out.

Steps 3 to 5 need Node 18+. `python scripts/nodecheck.py` says whether it is there,
and `reference/node-setup.md` holds what to do when it is not.
