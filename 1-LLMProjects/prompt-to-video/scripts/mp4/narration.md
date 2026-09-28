# Narration script: "Five jobs, five toolchains"

Narration is written first. Each scene carries a time budget in seconds. The
animation is then built to the budget, not the other way round. This is the
method inherited from the Cornerstone build, and it is the one part of that
work that is tool-agnostic.

`Screen:` lines state what must be visible while the sentence is spoken. They
exist to catch mismatches before anything is rendered.

Budgets are set at roughly 2.2 words per second, which is a comfortable
narration pace. Check with `python3 ../sound/tts_narrate.py --project . --dry-run` before
generating audio: anything much above 2.5 words per second will not be readable
in the time allowed, and the build will refuse the take rather than let it push
everything after it out of sync.

House rules in force: no em dashes in visible copy, 1920x1080 at 30fps,
sentence case for body copy.

---

## 1 - Title - ~7s

Five jobs, five toolchains. A field guide to making video without wasting a month on it.

*Screen:* Title card. Product name, subtitle, accent rule.

---

## 2 - The problem - ~14s

Make an AI video is not one task. It describes five different jobs, each with its own tools and its own failure mode. Most wasted effort here comes from treating them as one thing.

*Screen:* The phrase "make an AI video" centred, then fracturing into five labelled fragments.

---

## 3 - The five jobs - ~17s

A person explaining a policy. Footage from a text prompt. Narration for anything. A recording of a real product. And purpose built animation for software that cannot be filmed because it does not exist yet.

*Screen:* Five rows revealing in sequence, each with an index number and a one line descriptor.

---

## 4 - The decision rule - ~14s

So the rule is short. If a person can say it, buy a presenter tool. If a screen can show it, record the screen. Only build when there is nothing to film.

*Screen:* Three-row decision table. Buy, record, build. The build row highlighted with its cost multiple.

---

## 5 - Where quality actually goes wrong - ~13s

None of that is the hard part. Retention drops against flat synthetic narration, and viewers tend to trust everything or nothing. One off-key moment writes off the whole asset.

*Screen:* Single large statement, quiet supporting line beneath.

---

## 6 - End card - ~7s

Identify the job first. The tool list will be stale in six months. The judgement will not.

*Screen:* End card. Closing line, practice byline.
