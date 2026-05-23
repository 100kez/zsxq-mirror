/* 狼吃羊棋 — 前端棋盘 */
(function () {
  "use strict";

  const N = 5;
  const WOLF = "W", SHEEP = "S", EMPTY = ".";

  const boardEl = document.getElementById("ws-board");
  const turnEl = document.getElementById("ws-turn");
  const sheepEl = document.getElementById("ws-sheep");
  const winnerEl = document.getElementById("ws-winner");
  const thinkingEl = document.getElementById("ws-thinking");
  const newBtn = document.getElementById("ws-new");
  const sideSel = document.getElementById("ws-side");
  const strengthSel = document.getElementById("ws-strength");

  // ── State ──────────────────────────────────────────────────────────
  let state = JSON.parse(document.getElementById("ws-initial").textContent);
  let humanSide = sideSel.value;
  let selectedFrm = null;          // [r,c] of currently selected piece
  let legalTargets = [];           // [{frm,to,captured}]
  let lastMove = null;             // { frm:[r,c], to:[r,c], captured:[r,c]|null }
  let busy = false;

  // ── Render ─────────────────────────────────────────────────────────
  function cellAt(r, c) { return state.board[r * N + c]; }

  function render() {
    boardEl.innerHTML = "";
    const css = getComputedStyle(boardEl);
    const cell = parseFloat(css.getPropertyValue("--cell"));

    // Compute target sets if a piece is selected
    const moveTargets = new Set();      // 普通走子的目标（空点）
    const captureTargets = new Set();   // 跳吃的目标（羊点）
    if (selectedFrm) {
      legalTargets.forEach(m => {
        const idx = m.to[0] * N + m.to[1];
        if (m.captured) captureTargets.add(idx);
        else moveTargets.add(idx);
      });
    }

    for (let r = 0; r < N; r++) {
      for (let c = 0; c < N; c++) {
        const piece = cellAt(r, c);
        const idx = r * N + c;
        const div = document.createElement("div");
        // 棋子落到交叉点：(c*cell, r*cell)，再靠 CSS 的 translate(-50%, -50%) 居中
        div.style.left = (c * cell) + "px";
        div.style.top  = (r * cell) + "px";
        div.dataset.r = r;
        div.dataset.c = c;

        if (piece === WOLF) {
          div.className = "ws-cell wolf";
          div.textContent = "狼";
        } else if (piece === SHEEP) {
          div.className = "ws-cell sheep";
          div.textContent = "羊";
          if (captureTargets.has(idx)) div.classList.add("capture-target");
        } else {
          div.className = "ws-cell empty";
          if (moveTargets.has(idx)) div.classList.add("target");
        }

        // Highlight selected piece
        if (selectedFrm && selectedFrm[0] === r && selectedFrm[1] === c) {
          div.classList.add("selected");
        }
        // Highlight last move
        if (lastMove) {
          if (lastMove.frm[0] === r && lastMove.frm[1] === c) div.classList.add("last-from");
          if (lastMove.to[0]  === r && lastMove.to[1]  === c) div.classList.add("last-to");
        }

        // Click handler
        div.addEventListener("click", () => onCellClick(r, c));
        boardEl.appendChild(div);
      }
    }

    turnEl.textContent = state.turn === WOLF ? "狼" : "羊";
    sheepEl.textContent = state.sheep_count;
    if (state.winner) {
      winnerEl.textContent = (state.winner === WOLF ? "狼" : "羊") + "胜！";
    } else {
      winnerEl.textContent = "";
    }
  }

  // ── Click logic ────────────────────────────────────────────────────
  function onCellClick(r, c) {
    if (busy || state.winner) return;
    if (state.turn !== humanSide) return;

    const piece = cellAt(r, c);

    // 选择自己一颗子
    if (piece === humanSide) {
      selectedFrm = [r, c];
      legalTargets = (state.legal_moves || []).filter(m => m.frm[0] === r && m.frm[1] === c);
      render();
      return;
    }

    // 已选中 & 点击合法目标 → 提交
    if (selectedFrm) {
      const tgt = legalTargets.find(m => m.to[0] === r && m.to[1] === c);
      if (tgt) {
        submitMove(selectedFrm, [r, c]);
        return;
      }
      // 点空白或对方子：取消选择
      selectedFrm = null;
      legalTargets = [];
      render();
    }
  }

  // ── Server I/O ─────────────────────────────────────────────────────
  function submitMove(frm, to) {
    if (busy) return;
    busy = true;
    selectedFrm = null;
    legalTargets = [];
    thinkingEl.hidden = false;

    const [t, d] = strengthSel.value.split(",");

    fetch(window.location.pathname.replace(/\/?$/, "/") + "move/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        board: state.board,
        turn: state.turn,
        move: { frm, to },
        human_side: humanSide,
        ai_time_limit: parseFloat(t),
        ai_depth: parseInt(d, 10),
      }),
    })
      .then(r => r.json().then(j => ({ ok: r.ok, j })))
      .then(({ ok, j }) => {
        if (!ok) {
          alert("出错：" + (j.error || "未知"));
          return;
        }
        state = j.state;
        lastMove = j.ai_move || j.player_move || null;
        render();
      })
      .catch(err => alert("网络错：" + err))
      .finally(() => {
        busy = false;
        thinkingEl.hidden = true;
      });
  }

  // ── New game ───────────────────────────────────────────────────────
  function newGame() {
    humanSide = sideSel.value;
    state = initialState();
    selectedFrm = null;
    legalTargets = [];
    lastMove = null;
    syncWithServer();
  }

  // 同步：把当前 state 发给后端；若现在轮到 AI，AI 会走一步后返回新状态
  function syncWithServer() {
    if (busy) return;
    busy = true;
    thinkingEl.hidden = (state.turn === humanSide);

    const [t, d] = strengthSel.value.split(",");
    fetch(window.location.pathname.replace(/\/?$/, "/") + "move/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        board: state.board,
        turn: state.turn,
        move: null,
        human_side: humanSide,
        ai_time_limit: parseFloat(t),
        ai_depth: parseInt(d, 10),
      }),
    })
      .then(r => r.json().then(j => ({ ok: r.ok, j })))
      .then(({ ok, j }) => {
        if (!ok) {
          alert("出错：" + (j.error || "未知"));
          return;
        }
        state = j.state;
        if (j.ai_move) lastMove = j.ai_move;
        render();
      })
      .catch(err => alert("网络错：" + err))
      .finally(() => {
        busy = false;
        thinkingEl.hidden = true;
      });
  }

  function initialBoard() {
    const b = Array(N * N).fill(EMPTY);
    [[0, 1], [0, 2], [0, 3]].forEach(([r, c]) => b[r * N + c] = WOLF);
    for (let r = 2; r < 5; r++) for (let c = 0; c < N; c++) b[r * N + c] = SHEEP;
    return b;
  }

  function initialState() {
    return {
      board: initialBoard(),
      turn: WOLF,
      sheep_count: 15,
      winner: null,
      legal_moves: [],
    };
  }

  // ── Wire up ────────────────────────────────────────────────────────
  newBtn.addEventListener("click", newGame);
  sideSel.addEventListener("change", () => {
    if (confirm("切换执子方将开始新对局，确定？")) newGame();
    else sideSel.value = humanSide;
  });

  render();
  // 页面初次加载：若现在轮到 AI，让 AI 走第一手
  if (state.turn !== humanSide && !state.winner) {
    syncWithServer();
  }
})();
