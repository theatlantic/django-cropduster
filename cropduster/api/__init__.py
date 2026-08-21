"""Cropduster's versioned JSON API.

The ``state/``, ``upload/``, and ``crop/`` endpoints under ``api/v1/`` return
the v1 payload from :func:`cropduster.services.payload.build_payload`. Failures
use non-200 status codes and a common JSON error object. The 5.0 crop dialog
uses these endpoints.

The legacy ``/upload/`` and ``/crop/`` endpoints retain their existing formset
format and HTTP-200 error responses. Both APIs use
:mod:`cropduster.services` for storage and crop operations.
"""
