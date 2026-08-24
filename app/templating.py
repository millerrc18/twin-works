"""Shared Jinja2 templates instance + custom filters."""
from pathlib import Path
from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def fmt_date(d, fmt="%m/%d"):
    if d is None:
        return "—"
    return d.strftime(fmt)


def delta_color(days):
    if days is None:
        return "gray"
    if days <= 0:
        return "green"
    if days <= 7:
        return "amber"
    return "red"


templates.env.filters["fmt_date"] = fmt_date
templates.env.filters["delta_color"] = delta_color
