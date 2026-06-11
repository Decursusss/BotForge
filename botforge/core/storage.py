from __future__ import annotations
import json
import dataclasses
from pathlib import Path
from typing import Optional

from .models import BotConfig, Trigger, Block, Action


def _to_dict(obj) -> dict:
    return dataclasses.asdict(obj)


def _action_from_dict(d: Optional[dict]) -> Optional[Action]:
    if d is None:
        return None
    return Action(**{k: v for k, v in d.items() if k in Action.__dataclass_fields__})


def _trigger_from_dict(d: dict) -> Trigger:
    return Trigger(**{k: v for k, v in d.items() if k in Trigger.__dataclass_fields__})


def _block_from_dict(d: dict) -> Block:
    action = _action_from_dict(d.get("action"))
    actions = [a for a in (_action_from_dict(x) for x in d.get("actions", [])) if a]
    return Block(
        id=d.get("id", ""),
        type=d.get("type", "action"),
        label=d.get("label", ""),
        action=action,
        actions=actions,
        trigger_id=d.get("trigger_id"),
        wait_timeout_ms=d.get("wait_timeout_ms", 10000),
        repeat_delay_ms=d.get("repeat_delay_ms", 200),
        max_repeats=d.get("max_repeats", 0),
        invert=d.get("invert", False),
    )


def save_config(config: BotConfig, path: str) -> None:
    data = _to_dict(config)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_config(path: str) -> BotConfig:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    triggers = [_trigger_from_dict(t) for t in data.get("triggers", [])]
    blocks = [_block_from_dict(b) for b in data.get("blocks", [])]

    return BotConfig(
        name=data.get("name", "Бот"),
        loop=data.get("loop", True),
        loop_delay_ms=data.get("loop_delay_ms", 50),
        max_iterations=data.get("max_iterations", 0),
        triggers=triggers,
        blocks=blocks,
    )
