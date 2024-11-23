"""
Contains main player class.
"""
from typing import Dict, List

class Player:
    def __init__(self, name: str, account_id: str, alias: str=""):
        self.name = name
        self.account_id = account_id
        self.alias = alias if alias != "" else self.name 

    def get_rank_counts(self, all_pbs: Dict) -> None:
        """
        Sets the attribute 'medal_count' which is a dict of: 
        {"gold": a, "silver": b, "bronze": c, "unfinished": d}

        Note that unifinished refers to either unifinished or not in top 3.
        """
        self.medal_count = {"gold":0, "silver": 0, "bronze": 0, "unfinished":0}

        for pb_dict in all_pbs:
            players = pb_dict.get("players", [])

            if len(players) > 0 and players[0]["player"].account_id == self.account_id:
                self.medal_count["gold"] += 1
            elif len(players) > 1 and players[1]["player"].account_id == self.account_id:
                self.medal_count["silver"] += 1
            elif len(players) > 2 and players[2]["player"].account_id == self.account_id:
                self.medal_count["bronze"] += 1
            else:
                self.medal_count["unfinished"] += 1
      

    def get_total_rank_points(self, all_pbs: Dict) -> None:
        """
        Sums up a player's rank points. 
        Sets attribute 'total_rank_points' which is an int.
        """
        if not hasattr(self, "medal_count"):
            self.get_rank_counts(all_pbs)

        self.total_rank_points: int = (
            1 * self.medal_count["gold"] +
            2 * self.medal_count["silver"] +
            3 * self.medal_count["bronze"] +
            5 * self.medal_count["unfinished"]
        )


PLAYERS: List[Player] = [
    Player(name="EljayKay", account_id="7e468ff6-4558-43ce-ad23-591dd86291c0", alias="Elliot"),
    Player(name="LryKo", account_id="f00ab19a-14e5-4e6e-9a45-78f1af8487e1", alias="Ellery"),
    Player(name="Timo._.o", account_id="b9b79f89-19e7-4f26-be01-03556b8890b9", alias="Timo")
]