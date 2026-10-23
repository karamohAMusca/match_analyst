"""Match Analyst — Streamlit front end.

    streamlit run app.py

Three tabs: the chat with the assistant coach (conversation memory, citations as badges, the
cards of every answer next to it, what the guardrails did, time and cost of each answer), the
31 cards of the knowledge base, and the measured results of the saved evaluation runs.
The page only renders: the agent and the numbers come from src/ui/backend.py, the formatting
from src/ui/view.py. Needs Qdrant running (docker compose up -d), the index built and
OPENAI_API_KEY in .env; with Phoenix running, every question is also a trace. Every chat is saved
in chats/, and what happens while chatting is written to logs/match_analyst.log.
"""

import logging
import os

os.environ.setdefault("DATAPIZZA_AGENT_LOG_LEVEL", "WARNING")   # no agent log panels in the terminal

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from src.core.config import PROJECT_ROOT, load_settings  # noqa: E402
from src.observability.logs import setup_logging  # noqa: E402
from src.ui import backend, graphics, view  # noqa: E402

RUNS_DIR = PROJECT_ROOT / "eval" / "runs"
logger = logging.getLogger("src.app")   # under "src": written to the project's log

st.set_page_config(page_title="Match Analyst", page_icon="⚽", layout="wide")
st.markdown(view.CSS, unsafe_allow_html=True)


@st.cache_resource(show_spinner=False)
def get_logging() -> None:
    settings = load_settings()
    setup_logging(settings.log_level, console=settings.log_console)
    logger.info("app started")


@st.cache_resource(show_spinner="Carico l'indice delle schede…")
def get_retriever():
    return backend.build_retriever()


@st.cache_resource(show_spinner=False)
def get_tracing() -> str:
    return backend.start_tracing()


@st.cache_data(show_spinner=False)
def get_cards() -> dict:
    return view.load_card_index()


def show_card(card: dict, height: int, number: int | None = None) -> None:
    st.markdown(view.card_header_html(card, number), unsafe_allow_html=True)
    if timeline := graphics.timeline_svg(card, animate=False):   # a final: its timeline, from the card
        st.markdown(timeline, unsafe_allow_html=True)
    if numbers := graphics.numbers_svg(card, animate=False):   # a final with a "Numeri" table: its numbers
        st.markdown(numbers, unsafe_allow_html=True)
    if shots := graphics.match_shots().get(card["id"]):   # a final with StatsBomb data: its shots
        st.markdown(graphics.shots_svg(shots, card, animate=False), unsafe_allow_html=True)
    for change in card.get("shape_changes") or []:   # a coach's changes of shape, from the card
        st.markdown(graphics.shape_svg(card, change, animate=False), unsafe_allow_html=True)
    if goals := graphics.goal_actions().get(card["id"]):   # a final with StatsBomb data: the action of a goal
        longest = goals.index(graphics.pick_goal(goals, ""))
        pick = st.segmented_control("L'azione di un gol (StatsBomb)", list(range(len(goals))), default=longest,
                                    format_func=lambda i: graphics.goal_label(goals[i]), key=f"goal_{card['id']}_{height}")
        if pick is not None:
            st.markdown(graphics.goal_svg(goals[pick], card), unsafe_allow_html=True)
    with st.container(height=height):
        st.markdown(view.card_body(card))
    with st.expander(f"📚 Fonti della scheda ({len(card['sources'])})"):
        st.markdown("\n".join(f"- {s}" for s in card["sources"]) or "—")


def show_goal(index: int, case_id: str, goals: list[dict], default: int, english: bool, animate: bool) -> None:
    """The action of a goal of the real case, as in the cards tab: the goal its line points to is picked,
    the coach can pick another."""
    pick = st.segmented_control("L'azione di un gol (StatsBomb)", list(range(len(goals))), default=default,
                                key=f"goal_chat_{index}_{case_id}",
                                format_func=lambda i: graphics.goal_label(goals[i], english))
    if pick is not None:
        st.markdown(graphics.goal_svg(goals[pick], cards[case_id], english=english, animate=animate),
                    unsafe_allow_html=True)


