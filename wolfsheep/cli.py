"""命令行界面：人机对弈 + AI 自对弈。

用法：
  python -m wolfsheep.cli              # 人机对弈，玩家执羊
  python -m wolfsheep.cli --side wolf  # 玩家执狼
  python -m wolfsheep.cli --selfplay   # AI 自对弈
"""
from __future__ import annotations
import argparse
import re
import sys
import time

from .game import State, Move, WOLF, SHEEP, EMPTY, BOARD_SIZE, DIRS, in_bounds
from .ai import Searcher


COORD_RE = re.compile(r"^\s*(\d)\s*[, ]\s*(\d)\s*->\s*(\d)\s*[, ]\s*(\d)\s*$")


def parse_human_move(text: str, state: State) -> Move | None:
    """解析 'r,c -> r,c' 格式的输入。"""
    m = COORD_RE.match(text)
    if not m:
        return None
    fr, fc, tr, tc = map(int, m.groups())
    if not (in_bounds(fr, fc) and in_bounds(tr, tc)):
        return None
    # 在 legal_moves 里找匹配
    for mv in state.legal_moves():
        if mv.frm == (fr, fc) and mv.to == (tr, tc):
            return mv
    return None


def human_vs_ai(human_side: str, time_limit: float = 2.0, max_depth: int = 8):
    state = State.initial()
    ai = Searcher(max_depth=max_depth, time_limit=time_limit)
    print(f"你执 {'狼' if human_side == WOLF else '羊'}，AI 执对方。")
    print("输入格式：r,c -> r,c   （例如 2,0 -> 1,0）")
    while True:
        print()
        print(state.render())
        win = state.winner()
        if win is not None:
            print(f"\n=== {'狼' if win == WOLF else '羊'}胜 ===")
            return
        if state.turn == human_side:
            moves = state.legal_moves()
            print(f"你的合法走法（{len(moves)}）：")
            for i, mv in enumerate(moves[:20]):
                print(f"  [{i}] {mv}")
            if len(moves) > 20:
                print(f"  ... 还有 {len(moves) - 20} 个")
            raw = input("> 输入走法或编号: ").strip()
            mv: Move | None = None
            if raw.isdigit() and int(raw) < len(moves):
                mv = moves[int(raw)]
            else:
                mv = parse_human_move(raw, state)
            if mv is None:
                print("非法走法，重输")
                continue
            state = state.apply(mv)
        else:
            t0 = time.time()
            mv, score = ai.search(state)
            dt = time.time() - t0
            print(f"AI 走 {mv}  分={score}  节点={ai.nodes}  用时={dt:.2f}s")
            if mv is None:
                print("AI 无合法走法")
                return
            state = state.apply(mv)


def self_play(time_limit: float = 1.0, max_depth: int = 6, verbose: bool = True):
    state = State.initial()
    ai = Searcher(max_depth=max_depth, time_limit=time_limit)
    history: dict[tuple, int] = {}
    moves_since_capture = 0
    turn_no = 0
    while True:
        if verbose:
            print()
            print(state.render())
        win = state.winner()
        if win is not None:
            print(f"\n=== {'狼' if win == WOLF else '羊'}胜（{turn_no} 回合）===")
            return win
        # 三次重复判和
        k = state.key()
        history[k] = history.get(k, 0) + 1
        if history[k] >= 3:
            print(f"\n=== 三次重复局面，平局（{turn_no} 回合）===")
            return None
        if moves_since_capture >= 50:
            print(f"\n=== 50 步无吃子，平局（{turn_no} 回合）===")
            return None
        t0 = time.time()
        mv, score = ai.search(state)
        dt = time.time() - t0
        print(f"[{turn_no:03d}] {state.turn} 走 {mv}  分={score}  节点={ai.nodes}  {dt:.2f}s")
        if mv is None:
            print(f"无合法走法，{state.turn} 输")
            return
        moves_since_capture = 0 if mv.captured else moves_since_capture + 1
        state = state.apply(mv)
        turn_no += 1
        if turn_no > 500:
            print("回合数过多，平局")
            return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--side", choices=["wolf", "sheep"], default="sheep",
                   help="人类执子方（默认羊）")
    p.add_argument("--selfplay", action="store_true", help="AI 自对弈")
    p.add_argument("--time", type=float, default=2.0, help="AI 每步思考秒数")
    p.add_argument("--depth", type=int, default=8, help="最大搜索深度")
    args = p.parse_args()
    if args.selfplay:
        self_play(time_limit=args.time, max_depth=args.depth)
    else:
        side = WOLF if args.side == "wolf" else SHEEP
        human_vs_ai(side, time_limit=args.time, max_depth=args.depth)


if __name__ == "__main__":
    main()
