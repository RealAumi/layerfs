"""Scoped regimes and complete phase qualification remain separate evidence."""

PHASES = ("mount", "command", "commit", "unmount")


def phase_inputs_qualified(evidence):
    boundaries = evidence.get("phase_input_boundaries")
    observed = evidence.get("phase_cache_observations")
    if not (isinstance(boundaries, dict) and isinstance(observed, dict)
            and set(boundaries) == set(observed) == set(PHASES)):
        return False
    for phase in PHASES:
        boundary, proof = boundaries[phase], observed[phase]
        if not (isinstance(boundary, dict) and isinstance(proof, dict)):
            return False
        files = boundary.get("files")
        before, started = proof.get("observed_monotonic_ns"), boundary.get("started_monotonic_ns")
        if not (isinstance(files, dict) and set(files) == {"store", "overlay"}
                and all(isinstance(value, dict) and value for value in files.values())
                and proof.get("files") == files and proof.get("identity_checked") is True
                and proof.get("all_paid_input_scopes_complete") is True
                and proof.get("clock_id") == "monotonic" and type(before) is int
                and type(started) is int and 0 <= before < started
                and proof.get("status") == "VERIFIED_COLD"
                and type(proof.get("resident_pages")) is int and proof["resident_pages"] == 0
                and proof.get("metadata_state") == "VERIFIED_COLD"
                and proof.get("sqlite_reader_cache_state") == "VERIFIED_COLD"):
            return False
    return True


def validate(cache_class, evidence):
    if cache_class in ("B", "C"):
        if not phase_inputs_qualified(evidence):
            return "INELIGIBLE"
        own_written = evidence.get("has_own_write_input")
        if type(own_written) is not bool:
            return "INELIGIBLE"
        if own_written:
            cold = evidence.get("own_write_cold_observation")
            started = evidence.get("commit_started_monotonic_ns")
            if not (isinstance(cold, dict) and cold.get("status") == "VERIFIED_COLD"
                    and cold.get("phase") == "before_commit"
                    and type(cold.get("resident_pages")) is int and cold["resident_pages"] == 0
                    and cold.get("metadata_state") == "VERIFIED_COLD"
                    and cold.get("identity_checked") is True
                    and type(cold.get("observed_monotonic_ns")) is int
                    and type(started) is int and cold["observed_monotonic_ns"] < started):
                return "INELIGIBLE"
    return regime_status(cache_class, evidence)


def regime_status(cache_class, evidence):
    """The original selected state predicate alone never claims all paid inputs."""
    if cache_class == "A":
        pages = evidence.get("resident_pages")
        metadata = evidence.get("metadata_state")
        return "ELIGIBLE" if type(pages) is int and pages == 0 and metadata == "VERIFIED_COLD" else "INELIGIBLE"
    if cache_class == "B":
        return "ELIGIBLE" if (evidence.get("fresh_mount") is True
                              and evidence.get("warmup_terminal_unmount") is True
                              and evidence.get("warmup_cleanup") == "Gone"
                              and type(evidence.get("object_demands")) is int
                              and evidence["object_demands"] == 0) else "INELIGIBLE"
    if cache_class == "C":
        interval = evidence.get("warm_interval_ns")
        return "ELIGIBLE" if (evidence.get("same_mount") is True and type(interval) is int
                              and 0 <= interval < 60_000_000_000) else "INELIGIBLE"
    raise ValueError("cache class must be A, B or C")
