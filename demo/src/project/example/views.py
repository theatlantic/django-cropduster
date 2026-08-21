"""
Render an admin form inside an 830x550 iframe for browser tests.

This matches a downstream editor's embed, where ``auto`` opens a separate
window because the modal does not fit in the iframe.
"""

from django.shortcuts import render
from django.urls import reverse

#: Dimensions of the downstream editor's iframe.
IFRAME_WIDTH = 830
IFRAME_HEIGHT = 550


def tiny_iframe(request, pk=None):
    if pk is None:
        iframe_url = reverse("admin:example_article_add")
    else:
        iframe_url = reverse("admin:example_article_change", args=[pk])
    return render(request, "example/tiny_iframe.html", {
        "iframe_url": iframe_url,
        "width": IFRAME_WIDTH,
        "height": IFRAME_HEIGHT,
    })
