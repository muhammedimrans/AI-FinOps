"""Single source of truth for the agent's version string.

Bump this on every release. `costorah-agent version` and the /health and
/metrics endpoints all read from here — never hardcode the version anywhere
else.
"""

__version__ = "0.1.0"
