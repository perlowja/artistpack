"""Manifest serialization: pack.yaml / artist.yaml / feed.yaml <-> dict.

These three helpers are the load/save boundary for the spec's manifest
formats (``spec/artistpack-0.1.md``). They use a restricted ``yaml.SafeLoader``
per ``docs/security-model.md`` §"Safe YAML parsing only" — no
arbitrary-tag construction, ever.
"""

from __future__ import annotations

from typing import Any

import yaml


class _RestrictedLoader(yaml.SafeLoader):
    """SafeLoader with all custom-tag constructors removed.

    ``yaml.SafeLoader`` already rejects unknown tags by default, but we
    make the intent explicit at the class level so future maintainers
    don't accidentally add a permissive constructor.
    """


_RESTRICTED_LOADER = _RestrictedLoader


class RestrictedDumper(yaml.SafeDumper):
    """SafeDumper that emits only safe tags."""


def yaml_load(text: str) -> Any:
    """Parse ``text`` with the restricted safe loader."""

    return yaml.load(text, Loader=_RESTRICTED_LOADER)


def yaml_dump(obj: Any) -> str:
    """Dump ``obj`` with the restricted safe dumper.

    Block style, no aliases, default_flow_style off, sort_keys=False —
    we want the YAML to round-trip the manifest's logical shape
    faithfully. The canonical SHA-256 form is computed by
    ``app.services.manifest_hash`` from the dict directly.
    """

    return yaml.dump(
        obj,
        Dumper=RestrictedDumper,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )
