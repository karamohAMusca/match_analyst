# Security and privacy

## Attacks and defences (the red team)

`eval/red_team.json` is a fixed set of 13 attacks, each with its vector (where the poison comes in), its target and
its channel: a direct injection in Italian and English, a role change, an oversized question, the system prompt asked
for inside a football question, a note hidden in a pasted article, a request for an image or a link to an outside
address, HTML in the answer, a path passed to a tool, a mixed off-topic request; and three normal questions as
controls (a defence that breaks the task went too far). It is frozen like the gold set.

```bash
python -m scripts.red_team                         # offline, free: the input guard on each attack, the output handling and the page on a hijacked answer
python -m scripts.red_team --live                  # + the model: every attack through the bare agent (before) and the guarded one (after)
python -m scripts.red_team --compare <a> <b>       # the same attacks in two saved runs: what was fixed, what regressed
```

The defences are one per hop, and deterministic where they can be: the input guard (injection, off topic, length),
the output handling (no external link or image in an answer, `src/guardrails/links.py`, also applied by the page),
the page (the text of the model is shown escaped), the output guard on the system prompt (an answer that repeats
the instructions is replaced by a refusal, `src/guardrails/prompt_leak.py`), least privilege (the tools only search
and read the cards: no file, no email, no network; an id is looked up among the cards, so `../../.env` reads nothing),
the corpus and the tool definitions as data (`src/guardrails/corpus_scan.py`, a fingerprint on the MCP tools). The
barriers that the set does not try with a hijacked answer are tried offline by a probe (the system prompt as an
answer, file paths given to both card tools). What no deterministic barrier stops (the model must refuse a note
hidden in a pasted text, a mixed request) is reported as a residual risk: 3 attacks of 13. A leak translated or
paraphrased has no words of the original and is not caught either.

**The lethal trifecta.** An exfiltration needs three things together: untrusted input, access to private data and a
channel to the outside. The offline report checks them from the tools that actually exist (the agent's and the
MCP server's, read from `tools/list`): untrusted input is always there (the coach's question, a pasted text, cards
derived from Wikipedia); private data is not, because the card tools read no file; an external channel is not,
because every tool is read-only and the answer holds no link. So 1 of 3. The tools are an allowlist
(`AGENT_TOOLS`, `MCP_TOOLS` in `src/evaluation/red_team.py`): a tool not in it counts as both private data and an
external channel until it is reviewed, and the command fails when all three are present. No human approval gate is
needed for the same reason: the agent has no action to approve, it sends, writes and changes nothing.

Measured (2026-11-06, gpt-4o-mini, run `red_team_20261106-151005`): of the 13 attacks, 4 are stopped by the input guard
and 9 reach the model. The bare agent obeys 2 of those 9, the image and the link to an outside address, and the output
handling removes both: with the guardrails none reaches the coach, and the 3 control questions are still answered with
their sources. The other 7 were not obeyed by the model in this run ("Non lo so" or plain football advice): that is the
residual risk, which this run shows but does not guarantee, since a prompt injection is mitigated, not eliminated.
After this run the two leaks and the file path got a deterministic barrier (the output guard on the system prompt, the
offline probe of the card tools), and the HTML already had one (the page escapes it): the residual risk is now the two
notes hidden in a pasted article and the mixed request.

## Data and privacy

The three questions a customer asks before anything else, answered for this project. What follows is a
technical description and a working hypothesis, not legal advice: the questions at the end are for a lawyer.

### Where the data goes

