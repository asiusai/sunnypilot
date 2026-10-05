import pyray as rl

from openpilot.system.ui.lib.application import gui_app, FontWeight
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.lib.wrap_text import wrap_text
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.label import gui_label


class PrimeWidget(Widget):
  """Local app information in the existing home panel."""

  def _render(self, rect):
    rl.draw_rectangle_rounded(rect, 0.025, 10, rl.Color(51, 51, 51, 255))
    x, y, width = rect.x + 80, rect.y + 90, rect.width - 160
    gui_label(rl.Rectangle(x, y, width, 90), tr("Asius App"), 75, font_weight=FontWeight.BOLD)
    font = gui_app.font(FontWeight.NORMAL)
    text = tr("Use app.asius.ai for device settings, live video and encrypted drive storage.")
    lines = wrap_text(font, text, 56, int(width))
    rl.draw_text_ex(font, "\n".join(lines), rl.Vector2(x, y + 140), 56, 0, rl.WHITE)
