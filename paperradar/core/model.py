from dataclasses import dataclass, field
from typing import List

@dataclass
class Item:
    id: str
    title: str
    abstract: str
    url: str
    published: str
    source: str
    authors: list
    venue: str
    year: str

@dataclass
class Bullets:
    similarities: List[str] = field(default_factory=list)
    ideas: List[str] = field(default_factory=list)
    tag: str = "heur"  # "heur" | "llm" | "llm_cache" | "llm_fail"
