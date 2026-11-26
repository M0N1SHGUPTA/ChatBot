/*!
 * JIBB Assistant: embeddable chat widget.
 *
 *   <script src="https://YOUR-CHATBOT-DOMAIN/widget.js" defer></script>
 *
 * The API base is taken from this script's own URL, so the one tag is all a site needs.
 * Optional attributes on the tag:
 *   data-api="https://..."     use a different API base
 *   data-lang="en" | "ja"      force the UI language (default: <html lang> or a /ja/ path)
 *   data-position="left"       launcher on the bottom-left instead of bottom-right
 *   data-open="true"           open the panel on page load
 *
 * Everything renders inside a Shadow DOM, so the host page's CSS can't break the widget
 * and the widget's CSS can't leak into the page.
 */
(function () {
  "use strict";
  if (window.__jibbChatWidget) return;
  window.__jibbChatWidget = true;

  var script = document.currentScript || (function () {
    var all = document.querySelectorAll('script[src*="widget.js"]');
    return all[all.length - 1];
  })();
  var opt = (script && script.dataset) || {};
  var API = (opt.api || (script ? new URL(script.src, location.href).origin : "")).replace(/\/+$/, "");

  // ---------------------------------------------------------------- storage (never required)
  var NS = "jibb_chat_";
  function sget(store, k) { try { return window[store].getItem(NS + k); } catch (e) { return null; } }
  function sset(store, k, v) { try { window[store].setItem(NS + k, v); } catch (e) { /* private mode */ } }

  function newId() {
    try { if (crypto.randomUUID) return "w_" + crypto.randomUUID(); } catch (e) {}
    return "w_" + Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
  }
  var sessionId = sget("localStorage", "sid") || newId();
  sset("localStorage", "sid", sessionId);

  // ---------------------------------------------------------------- language
  var lang = opt.lang || ((document.documentElement.lang || "").toLowerCase().indexOf("ja") === 0 ||
    /^\/ja(\/|$)/.test(location.pathname) ? "ja" : "en");
  var T = {
    en: {
      title: "JIBB Assistant",
      subtitle: "Japan–India Business Bureau",
      greet: "Hello! 👋 I'm the JIBB assistant. Ask me about our services, membership, events, or doing business between Japan and India.",
      placeholder: "Type your question…",
      open: "Chat with JIBB", close: "Close chat", reset: "Start a new conversation", send: "Send",
      suggestions: ["What services does JIBB offer?", "How do I become a member?", "Where are your offices?"],
      error: "Sorry, I couldn't reach the server. Please try again in a moment.",
      leadTitle: "Connect with our advisory team",
      leadText: "Share your details and a JIBB advisor will get in touch.",
      leadService: "Service of interest",
      leadName: "Full name", leadEmail: "Work email",
      leadSubmit: "Submit", leadSending: "Submitting…", leadLater: "Maybe later",
      leadMissing: "Please enter your name and a valid email.",
      leadFail: "Couldn't submit right now. Please try again.",
      leadThanks: function (n, s, e) { return "Thank you, " + n + "! Your interest in " + s + " has been recorded. Our team will contact you at " + e + "."; },
      resetDone: "New conversation started. How can I help?",
      powered: "AI answers may be imperfect. Please verify important details.",
    },
    ja: {
      title: "JIBB アシスタント",
      subtitle: "日印ビジネスビューロー",
      greet: "こんにちは！👋 JIBBアシスタントです。サービス、会員制度、イベント、日印ビジネスについてお気軽にご質問ください。",
      placeholder: "ご質問を入力してください…",
      open: "JIBBにチャットで相談", close: "チャットを閉じる", reset: "新しい会話を始める", send: "送信",
      suggestions: ["JIBBのサービス内容は？", "会員になるには？", "オフィスの所在地は？"],
      error: "申し訳ありません。サーバーに接続できませんでした。しばらくしてから再度お試しください。",
      leadTitle: "アドバイザーにご相談ください",
      leadText: "ご連絡先をご入力いただくと、JIBBの担当者よりご連絡いたします。",
      leadService: "ご関心のあるサービス",
      leadName: "お名前", leadEmail: "メールアドレス（勤務先）",
      leadSubmit: "送信", leadSending: "送信中…", leadLater: "後で",
      leadMissing: "お名前と有効なメールアドレスをご入力ください。",
      leadFail: "送信できませんでした。もう一度お試しください。",
      leadThanks: function (n, s, e) { return n + "様、ありがとうございます。「" + s + "」へのご関心を承りました。担当者より " + e + " にご連絡いたします。"; },
      resetDone: "新しい会話を開始しました。ご質問をどうぞ。",
      powered: "AIの回答には誤りが含まれる場合があります。重要な情報はご確認ください。",
    },
  };
  T = T[lang] || T.en;

  // ---------------------------------------------------------------- transcript (survives page navigation)
  var transcript = [];
  try { transcript = JSON.parse(sget("sessionStorage", "log") || "[]") || []; } catch (e) { transcript = []; }
  function saveTranscript() { sset("sessionStorage", "log", JSON.stringify(transcript.slice(-40))); }
  var leadDone = sget("localStorage", "lead_done") === "1";
  var leadShown = sget("sessionStorage", "lead_shown") === "1";

  // ---------------------------------------------------------------- safe mini-markdown
  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function inline(s) {
    s = esc(s);
    s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
    s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/(^|[^*\w])\*([^*\n]+)\*(?!\w)/g, "$1<em>$2</em>");
    s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
    s = s.replace(/(^|[\s(])(https?:\/\/[^\s<)]+[^\s<).,;:!?])/g, '$1<a href="$2" target="_blank" rel="noopener noreferrer">$2</a>');
    return s;
  }
  function md(text) {
    var lines = String(text || "").replace(/\r/g, "").split("\n");
    var out = [], list = null, para = [];
    function flushPara() { if (para.length) { out.push("<p>" + para.map(inline).join("<br>") + "</p>"); para = []; } }
    function flushList() { if (list) { out.push("<" + list.tag + ">" + list.items.map(function (i) { return "<li>" + inline(i) + "</li>"; }).join("") + "</" + list.tag + ">"); list = null; } }
    lines.forEach(function (raw) {
      var line = raw.trim(), m;
      if (!line) { flushPara(); flushList(); return; }
      if (/^(-{3,}|\*{3,})$/.test(line)) { flushPara(); flushList(); out.push("<hr>"); return; }
      if ((m = line.match(/^#{1,6}\s+(.*)$/))) { flushPara(); flushList(); out.push("<h4>" + inline(m[1]) + "</h4>"); return; }
      if ((m = line.match(/^[-*•]\s+(.*)$/)) || (m = line.match(/^(\d+)[.)]\s+(.*)$/))) {
        var ordered = m.length === 3, item = ordered ? m[2] : m[1], tag = ordered ? "ol" : "ul";
        flushPara();
        if (!list || list.tag !== tag) { flushList(); list = { tag: tag, items: [] }; }
        list.items.push(item);
        return;
      }
      if (/^\|.*\|$/.test(line)) { // tables: render rows as plain lines
        if (/^\|[\s:|-]+\|$/.test(line)) return;
        line = line.replace(/^\||\|$/g, "").split("|").map(function (c) { return c.trim(); }).join(" · ");
      }
      flushList();
      para.push(line);
    });
    flushPara(); flushList();
    return out.join("");
  }

  // ---------------------------------------------------------------- styles
  var CSS = [
    ":host{all:initial}",
    ".w{--indigo:#243b6b;--indigo-d:#1a2d52;--orange:#e98b2a;--orange-d:#d4893a;--sakura:#d96c6c;",
    "--bg:#f8f7f4;--card:#fff;--fg:#1a1a1a;--muted:#6b7280;--border:#e5e2dc;--bot:#fff;--user:#243b6b;--user-fg:#fff;",
    "--shadow:0 16px 48px rgba(0,0,0,.14),0 8px 20px rgba(0,0,0,.08);",
    "font-family:Inter,'Noto Sans JP',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;font-size:14px;line-height:1.5;color:var(--fg);",
    "-webkit-font-smoothing:antialiased}",
    ".w.dark{--indigo:#7b9fe0;--indigo-d:#5a7dc0;--orange:#f0a455;--orange-d:#e98b2a;--bg:#0f1629;--card:#1a2340;--fg:#f0ede8;",
    "--muted:#8b95a8;--border:rgba(255,255,255,.12);--bot:#1a2340;--user:#2e4d8a;--user-fg:#fff;--shadow:0 16px 48px rgba(0,0,0,.5)}",
    "*{box-sizing:border-box}",
    "button{font:inherit;cursor:pointer}",
    // launcher
    ".launch{position:fixed;bottom:22px;right:22px;z-index:2147483646;width:60px;height:60px;border-radius:50%;border:0;",
    "background:var(--orange);color:#fff;display:flex;align-items:center;justify-content:center;",
    "box-shadow:0 8px 24px rgba(233,139,42,.35),0 2px 6px rgba(0,0,0,.12);transition:transform .25s,background .2s}",
    ".launch:hover{background:var(--orange-d);transform:translateY(-2px)}",
    ".launch:focus-visible{outline:3px solid var(--indigo);outline-offset:3px}",
    ".launch svg{width:28px;height:28px;transition:transform .25s,opacity .2s}",
    ".launch .ic-close{position:absolute;opacity:0;transform:rotate(-90deg)}",
    ".w.open .launch .ic-chat{opacity:0;transform:rotate(90deg)}",
    ".w.open .launch .ic-close{opacity:1;transform:none}",
    ".nudge{position:fixed;bottom:34px;right:94px;z-index:2147483646;background:var(--card);color:var(--fg);border:1px solid var(--border);",
    "padding:9px 14px;border-radius:12px;box-shadow:0 4px 16px rgba(0,0,0,.1);font-size:13px;font-weight:500;max-width:240px;",
    "animation:pop .35s ease both;cursor:pointer}",
    ".w.open .nudge{display:none}",
    ".left .launch{right:auto;left:22px}.left .nudge{right:auto;left:94px}.left .panel{right:auto;left:22px;transform-origin:bottom left}",
    // panel
    ".panel{position:fixed;bottom:96px;right:22px;z-index:2147483647;width:390px;height:min(640px,calc(100vh - 120px));",
    "background:var(--bg);border:1px solid var(--border);border-radius:18px;box-shadow:var(--shadow);display:flex;flex-direction:column;",
    "overflow:hidden;transform-origin:bottom right;transform:scale(.92) translateY(12px);opacity:0;visibility:hidden;",
    "transition:transform .25s cubic-bezier(.2,.8,.2,1),opacity .2s,visibility 0s .25s}",
    ".w.open .panel{transform:none;opacity:1;visibility:visible;transition:transform .25s cubic-bezier(.2,.8,.2,1),opacity .2s}",
    ".head{background:linear-gradient(135deg,#243b6b 0%,#1a2d52 100%);color:#fff;padding:14px 14px 14px 16px;display:flex;align-items:center;gap:12px;position:relative}",
    ".head:after{content:'';position:absolute;left:0;right:0;bottom:0;height:3px;background:linear-gradient(90deg,var(--orange),var(--sakura))}",
    ".logo{width:42px;height:42px;border-radius:12px;background:#fff;display:flex;align-items:center;justify-content:center;flex:none;padding:6px}",
    ".logo img{max-width:100%;max-height:100%;display:block}",
    ".ht{flex:1;min-width:0}",
    ".ht b{display:block;font-family:'Plus Jakarta Sans',Inter,sans-serif;font-size:15px;font-weight:700;letter-spacing:-.01em}",
    ".ht span{display:flex;align-items:center;gap:6px;font-size:12px;opacity:.8}",
    ".ht span:before{content:'';width:7px;height:7px;border-radius:50%;background:#34d399;box-shadow:0 0 0 2px rgba(52,211,153,.25)}",
    ".hb{background:transparent;border:0;color:#fff;opacity:.8;width:34px;height:34px;border-radius:8px;display:flex;align-items:center;justify-content:center}",
    ".hb:hover{opacity:1;background:rgba(255,255,255,.12)}",
    ".hb svg{width:18px;height:18px}",
    // messages
    ".msgs{flex:1;overflow-y:auto;padding:18px 14px 8px;display:flex;flex-direction:column;gap:12px;scroll-behavior:smooth;overscroll-behavior:contain}",
    ".msgs::-webkit-scrollbar{width:6px}.msgs::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}",
    ".row{display:flex;gap:8px;align-items:flex-end;animation:pop .25s ease both}",
    ".row.user{justify-content:flex-end}",
    ".av{width:26px;height:26px;border-radius:50%;background:var(--indigo);color:#fff;flex:none;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:800;font-family:'Plus Jakarta Sans',sans-serif}",
    ".w.dark .av{background:#2e4d8a}",
    ".b{max-width:82%;padding:10px 14px;border-radius:16px;word-wrap:break-word;overflow-wrap:anywhere}",
    ".bot .b{background:var(--bot);border:1px solid var(--border);border-bottom-left-radius:4px;box-shadow:0 1px 2px rgba(0,0,0,.04)}",
    ".user .b{background:var(--user);color:var(--user-fg);border-bottom-right-radius:4px;white-space:pre-wrap}",
    ".b p{margin:0 0 8px}.b p:last-child{margin-bottom:0}",
    ".b ul,.b ol{margin:4px 0 8px;padding-left:20px}.b li{margin:2px 0}.b li::marker{color:var(--orange)}",
    ".b h4{margin:8px 0 4px;font-size:14px;font-family:'Plus Jakarta Sans',sans-serif;color:var(--indigo)}",
    ".b strong{font-weight:650}",
    ".b code{font-family:ui-monospace,Menlo,monospace;font-size:12.5px;background:rgba(36,59,107,.08);padding:1px 5px;border-radius:4px}",
    ".b a{color:var(--indigo);text-decoration:underline;text-underline-offset:2px}",
    ".user .b a{color:#fff}",
    ".b hr{border:0;border-top:1px solid var(--border);margin:8px 0}",
    ".b.err{border-color:rgba(217,108,108,.5);color:var(--sakura)}",
    ".dots{display:inline-flex;gap:4px;padding:4px 0}",
    ".dots i{width:7px;height:7px;border-radius:50%;background:var(--muted);opacity:.5;animation:blink 1.2s infinite}",
    ".dots i:nth-child(2){animation-delay:.15s}.dots i:nth-child(3){animation-delay:.3s}",
    // suggestions
    ".sugg{display:flex;flex-wrap:wrap;gap:6px;padding-left:34px}",
    ".chip{background:var(--card);border:1px solid var(--border);color:var(--indigo);border-radius:999px;padding:6px 12px;font-size:12.5px;font-weight:500;transition:all .2s}",
    ".chip:hover{border-color:var(--orange);color:var(--orange-d)}",
    // lead card
    ".lead{margin-left:34px;background:var(--card);border:1px solid var(--border);border-top:3px solid var(--orange);border-radius:14px;padding:14px;animation:pop .3s ease both}",
    ".lead h5{margin:0 0 2px;font-family:'Plus Jakarta Sans',sans-serif;font-size:14px;color:var(--indigo)}",
    ".lead p{margin:0 0 10px;font-size:12.5px;color:var(--muted)}",
    ".lead label{display:block;font-size:11.5px;font-weight:600;color:var(--muted);margin:0 0 4px;text-transform:uppercase;letter-spacing:.04em}",
    ".lead select,.lead input{width:100%;font:inherit;font-size:13.5px;color:var(--fg);background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:8px 10px;margin-bottom:8px;outline:none}",
    ".lead select:focus,.lead input:focus{border-color:var(--indigo);box-shadow:0 0 0 3px rgba(36,59,107,.12)}",
    ".lead .acts{display:flex;gap:8px;align-items:center;margin-top:2px}",
    ".lead .go{flex:1;background:var(--orange);color:#fff;border:0;border-radius:8px;padding:9px;font-weight:700}",
    ".lead .go:hover{background:var(--orange-d)}.lead .go:disabled{opacity:.6}",
    ".lead .later{background:none;border:0;color:var(--muted);font-size:12.5px;padding:9px 6px}",
    ".lead .msg{font-size:12px;color:var(--sakura);margin:-2px 0 8px;display:none}",
    ".lead.ok{border-top-color:#10b981}.lead.ok p{color:var(--fg);margin:0}",
    // input
    ".foot{padding:10px 12px 8px;background:var(--bg);border-top:1px solid var(--border)}",
    ".bar{display:flex;align-items:flex-end;gap:8px;background:var(--card);border:1px solid var(--border);border-radius:14px;padding:6px 6px 6px 14px;transition:border-color .2s,box-shadow .2s}",
    ".bar:focus-within{border-color:var(--indigo);box-shadow:0 0 0 3px rgba(36,59,107,.1)}",
    "textarea{flex:1;border:0;outline:0;resize:none;background:transparent;color:var(--fg);font:inherit;font-size:14px;line-height:1.45;max-height:110px;padding:6px 0;min-height:22px}",
    "textarea::placeholder{color:var(--muted)}",
    ".send{width:36px;height:36px;flex:none;border:0;border-radius:10px;background:var(--orange);color:#fff;display:flex;align-items:center;justify-content:center;transition:background .2s,opacity .2s}",
    ".send:hover{background:var(--orange-d)}.send:disabled{opacity:.4;cursor:default}",
    ".send svg{width:18px;height:18px}",
    ".note{font-size:10.5px;color:var(--muted);text-align:center;margin-top:6px}",
    "@keyframes pop{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}",
    "@keyframes blink{0%,80%,100%{opacity:.25;transform:translateY(0)}40%{opacity:.9;transform:translateY(-3px)}}",
    "@media (max-width:480px){.panel{right:0!important;left:0!important;bottom:0;width:100%;height:100%;height:100dvh;border-radius:0;border:0}",
    ".w.open .launch{display:none}.launch{bottom:16px;right:16px}.left .launch{left:16px}.nudge{display:none}}",
    "@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}",
  ].join("");

  var ICON = {
    chat: '<svg class="ic-chat" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 9 9 0 0 1-3.9-.9L3 20l1.1-4.2A8.2 8.2 0 0 1 3 11.5 8.5 8.5 0 0 1 12 3a8.5 8.5 0 0 1 9 8.5z"/><path d="M8 11h.01M12 11h.01M16 11h.01" stroke-width="2.6"/></svg>',
    close: '<svg class="ic-close" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>',
    x: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>',
    reset: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/></svg>',
    send: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>',
  };

  // ---------------------------------------------------------------- DOM
  function mount() {
    var host = document.createElement("div");
    host.id = "jibb-chat-widget";
    document.body.appendChild(host);
    var root = host.attachShadow ? host.attachShadow({ mode: "open" }) : host;

    var style = document.createElement("style");
    style.textContent = CSS;
    root.appendChild(style);

    var w = document.createElement("div");
    w.className = "w" + (opt.position === "left" ? " left" : "");
    w.innerHTML =
      '<div class="panel" role="dialog" aria-label="' + esc(T.title) + '">' +
        '<div class="head">' +
          '<div class="logo"><img alt="JIBB" src="https://npo-jibb.org/jibb-logo.svg"></div>' +
          '<div class="ht"><b>' + esc(T.title) + '</b><span>' + esc(T.subtitle) + '</span></div>' +
          '<button class="hb" data-act="reset" title="' + esc(T.reset) + '" aria-label="' + esc(T.reset) + '">' + ICON.reset + '</button>' +
          '<button class="hb" data-act="close" title="' + esc(T.close) + '" aria-label="' + esc(T.close) + '">' + ICON.x + '</button>' +
        '</div>' +
        '<div class="msgs" aria-live="polite"></div>' +
        '<div class="foot">' +
          '<div class="bar"><textarea rows="1" placeholder="' + esc(T.placeholder) + '" aria-label="' + esc(T.placeholder) + '"></textarea>' +
          '<button class="send" aria-label="' + esc(T.send) + '" disabled>' + ICON.send + '</button></div>' +
          '<div class="note">' + esc(T.powered) + '</div>' +
        '</div>' +
      '</div>' +
      '<button class="launch" aria-label="' + esc(T.open) + '" aria-expanded="false">' + ICON.chat + ICON.close + '</button>';
    root.appendChild(w);

    var $ = function (s) { return w.querySelector(s); };
    var msgs = $(".msgs"), input = $("textarea"), sendBtn = $(".send"), launch = $(".launch");
    var busy = false;

    // follow the host site's dark mode (npo-jibb.org toggles .dark on <html>)
    function syncTheme() { w.classList.toggle("dark", document.documentElement.classList.contains("dark")); }
    syncTheme();
    try { new MutationObserver(syncTheme).observe(document.documentElement, { attributes: true, attributeFilter: ["class"] }); } catch (e) {}

    function scroll() { msgs.scrollTop = msgs.scrollHeight; }

    function bubble(role, html, extraClass) {
      var row = document.createElement("div");
      row.className = "row " + role;
      row.innerHTML = (role === "bot" ? '<div class="av">JIBB</div>' : "") + '<div class="b' + (extraClass ? " " + extraClass : "") + '"></div>';
      var b = row.querySelector(".b");
      if (role === "user") b.textContent = html; else b.innerHTML = html;
      msgs.appendChild(row);
      scroll();
      return b;
    }

    function suggestions() {
      var box = document.createElement("div");
      box.className = "sugg";
      T.suggestions.forEach(function (q) {
        var c = document.createElement("button");
        c.className = "chip"; c.type = "button"; c.textContent = q;
        c.onclick = function () { box.remove(); send(q); };
        box.appendChild(c);
      });
      msgs.appendChild(box);
    }

    function renderAll() {
      msgs.innerHTML = "";
      bubble("bot", md(T.greet));
      if (!transcript.length) suggestions();
      transcript.forEach(function (m) { bubble(m.r, m.r === "user" ? m.t : md(m.t)); });
    }

    // ---- lead card
    var services = null;
    function leadCard(list) {
      if (leadDone || leadShown || msgs.querySelector(".lead")) return;
      leadShown = true; sset("sessionStorage", "lead_shown", "1");
      list = list && list.length ? list : services || [];
      var card = document.createElement("div");
      card.className = "lead";
      card.innerHTML =
        "<h5>" + esc(T.leadTitle) + "</h5><p>" + esc(T.leadText) + "</p>" +
        "<label>" + esc(T.leadService) + "</label><select>" +
        list.map(function (s) { return "<option>" + esc(s) + "</option>"; }).join("") + "</select>" +
        '<input type="text" autocomplete="name" placeholder="' + esc(T.leadName) + '">' +
        '<input type="email" autocomplete="email" placeholder="' + esc(T.leadEmail) + '">' +
        '<div class="msg"></div>' +
        '<div class="acts"><button class="go" type="button">' + esc(T.leadSubmit) + '</button>' +
        '<button class="later" type="button">' + esc(T.leadLater) + "</button></div>";
      msgs.appendChild(card);
      scroll();

      var sel = card.querySelector("select"), ins = card.querySelectorAll("input"), err = card.querySelector(".msg"), go = card.querySelector(".go");
      card.querySelector(".later").onclick = function () { card.remove(); };
      go.onclick = function () {
        var name = ins[0].value.trim(), email = ins[1].value.trim(), service = sel.value;
        if (name.length < 2 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
          err.textContent = T.leadMissing; err.style.display = "block"; return;
        }
        err.style.display = "none"; go.disabled = true; go.textContent = T.leadSending;
        fetch(API + "/api/leads", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionId, name: name, email: email, service: service, notes: "Website widget: " + location.href }),
        }).then(function (r) {
          if (!r.ok) throw new Error(r.status);
          leadDone = true; sset("localStorage", "lead_done", "1");
          card.className = "lead ok";
          card.innerHTML = "<h5>✓</h5><p>" + esc(T.leadThanks(name, service, email)) + "</p>";
          transcript.push({ r: "bot", t: T.leadThanks(name, "**" + service + "**", email) }); saveTranscript();
        }).catch(function () {
          go.disabled = false; go.textContent = T.leadSubmit;
          err.textContent = T.leadFail; err.style.display = "block";
        });
      };
    }

    // ---- chat (Server-Sent Events over fetch)
    function send(text) {
      text = (text || "").trim();
      if (!text || busy) return;
      busy = true; sendBtn.disabled = true;
      var sugg = msgs.querySelector(".sugg"); if (sugg) sugg.remove();
      bubble("user", text);
      transcript.push({ r: "user", t: text }); saveTranscript();
      var b = bubble("bot", '<span class="dots"><i></i><i></i><i></i></span>');
      var answer = "", meta = null, failed = false;

      fetch(API + "/api/chat/stream", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, session_id: sessionId }),
      }).then(function (res) {
        if (!res.ok || !res.body) throw new Error("HTTP " + res.status);
        var reader = res.body.getReader(), dec = new TextDecoder("utf-8"), buf = "";
        function handle(line) {
          if (line.indexOf("data:") !== 0) return;
          var p; try { p = JSON.parse(line.slice(5).trim()); } catch (e) { return; }
          if (p.error) { failed = true; }
          if (p.token) { answer += p.token; b.innerHTML = md(answer); scroll(); }
          if (p.done) meta = p;
        }
        function pump() {
          return reader.read().then(function (r) {
            if (r.done) { if (buf) handle(buf); return; }
            buf += dec.decode(r.value, { stream: true });
            var parts = buf.split("\n"); buf = parts.pop();
            parts.forEach(handle);
            return pump();
          });
        }
        return pump();
      }).catch(function () { failed = true; }).then(function () {
        if (failed && !answer) { b.classList.add("err"); b.innerHTML = md(T.error); }
        else {
          transcript.push({ r: "bot", t: answer }); saveTranscript();
          if (meta && meta.trigger_lead_capture) leadCard(meta.services);
        }
        busy = false; sendBtn.disabled = !input.value.trim();
        scroll();
      });
    }

    function resetChat() {
      fetch(API + "/api/chat/clear", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId }),
      }).catch(function () {});
      sessionId = newId(); sset("localStorage", "sid", sessionId);
      transcript = []; saveTranscript();
      leadShown = false; sset("sessionStorage", "lead_shown", "0");
      msgs.innerHTML = "";
      bubble("bot", md(T.resetDone));
      suggestions();
    }

    // ---- open / close
    function setOpen(on) {
      w.classList.toggle("open", on);
      launch.setAttribute("aria-expanded", on ? "true" : "false");
      sset("sessionStorage", "open", on ? "1" : "0");
      var n = w.querySelector(".nudge"); if (n && on) n.remove();
      if (on) { sset("localStorage", "seen", "1"); setTimeout(function () { input.focus({ preventScroll: true }); scroll(); }, 120); }
    }
    launch.onclick = function () { setOpen(!w.classList.contains("open")); };
    w.querySelector('[data-act="close"]').onclick = function () { setOpen(false); launch.focus(); };
    w.querySelector('[data-act="reset"]').onclick = resetChat;
    w.addEventListener("keydown", function (e) { if (e.key === "Escape" && w.classList.contains("open")) { setOpen(false); launch.focus(); } });

    input.addEventListener("input", function () {
      input.style.height = "auto";
      input.style.height = Math.min(input.scrollHeight, 110) + "px";
      sendBtn.disabled = busy || !input.value.trim();
    });
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { // isComposing: Japanese IME confirm
        e.preventDefault();
        var v = input.value; input.value = ""; input.style.height = "auto"; sendBtn.disabled = true; send(v);
      }
    });
    sendBtn.onclick = function () { var v = input.value; input.value = ""; input.style.height = "auto"; sendBtn.disabled = true; send(v); };

    renderAll();

    // services for the lead card (fallback if the stream doesn't include them)
    fetch(API + "/api/services").then(function (r) { return r.json(); }).then(function (d) { services = d.services; }).catch(function () {});

    var startOpen = opt.open === "true" || sget("sessionStorage", "open") === "1";
    if (startOpen) setOpen(true);
    else if (!sget("localStorage", "seen")) {
      setTimeout(function () {
        if (w.classList.contains("open")) return;
        var n = document.createElement("div");
        n.className = "nudge";
        n.textContent = lang === "ja" ? "ご質問はありますか？お気軽にどうぞ 👋" : "Questions about JIBB? Ask me 👋";
        n.onclick = function () { setOpen(true); };
        w.appendChild(n);
      }, 4000);
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount);
  else mount();
})();
