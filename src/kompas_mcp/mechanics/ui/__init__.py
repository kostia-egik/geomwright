"""Compatibility alias for :mod:`geomwright.studio`.

New integrations should import ``geomwright.studio`` directly.
"""

from geomwright.studio import create_app

__all__ = ["create_app"]
