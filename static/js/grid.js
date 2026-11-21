/* 엑셀 자동 필터 같은 목록 조회 (서버 재요청 없음, 외부 라이브러리 없음)
 *
 * 사용법
 *   <div class="g-bar">                              ← 건수 · 필터 해제 버튼 (선택)
 *     <span class="g-count"></span> <button class="btn btn-sm g-clear" hidden>필터 모두 해제</button>
 *   </div>
 *   <table data-grid data-grid-bar="#막대id">
 *     <thead><tr><th data-f>칼럼</th> ...</tr></thead>   ← data-f 가 붙은 열: 필터(▾) + 머리글 클릭 정렬
 *
 *   화면을 다시 그리는 표(자바스크립트로 tbody 를 채우는 표)는 그린 뒤 Grid.refresh(table) 를 부른다.
 *
 * 동작
 *   - 머리글 ▾ : 값 목록(체크박스)에서 보일 값만 고른다. 여러 열 필터는 AND.
 *               목록에는 "다른 열 필터를 통과한 행"의 값만 나온다 (엑셀과 같음).
 *   - 머리글 글자 클릭 : 오름차순 → 내림차순 → 원래 순서.
 *   - 칸 값 : td 의 data-v 속성 → 안에 있는 입력칸/선택칸 값 → 글자 순서로 읽는다.
 *   - 상세 행 : class="g-child" 인 행은 바로 위 행에 붙어서 같이 숨겨지고 같이 정렬된다.
 *   - 빈 목록 안내 행 : data-no-filter 가 붙은 행은 건드리지 않는다.
 */
