"""狼吃羊 AI：迭代加深 + PVS + 静默搜索 + Killer + History + 置换表。

约定：evaluate() 从狼视角；内部 negamax 一律从当前轮到方视角；search() 返回
分数转回狼视角，方便外部统一阅读（正=狼优）。
"""
from __future__ import annotations
import time
from typing import Optional

from .game import (
    State, Move, WOLF, SHEEP, EMPTY, BOARD_SIZE, DIRS, in_bounds,
)

MATE = 100_000          # 终局基线，远大于 evaluate 量级
INF = 10_000_000
MAX_PLY = 64            # killer 表深度上限


# ── 评估函数 ─────────────────────────────────────────────────────────────────
def evaluate(s: State) -> int:
    """非终局静态评估。正 = 狼方好。"""
    wolves = s.positions_of(WOLF)
    sheep = s.positions_of(SHEEP)
    sheep_set = set(sheep)

    # 1) 物质：被吃的羊数（决定性指标）
    score = (15 - s.sheep_count) * 250

    # 2) 狼每方向遍历 → 拆三个量
    wolf_mob = 0          # 狼可移动的方向数
    wolf_threats = 0      # W → 空 → 羊：下一手即可吃
    blocking_sheep = 0    # 羊紧贴狼：堵死狼这个方向的跳吃
    for r, c in wolves:
        for dr, dc in DIRS:
            nr, nc = r + dr, c + dc
            if not in_bounds(nr, nc):
                continue
            cell = s.at(nr, nc)
            if cell == EMPTY:
                wolf_mob += 1
                jr, jc = nr + dr, nc + dc
                if in_bounds(jr, jc) and s.at(jr, jc) == SHEEP:
                    wolf_threats += 1
            elif cell == SHEEP:
                blocking_sheep += 1

    score += wolf_mob * 4
    score += wolf_threats * 90
    score -= blocking_sheep * 25

    # 3) 边角狼：行动空间小，离被围死更近
    edge_pen = 0
    for r, c in wolves:
        edge_pen += (r == 0) + (r == BOARD_SIZE - 1) + (c == 0) + (c == BOARD_SIZE - 1)
    score -= edge_pen * 4

    # 4) 羊群凝聚（次要）
    pair_count = 0
    for r, c in sheep:
        if (r, c + 1) in sheep_set:
            pair_count += 1
        if (r + 1, c) in sheep_set:
            pair_count += 1
    score -= pair_count * 2

    # 5) 狼协同度：3 狼互相过远 → 难配合
    if len(wolves) >= 2:
        spread = 0
        for i in range(len(wolves)):
            for j in range(i + 1, len(wolves)):
                spread += abs(wolves[i][0] - wolves[j][0]) + abs(wolves[i][1] - wolves[j][1])
        score -= spread

    return score


def _eval_for_side(s: State) -> int:
    """评估值从 s.turn 视角。"""
    e = evaluate(s)
    return e if s.turn == WOLF else -e


class _TimeUp(Exception):
    pass


