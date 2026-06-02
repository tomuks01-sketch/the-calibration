# Brief #007 — "The first call scored" (ready-to-execute template)

> **Location is deliberate:** this file lives at the repo root, NOT under `web/`,
> so GitHub Pages never serves it. It is a working template, not a published page.
> When the trigger fires, copy the skeleton below into
> `web/briefs/2026-MM-DD-007.html`, fill the `{{...}}` slots, then run the
> publish checklist. Do NOT publish a half-filled draft.

## TRIGGER (publish only when true)
The FIRST ledger resolution exists. Check:
```
python src/status.py          # "resolved" goes 0 -> 1+
# or:
python -c "import json;print([e for e in json.load(open('web/ledger.json'))['entries'] if e['status']=='RESOLVED'])"
```
A **crypto** forecast resolving first (web/crypto_ledger.json, status RESOLVED)
is also a valid #007 angle ("the first scored read") — pick whichever lands first.

## DATA TO PULL (from the resolved entry — never invent)
- `question` / `eventTitle`, `category`
- `modelProb` (QEST at call time), `crowdProbAtCallTime`
- `resolvedOutcome` (1 = YES happened, 0 = NO)
- `modelBrier`, `marketBrier`  → **model beat crowd IFF modelBrier < marketBrier**
- `openedAt` → `resolvedAt` (how long it was open)

## HONESTY RULES (non-negotiable — this brief is the moat in action)
1. **One resolved call proves NOTHING statistically.** Say so explicitly: the
   scoreboard stays "confidence: none" until ≥10 resolved. This is a data point,
   not a track record.
2. **If the model LOST to the crowd, LEAD WITH THAT.** The pledge is that wrong
   calls stay on the record, unedited. A first-loss brief is *more* credible than
   a first-win victory lap. No spin either way.
3. No advice, no edge claim, no "we told you so." Register = "here is a number we
   were held to, and here is how it scored."
4. Link the public Scoreboard so readers can audit.

## STRUCTURE (mirror #006; ~2 min read, 600–850 words)
- kicker: `Crowd Signal #007 · {{DD Mon 2026}} · 2 min read`
- h1: e.g. `The first call, <em>scored</em>` (or `The first call we got {{right|wrong}}`)
- standfirst: what resolved, the result in one breath, and the honest "one point, not a record" caveat.
- `1 · What resolved` — the market, the call, model% vs crowd% at call time, the outcome.
- `2 · How it scored` — modelBrier vs crowdBrier; beat-the-crowd or not, plainly.
- `3 · What it does and doesn't mean` — the N<10 caveat; the pledge restated.
- `4 · The board now` — open calls count + next expected resolutions.
- `5 · Scorecard` — continue the running #00X scorecard format.

## HTML SKELETON (copy to web/briefs/2026-MM-DD-007.html, fill {{...}})
```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>The Crowd Signal #007 — {{SHORT TITLE}}</title>
<meta name="description" content="{{1-2 sentence summary — the first scored call, won or lost, and what it means.}}" />
<link rel="stylesheet" href="../styles.css" />
  <link rel="icon" href="/the-calibration/favicon.svg" type="image/svg+xml" />
  <link rel="canonical" href="https://tomuks01-sketch.github.io/the-calibration/briefs/2026-MM-DD-007.html" />
  <meta name="robots" content="index, follow" />
  <meta property="og:site_name" content="The Calibration" />
  <meta property="og:type" content="article" />
  <meta property="og:title" content="The Crowd Signal #007 — {{SHORT TITLE}}" />
  <meta property="og:description" content="{{summary}}" />
  <meta property="og:url" content="https://tomuks01-sketch.github.io/the-calibration/briefs/2026-MM-DD-007.html" />
  <meta property="og:image" content="https://tomuks01-sketch.github.io/the-calibration/og-image.png" />
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="The Crowd Signal #007 — {{SHORT TITLE}}" />
  <meta name="twitter:description" content="{{summary}}" />
  <meta name="twitter:image" content="https://tomuks01-sketch.github.io/the-calibration/og-image.png" />
  <script type="application/ld+json">{"@context":"https://schema.org","@type":"Article","headline":"The Crowd Signal #007 — {{SHORT TITLE}}","datePublished":"2026-MM-DD","author":{"@type":"Organization","name":"The Calibration"},"publisher":{"@type":"Organization","name":"The Calibration"},"mainEntityOfPage":"https://tomuks01-sketch.github.io/the-calibration/briefs/2026-MM-DD-007.html"}</script>
</head>
<body>
<header class="rail">
  <a class="wm" href="../">THE&nbsp;<span>CALIBRATION</span></a>
  <div class="meta"><span class="state"><span class="dotlive"></span>DELAYED</span></div>
  <nav>
    <a href="../">Terminal</a>
    <a href="./" aria-current="page">Briefs</a>
    <a href="../scoreboard/">Scoreboard</a>
  </nav>
</header>

<article class="brief">
  <a class="back" href="./">← The Crowd Signal · archive</a>
  <p class="kicker">Crowd Signal #007 · {{DD Mon 2026}} · 2 min read</p>
  <h1>{{HEADLINE with <em>emphasis</em>}}</h1>
  <p class="standfirst">{{What resolved, the result, and the "one point, not a record" caveat.}}</p>

  <h2>1 · What resolved</h2>
  <p>{{Market + the call: QEST read {{X}}% vs the crowd's {{Y}}% at call time, opened {{date}}. It resolved {{YES|NO}}.}}</p>

  <h2>2 · How it scored</h2>
  <p>{{modelBrier {{m}} vs crowdBrier {{c}} — the model {{beat|did not beat}} the crowd on this one call. State it plainly, no spin.}}</p>

  <h2>3 · What it does — and doesn't — mean</h2>
  <p>{{One resolved call is a data point, not a track record. The scoreboard stays "confidence: none" until ≥10 resolved. The pledge: this result stays on the record forever, win or lose.}}</p>

  <h2>4 · The board now</h2>
  <p>{{N open calls; next expected resolutions.}}</p>

  <h2>5 · Scorecard</h2>
  <p>{{Continue running scorecard.}}</p>

  <nav class="brief-nav">
    <a href="2026-05-30-006.html">← #006</a>
    <span></span>
  </nav>
</article>

<script src="../briefs.js"></script>
</body>
</html>
```
(Check #006's actual footer/nav + script tags and match them exactly — copy from
`web/briefs/2026-05-30-006.html` so prev/next + reading-time behave.)

## PUBLISH CHECKLIST (same commit — the single staleness list)
1. `web/briefs/2026-MM-DD-007.html` — the new page (filled, reviewed).
2. `web/briefs/latest.json` — title / standfirst / date / url (homepage hero reads it).
3. `web/sitemap.xml` — add `<url>` + bump `lastmod`.
4. `web/index.html` — "Recent briefs" list (top 3).
5. `web/briefs/index.html` — archive list.
6. `web/feed.xml` — new `<item>` at top + bump `<lastBuildDate>`.
7. `web/briefs/2026-05-30-006.html` — add a "next → #007" link in its `.brief-nav`.

## WORKFLOW (per memory standing rules)
fresh snapshot → write from REAL resolved data → independent honesty review
(silent-failure-hunter) → fix → deploy (rebase-safe) → update memory.
