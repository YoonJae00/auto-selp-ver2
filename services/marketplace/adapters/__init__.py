from adapters.coupang import CoupangAdapter
from adapters.smartstore import SmartstoreAdapter

ADAPTERS = {
    "smartstore": SmartstoreAdapter(),
    "coupang": CoupangAdapter(),
}

__all__ = ["SmartstoreAdapter", "CoupangAdapter", "ADAPTERS"]
