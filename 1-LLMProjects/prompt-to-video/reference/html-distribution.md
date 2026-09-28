# Getting it to people

The deliverable is an HTML file. That is unusual enough that how it travels deserves its own
page, because most of the ways it can go wrong are logistical rather than technical.

---

## The one guarantee

`build/check.mjs` exiting 0 means the file references **nothing** outside itself. No CDN, no
sibling files, no network. It renders identically on a plane, behind a corporate proxy, on a
machine with fonts.googleapis.com blocked, and in five years when whatever CDN you would have
used has moved on.

Run it before sending anything. It is the whole basis of the promise.

---

## Routes, ranked by how well they actually work

### SharePoint or OneDrive, shared as a link — best

Upload the file, share the link. Colleagues click and it opens.

One caveat worth knowing: **SharePoint may download the file rather than render it in the
browser**, depending on how the tenant is configured. Downloading is not a failure. The file
still opens correctly by double-clicking, and because it is self-contained it works fine from the
Downloads folder. But it is a worse first impression than an inline render, so test the exact link
you intend to send before you send it widely.

### Embedded in a page with an iframe — best for a site

```html
<iframe src="my-deck.html?embed=1"
        style="width:100%;aspect-ratio:16/9;border:0"
        title="A short explainer" allowfullscreen></iframe>
```

`?embed=1` turns on autoplay and looping and hides the controls, which is what you want inside
someone else's page. The stage scales to whatever the iframe gives it.

### A screen at the event — very good

Open it fullscreen with `?loop=1&controls=0`, press `f`, walk away. It repeats until the laptop
sleeps. Turn off the screensaver.

This is the case where HTML beats video outright: no player software, no codec, no file that has
to be copied to the right machine.

### Email attachment — expect friction

**Many corporate mail gateways strip or quarantine `.html` attachments**, because HTML
attachments are a classic phishing vector. This is not a Client quirk, it is standard practice, and
it is the single most likely way this deliverable fails to arrive.

If you must email it:

- Zip it first. This usually survives, though some gateways also inspect inside zips.
- Better: send a link to it on SharePoint and skip the attachment entirely.
- Test by sending it to yourself first, and to one person outside your immediate team.

### Teams, LinkedIn, PowerPoint — will not work

None of these accept an HTML file as playable content. If the piece needs to go to any of them,
**you need the mp4**, which is what `../poc-html` produces from the same deck.

---

## Size

| Contents | Typical | Notes |
|---|---|---|
| Silent deck | 40 to 80 KB | Nothing to think about. |
| With 30s of narration | 300 to 600 KB | Fine everywhere. |
| With 2 minutes of narration | 1.5 to 3 MB | Still fine, but compress the audio properly. |
| With photographs | anything | Resize before inlining. A 4 MB camera JPEG becomes 5.3 MB of base64. |

Base64 costs about 33 per cent over the raw bytes, and it does not compress well afterwards. If
you are inlining a photo, resize it to the size it will actually display at and export at quality
80. `check.mjs` warns above 5 MB and again above 10 MB, where mail gateways start refusing.

---

## Fonts

A self-contained file cannot fetch a webfont, so the deck is designed for what is already on the
machine: **Georgia** for display and **Segoe UI** on Windows, San Francisco on macOS, via
`system-ui`. Type sizes and letter-spacing in the sample are tuned for Georgia specifically, not
inherited from a design that assumed something else.

To use a real webfont, embed it:

1. Get the `.woff2`. Check the licence permits embedding and redistribution. SIL Open Font
   License fonts are fine; many commercial licences are not, and a self-contained HTML file is
   redistribution.
2. Put it beside the deck and reference it normally:

```css
@font-face {
  font-family: 'Your Font';
  src: url('yourfont.woff2') format('woff2');
  font-weight: 400;
  font-display: block;   /* not swap: a font swap mid-animation looks like a bug */
}
```

3. `pack.mjs` turns that `url()` into a data URL automatically.

Budget 20 to 40 KB per weight. Two weights is usually enough. Subsetting to the characters the
deck actually uses cuts it further, and matters more than it sounds when the file is also carrying
audio.

---

## Accessibility

The deck's copy is real DOM text, not pixels, so a screen reader can read it. Three things the
sample does that are worth keeping:

- **A visually hidden transcript** carrying the whole script as continuous prose. Scenes are
  transparent until their turn, so without this a screen reader gets a disjointed reading. Update
  it when you change the copy.
- **A `<noscript>` block** with the essential facts, so a JS-off viewer still gets the date, the
  place and the link.
- **`prefers-reduced-motion` is honoured.** Scenes still change on schedule and things still
  fade, but nothing slides, scales or grows. Note the implementation detail: elements settle at
  their *final* geometry rather than having the animated property removed, because removing it
  would leave, say, a `width: 0` bar invisible forever.

If the deck carries narration, provide the script as text somewhere too. Audio alone is not
accessible.

---

## Editing it later

Edit `src/`, then re-pack. **Never edit a file in `dist/`**: it is generated, it has a 30 KB blob
of inlined JavaScript in the middle, and your change will be overwritten by the next build. The
banner at the top of every packed file says so.

If someone sends you back a packed file with edits, the copy in it is still readable text. Port
the changes to the source by hand rather than trying to keep working from the packed one.

---

## Compared with the mp4 route

| | This (`poc-html-nomp4`) | mp4 (`../poc-html`) |
|---|---|---|
| Deliverable | one .html | one .mp4 |
| Viewer needs | a browser | anything |
| Build step | pack, about a second | render + encode, minutes |
| Goes in Teams / LinkedIn / PowerPoint | no | yes |
| Emails cleanly | often blocked | yes |
| Loops on a screen | trivially | needs a player |
| Editing one line of copy | edit text, re-pack | re-render the affected frames |
| Sound on autoplay | blocked, unmute button | same policy in any web player |
| Looks identical everywhere | no, fonts and rendering vary slightly | yes, pixels are fixed |

That last row is the real trade. A video is the same pixels on every machine. An HTML file is
re-rendered by each browser, so a headline can wrap one word differently on a Mac. For a promo
teaser that is nothing. For something where exact layout is contractual, render the video.

**The two are not exclusive.** The deck schema is shared, so the same source can produce both:
ship the HTML for the intranet and the screen at the event, render the mp4 for Teams.
