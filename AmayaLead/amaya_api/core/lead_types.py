from typing import TypedDict
import json


class DisplayName(TypedDict):
    text:str 
    languageCode:str


class Place(TypedDict):
    displayName:DisplayName
    nationalPhoneNumber: str
    internationalPhoneNumber:str
    formattedAddress: str
    weeklyOpeningHours:str
    websiteUri:str


class HashablePlace:
    def __init__(self, place:Place) -> None:
        self.place = place

    def __eq__(self, value: object, /) -> bool:
        if not isinstance(value, HashablePlace):
            return False
        return self.place == value

    def __hash__(self) -> int:
        return hash(json.dumps(self.place,sort_keys=True))

    def __repr__(self) -> str:
        return f"HashablePlace{self.place}"
    
    def to_dict(self) -> dict:
        return self.place