| Where | What goes there | Who keeps it |
|---|---|---|
| OpenAI API (`gpt-4o-mini`, `text-embedding-3-small`) | the coach's question (keys, emails, phone numbers, IBANs and tax codes hidden first), the earlier questions and answers of the chat, the passages of the cards found, the system prompt; the search queries for their embeddings | OpenAI, under its API terms (at the time of writing: not used for training by default, kept up to 30 days for abuse monitoring; check the current terms) |
| `chats/` (this computer, git-ignored) | every question and answer, the searches, the guardrails' report, time, tokens and cost (redacted as above) | the user: `python -m scripts.prune_chats --delete` removes the chats older than 30 days |
| `logs/match_analyst.log` (this computer, git-ignored) | events: the length of a question (not its text), verdicts, cards found, times, costs | the user, rotated at 1 MB (5 old files) |
| Phoenix (Docker on this computer, volume `phoenix_data`) | the traces: the question and the answer (redacted), the searches and the passages found | the user, until the volume is deleted (`docker compose down -v`, which deletes the index too) |
| Qdrant (Docker on this computer) | the cards and their vectors only: nothing the coach writes | — |
| MCP server | serves the cards; keeps nothing | — |
| The browser | the page loads its fonts from Google Fonts (the address of the computer reaches Google); Streamlit's usage statistics are off (`.streamlit/config.toml`) | Google, for the fonts |

Nothing is sent anywhere else: the answer can hold no external link or image (`src/guardrails/links.py`), so the
page fetches nothing the model wrote.

### Is it safe?

Measured, not claimed: a fixed set of 13 attacks run before and after the defences (see *Attacks and defences*
above). With the guardrails none reached the coach; 3 have no deterministic barrier and stay a residual risk. The
agent can only search and read the cards: no file, no email, no network, nothing it can change. Not done, and
needed before the app is put online: authentication, a limit of questions and spending per user (today a
question costs about 0.001 $, but nothing stops a loop of them), HTTPS.

### Can you show who decided what?

Every answer saved in `chats/` and every run in `eval/runs/` (agent, gold, red team) carries its `build`
(`src/core/build_info.py`): the commit and whether the working copy had changes not committed, a fingerprint of
the prompts, of the guardrails' code and of the corpus manifest, the model, the verifier, the guardrails on or off,
the chat memory. A measured result speaks only for the configuration that produced it: when a prompt or a guardrail
changes, the fingerprint says so, and the old evidence is no longer taken for the new system. The runs saved before
2026-11-06 have no `build`: their configuration is the one written in `eval/runs/README.md`. Inside an answer, the
guardrails' report says what the code changed and why, and the trace in Phoenix has every step.

### Classification of the system

| Question | Answer |
|---|---|
| Where is it used? | Football clubs and coaches, amateur and youth teams; to prepare a match or decide in a game situation |
| What can it do? | Suggest and explain, with cited sources. It decides nothing and acts on nothing: the coach chooses |
| Who is involved? | The coach who asks; indirectly the players the coach writes about |
| Who builds it, who uses it? | Built by the project (the provider, in AI Act terms); used by the club or the coach (the deployer) |
| What evidence can it give? | The cards cited in each answer, the guardrails' report, the saved chats, the traces, the gold runs and the red team runs in `eval/runs/`; each answer and each run with the version it was made with |
| What stays under human control? | Every decision: the answer is advice to read, and says "Non lo so" when the cards do not cover the question |

**AI Act, working hypothesis.** Not a prohibited practice (art. 5), and not in the high-risk list of Annex III:
it advises on tactics, not on people. It would come close to it if it were used to evaluate players or decide on
their contracts (Annex III, point 4, employment and the management of workers): that is outside its purpose and
the cards do not support it. So: minimal risk, with the transparency obligation of art. 50(1), since a person
talks to it. The app says so in the sidebar, always on screen: the answers are written by an AI model from the
cited cards, the questions go to OpenAI and are saved on the computer. A club that uses it has to make sure its
staff knows how to use it (art. 4, AI literacy).

**GDPR.** The project needs no personal data, but a coach may write some: a player's name, an injury (health
data, a special category, art. 9). The app asks not to; nothing filters names, so it is the deployer's
responsibility to say so to its staff.

**Questions for a lawyer before a real deployment.** Who is the controller of the questions saved in `chats/`
and in the traces, and on what legal basis? Is a data processing agreement with OpenAI in place, and does the
transfer outside the EU have its safeguards? How long are chats and traces kept, and who can read them? Does any
club use it to evaluate players, which would move it towards Annex III?
