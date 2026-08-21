"""Test-only host pages for embedded crop dialogs."""

from django.http import HttpResponse
from django.urls import reverse
from django.utils.html import escape


CALLBACK_HOST_PAGE = """<!DOCTYPE html>
<html>
<head><title>cropduster callback host</title></head>
<body>
<script>
    // What the dialog hands back, in the order it hands it back. The dialog
    // calls `parent[callback_fn](callback_fn, payload)`, so a call records
    // both the name it was reached by and the payload.
    window.cropdusterCallbackCalls = [];
    window.myCb = function () {
        window.cropdusterCallbackCalls.push(
            Array.prototype.slice.call(arguments));
    };
</script>
<iframe id="dialog-frame" src="%(src)s" width="900" height="650"
        frameborder="0"></iframe>
</body>
</html>
"""


def callback_host(request):
    """
    Render the standalone dialog in an iframe with a parent callback.

    The dialog calls a named global on this page and does not use
    ``window.opener`` or ``CropDuster.complete()``.
    """
    src = request.GET.get('dialog') or reverse('cropduster-standalone')
    return HttpResponse(CALLBACK_HOST_PAGE % {'src': escape(src)})
