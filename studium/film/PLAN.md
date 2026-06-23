# Film layer — the fourth commentary system

> Reading · handwriting · translation · **music** were the three commentary systems. **Film is the
> fourth.** A film that "relates" is not illustration — it is an independent account of the same FORCE
> (wrath, fate, grief, law …) meeting the work on its own terms. Often a film from anywhere (Vietnam,
> the Eastern Front, a samurai apocalypse) encodes a force more truthfully than any direct adaptation.

## The shape
- **One `studium/film/<work>.yaml` per work** (not per-division — film is a *weekly* medium; the protocol
  is deliberately finite). Each film: `title · director · year · force · divisions · objects · letterboxd ·
  scene_or_theme · object_lesson · why · content_note`. Every `force` is a key of
  [`../dominant-force.yaml`](../dominant-force.yaml); every `object` of [`object-taxonomy.yaml`](object-taxonomy.yaml).
  - **`object_lesson`** — the precise principle the film makes *visible* (the bridge to his
    [Object Lessons](object-lessons.md) project, objectlessons.film); **`objects`** — tracked cinematic objects
    (mirror/clock/gun/…); **`divisions`** — which book(s) it speaks to (so the daily face promotes the right pick).
- **`adaptations:`** (optional) — direct films OF the work (the *obvious* one, deliberately set aside; never
  promoted as Film of the Day), with `scenes: [{division, force, scene}]` tying a scene to its book/canto.
- **Gold standard:** [`iliad.yaml`](iliad.yaml) — 10 force-matched films + per-film object lessons + the set-aside *Troy* overlay.

## How it surfaces
- **Film of the Day** (`scripts/studium.py`): promotes **one** pick best-fitting TODAY (its `divisions` includes
  today's book → else the day's force), rendered as a headline **"🎬 Today's film — an object lesson in `<force>`"**
  block above the weekly companion. The literal adaptation is never promoted. See [`object-lessons.md`](object-lessons.md).
- **Daily face** card: lists the work's films, **highlights the day's-force ones**, marks any he has **seen**
  (Letterboxd), with legal watch links (**Letterboxd** + JustWatch + search — never a pirated source).
- **Letterboxd / Object Lessons bridge:** `scripts/studium-letterboxd.py` ingests his watch history →
  `scripts/studium-objectlessons.py` joins the day's pick to his 253-film `objectlessons.film` DB by Letterboxd slug.
- **Community** (`../community/`): the weekly **Watch-Along** ritual screens one film; `#screening-room` is its surface.
- **Rubric:** [`../rubric/film-engagement.md`](../rubric/film-engagement.md) — film as a fourth reading, diagnostic not gatekeeping.
- **Validator:** `python3 scripts/studium-validate.py --film` checks every `force` ∈ taxonomy.

## Register discipline (mirrors the music layer)
The grief / lament / mercy films (the women's lament, the enemy humanized) belong to a work's **late** movement —
its death/catastrophe divisions — exactly as the music layer reserves the funeral-march register. Note this in
each `principle` and let `scene_or_theme` point the film at the right division.

## Coverage — status (✓ = `film/<work>.yaml` authored)
| Work | Film companion |
| --- | :--: |
| The Iliad | ✓ (gold standard) |
| The Qur'an | ✓ |
| *all other first-pass works* | ☐ — staged in [`../expansion-backlog.yaml`](../expansion-backlog.yaml) (`film` pillar) |
| *Tier-2 works* | ☐ — staged (after the first pass) |

> Breadth (the remaining ~24 + 5 tier-2 companions) is fleet work on his gate, in the Iliad format — NOT
> ground out solo ([[token-economy-overrides-ultracode]]). Each task: tag the work's forces → pick films that
> meet each force's register → justify every choice → `studium-validate.py --film`.
