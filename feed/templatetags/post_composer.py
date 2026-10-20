from django import template
from feed.forms import PostForm

register = template.Library()


@register.inclusion_tag("feed/post_composer.html", takes_context=True)
def post_composer(context):
    return {
        "composer_form": PostForm(auto_id="composer_%s"),
        "csrf_token": context.get("csrf_token"),
    }
