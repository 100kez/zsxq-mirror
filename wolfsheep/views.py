"""狼吃羊棋 Web 视图。

无状态：前端持有棋盘，每次出招把 (board, turn, move) 提交上来，
后端验证 + 落子 + 让 AI 走，再返回新状态。
"""
import json

from django.http import JsonResponse, HttpResponseBadRequest
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET

from .ai import Searcher
from .game import (
    BOARD_SIZE, EMPTY, SHEEP, WOLF, Move, State,
)


# ─────────────────────────────────────────────────────────────────────────────
# 序列化辅助
# ─────────────────────────────────────────────────────────────────────────────
def _serialize_state(s: State) -> dict:
    return {
        "board": s.board,
        "turn": s.turn,
        "sheep_count": s.sheep_count,
        "winner": s.winner(),
        "legal_moves": [
            {"frm": list(m.frm), "to": list(m.to),
             "captured": list(m.captured) if m.captured else None}
            for m in s.legal_moves()
        ],
    }


def _deserialize_state(data: dict) -> State:
    board = list(data["board"])
    turn = data["turn"]
    if len(board) != BOARD_SIZE * BOARD_SIZE:
        raise ValueError("board 长度错")
    if any(c not in (EMPTY, WOLF, SHEEP) for c in board):
        raise ValueError("board 含非法字符")
    if turn not in (WOLF, SHEEP):
        raise ValueError("turn 非法")
    return State(board, turn)


def _find_legal(state: State, frm: tuple[int, int], to: tuple[int, int]) -> Move | None:
    for m in state.legal_moves():
        if m.frm == frm and m.to == to:
            return m
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 视图
# ─────────────────────────────────────────────────────────────────────────────
@require_GET
def board_page(request):
    """棋盘页面。"""
    initial = _serialize_state(State.initial())
    return render(request, "wolfsheep/board.html", {
        "initial_state_json": json.dumps(initial),
    })


@csrf_exempt
@require_POST
def api_move(request):
    """玩家走一步 → 后端校验 + 应用 → AI 接着走 → 返回新状态。

    入参 JSON:
      { board: [...25...], turn: 'W'|'S',
        move: { frm: [r,c], to: [r,c] },
        human_side: 'W'|'S',
        ai_time_limit: 2.0, ai_depth: 8 }
    """
    try:
        payload = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return HttpResponseBadRequest("invalid json")

    try:
        state = _deserialize_state(payload)
    except (KeyError, ValueError) as e:
        return JsonResponse({"error": f"state invalid: {e}"}, status=400)

    human_side = payload.get("human_side", SHEEP)
    if human_side not in (WOLF, SHEEP):
        return JsonResponse({"error": "human_side 非法"}, status=400)

    # 终局直接返回
    if state.winner() is not None:
        return JsonResponse({"state": _serialize_state(state), "ai_move": None})

    # 1) 若该玩家走，应用其走子（若未带走子，则视为请求初始/AI 走的状态）
    player_move = None
    if state.turn == human_side:
        mv = payload.get("move")
        if mv is None:
            # 玩家是当前回合但未走子（例如刚开局、玩家先手）→ 直接返回当前状态
            return JsonResponse({
                "state": _serialize_state(state),
                "player_move": None,
                "ai_move": None,
            })
        try:
            frm = tuple(mv["frm"])
            to = tuple(mv["to"])
        except (KeyError, TypeError):
            return JsonResponse({"error": "move 格式错"}, status=400)
        legal = _find_legal(state, frm, to)
        if legal is None:
            return JsonResponse({"error": "非法走子"}, status=400)
        player_move = legal
        state = state.apply(legal)

    # 终局检查
    if state.winner() is not None:
        return JsonResponse({
            "state": _serialize_state(state),
            "player_move": _move_to_dict(player_move) if player_move else None,
            "ai_move": None,
        })

    # 2) AI 接着走（若还轮到 AI）
    ai_move_dict = None
    if state.turn != human_side:
        time_limit = float(payload.get("ai_time_limit", 2.0))
        max_depth = int(payload.get("ai_depth", 8))
        searcher = Searcher(max_depth=max_depth, time_limit=time_limit)
        ai_move, _score = searcher.search(state)
        if ai_move is not None:
            ai_move_dict = _move_to_dict(ai_move)
            state = state.apply(ai_move)

    return JsonResponse({
        "state": _serialize_state(state),
        "player_move": _move_to_dict(player_move) if player_move else None,
        "ai_move": ai_move_dict,
    })


def _move_to_dict(m: Move) -> dict:
    return {
        "frm": list(m.frm),
        "to": list(m.to),
        "captured": list(m.captured) if m.captured else None,
    }
