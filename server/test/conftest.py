from __future__ import annotations

import os
from datetime import datetime

import pytest

os.environ["NEWS_APP_ENV"] = "demo"
os.environ["NEWS_DECISION_ENGINE"] = "heuristic"

from Core.registry import SourceRegistry
from Core.settings import Settings
from test.helpers import NOW
from tool.decisions_heuristic import HeuristicDecisionEngine
from tool.fixture_adapters import StaticClock


@pytest.fixture
def now() -> datetime:
    return NOW


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, app_env="demo")


@pytest.fixture
def registry() -> SourceRegistry:
    return SourceRegistry.load()


@pytest.fixture
def clock() -> StaticClock:
    return StaticClock(NOW)


@pytest.fixture
def decisions() -> HeuristicDecisionEngine:
    return HeuristicDecisionEngine()
