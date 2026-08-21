# django-cropduster demo

This project runs the checked-out copy of django-cropduster in a small Django
admin site. Its models cover top-level fields, two fields on one model,
callable size declarations, and aliases; its admin registers a sortable
nested inline and inlines nested two levels deep.

Install the demo environment and create its database:

```console
uv sync --project demo
uv run --project demo python demo/src/manage.py migrate
uv run --project demo python demo/src/manage.py seed_e2e
```

Start the development server:

```console
uv run --project demo python demo/src/manage.py runserver 127.0.0.1:8000
```

With the default `auto` mode, the dialog opens as a modal on a full-size
admin page. Set `CROPDUSTER_DIALOG_MODE=window` to always use a separate
window. The `/tiny-iframe/` page embeds the Article form at 830x550, where
`auto` selects the window because the modal does not fit.

Open <http://127.0.0.1:8000/admin/> and sign in with username `admin` and
password `admin`. The Article form is the smallest example. Upload an image in
either field, step through its crops, save the article, and reopen it to confirm
that the original and generated thumbnails are retained.

The Gallery form contains a cropduster field on a sortable inline one level
deep.
The Page form has two nested levels: Page → PageSection → PageItem. Add and
reorder rows, upload an image to a nested item, save, and reopen the page to
confirm that the order and image association have not changed.

The SQLite database, uploaded media, and collected static files are written
under `demo/` and are ignored by Git. Set `DEMO_DB_PATH` to use another SQLite
path.
