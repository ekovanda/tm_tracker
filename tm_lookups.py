"""
Contains dataclasses of mapping objects
"""

from dataclasses import dataclass


@dataclass
class Club:
    clubId: str
    owner_account_id: str
    owner_alias: str | None


CLUBS: dict[str, Club] = {
    "Elliot": Club("85915", "7e468ff6-4558-43ce-ad23-591dd86291c0", "Elliot")
}