def show_figures(index: int, animate: bool) -> None:
    """The graphics of the answer `index` (src/ui/graphics/answer.py: the formations the coach wrote, a coach's
    change of shape, the timeline, the numbers and the shots of a final, the action of a goal; st.html would
    strip the <svg>). One is drawn as it is, several go in tabs, so that the answer is not buried under them."""
    figures = graphics.answer_figures(state.messages, index, cards, animate=animate, goals=False)
    goals = graphics.answer_goals(state.messages, index, cards)
    if len(figures) + len(goals) < 2:
        for figure in figures:
            st.markdown(figure, unsafe_allow_html=True)
        for goal in goals:
            show_goal(index, *goal, animate)
        return
    tabs = st.tabs(graphics.figure_tabs(figures, len(goals)))
    for tab, figure in zip(tabs, figures):
        with tab:
            st.markdown(figure, unsafe_allow_html=True)
    for tab, goal in zip(tabs[len(figures):], goals):
        with tab:
            show_goal(index, *goal, animate)


def new_conversation() -> None:
    state.messages = []
    state.conversation = None
    state.pop("panel_answer", None)


def show_in_panel(index: int) -> None:
    """The cards panel next to the chat shows the cards of this answer (by default, the newest)."""
    state.panel_answer = index


# ----------------------------------------------------------------- state and backend
get_logging()
state = st.session_state
state.setdefault("messages", [])
state.setdefault("conversation", None)
cards = get_cards()

ready, problem = True, ""
try:
    retriever = get_retriever()
except Exception as e:  # Qdrant not running, index missing, API key not set
    logger.exception("assistant not ready")
    ready, problem = False, ("Non riesco a preparare l'assistente: controlla che Qdrant sia acceso "
                             "(`docker compose up -d`) e che `OPENAI_API_KEY` sia impostata nel `.env`. "
                             f"Schede e valutazione restano consultabili.\n\nDettaglio: {e}")
tracing = get_tracing() if ready else ""

# ----------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown("## ⚽ Match Analyst")
    st.button("🆕 Nuova conversazione", on_click=new_conversation, use_container_width=True)

    st.markdown("#### ⚙️ Impostazioni")
    model = st.selectbox("Modello", backend.MODELS, key="model",
                         help="gpt-4o-mini costa circa un terzo; gpt-4.1-mini dà risposte più complete.")
    guardrails = st.toggle("Guardrail attivi", value=True, key="guardrails",
                           help="Ingresso: ferma le domande fuori tema prima del modello. "
                                "Uscita: controlla lingua, nomi/numeri e citazioni, e se serve fa riscrivere la risposta.")
    cards_panel = st.toggle("Schede della risposta accanto alla chat", value=True, key="cards_panel",
                            help="Spento, la chat prende tutta la larghezza: i grafici sono più grandi.")

    st.markdown("#### 💡 Prova con")
    for label, question in view.EXAMPLES:
        if st.button(label, use_container_width=True, disabled=not ready):
            state.pending = question

    st.markdown("#### 🔭 Osservabilità")
    st.caption(tracing or "—")
    if tracing.startswith("Tracing attivo"):
        st.link_button("Apri le tracce in Phoenix", backend.phoenix_url(), use_container_width=True)

    answers = [m for m in state.messages if m["role"] == "assistant" and m.get("meta")]
    if answers:
        st.markdown("#### 🧾 Questa conversazione")
        c1, c2 = st.columns(2)
        c1.metric("Risposte", len(answers))
        c2.metric("Costo", f"{sum(m['meta']['cost_usd'] for m in answers):.3f} $")
        log = state.conversation.log.path if state.conversation else None
        if log and log.exists():
            st.download_button("⬇️ Scarica la chat", log.read_bytes(), file_name=log.name,
                               mime="application/jsonl", use_container_width=True,
                               help=f"Salvata anche in chats/{log.name}: domande, risposte, schede, "
                                    "ricerche, guardrail e memoria dell'agente.")

