"""Graphics under a chat answer, drawn as SVG by code in the colours of the design system (the
`--ma-*` variables of the CSS block in view.py, light and dark): no chart library, no JavaScript;
the movement is CSS only, and it stops when the system asks for reduced motion.
The app renders them with `st.markdown(..., unsafe_allow_html=True)`: `st.html` sanitizes the
`<svg>` element away. Nothing here comes from the model.

One module per graphic:
- `formations.py`: the pitch with the formations the coach wrote in the questions;
- `shape.py`: how a coach's team changes shape, from the `shape_changes:` of the coach's card;
- `timeline.py`: the timeline of a final, from the `timeline:` of its card;
- `match_numbers.py`: the numbers of a final, the two teams side by side, from the "Numeri" table of its card;
- `goal.py`: the action of a goal of a final, from StatsBomb's events;
with `badges.py` (the teams' symbols) and `svg.py` (the pitch, the colours, the text, the style of an
animation, the caption) shared, and `answer.py` choosing the graphics under an answer.
This package keeps the names the app, the scripts and the tests import.
"""

from src.ui.graphics.answer import ANSWERED, answer_figures, real_cases
from src.ui.graphics.badges import badge_width, team_badge
from src.ui.graphics.formations import coach_formations, formation_places, formations_in, formations_svg
from src.ui.graphics.goal import GOAL_ACTIONS, goal_actions, goal_label, goal_svg, pick_goal
from src.ui.graphics.match_numbers import final_numbers, names_a_number, numbers_svg
from src.ui.graphics.shape import cited_shape_changes, shape_moves, shape_svg
from src.ui.graphics.svg import pitch_svg
from src.ui.graphics.timeline import PERIODS, event_minutes, timeline_svg

__all__ = [
    "ANSWERED", "GOAL_ACTIONS", "PERIODS", "answer_figures", "badge_width", "cited_shape_changes", "coach_formations",
    "event_minutes", "final_numbers", "formation_places", "formations_in", "formations_svg", "goal_actions",
    "goal_label", "goal_svg", "names_a_number", "numbers_svg", "pick_goal", "pitch_svg", "real_cases", "shape_moves",
    "shape_svg", "team_badge", "timeline_svg",
]
