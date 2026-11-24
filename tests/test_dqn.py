"""Tests for the deep Q-network attacker."""
from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")

from rl.agent import QLearningAgent
from rl.arena import ACTION_SPACE
from rl.deep_arena import DeepSimArena
from rl.dqn_agent import DQNAgent
from rl.features import STATE_DIM, encode


def test_dqn_interface_and_checkpoint(tmp_path):
    agent = DQNAgent(seed=1)
    state = encode(None, None, 0, agent.epsilon)
    assert len(state) == STATE_DIM
    assert agent.choose(state) in ACTION_SPACE
    assert len(agent.q_values(state)) == len(ACTION_SPACE)

    arena = DeepSimArena(seed=1)
    for index in range(40):
        action = ACTION_SPACE[index % len(ACTION_SPACE)]
        result = arena.step(action)
        agent.remember(state, action, result.reward, encode(result, action, index, agent.epsilon))
    for _ in range(40):
        agent.train_step()
    assert agent.steps > 0
    assert agent.ranked(state)

    path = agent.save(tmp_path / "dqn.pt")
    loaded = DQNAgent.load(path)
    assert loaded.q_values(state) == pytest.approx(agent.q_values(state), abs=1e-6)


def test_competitive_dqn_beats_tabular_on_seeded_arena():
    deep = DQNAgent.load("ml/deep/dqn.pt")
    deep.epsilon = 0.0
    tabular = QLearningAgent()
    tabular.epsilon = 0.0
    arena = DeepSimArena(seed=9000)

    deep_total = 0.0
    for episode in range(5):
        arena.reset(9000 + episode)
        state = encode(None, None, 0, 0.0, 12)
        episode_total = 0.0
        for step in range(12):
            action = deep.best_action(state)
            result = arena.step(action)
            episode_total += result.reward
            state = encode(result, action, step, 0.0, 12)
        deep_total += episode_total / 12

    tabular_total = 0.0
    for episode in range(5):
        arena.reset(9000 + episode)
        state = "calm"
        episode_total = 0.0
        for step in range(12):
            action = tabular.best_action(state)
            result = arena.step(action)
            episode_total += result.reward
            state = result.state
        tabular_total += episode_total / 12

    assert deep_total > tabular_total