# a different model or guardrail setting starts a new conversation
conversation = state.conversation
if ready and (conversation is None or (conversation.model, conversation.guardrails) != (model, guardrails)):
    try:
        if conversation is not None and state.messages:
            state.messages = []
            st.toast("Impostazioni cambiate: nuova conversazione.", icon="🔄")
        state.conversation = conversation = backend.Conversation(model, guardrails, retriever)
    except (ValueError, RuntimeError) as e:   # missing API key, ...
        logger.exception("conversation not created")
        ready, problem = False, f"Non riesco a creare l'assistente: {e}"

# ----------------------------------------------------------------- page
st.markdown(view.header_html(cards), unsafe_allow_html=True)
if not ready:
    st.error(problem)

tab_chat, tab_cards, tab_eval = st.tabs(["💬 Chat", "📚 Schede", "📈 Valutazione"])

with tab_chat:
    # the answers with cards, and the one whose cards the panel shows: the one the coach picked, else the newest
    with_cards = [i for i, m in enumerate(state.messages) if m["role"] == "assistant" and view.ordered_cards(m, cards)]
    shown = state.get("panel_answer") if state.get("panel_answer") in with_cards else (with_cards[-1] if with_cards else None)
    if cards_panel:
        col_chat, col_cards = st.columns([5, 3], gap="large")
    else:   # the chat takes the whole width, the graphics are larger
        col_chat, col_cards = st.container(), None
    with col_chat:
        if not state.messages:
            st.markdown(view.welcome_html(), unsafe_allow_html=True)
            st.caption("Scrivi in basso, oppure scegli un esempio nella barra a sinistra.")
        last_answer = max((i for i, m in enumerate(state.messages) if m["role"] == "assistant"), default=-1)
        for index, message in enumerate(state.messages):
            with st.chat_message(message["role"], avatar="🧑‍🏫" if message["role"] == "user" else "⚽"):
                if message["role"] == "user":
                    st.markdown(message["content"])
                    continue
                st.markdown(view.answer_html(message["content"], cards), unsafe_allow_html=True)
                show_figures(index, animate=index == last_answer)   # only the newest answer moves
                if cards_panel and index in with_cards:   # which answer the cards on the right are of
                    st.button("📄 Schede a destra" if index == shown else "📄 Mostra le schede a destra",
                              key=f"panel_{index}", disabled=index == shown, on_click=show_in_panel, args=(index,))
                if message.get("guard_note"):
                    st.markdown(view.guard_html(message), unsafe_allow_html=True)
                if message.get("meta"):
                    with st.expander("📊 Dettagli della risposta"):
                        st.markdown(view.details_markdown(message))
                if message.get("calls"):
                    with st.expander("🔎 Cosa ha cercato l'assistente"):
                        st.markdown(view.searches_markdown(message["calls"], cards))

    if col_cards is not None:
        with col_cards:
            st.markdown('<div class="ma-panel"></div>', unsafe_allow_html=True)   # marks the column: it stays in view
            st.markdown("#### 📄 Schede della risposta")
            last = state.messages[shown] if shown is not None else None
            ids = view.ordered_cards(last, cards) if last else []
            numbers = view.citation_numbers(last["content"], cards) if last else {}   # as on the badges
            if not ids:
                st.info("Qui compaiono le schede che l'assistente ha consultato e citato, da leggere per intero.")
            else:
                if shown > 0 and state.messages[shown - 1]["role"] == "user":
                    st.markdown(view.panel_note_html(state.messages[shown - 1]["content"]), unsafe_allow_html=True)
                pick = st.selectbox("Scheda", ids, key=f"answer_card_{shown}_{len(state.messages)}",
                                    label_visibility="collapsed",
                                    format_func=lambda i: (f"{numbers[i]} · " if i in numbers else "")
                                    + view.card_label(cards[i]))
                show_card(cards[pick], height=460, number=numbers.get(pick))

with tab_cards:
    col_list, col_card = st.columns([1, 2], gap="large")
    with col_list:
        category = st.radio("Categoria", list(view.CATEGORIES), format_func=view.category_name, key="browse_category")
        in_category = [i for i, c in cards.items() if c["category"] == category]
        pick = st.radio("Scheda", in_category, format_func=lambda i: view.short_title(cards[i], 60),
                        key=f"browse_card_{category}")
    with col_card:
        show_card(cards[pick], height=560)

