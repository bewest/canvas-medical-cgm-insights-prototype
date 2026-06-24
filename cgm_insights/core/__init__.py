"""SDK-free core logic for cgm_insights.

Everything in this package is pure Python using only the standard library
(and only the subset permitted by the Canvas plugin sandbox). It contains no
``canvas_sdk`` imports, so it can be unit-tested with plain pytest outside of
Canvas, and imported unchanged by the sandboxed handlers.
"""
