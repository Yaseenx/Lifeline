# Removed in the demo -> real refactor.
# The real system is the FastAPI server (server/app.py) with the call-taker
# console (server/console.html). Real integration is exercised by:
#   tests/test_corridor.py   — dispatch-driven corridor, end to end
#   tests/test_flow.py       — intake -> dispatch -> coordinator
#   tests/test_intake_channels.py — call (address+geocode) and WhatsApp intake
# This demo/ folder can be deleted.
