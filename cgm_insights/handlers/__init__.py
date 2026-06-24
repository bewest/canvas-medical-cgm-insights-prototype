"""Canvas event handlers for cgm_insights.

This package is the thin glue between Canvas events and the SDK-free ``core``
logic. Handlers fetch Nightscout data, delegate all computation to ``core``,
and translate the result into Canvas effects. Keep logic out of here.
"""