# ── 搜索器 ──────────────────────────────────────────────────────────────────
class Searcher:
    """迭代加深 + PVS + 静默搜索 + Killer + History + TT。"""

    def __init__(self, max_depth: int = 10, time_limit: float = 3.0):
        self.max_depth = max_depth
        self.time_limit = time_limit
        # 置换表: key -> (depth, score, flag, best_move)
        # flag: 'exact' | 'lower' | 'upper'
        self.tt: dict = {}
        # killer[ply] = [Move, Move]
        self.killers: list[list[Optional[Move]]] = []
        # history[(turn, frm, to)] = count
        self.history: dict = {}
        self.nodes = 0
        self._deadline = 0.0

    # ── Public ──────────────────────────────────────────────────────────
    def search(self, s: State) -> tuple[Optional[Move], int]:
        """迭代加深。返回 (最佳走法, 从狼视角的分数)。"""
        self.killers = [[None, None] for _ in range(MAX_PLY)]
        self.history = {}
        self.tt = {}
        self.nodes = 0
        self._deadline = time.time() + self.time_limit

        best_move: Optional[Move] = None
        best_score_side = 0      # 当前轮到方视角
        pv_move: Optional[Move] = None

        for depth in range(1, self.max_depth + 1):
            try:
                score, move = self._root(s, depth, pv_move)
            except _TimeUp:
                break
            if move is None:
                break
            best_move = move
            best_score_side = score
            pv_move = move
            # 已经找到必杀就不必再深
            if score >= MATE - MAX_PLY:
                break

        # 转回狼视角
        wolf_score = best_score_side if s.turn == WOLF else -best_score_side
        return best_move, wolf_score

    # ── Root search ────────────────────────────────────────────────────
    def _root(self, s: State, depth: int, pv_move: Optional[Move]) -> tuple[int, Optional[Move]]:
        moves = s.legal_moves()
        if not moves:
            return -(MATE - 0), None

        moves = self._order_moves(s, moves, 0, pv_move)
        best_score = -INF
        best_move = moves[0]
        alpha, beta = -INF, INF

        for i, m in enumerate(moves):
            child = s.apply(m)
            if i == 0:
                sc = -self._negamax(child, depth - 1, -beta, -alpha, 1)
            else:
                # PVS: 用零窗口快速验证「不会更好」
                sc = -self._negamax(child, depth - 1, -alpha - 1, -alpha, 1)
                if alpha < sc < beta:
                    sc = -self._negamax(child, depth - 1, -beta, -sc, 1)
            if sc > best_score:
                best_score, best_move = sc, m
            if sc > alpha:
                alpha = sc
        return best_score, best_move

    # ── Negamax ────────────────────────────────────────────────────────
    def _negamax(self, s: State, depth: int, alpha: int, beta: int, ply: int) -> int:
        if time.time() > self._deadline:
            raise _TimeUp
        self.nodes += 1

        # 终局：胜方判断与 s.turn 比较，越早分数越高
        w = s.winner()
        if w is not None:
            return (MATE - ply) if w == s.turn else -(MATE - ply)

        # 深度耗尽 → 进入静默搜索
        if depth <= 0:
            return self._quiesce(s, alpha, beta, ply)

        # TT 查询
        key = s.key()
        tt_move: Optional[Move] = None
        entry = self.tt.get(key)
        if entry is not None:
            d_st, sc_st, flag_st, mv_st = entry
            tt_move = mv_st
            if d_st >= depth:
                if flag_st == "exact":
                    return sc_st
                if flag_st == "lower" and sc_st >= beta:
                    return sc_st
                if flag_st == "upper" and sc_st <= alpha:
                    return sc_st

        moves = s.legal_moves()
        if not moves:
            return -(MATE - ply)

        moves = self._order_moves(s, moves, ply, tt_move)

        original_alpha = alpha
        best_score = -INF
        best_move = moves[0]

        for i, m in enumerate(moves):
            child = s.apply(m)
            if i == 0:
                sc = -self._negamax(child, depth - 1, -beta, -alpha, ply + 1)
            else:
                sc = -self._negamax(child, depth - 1, -alpha - 1, -alpha, ply + 1)
                if alpha < sc < beta:
                    sc = -self._negamax(child, depth - 1, -beta, -sc, ply + 1)

            if sc > best_score:
                best_score, best_move = sc, m
            if sc > alpha:
                alpha = sc
            if alpha >= beta:
                # beta-cutoff
                if not m.captured:
                    self._store_killer(ply, m)
                    h_key = (s.turn, m.frm, m.to)
                    self.history[h_key] = self.history.get(h_key, 0) + depth * depth
                break

        # 存 TT
        if best_score <= original_alpha:
            flag = "upper"
        elif best_score >= beta:
            flag = "lower"
        else:
            flag = "exact"
        self.tt[key] = (depth, best_score, flag, best_move)
        return best_score

    # ── Quiescence ─────────────────────────────────────────────────────
    def _quiesce(self, s: State, alpha: int, beta: int, ply: int) -> int:
        """静默搜索：在主搜索深度耗尽后继续追跳吃，消除地平线效应。

        本游戏只有狼能吃，所以只有狼的回合才有 noisy 走法可搜。
        """
        if time.time() > self._deadline:
            raise _TimeUp
        self.nodes += 1

        w = s.winner()
        if w is not None:
            return (MATE - ply) if w == s.turn else -(MATE - ply)

        # Stand-pat：当前位置不动的评估
        stand = _eval_for_side(s)
        if stand >= beta:
            return stand
        if stand > alpha:
            alpha = stand

        # 羊回合无吃法，直接返回 stand-pat
        if s.turn != WOLF:
            return alpha

        if ply >= MAX_PLY - 2:
            return alpha

        captures = [m for m in s.legal_moves() if m.captured]
        if not captures:
            return alpha

        for m in captures:
            child = s.apply(m)
            sc = -self._quiesce(child, -beta, -alpha, ply + 1)
            if sc >= beta:
                return sc
            if sc > alpha:
                alpha = sc
        return alpha

    # ── Move ordering ──────────────────────────────────────────────────
    def _order_moves(self, s: State, moves: list[Move], ply: int,
                     hint: Optional[Move]) -> list[Move]:
        """排序：PV/TT 走法 → 吃子 → killer → 按 history 排序的其余。"""
        killers = self.killers[ply] if ply < len(self.killers) else [None, None]
        hist = self.history

        def score(m: Move) -> int:
            if hint is not None and m.frm == hint.frm and m.to == hint.to:
                return 10_000_000
            if m.captured is not None:
                return 1_000_000
            for i, k in enumerate(killers):
                if k is not None and k.frm == m.frm and k.to == m.to:
                    return 500_000 - i
            return hist.get((s.turn, m.frm, m.to), 0)

        return sorted(moves, key=score, reverse=True)

    def _store_killer(self, ply: int, m: Move) -> None:
        if ply >= len(self.killers):
            return
        killers = self.killers[ply]
        if killers[0] is not None and killers[0].frm == m.frm and killers[0].to == m.to:
            return
        killers[1] = killers[0]
        killers[0] = m
