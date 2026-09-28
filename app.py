"""Match Analyst — Streamlit front end.

    streamlit run app.py

Three tabs: the chat with the assistant coach (conversation memory, citations as badges, the
cards of every answer next to it, what the guardrails did, time and cost of each answer), the
31 cards of the knowledge base, and the measured results of the saved evaluation runs.
The page only renders: the agent and the numbers come from src/ui/backend.py, the formatting
from src/ui/view.py. Needs Qdrant running (docker compose up -d), the index built and
OPENAI_API_KEY in .env; with Phoenix running, every question is also a trace.
"""

import os

os.environ.setdefault("DATAPIZZA_AGENT_LOG_LEVEL", "WARNING")   # no agent log panels in the terminal

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from src.core.config import PROJECT_ROOT  # noqa: E402
from src.ui import backend, view  # noqa: E402

RUNS_DIR = PROJECT_ROOT / "eval" / "runs"

st.set_page_config(page_title="Match Analyst", page_icon="⚽", layout="wide")
st.markdown(view.CSS, unsafe_allow_html=True)


@st.cache_resource(show_spinner="Carico l'indice delle schede…")
def get_retriever():
    return backend.build_retriever()


@st.cache_resource(show_spinner=False)
def get_tracing() -> str:
    return backend.start_tracing()


@st.cache_data(show_spinner=False)
def get_cards() -> dict:
    return view.load_card_index()


def show_card(card: dict, height: int) -> None:
    st.markdown(view.card_header_html(card), unsafe_allow_html=True)
    with st.container(height=height):
        st.markdown(view.card_body(card))
    with st.expander(f"📚 Fonti della scheda ({len(card['sources'])})"):
        st.markdown("\n".join(f"- {s}" for s in card["sources"]) or "—")


def new_conversation() -> None:
    state.messages = []
    state.conversation = None


# ----------------------------------------------------------------- state and backend
state = st.session_state
state.setdefault("messages", [])
state.setdefault("conversation", None)
cards = get_cards()

ready, problem = True, ""
try:
    retriever = get_retriever()
except Exception as e:  # Qdrant not running, index missing, API key not set
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

# a different model or guardrail setting starts a new conversation
conversation = state.conversation
if ready and (conversation is None or (conversation.model, conversation.guardrails) != (model, guardrails)):
    try:
        if conversation is not None and state.messages:
            state.messages = []
            st.toast("Impostazioni cambiate: nuova conversazione.", icon="🔄")
        state.conversation = conversation = backend.Conversation(model, guardrails, retriever)
    except (ValueError, RuntimeError) as e:   # missing API key, ...
        ready, problem = False, f"Non riesco a creare l'assistente: {e}"

# ----------------------------------------------------------------- page
st.markdown(view.header_html(cards), unsafe_allow_html=True)
if not ready:
    st.error(problem)

tab_chat, tab_cards, tab_eval = st.tabs(["💬 Chat", "📚 Schede", "📈 Valutazione"])

with tab_chat:
    col_chat, col_cards = st.columns([3, 2], gap="large")
    with col_chat:
        if not state.messages:
            for col, (icon, title, text) in zip(st.columns(3), view.WELCOME):
                col.markdown(f'<div class="ma-feature"><div class="i">{icon}</div><div class="t">{title}</div>'
                             f'<div class="d">{text}</div></div>', unsafe_allow_html=True)
            st.caption("Scrivi in basso, oppure scegli un esempio nella barra a sinistra.")
        for message in state.messages:
            with st.chat_message(message["role"], avatar="🧑‍🏫" if message["role"] == "user" else "⚽"):
                if message["role"] == "user":
                    st.markdown(message["content"])
                    continue
                st.markdown(view.cite_badges(message["content"], cards), unsafe_allow_html=True)
                if message.get("guard_note"):
                    st.caption(f"🛡️ {message['guard_note']}")
                if message.get("meta"):
                    with st.expander("📊 Dettagli della risposta"):
                        st.markdown(view.details_markdown(message))
                if message.get("calls"):
                    with st.expander("🔎 Cosa ha cercato l'assistente"):
                        st.markdown(view.searches_markdown(message["calls"], cards))

    with col_cards:
        st.markdown("#### 📄 Schede della risposta")
        last = next((m for m in reversed(state.messages) if m["role"] == "assistant"), None)
        ids = view.ordered_cards(last, cards) if last else []
        if not ids:
            st.info("Qui compaiono le schede che l'assistente ha consultato e citato, da leggere per intero.")
        else:
            pick = st.selectbox("Scheda", ids, format_func=lambda i: view.card_label(cards[i]),
                                key=f"answer_card_{len(state.messages)}", label_visibility="collapsed")
            show_card(cards[pick], height=460)

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
        st.caption("Fedeltà e pertinenza, date da un giudice LLM, sono in validazione: il primo giudice dava 1,0 "
                   "anche a risposte sbagliate. Il risultato arriverà con il giudice verificato.")
    col_a, col_b = st.columns(2, gap="large")
    with col_a:
        st.markdown("#### 🤖 Risposte che passano i controlli automatici")
        if runs["agent"]:
            agent = pd.DataFrame(runs["agent"])
            agent["% che passano"] = (100 * agent["passano"] / agent["domande"]).round()
            st.bar_chart(agent, x="run", y="% che passano", horizontal=True, color="#2fa84f")
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
    with st.spinner("Sto studiando le schede…"):
        try:
            state.messages.append(conversation.ask(question))
        except Exception as e:  # network or API error: keep the conversation alive
            state.messages.append({"role": "assistant", "content": f"⚠️ Errore durante l'analisi: {e}"})
    st.rerun()
