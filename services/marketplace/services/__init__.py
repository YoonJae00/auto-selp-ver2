"""Marketplace domain services."""

__all__ = ["generate_drafts_for_job"]


def __getattr__(name):
    if name == "generate_drafts_for_job":
        from services.draft_generation import generate_drafts_for_job

        return generate_drafts_for_job
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
