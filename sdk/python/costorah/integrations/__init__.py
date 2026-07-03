"""
costorah.integrations — optional framework integrations (EP-18.4).

Each integration lives in its own submodule and imports its target
framework lazily — `import costorah.integrations` itself never requires
any framework to be installed; only importing a specific submodule
(e.g. `costorah.integrations.fastapi`) does, and only if that framework
isn't installed does it raise a clear `ImportError` explaining what to
install.
"""

from __future__ import annotations
