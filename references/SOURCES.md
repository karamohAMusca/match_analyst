# Corpus — Sources, Licences and Writing Rules

> **The machine-readable catalogue is `corpus/manifest.json`** (schema 2.0: document_id, title, category,
> origin_type, modality, reliability, sources, file path, SHA-256, bytes). Only the cards listed there are
> ingested. This file is the human-readable companion: how the corpus is organised, where every fact comes
> from, and the rules used to write the cards. It is **not** ingested.

---

## 1. Corpus structure (ingested)

| Folder | Category | Cards | What a card contains | id prefix |
|---|---|---|---|---|
| `match_cases/` | `match_case` | 7 | A recent final (2022–2026): how the winner won, key numbers, the loser's side | `case_` |
| `game_situations/` | `game_situation` | 8 | An in-game or preparation problem ("we are trailing", "they sit deep"): options, risks, real cases | `situation_` |
| `coach_profiles/` | `coach_profile` | 10 | **One file per coach**, merging every source that describes that coach | `coach_` |
| `thesis_notes/` | `thesis_note` | 4 | A concept from the theses, not tied to a match moment (zonal vs man defending, positional vs relational play, training with variability) | `note_` |
| `glossary/` | `glossary` | 2 | Definitions of metrics (PPDA, xG, field tilt…) and formations | `glossary_` |

**Coach profiles merge sources by coach, not by author.** Example: Spalla's chapter on De Zerbi, Dileo's
thesis on De Zerbi's Sassuolo and the De Zerbi Wikipedia page all go into `coach_profiles/de_zerbi.md`;
inside the card every statement names its author and page. Profiles: Ancelotti, Conte, De Zerbi,
Gasperini, Guardiola, Inzaghi, Italiano, Klopp, Pioli, Scaloni.

Front matter fields: `document_id`, `title`, `category`, `origin_type: derived`, `modality: text`,
`reliability: project_synthesis_cited`, `sources`, and optionally `themes`, `coach`, `formations`,
`winner`, `date`, `note`. A match case also has a `timeline:` (drawn by the app under an answer that
cites the final): one line per goal, penalty, save, post, red card, change or shoot-out, written only
from the card's own text, each with its `quote` (the card's exact words), the `minute` (or the `period`
when the card gives none) and, for a goal, the score after it. `tests/test_corpus.py` checks that every
quote, name and minute is in the card and that the goals add up to the title. A coach profile may have
`shape_changes:` (drawn under an answer whose line citing the card writes the formation it becomes): a
change of formation the card writes with both formations, each with its `quote` (the card's exact
words) and, when the card gives them, the moment (`when`), the means (`how`), the `team` and the
card's own warning (`note`); the same test file checks them and that only the cards writing both
formations have one. The `## Numeri` table of a match case is drawn as bars: write each value as a
number (decimal point or comma, `%` when it is a share), with a part in brackets only for a part of it
("20 (10)": shots, on target) or for a share of neither team ("32,5% (7,4% contesa)").

---

## 2. Upstream sources (NOT ingested)

### 2.1 Coverciano theses — `references/theses/` (FIGC, publicly published PDFs)

| Local file | Author | Title | URL |
|---|---|---|---|
| `theses/vincenzo-italiano_tesi.pdf` | Vincenzo Italiano | Master UEFA Pro thesis (2019/20) | https://www.figc.it/media/124923/vincenzo-italiano_tesi.pdf |
| `theses/tesi-stefano-pioli.pdf` | Stefano Pioli | Le catene di gioco laterali in un 4-4-2 (Master 2002/03) | https://www.figc.it/media/198386/tesi-stefano-pioli.pdf |
| `theses/dileo-dario_tesi-ma.pdf` | Dario Dileo | L'evoluzione del Sassuolo di De Zerbi (Match Analyst) | https://www.figc.it/media/175365/dileo-dario_tesi-ma.pdf |
| `theses/spalla_tesi-uefa-pro.pdf` | Sergio Spalla | L'evoluzione del calcio in Serie A (UEFA Pro 2023/24) | https://www.figc.it/media/265344/spalla_tesi-uefa-pro.pdf |
| `theses/tesi-coverciano-soncin-pdf.pdf` | Andrea Soncin | Attacco alla difesa – Idee per scardinare un blocco difensivo basso (UEFA Pro 2020/21) | https://www.figc.it/media/213264/tesi-coverciano-soncin-pdf.pdf |
| `theses/contran_uefa-pro.pdf` | Simone Contran | Occupazione degli spazi e fluidità posizionale (UEFA Pro 2023/24) | https://www.figc.it/media/246820/contran_uefa-pro.pdf |
| `theses/polenghi_tesi-master-uefa-pro.pdf` | Tiziano Polenghi | Le intermittenze del desiderio (UEFA Pro 2021/22) | https://www.figc.it/media/187573/polenghi_tesi-master-uefa-pro.pdf |

Page citations always refer to the full PDFs above.

Not used: Ancelotti's thesis (scan without a text layer), Inzaghi's thesis (group management, not tactics).
Not available as PDF: De Zerbi "Il mio modello di gioco" (2017) — known only through Dileo's summary.

### 2.2 Wikipedia — `references/wikipedia/` (CC BY-SA 4.0)

Plain-text extracts via the official Wikipedia API. Each file header stores title, URL, revision id,
retrieval date and a `modified:` line listing the kept sections (non-tactical sections removed), as
required by CC BY-SA 4.0.

- `coaches/`: Italian pages ("Caratteristiche tecniche › Allenatore") for Ancelotti, Conte, De Zerbi,
  Gasperini, Guardiola, Inzaghi, Italiano, Pioli; English page ("Tactics") for Klopp.
