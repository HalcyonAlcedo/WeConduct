import hashlib


class StableIdentityService:
    def create_lowered_node_id(
        self,
        *,
        source_anchor_ref: str,
        expansion_role: str,
        lowered_kind: str,
    ) -> str:
        seed = "|".join([source_anchor_ref, expansion_role, lowered_kind])
        digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
        return f"ln:{digest}"
