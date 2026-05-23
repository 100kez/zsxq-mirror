"""狼吃羊棋核心：5×5 交叉点，纯横竖连线，3 狼 vs 15 羊。

规则:
  - 棋盘 5×5，仅横竖相邻可走
  - 双方一步只能走一格到相邻空点
  - 狼跳吃：狼 → 空 → 羊（同方向相连），狼跳到羊的位置吃掉，一回合仅一次
  - 羊不能吃
  - 终局：羊 < 3 只 → 狼胜；3 狼全部无合法动作 → 羊胜
  - 狼先手
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterator, Optional

BOARD_SIZE = 5
WOLF = "W"
SHEEP = "S"
EMPTY = "."

DIRS = ((-1, 0), (1, 0), (0, -1), (0, 1))

INITIAL_WOLVES = ((0, 1), (0, 2), (0, 3))
INITIAL_SHEEP = tuple((r, c) for r in (2, 3, 4) for c in range(5))
# 棋盘 5×5：第 0 行放 3 狼（中央 3 点），第 1 行空，第 2/3/4 行 15 羊


def in_bounds(r: int, c: int) -> bool:
    return 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE


@dataclass(frozen=True)
class Move:
    """from_pos → to_pos；若是跳吃，captured 是被吃羊的位置。"""
    frm: tuple[int, int]
    to: tuple[int, int]
    captured: Optional[tuple[int, int]] = None

    def __repr__(self) -> str:
        s = f"{self.frm}->{self.to}"
        if self.captured:
            s += f" x{self.captured}"
        return s


class State:
    __slots__ = ("board", "turn", "_sheep_count")

    def __init__(self, board: list[str], turn: str):
        self.board = board  # 25 长度的列表
        self.turn = turn
        self._sheep_count = sum(1 for c in board if c == SHEEP)

    @classmethod
    def initial(cls) -> "State":
        b = [EMPTY] * (BOARD_SIZE * BOARD_SIZE)
        for r, c in INITIAL_WOLVES:
            b[r * BOARD_SIZE + c] = WOLF
        for r, c in INITIAL_SHEEP:
            b[r * BOARD_SIZE + c] = SHEEP
        return cls(b, WOLF)

    # ── 访问器 ────────────────────────────────────────────────────────────
    def at(self, r: int, c: int) -> str:
        return self.board[r * BOARD_SIZE + c]

    def positions_of(self, piece: str) -> list[tuple[int, int]]:
        return [
            (i // BOARD_SIZE, i % BOARD_SIZE)
            for i, v in enumerate(self.board)
            if v == piece
        ]

    @property
    def sheep_count(self) -> int:
        return self._sheep_count

    def copy(self) -> "State":
        return State(self.board[:], self.turn)

    def key(self) -> tuple:
        return (tuple(self.board), self.turn)

    # ── 走子生成 ─────────────────────────────────────────────────────────
    def legal_moves(self) -> list[Move]:
        if self.turn == WOLF:
            return self._wolf_moves()
        return self._sheep_moves()

    def _wolf_moves(self) -> list[Move]:
        moves: list[Move] = []
        captures: list[Move] = []
        for r, c in self.positions_of(WOLF):
            for dr, dc in DIRS:
                nr, nc = r + dr, c + dc
                if not in_bounds(nr, nc):
                    continue
                if self.at(nr, nc) != EMPTY:
                    continue
                # 普通走一格
                moves.append(Move((r, c), (nr, nc)))
                # 跳吃：W → 空 → 羊，狼落到羊位置吃掉
                jr, jc = nr + dr, nc + dc
                if in_bounds(jr, jc) and self.at(jr, jc) == SHEEP:
                    captures.append(Move((r, c), (jr, jc), (jr, jc)))
        # 吃子动作优先，提高 alpha-beta 剪枝效率
        return captures + moves

    def _sheep_moves(self) -> list[Move]:
        moves: list[Move] = []
        for r, c in self.positions_of(SHEEP):
            for dr, dc in DIRS:
                nr, nc = r + dr, c + dc
                if in_bounds(nr, nc) and self.at(nr, nc) == EMPTY:
                    moves.append(Move((r, c), (nr, nc)))
        return moves

    # ── 应用走子 ─────────────────────────────────────────────────────────
    def apply(self, m: Move) -> "State":
        new_board = self.board[:]
        fr, fc = m.frm
        tr, tc = m.to
        piece = new_board[fr * BOARD_SIZE + fc]
        # 先清空起点和被吃位置，再落子（吃子时落点 == 被吃位置，必须最后落）
        new_board[fr * BOARD_SIZE + fc] = EMPTY
        if m.captured:
            cr, cc = m.captured
            new_board[cr * BOARD_SIZE + cc] = EMPTY
        new_board[tr * BOARD_SIZE + tc] = piece
        next_turn = SHEEP if self.turn == WOLF else WOLF
        return State(new_board, next_turn)

    # ── 终局判定 ─────────────────────────────────────────────────────────
    def winner(self) -> Optional[str]:
        """返回 'W' / 'S' 或 None（未结束）。"""
        if self._sheep_count < 3:
            return WOLF
        # 3 狼全部无任何走法 → 羊胜（不管轮到谁）
        if not self._any_wolf_can_act():
            return SHEEP
        # 轮到当前方但无合法走法 → 当前方判负
        if not self.legal_moves():
            return SHEEP if self.turn == WOLF else WOLF
        return None

    def _any_wolf_can_act(self) -> bool:
        for r, c in self.positions_of(WOLF):
            for dr, dc in DIRS:
                nr, nc = r + dr, c + dc
                if in_bounds(nr, nc) and self.at(nr, nc) == EMPTY:
                    return True  # 普通走子或跳吃，至少能走
        return False

    # ── 显示 ─────────────────────────────────────────────────────────────
    def render(self) -> str:
        rows = ["    " + " ".join(str(c) for c in range(BOARD_SIZE))]
        rows.append("   " + "--" * BOARD_SIZE)
        for r in range(BOARD_SIZE):
            line = f"{r} | " + " ".join(self.at(r, c) for c in range(BOARD_SIZE))
            rows.append(line)
        rows.append(f"turn: {self.turn}   sheep: {self._sheep_count}")
        return "\n".join(rows)
