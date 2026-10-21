"""Graphics under a chat answer, drawn as SVG by code in the colours of the design system (the
`--ma-*` variables of the CSS block in view.py, light and dark): no chart library, no JavaScript;
the movement is CSS only, and it stops when the system asks for reduced motion.
The app renders them with `st.markdown(..., unsafe_allow_html=True)`: `st.html` sanitizes the
`<svg>` element away. Nothing here comes from the model.

One module per graphic:
- `formations.py`: the pitch with the formations the coach wrote in the questions;
- `timeline.py`: the timeline of a final, from the `timeline:` of its card;
- `goal.py`: the action of a goal of a final, from StatsBomb's events;
with `badges.py` (the teams' symbols) and `svg.py` (the pitch, the colours, the text, the style of an
animation, the caption) shared, and `answer.py` choosing the graphics under an answer.
This package keeps the names the app, the scripts and the tests import.
"""

from src.ui.graphics.answer import ANSWERED, answer_figures, real_cases
from src.ui.graphics.badges import badge_width, team_badge
from src.ui.graphics.formations import coach_formations, formation_places, formations_in, formations_svg
from src.ui.graphics.goal import GOAL_ACTIONS, goal_actions, goal_label, goal_svg, pick_goal
from src.ui.graphics.svg import pitch_svg
from src.ui.graphics.timeline import PERIODS, event_minutes, timeline_svg

__all__ = [
    "ANSWERED", "GOAL_ACTIONS", "PERIODS", "answer_figures", "badge_width", "coach_formations", "event_minutes",
    "formation_places", "formations_in", "formations_svg", "goal_actions", "goal_label", "goal_svg", "pick_goal",
    "pitch_svg", "real_cases", "team_badge", "timeline_svg",
]
