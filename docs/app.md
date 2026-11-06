# The app, saved chats and traces

## The app (uses the OpenAI API)

```bash
python -m scripts.start           # Qdrant + Phoenix (Docker), wait until ready, then the app
                                  # (log live in the terminal; Ctrl+C: review of the session's chats)
python -m scripts.start --stop    # stop Qdrant and Phoenix (index and traces are kept)
streamlit run app.py              # only the app, if the services are already running
```

The app opens at http://localhost:8501.

Three tabs. **Chat**: the conversation with the assistant coach (follow-up questions work);
citations appear as badges with the card title, the cards of the answer can be read in full next
to it; when the coach writes the formations ("noi giochiamo 4-3-3, loro un 4-4-2 basso"), the answer
shows them on a pitch, drawn in the app's colours with the players running to their place (an
indicative layout, read from the question, not a fact of the cards); when the answer cites a coach's
card and writes the shape his team takes ("il 3-5-2 diventa 5-3-2 senza palla"), the players move from
one formation to the other (the change in the card's words, who goes where indicative); when the
answer cites a final as its real case, its timeline follows (goals and score, saves, red cards, changes, extra time and
penalties, each from the card's own words, with the teams' symbols: the flag of a national team, a neutral
shield with the initials for a club, as club crests and competition logos are trademarks); the numbers of a final the answer cites,
when the question names one of them (a bar per metric of the card's "Numeri" table, split between the two teams) and,
for the two finals with StatsBomb event data (2022
World Cup, Euro 2024), the action of a goal: the ball travelling through the passes at the real tempo,
every player named when he touches it (the goal its real-case line points to is shown, and a picker under
the answer lets the coach play any other goal of the final), and the map of the final's shots (each where it was taken, as
large as its xG, the goals labelled) when the question speaks of the shots; and every answer shows what the guardrails did and, under "Dettagli", its time, tokens,
cost and the searches the agent made. Several graphics under one answer go in tabs (the pitch, the change of shape, the timeline, the numbers, the
shots, the action of a goal), one is drawn as it is. The sidebar starts a new conversation, switches model and
guardrails (to show them at work), can hide the cards panel next to the chat (the chat then takes the whole
width). The panel says which question its cards answer, stays in view while the chat scrolls, and a button under
each answer chooses the answer it shows; the graphics are not wider than 460 to 680 px, so that a pitch fits
beside the answer on a laptop screen. The sidebar has example questions, each showing one thing the system does: a goal
animated under the advice (a comeback, wing play), the numbers and shots of a final, a coach's change of shape, the
answer in English, the honest "Non lo so", a contact hidden before the model and an attempt to change the
instructions stopped by the input guard.
**Schede**: the 31 cards by category; a final with its timeline, its numbers and the goals to play, a
coach with the change of shape his card writes. **Valutazione**: the measured results of the saved runs
(no API call). With Phoenix running, every question is also a trace.

## Saved chats and the log

Every conversation of the app is saved in `chats/`, one JSON Lines file per chat named after the
time it started (`2026-09-30_153012.jsonl`), one line per answer written as soon as it is given:
question, answer, consulted cards, searches, guardrails, time/tokens/cost, and the turns added to
the agent's memory (datapizza `Memory`, tool calls and results included, as the model saw them
while answering). The sidebar button
"⬇️ Scarica la chat" downloads the current one.

```bash
python -m scripts.review_chats            # the last chat, answer by answer (offline, no key)
python -m scripts.review_chats --all      # every saved chat
```

It runs the automatic checks of `eval_agent` on every saved answer, against the text of the cards
it consulted: citations only to consulted cards, names and numbers present in those cards or in
the coach's questions, tool use, answer language. An answer built on cards read earlier in the
same chat is checked against those cards, and a "Non lo so" is not flagged for citing nothing.
Each answer shows its tokens. In the chats saved before 2026-10-23 they grow turn after turn,
because the conversation memory kept the cards read before (from about 1,700 to 54,000 tokens in a
15-question chat; 8,300, 14,900, 18,400 and 22,300 in the first four turns of one chat); since then
the memory keeps only the questions and the answers, and a follow-up that needs the cards searches
again. Then the chat's totals (flagged answers, questions stopped, rewrites, time, tokens, cost).

What happens while chatting (app and CLI) is written to `logs/match_analyst.log`: new
conversation and its file, every question (its length, not its text), the input guard's verdict,
the searches with the cards found and their time, the output guard and the rewrite, every answer
with time, tokens and cost; warnings for stopped questions and discarded rewrites; errors with
their stack trace. `LOG_LEVEL=DEBUG` in `.env` also writes the search queries. The file is rotated
at 1 MB (5 old files kept). Both folders are git-ignored: they hold what the users typed.

A key or a contact written in a question (an OpenAI key pasted by mistake, an email, a phone number, an IBAN,
a tax code) is hidden before the question reaches the model, and again in the chat's file, in the traces and
in the log (`src/guardrails/redact.py`); the note under the answer says what was hidden. Names are not: nothing
tells a player's name from a coach's, so the app asks not to write the players' personal data.

```bash
python -m scripts.prune_chats             # the chats older than 30 days, listed (nothing deleted)
python -m scripts.prune_chats --delete    # delete them (--days N for another limit)
```

With `python -m scripts.start` everything is in one terminal: while the app is open the log lines
are printed there too (marked `[log]`), and Ctrl+C closes the app and prints the review of the
chats of that session (the same report as `scripts.review_chats`) with where the chats and the log
are.

## Tracing with Phoenix

`docker compose up -d` also starts [Arize Phoenix](http://localhost:6006). With Phoenix running,
the CLI and `eval_agent` turn every question into one trace: input guardrail, each agent step,
the searches with the chunks found (card id and score), every model call with its messages and
tokens, the output guardrail and the rewrite with the cards it was given. datapizza-ai emits
OpenTelemetry spans with its own attribute names; `src/observability/tracing.py` translates them
to the OpenInference names Phoenix reads. If Phoenix is not running, tracing is switched off and
the scripts say so; `eval_agent --no-trace` switches it off on purpose.