with tab_eval:
    runs = view.run_summaries(RUNS_DIR)
    gold = runs["gold_live"]
    st.markdown("#### 🎯 Gold run: il sistema completo sulle domande di prova")
    if gold:
        m = gold["metrics"]
        cols = st.columns(5)
        cols[0].metric("recall@5", f"{m['recall@5']:.2f}", help="La scheda giusta è tra le prime 5 trovate")
        cols[1].metric("MRR", f"{m['MRR']:.2f}", help="Quanto in alto compare la scheda giusta (1 = sempre prima)")
        cols[2].metric("Astensione fuori corpus", f"{m['abstention_out_of_corpus']:.0%}",
                       help="Quante volte dice «Non lo so» quando le schede non hanno la risposta")
        cols[3].metric("Tempo p50 / p95", f"{m['latency_p50_s']:.1f} / {m['latency_p95_s']:.1f} s")
        cols[4].metric("Costo a domanda", f"{m['cost_per_query_usd']:.4f} $")
    if runs["final"]:
        st.markdown("#### ⚖️ Fedeltà e pertinenza: i due modelli dell'agente a confronto")
        final = pd.DataFrame(runs["final"]).set_index("agente")
        cols = st.columns(len(final))
        for col, (model, row) in zip(cols, final.iterrows()):
            col.metric(f"{model} · fedeltà", f"{row['fedeltà']:.2f}", help="Quota di affermazioni supportate dalle schede")
            col.metric(f"{model} · pertinenza", f"{row['pertinenza']:.2f}", help="Quanto la risposta risponde alla domanda")
        st.caption(f"Giudice {final['giudice'].iloc[0]}, affermazione per affermazione, sulle stesse 41 domande. "
                   "gpt-4o-mini è il predefinito: stessa fedeltà a circa un terzo del costo, e nessuna "
                   "attribuzione sbagliata sulla domanda trappola.")
    col_a, col_b = st.columns(2, gap="large")
    with col_a:
        st.markdown("#### 🤖 Risposte che passano i controlli automatici")
        if runs["agent"]:
            agent = pd.DataFrame(runs["agent"])
            agent["% che passano"] = (100 * agent["passano"] / agent["domande"]).round()
            st.bar_chart(agent, x="run", y="% che passano", horizontal=True, color="#B3122B")
            st.caption("44 domande per run; da sinistra a destra nel tempo: modelli, ultimo giro di prompt, guardrail.")
    with col_b:
        st.markdown("#### 🔍 Ricerca: metodi a confronto")
        if runs["retrieval"]:
            retrieval = pd.DataFrame(runs["retrieval"]).set_index("metodo")
            st.bar_chart(retrieval, horizontal=True, stack=False)
            st.caption("recall@5 e MRR su 40 domande: la ricerca ibrida con interleave è la scelta.")
    with st.expander("📋 Tutte le run salvate"):
        index = RUNS_DIR / "README.md"
        st.markdown(index.read_text(encoding="utf-8") if index.exists() else "—")
    st.caption("Nuova valutazione (usa la chiave, circa 0,1 $): `python -m scripts.gold_run --tag <nome>`")

# ----------------------------------------------------------------- input (pinned at the bottom)
question = st.chat_input("Descrivi la tua squadra, l'avversario o la situazione di gara…", disabled=not ready)
question = question or state.pop("pending", None)
if question and ready:
    state.messages.append({"role": "user", "content": question})
    state.pop("panel_answer", None)   # the cards of the new answer
    with st.spinner("Sto studiando le schede…"):
        try:
            state.messages.append(conversation.ask(question))
            if state.messages[-1].get("log_error"):
                st.toast(f"Chat non salvata: {state.messages[-1]['log_error']}", icon="⚠️")
        except Exception as e:  # network or API error: keep the conversation alive
            state.messages.append({"role": "assistant", "content": f"⚠️ Errore durante l'analisi: {e}"})
    st.rerun()
