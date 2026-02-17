from markupsafe import Markup

from models import Tag

_BADGE_MARGIN_STYLE = "margin-right: 5px;"
_MUTED_BORDER_STYLE = "1px solid #ccc"
_GROUP_PREFIX_STYLE = "opacity: 0.7;"


def _resolve_tags(model) -> list[Tag]:
    if isinstance(model, Tag):
        return [model]
    return model.tags if hasattr(model, "tags") else []


def _render_tag_badge(tag: Tag, hide_group: bool) -> str:
    color = tag.group.color if tag.group else "secondary"
    opacity = "1" if tag.is_public else "0.5"
    border = _MUTED_BORDER_STYLE if not tag.is_public else "none"

    group_prefix = ""
    if not hide_group and tag.group:
        group_prefix = f'<small style="{_GROUP_PREFIX_STYLE}">{tag.group.title}:</small> '

    return (
        f'<span class="badge bg-{color}" '
        f'style="{_BADGE_MARGIN_STYLE} opacity: {opacity}; border: {border};">'
        f"{group_prefix}{tag.title}</span>"
    )


def format_tags_shared(model, context, hide_group: bool = False):
    """Shared formatter for Tag badges."""
    badges = [_render_tag_badge(tag, hide_group=hide_group) for tag in _resolve_tags(model)]
    return Markup("".join(badges))
