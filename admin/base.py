from markupsafe import Markup
from models import Tag

def format_tags_shared(model, context, hide_group: bool = False):
    """Shared formatter for Tag badges"""
    html = ""
    # Support both direct tag list and models with .tags
    tags = model.tags if hasattr(model, "tags") else []
    if not tags and isinstance(model, Tag):
        tags = [model]
        
    for tag in tags:
        color = "secondary"
        if tag.group:
            color = tag.group.color
        
        # If tag is not public, use an outlined/muted style
        opacity = "1" if tag.is_public else "0.5"
        border = "1px solid #ccc" if not tag.is_public else "none"
        
        # Include group name in small text if available, unless hidden
        group_prefix = ""
        if not hide_group and tag.group:
            group_prefix = f'<small style="opacity: 0.7;">{tag.group.title}:</small> '
        
        html += f'<span class="badge bg-{color}" style="margin-right: 5px; opacity: {opacity}; border: {border};">{group_prefix}{tag.title}</span>'
    return Markup(html)
