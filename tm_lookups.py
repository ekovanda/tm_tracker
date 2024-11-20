"""
Contains dataclasses of mapping objects
"""

from typing import Dict, List, Optional
from dataclasses import dataclass

@dataclass
class Club:
    clubId: str
    owner_account_id: str
    owner_alias: Optional[str]

@dataclass
class Map:
    name: str
    uid: str

@dataclass
class Player:
    name: str
    account_id: str
    alias: Optional[str] = ""

CLUBS: List[Club] = [Club("85915", "7e468ff6-4558-43ce-ad23-591dd86291c0", "Elliot")] 

MAPS: List[Map] = [Map("Fall-12", "MXCtvB4zmW3iliJ48Jti6luY9Zi")]

PLAYERS: List[Player] = [
    Player("EljayKay", "7e468ff6-4558-43ce-ad23-591dd86291c0", "Elliot"),
    Player("LryKo", "f00ab19a-14e5-4e6e-9a45-78f1af8487e1", "Ellery"),
    Player("Timo._.o", "b9b79f89-19e7-4f26-be01-03556b8890b9", "Timo")
]