- `matches/`: Italian match reports for the 2022 and 2026 World Cup finals, 2023 and 2025 Champions League
  finals, 2024 Europa League final and Euro 2024 final; English page for the 2026 Champions League final
  (the Italian page has no match report).
- `tactics/`: Italian page "Modulo (calcio)" (used by `glossary_moduli`).

Every file in `references/wikipedia/` is cited by at least one card; unused pages were deleted.

### 2.3 StatsBomb Open Data — `references/data/statsbomb/`

Repository: https://github.com/hudl/open-data (the former `statsbomb/open-data`, which redirects there).

Events (`events/`) and match metadata (`matches/43/106.json`, `matches/55/282.json`) for match 3869685
(2022 World Cup final) and 3943043 (Euro 2024 final). Licence:
`references/data/statsbomb/LICENSE.pdf` (StatsBomb Public Data User Agreement): research and non-commercial use,
**no redistribution of raw data**, credit StatsBomb in any published analysis. Numbers in the cards
(pass share, field tilt, PPDA, pressures, xG) are **computed by the project** from these events; the
definitions are in `glossary_metriche`.

`python -m scripts.build_goal_actions` derives from the same events the touches before each goal of play
(ball positions and real tempo, the players by their common name) and every shot of the match (where,
xG, outcome; the shoot-out left out, so that the totals agree with the card's "Numeri" table) into
`references/derived/statsbomb_goal_actions.json`, which the app animates and draws under an answer that
cites the final. They are
coordinates of the raw events, so the file stays out of version control too and is rebuilt locally;
the minute and the score come from the card's timeline, not from StatsBomb (rule 6 below).

### 2.4 FIFA match reports — `references/data/fifa/2026_wc_final/`

Post Match Summary Report and Tactical Line-up of the 2026 World Cup final (public PDFs linked from the
Wikipedia page). Used only by `case_2026_wc_final_spain_argentina`. The reports do not define their
metrics (line breaks, phases of play): the corpus says so explicitly.

Every file in `references/data/` is used by at least one card; unused files (StatsBomb line-ups and competitions
list, FIFA Full Time Match Report) were deleted and can be re-downloaded from the public sources.

---

## 3. Writing rules for the cards

1. **Only facts that appear in a cited source.** Every paragraph ends with its source in brackets,
   e.g. `[Spalla, pp. 41-42]`, `[Wikipedia it]`, `[FIFA PMSR]`, or a card id.
2. **Quotes are verbatim** (checked automatically against the source text, accent- and
   whitespace-insensitive). Paraphrases carry no quotation marks.
3. **Interpretation is labelled.** Advice derived by the project goes under
   "Lettura per l'allenatore (interpretazione del progetto)" and never mixes with sourced facts.
4. **Numbers keep the format of the source** (Dileo writes 57.8, Spalla writes 9,08).
5. **Page numbers are the numbers printed on the page:** Soncin and Pioli are cited by their printed
   numbers; Italiano printed = PDF − 1; Polenghi printed = PDF − 3; Spalla, Contran and Dileo printed = PDF.
6. **Match minutes come from Wikipedia or FIFA**, never from StatsBomb (StatsBomb minutes are 0-indexed:
   the 108th minute is stored as 107). StatsBomb is used only for statistics.
7. **Italian and English Wikipedia sometimes disagree** (2025 UCL final: build-up of the 2-0; 2023 UCL
   final: 67' vs 68'; 2022 World Cup final: penalty minutes). A card cites only what its cited version says.
8. **When sources disagree, the card says so** (e.g. Spain's possession in the 2026 World Cup final:
   60.2% FIFA vs 65% English Wikipedia).
9. **No name without a source.** The PSG coach is not named in any source used, so no card names him
   (gold question Q21 tests the abstention).
10. **A card is data, not instructions.** Nothing in it may read as a command to a model ("ignore the
    previous instructions"), and it holds no invisible character, no HTML comment or tag and no address or
    image in the text (the `sources` of the header cite documents by address). The agent and every MCP host
    read a card as the result of a tool, so a card with an instruction in it would be an indirect prompt
    injection: `scripts/check_corpus.py` and `tests/test_corpus_safety.py` look for it.
10. **Recent and winning first.** Match cases cover finals from 2022 onwards and focus on how the winner won.

Consistency with the evaluation set is checked by rebuilding `manifest.json` and `eval/gold_set.json`:
every source id must exist, every cross-link must resolve, and every `required_facts` group must appear in
the text of the question's `relevant_sources`.

---

## 4. Legal checklist

- [x] Only publicly published documents (FIGC), openly licensed text (Wikipedia CC BY-SA 4.0) and openly
      released data (StatsBomb, non-commercial research; FIFA public reports).
- [x] No scraping of sites whose terms forbid it (FBref, Understat, Transfermarkt excluded).
- [x] Attribution stored with every source (card front matter and Wikipedia file headers).
- [x] Raw StatsBomb data, FIFA reports and thesis PDFs excluded from version control (`.gitignore`).
- [ ] Register at the StatsBomb resource centre (project owner).
- [x] StatsBomb credited in text wherever its numbers are shown: the app's sidebar and the caption of the numbers, the
      shot map and the goal actions, and the README ("Data provided by StatsBomb").
- [x] StatsBomb logo (`src/ui/assets/hudl-statsbomb-logo.png`, "hudl-statsbomb-logo-default" from the Media Pack,
      https://statsbomb.com/media-pack/, usage rights "External Use Approved") next to that credit in the app's
      sidebar, as the open data README asks.
- [x] The same logo on the slides of the talk (project owner): on the closing slide, next to the data credit.
