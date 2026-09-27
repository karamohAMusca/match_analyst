---
document_id: glossary_metriche
title: "Glossario: metriche di prestazione"
category: glossary
origin_type: derived
modality: text
reliability: project_synthesis_cited
themes: [ppda, xg, field_tilt, pressing, possesso, metriche]
sources:
  - "Dileo, L'evoluzione del Sassuolo di De Zerbi (tesi Match Analyst), pp. 5, 16-17, 20"
  - "Spalla, L'evoluzione del calcio in Serie A (UEFA Pro 2023/24), p. 51"
  - "Project computation from StatsBomb Open Data (matches 3869685, 3943043)"
  - "FIFA Post Match Summary Report, Spain v Argentina, 19 July 2026"
---

# Glossario: metriche di prestazione

## Pressing
- **PPDA (Passes Per Defensive Action):** passaggi concessi all'avversario divisi per le azioni difensive (tentativi di intercetto, contrasti vinti o persi, falli). Indica quanto spesso una squadra prova a riconquistare palla nelle prime fasi della costruzione avversaria: **più è basso, più il pressing è aggressivo** [Dileo, p. 17; Spalla, p. 51].
  - Esempi: Sassuolo 13.48 → 10.30 con De Zerbi (soccerment) [Dileo, p. 16]; Inter di Conte 9,08 nel 2019-20 e 13,44 nel 2020-21 [Spalla, p. 51].
  - Nelle schede partita del corpus il PPDA è calcolato dal progetto sui dati StatsBomb: passaggi dell'avversario nel suo 60% di campo diviso per contrasti, intercetti e falli della squadra nel 60% avversario.
- **BDP:** misura l'effetto del pressing sulla percentuale di passaggi riusciti dell'avversario rispetto alla sua media. Più il pressing è efficace, meno passaggi riesce a fare l'avversario; il valore può essere positivo o negativo [Dileo, p. 17]. Dileo lo scrive sia "BDP" sia "BPD".

## Pericolosità e risultati attesi [Dileo, p. 20]
- **xG:** gol previsti; il totale include i rigori ma non quelli a fine partita (fbref). **xGA:** gol previsti concessi.
- **xPts:** punti previsti (soccerment).
- **xT (Expected Threat):** valore attribuito a un'azione che avvicina il pallone alla porta avversaria (soccerment).
- **IPO / IRD:** indice di pericolosità offensiva e indice di rischio difensivo (SICS); **IPO-IRD** è la loro differenza.
- **Matrice di Viscidi:** incrocia possesso palla e IPO-IRD. Le "pessime prestazioni" sono quelle con possesso inferiore al 50% e IPO-IRD negativo [Dileo, p. 5].

## Passaggi (fbref) [Dileo, p. 20]
Corti tra 4 e 13 metri, medi tra 13 e 27 metri, lunghi oltre 27 metri. **Tocchi:** ricevere, dribblare e passare conta come un solo tocco.

## Territorio (calcolo del progetto su StatsBomb)
- **Pass share:** quota dei passaggi della partita fatti dalla squadra; è un'approssimazione del possesso.
- **Field tilt:** quota dei passaggi giocati nel terzo offensivo fatti dalla squadra. Indica quanto una squadra "schiaccia" l'altra.
- **Pressioni:** eventi di pressione StatsBomb, contati anche nel solo terzo offensivo.
- I minuti degli eventi StatsBomb partono da 0: per i minuti dei gol le schede usano Wikipedia o FIFA.

## Metriche FIFA (finale Mondiale 2026)
Il report FIFA riporta "Completed Line Breaks" (linee rotte), "Receptions in the Final Third", "Forced Turnovers", "Second Balls" e le fasi di gioco (Build Up, Progression, Final Third, Counter-press, High/Mid/Low Press, High/Mid/Low Block…), ma nei documenti del corpus **non c'è una definizione** di queste metriche: vanno usate solo come confronto tra le due squadre.

## Attenzione (interpretazione del progetto)
Valori di fornitori diversi (fbref, soccerment, SICS, StatsBomb, FIFA) sono calcolati in modo diverso: si confrontano solo numeri della stessa fonte.

Collegamenti: situation_pressing_alto_e_riaggressione, coach_de_zerbi, coach_conte.
