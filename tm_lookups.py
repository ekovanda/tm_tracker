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
class Track:
    name: str
    uid: str

@dataclass
class Player:
    name: str
    account_id: str
    alias: Optional[str] = ""

CLUBS: List[Club] = [Club("85915", "7e468ff6-4558-43ce-ad23-591dd86291c0", "Elliot")] 

# Manually obtained from: https://trackmania.io/#/campaigns/0/77963 
TRACKS: List[Track] = [
    Track("Fall-01", "rw7jr8WlTrYor0vN0A0PiKzgg78"),
    Track("Fall-02", "tl_RqArUrUQ9KQDe0U5fskzdrpj"),
    Track("Fall-03", "6h3gOaF9HJBCnQbxtBopC_IMs10"),
    Track("Fall-04", "ecpLvJZCuyoAJj1LhfZZwhoHfSa"),
    Track("Fall-05", "d83GbrV9SN7kfY3ftaK8FRVB44b"),
    Track("Fall-06", "trDIbaxC_9IVdg6yen9q7zISZbk"),
    Track("Fall-07", "q5L8T_fy0w5MkZfJO1gQ_my87bj"),
    Track("Fall-08", "2msqSkfJP683MmDGhfpkJM4q7Sk"),
    Track("Fall-09", "ti8ot1biy4yCUdi7lPmGqFE6aRj"),
    Track("Fall-10", "BKwVaqdgCe4PCWQwluvi99iLe5b"),
    Track("Fall-11", "3sDimlZCd0QPmmRiGASA1Pbtv05"),
    Track("Fall-12", "MXCtvB4zmW3iliJ48Jti6luY9Zi"),
    Track("Fall-13", "glysLJbIhBkhDFRB7zhvhatgIqa"),
    Track("Fall-14", "SnLRynzusvgCyqlu9X0Ux_NkcMd"),
    Track("Fall-15", "WGEcRcfn0NGxxrodXzshYdwzfIg"),
    Track("Fall-16", "5BretnXASvk2RoKa2WqFOcnW9x7"),
    Track("Fall-17", "yCaeXB3t3c8_SrsIBefjDws5hqg"),
    Track("Fall-18", "DrJSswMXezYuYTS8bEjjQmdWDVa"),
    Track("Fall-19", "JndUMBgeR4vQ2zadb164PFOBS9"),
    Track("Fall-20", "uTRn1j2ZvRr02krtvKJQJqEGwH7"),
    Track("Fall-21", "p5tWnXUzwNxyxgsg7m8ZoaUbqAa"),
    Track("Fall-22", "S927zT5HCIybPpRgh5RY79Zcb5h"),
    Track("Fall-23", "WxCghen5pI7lbDKigtekKq0Uut3"),
    Track("Fall-24", "9fEY2mqkUY50nhtj9c0NXWax5xk"),
    Track("Fall-25", "End5ikYJa8pgN8RI347E6l4i7lg"),
    ]

PLAYERS: List[Player] = [
    Player("EljayKay", "7e468ff6-4558-43ce-ad23-591dd86291c0", "Elliot"),
    Player("LryKo", "f00ab19a-14e5-4e6e-9a45-78f1af8487e1", "Ellery"),
    Player("Timo._.o", "b9b79f89-19e7-4f26-be01-03556b8890b9", "Timo")
]
