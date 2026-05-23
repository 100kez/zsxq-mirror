"""狼吃羊基本逻辑测试。运行：python -m wolfsheep.tests"""
from __future__ import annotations
import sys

from .game import State, Move, WOLF, SHEEP, EMPTY, BOARD_SIZE


def assert_eq(actual, expected, msg=""):
    if actual != expected:
        print(f"FAIL: {msg}  期望 {expected!r}, 实际 {actual!r}")
        sys.exit(1)


def test_initial_state():
    s = State.initial()
    assert_eq(s.turn, WOLF, "狼先手")
    assert_eq(s.sheep_count, 15, "初始 15 羊")
    assert_eq(len(s.positions_of(WOLF)), 3, "初始 3 狼")
    # 狼应在第 0 行中央
    assert_eq(set(s.positions_of(WOLF)), {(0, 1), (0, 2), (0, 3)})
    # 羊在 2/3/4 行
    assert_eq(set(s.positions_of(SHEEP)),
              {(r, c) for r in (2, 3, 4) for c in range(5)})


def test_wolf_initial_moves():
    s = State.initial()
    moves = s.legal_moves()
    # 狼 (0,1)(0,2)(0,3)；下行 1 全空，第 2 行全是羊。新规则下狼可以直接跳吃：
    # 普通走子：(0,1)→(0,0), (0,1)→(1,1), (0,2)→(1,2), (0,3)→(0,4), (0,3)→(1,3)
    # 跳吃：(0,1)→(2,1), (0,2)→(2,2), (0,3)→(2,3)  ← 行 1 空、行 2 羊
    expected_set = {
        ((0, 1), (0, 0)), ((0, 1), (1, 1)), ((0, 1), (2, 1)),
        ((0, 2), (1, 2)), ((0, 2), (2, 2)),
        ((0, 3), (0, 4)), ((0, 3), (1, 3)), ((0, 3), (2, 3)),
    }
    actual = {(m.frm, m.to) for m in moves}
    assert_eq(actual, expected_set, "初始狼走法")
    caps = [m for m in moves if m.captured is not None]
    assert_eq(len(caps), 3, "初始有 3 个跳吃")


def test_capture():
    # 直接用初始局面 — 狼 (0,2)，空 (1,2)，羊 (2,2) → 跳吃到 (2,2)
    s = State.initial()
    moves = s.legal_moves()
    cap_move = next(
        (m for m in moves
         if m.frm == (0, 2) and m.to == (2, 2) and m.captured == (2, 2)),
        None,
    )
    assert cap_move is not None, "应能跳吃 (0,2)->(2,2) x(2,2)"

    s2 = s.apply(cap_move)
    assert_eq(s2.sheep_count, 14, "吃 1 羊后剩 14")
    assert_eq(s2.at(2, 2), WOLF, "狼落到羊原位")
    assert_eq(s2.at(0, 2), EMPTY, "起点空")
    assert_eq(s2.at(1, 2), EMPTY, "跨过的空格仍空")


def test_winner_wolves_eat_enough():
    # 构造只剩 2 只羊的局面
    b = [EMPTY] * 25
    b[0] = WOLF
    b[1] = WOLF
    b[2] = WOLF
    b[10] = SHEEP
    b[11] = SHEEP
    s = State(b, WOLF)
    assert_eq(s.winner(), WOLF, "羊 < 3 → 狼胜")


def test_winner_wolves_trapped():
    # 新规则下"狼无动作"=所有 4 邻位都不是空。羊必须紧贴狼围死。
    # 3 狼挤在 (0,0)(0,1)(1,0)，被相邻羊全部封死
    b = [EMPTY] * 25
    b[0] = WOLF   # (0,0)
    b[1] = WOLF   # (0,1)
    b[5] = WOLF   # (1,0)
    # 围住所有狼的 4 邻位
    b[2]  = SHEEP  # (0,2) 紧贴 (0,1) 右
    b[6]  = SHEEP  # (1,1) 紧贴 (0,1) 下，(1,0) 右
    b[10] = SHEEP  # (2,0) 紧贴 (1,0) 下
    # 上方/左方已是边界，无需堵
    s = State(b, SHEEP)
    assert_eq(s.winner(), SHEEP, "3 狼全无动作 → 羊胜")


def test_sheep_cannot_eat():
    s = State.initial()
    s_sheep_turn = State(s.board[:], SHEEP)
    moves = s_sheep_turn.legal_moves()
    assert all(m.captured is None for m in moves), "羊不能吃"


def main():
    tests = [
        test_initial_state,
        test_wolf_initial_moves,
        test_capture,
        test_winner_wolves_eat_enough,
        test_winner_wolves_trapped,
        test_sheep_cannot_eat,
    ]
    for t in tests:
        t()
        print(f"PASS  {t.__name__}")
    print(f"\n全部 {len(tests)} 个测试通过")


if __name__ == "__main__":
    main()
