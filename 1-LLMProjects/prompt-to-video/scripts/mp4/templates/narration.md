# Narration template

Copy this next to your driver script and replace the content. The parser reads
exactly one line shape and ignores everything else, including this preamble.

## The contract

```
## <index> - <Title> - ~<seconds>s
```

Headings must be numbered **1..N in file order**. Playback follows file order,
but the scene counter and the `audio/NN.mp3` lookup follow the heading number,
so the two have to agree or the build refuses.

Under each heading: the narration as prose, and one `*Screen:*` line saying what
must be visible while those words are spoken. Every other line is joined with
spaces and becomes the text sent to speech synthesis. The `*Screen:*` line never
reaches the screen or the voice; it is your contract with the renderer.

## House rules

- Budget at roughly **2.2 words per second**. Above 2.5 the take will overrun,
  and an over-budget take stops the build rather than shifting every scene after
  it. Check with `tts_narrate.py --project . --dry-run`, which needs no key
  and no network.
- **No em dashes in visible copy.** Periods, commas, colons.
- Sentence case for body copy.
- Every figure on screen traces to the source document. If the source flags a
  number as unattributed, leave it out.

The three scenes below total 30 seconds and exist to show the shape. Delete
them.

---

## 1 - Title - ~8s

The opening line, spoken as a person would say it. Short enough to land before
the title card has finished settling.

*Screen:* Title card. Headline, accent rule, one line of subtitle.

---

## 2 - The substance - ~14s

The middle of the piece, where the actual point goes. At about two and a fifth
words per second, fourteen seconds is roughly thirty words, so this is a
paragraph and not an essay. Say one thing.

*Screen:* The claim, with whatever number supports it counting up beside it.

---

## 3 - Close - ~8s

The line you want them to leave with. End on the point, not on a summary of the
points.

*Screen:* Closing card. One sentence, held still.