(function () {
  "use strict";
  var BLANK = "(빈 값)";
  var states = new WeakMap();

  function cellValue(td) {
    if (!td) return BLANK;
    var v;
    if (td.hasAttribute("data-v")) v = td.getAttribute("data-v");
    else {
      var inp = td.querySelector("input:not([type=checkbox]):not([type=hidden]), select, textarea");
      v = inp ? (inp.tagName === "SELECT" ? (inp.options[inp.selectedIndex] || {}).text || "" : inp.value)
              : td.textContent;
    }
    v = (v || "").replace(/\s+/g, " ").trim();
    return v === "" ? BLANK : v;
  }

  function compare(a, b) {
    if (a === b) return 0;
    if (a === BLANK) return 1;
    if (b === BLANK) return -1;
    var na = Number(a.replace(/,/g, "")), nb = Number(b.replace(/,/g, ""));
    if (!isNaN(na) && !isNaN(nb)) return na - nb;
    return a.localeCompare(b, "ko");
  }

  function units(table) {
    // [{main: tr, children: [tr...], idx: 원래순서}]
    var out = [], cur = null;
    Array.prototype.forEach.call(table.tBodies[0] ? table.tBodies[0].rows : [], function (tr) {
      if (tr.hasAttribute("data-no-filter")) return;
      if (tr.classList.contains("g-child") && cur) { cur.children.push(tr); return; }
      cur = { main: tr, children: [], idx: out.length };
      out.push(cur);
    });
    return out;
  }

  function setup(table) {
    if (states.has(table)) return states.get(table);
    var st = { table: table, filters: {}, sortCol: -1, sortDir: 0, pop: null, popCol: -1, units: [] };
    states.set(table, st);

    var bar = document.querySelector(table.getAttribute("data-grid-bar") || "_");
    st.countEl = bar ? bar.querySelector(".g-count") : null;
    st.clearBtn = bar ? bar.querySelector(".g-clear") : null;
    if (st.clearBtn) st.clearBtn.addEventListener("click", function () {
      st.filters = {};
      apply(st);
    });

    var ths = Array.prototype.slice.call(table.tHead.rows[table.tHead.rows.length - 1].cells);
    st.ths = ths;
    ths.forEach(function (th, c) {
      if (!th.hasAttribute("data-f")) return;
      th.classList.add("g-th");
      var lab = document.createElement("span");
      lab.className = "g-sort";
      lab.title = "정렬";
      while (th.firstChild) lab.appendChild(th.firstChild);
      var arrow = document.createElement("i");
      arrow.className = "g-arrow";
      lab.appendChild(arrow);
      th.appendChild(lab);
      lab.addEventListener("click", function () {
        if (st.sortCol !== c) { st.sortCol = c; st.sortDir = 1; }
        else if (st.sortDir === 1) st.sortDir = -1;
        else { st.sortCol = -1; st.sortDir = 0; }
        apply(st);
      });
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "g-fbtn";
      btn.title = "필터";
      btn.textContent = "▾";
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        if (st.popCol === c) closePop(st); else openPop(st, c, btn);
      });
      th.appendChild(btn);
    });

    document.addEventListener("click", function (e) {
      if (st.pop && !st.pop.contains(e.target)) closePop(st);
    });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") closePop(st); });
    window.addEventListener("resize", function () { closePop(st); });
    var wrap = table.parentNode;
    if (wrap) wrap.addEventListener("scroll", function () { closePop(st); });

    refresh(table);
    return st;
  }

  function passes(st, u, skipCol) {
    for (var c in st.filters) {
      if (+c === skipCol) continue;
      if (!st.filters[c][cellValue(u.main.cells[c])]) return false;
    }
    return true;
  }

  function apply(st) {
    var shown = 0;
    var list = st.units.slice();
    if (st.sortCol >= 0) {
      var c = st.sortCol, d = st.sortDir;
      list.sort(function (a, b) {
        var r = compare(cellValue(a.main.cells[c]), cellValue(b.main.cells[c]));
        if (r === 0) return a.idx - b.idx;
        // 빈 값은 방향과 관계없이 항상 아래
        var av = cellValue(a.main.cells[c]), bv = cellValue(b.main.cells[c]);
        if (av === BLANK || bv === BLANK) return r;
        return r * d;
      });
    } else {
      list.sort(function (a, b) { return a.idx - b.idx; });
    }
    var tb = st.table.tBodies[0];
    list.forEach(function (u) {
      var ok = passes(st, u, -1);
      u.main.classList.toggle("g-hide", !ok);
      u.children.forEach(function (ch) { ch.classList.toggle("g-hide-p", !ok); });
      tb.appendChild(u.main);
      u.children.forEach(function (ch) { tb.appendChild(ch); });
      if (ok) shown++;
    });
    // 빈 목록 안내 행은 맨 아래 유지
    Array.prototype.forEach.call(tb.querySelectorAll("tr[data-no-filter]"), function (tr) { tb.appendChild(tr); });

    var active = Object.keys(st.filters).length > 0;
    st.ths.forEach(function (th, i) {
      th.classList.toggle("f-on", !!st.filters[i]);
      th.classList.toggle("s-asc", st.sortCol === i && st.sortDir === 1);
      th.classList.toggle("s-desc", st.sortCol === i && st.sortDir === -1);
    });
    st.table.classList.toggle("is-filtered", active);
    if (st.countEl) {
      var total = st.units.length;
      st.countEl.innerHTML = active
        ? "표시 <b>" + shown + "</b> / 전체 " + total + "건"
        : "전체 <b>" + total + "</b>건";
    }
    if (st.clearBtn) st.clearBtn.hidden = !active;
    st.table.dispatchEvent(new CustomEvent("grid:change", { detail: { shown: shown, total: st.units.length } }));
  }

  function closePop(st) {
    if (st.pop) { st.pop.parentNode.removeChild(st.pop); st.pop = null; st.popCol = -1; }
  }

  function openPop(st, col, btn) {
    closePop(st);
    st.popCol = col;
    var counts = {};
    st.units.forEach(function (u) {
      if (!passes(st, u, col)) return;
      var v = cellValue(u.main.cells[col]);
      counts[v] = (counts[v] || 0) + 1;
    });
    var values = Object.keys(counts).sort(compare);
    var cur = st.filters[col];

    var pop = document.createElement("div");
    pop.className = "g-pop";
    pop.innerHTML =
      '<div class="g-pop-sort">' +
      '  <button type="button" class="btn btn-sm" data-act="asc">↑ 오름차순</button>' +
      '  <button type="button" class="btn btn-sm" data-act="desc">↓ 내림차순</button>' +
      '</div>' +
      '<input type="search" class="g-pop-search" placeholder="값 찾기">' +
      '<div class="g-pop-list"></div>' +
      '<div class="g-pop-actions">' +
      '  <button type="button" class="btn btn-sm" data-act="reset">이 열 해제</button>' +
      '  <span class="spacer"></span>' +
      '  <button type="button" class="btn btn-sm btn-primary" data-act="ok">확인</button>' +
      '  <button type="button" class="btn btn-sm" data-act="cancel">취소</button>' +
      '</div>';
    var list = pop.querySelector(".g-pop-list");
    var search = pop.querySelector(".g-pop-search");

    function item(label, value, checked, count) {
      var lab = document.createElement("label");
      var cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = checked;
      if (value !== null) cb.value = value;
      var txt = document.createElement("span");
      txt.className = "v";
      txt.textContent = label;
      txt.title = label;
      lab.appendChild(cb);
      lab.appendChild(txt);
      if (count != null) {
        var n = document.createElement("span");
        n.className = "n";
        n.textContent = count;
        lab.appendChild(n);
      }
      return lab;
    }

    var allLab = item("(모두 선택)", null, true, null);
    allLab.classList.add("all");
    var allCb = allLab.querySelector("input");
    list.appendChild(allLab);
    var boxes = values.map(function (v) {
      var lab = item(v, v, cur ? !!cur[v] : true, counts[v]);
      list.appendChild(lab);
      return lab;
    });

    function visibleBoxes() {
      return boxes.filter(function (l) { return l.style.display !== "none"; })
                  .map(function (l) { return l.querySelector("input"); });
    }
    function syncAll() {
      var vb = visibleBoxes();
      var on = vb.filter(function (cb) { return cb.checked; }).length;
      allCb.checked = vb.length > 0 && on === vb.length;
      allCb.indeterminate = on > 0 && on < vb.length;
    }
    allCb.addEventListener("change", function () {
      visibleBoxes().forEach(function (cb) { cb.checked = allCb.checked; });
      syncAll();
    });
    boxes.forEach(function (l) { l.querySelector("input").addEventListener("change", syncAll); });
    search.addEventListener("input", function () {
      var q = search.value.trim().toLowerCase();
      boxes.forEach(function (l) {
        var v = l.querySelector(".v").textContent.toLowerCase();
        l.style.display = !q || v.indexOf(q) !== -1 ? "" : "none";
      });
      if (q) boxes.forEach(function (l) { l.querySelector("input").checked = l.style.display !== "none"; });
      syncAll();
    });
    syncAll();

    pop.addEventListener("click", function (e) {
      var act = e.target.getAttribute && e.target.getAttribute("data-act");
      if (!act) return;
      if (act === "ok") {
        var sel = {}, nSel = 0;
        boxes.forEach(function (l) {
          var cb = l.querySelector("input");
          if (cb.checked) { sel[cb.value] = true; nSel++; }
        });
        if (nSel === values.length) delete st.filters[col]; else st.filters[col] = sel;
        apply(st);
      } else if (act === "reset") {
        delete st.filters[col];
        apply(st);
      } else if (act === "asc" || act === "desc") {
        st.sortCol = col; st.sortDir = act === "asc" ? 1 : -1;
        apply(st);
      }
      closePop(st);
    });
    search.addEventListener("keydown", function (e) {
      if (e.key === "Enter") pop.querySelector('[data-act="ok"]').click();
    });

    document.body.appendChild(pop);
    st.pop = pop;
    var rc = btn.getBoundingClientRect();
    var left = rc.left + window.pageXOffset;
    var maxLeft = window.pageXOffset + document.documentElement.clientWidth - pop.offsetWidth - 8;
    pop.style.left = Math.max(8, Math.min(left, maxLeft)) + "px";
    pop.style.top = (rc.bottom + window.pageYOffset + 2) + "px";
    search.focus();
  }

  /** tbody 를 다시 그린 뒤 호출 — 필터·정렬 상태는 유지한다. */
  function refresh(table) {
    var st = states.get(table);
    if (!st) return setup(table);
    st.units = units(table);
    apply(st);
    return st;
  }

  /** 필터·정렬을 모두 풀고 원래 순서로 */
  function reset(table) {
    var st = states.get(table);
    if (!st) return;
    st.filters = {}; st.sortCol = -1; st.sortDir = 0;
    apply(st);
  }

  window.Grid = { setup: setup, refresh: refresh, reset: reset, value: cellValue };

  function init() {
    Array.prototype.forEach.call(document.querySelectorAll("table[data-grid]"), setup);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
