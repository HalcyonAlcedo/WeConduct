from __future__ import annotations

from .schema import ConfigField, ConfigurationDomain


class ConfigurationRegistry:
    def __init__(self) -> None:
        self._domains: dict[tuple[str, str], ConfigurationDomain] = {}
        self._fields: dict[tuple[str, str, str], ConfigField] = {}

    def register_domain(self, domain: ConfigurationDomain) -> None:
        identifier = (domain.scope, domain.key)
        if identifier in self._domains:
            raise ValueError(f"configuration domain already registered: {domain.scope}/{domain.key}")
        self._domains[identifier] = domain

    def register_field(self, config_field: ConfigField) -> None:
        if (config_field.scope, config_field.domain) not in self._domains:
            raise ValueError(
                f"configuration domain not found: {config_field.scope}/{config_field.domain}"
            )
        if config_field.status == "active" and not config_field.consumer:
            raise ValueError("active configuration field requires consumer")
        identifier = (config_field.scope, config_field.domain, config_field.key)
        if identifier in self._fields:
            raise ValueError(
                "configuration field already registered: "
                f"{config_field.scope}/{config_field.domain}/{config_field.key}"
            )
        self._fields[identifier] = config_field

    def get_field(self, *, scope: str, domain: str, key: str) -> ConfigField:
        config_field = self._fields.get((scope, domain, key))
        if config_field is None:
            raise ValueError(f"configuration field not found: /{domain}/{key}")
        return config_field

    def fields_for_scope(self, scope: str) -> list[ConfigField]:
        return sorted(
            (config_field for config_field in self._fields.values() if config_field.scope == scope),
            key=lambda config_field: (config_field.domain, config_field.order, config_field.key),
        )

    def domains_for_scope(self, scope: str) -> list[ConfigurationDomain]:
        return sorted(
            (domain for domain in self._domains.values() if domain.scope == scope),
            key=lambda domain: (domain.order, domain.key),
        )
