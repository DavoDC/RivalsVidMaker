# copied from a sibling local GUI kit (chrome.py)
"""Page chrome shared by every tab: global error handler, error banner, header with the
state word, footer with the build line, FIXTURE banner and the window.__debug surface.

Plain HTML and JS, injected once per page. Colours and sizes come from theme.py, which
takes them from tokens.py. Names from data are escaped before they reach the page.
"""
from __future__ import annotations

import html
import json

from gui import build_info, security, theme, timefmt

ERROR_JS = r"""
(function(){
  var TOKEN = __TOKEN__;
  function show(msg){
    try{
      var b=document.getElementById('error-banner');
      if(b){b.hidden=false;b.textContent='Something broke in the page: '+msg;}
    }catch(e){}
  }
  function report(kind,msg){
    console.error('[app-error] '+kind+': '+msg);
    show(msg);
    try{fetch('/__log',{method:'POST',headers:{'Content-Type':'application/json','X-RVM-Token':TOKEN},
      body:JSON.stringify({kind:kind,message:String(msg)})});}catch(e){}
  }
  window.addEventListener('error',function(e){
    var m=(e&&e.message)||'script error';
    // Benign browser notice (chart resize loops), not a page failure.
    if(/ResizeObserver loop/.test(m)){e.stopImmediatePropagation();return;}
    report('error',m);});
  window.addEventListener('unhandledrejection',function(e){
    report('rejection',(e&&e.reason&&(e.reason.message||e.reason))||'unhandled rejection');});
  var boot=null;
  setInterval(function(){
    fetch('/api/build',{cache:'no-store'}).then(function(r){return r.json();}).then(function(j){
      if(boot===null){boot=j.boot_id;}
      else if(j.boot_id!==boot){location.reload();}
    }).catch(function(){});
  },3000);
})();
"""

# Quit uses document-level delegation: NiceGUI strips on* attributes, so the header button has no
# inline handler. A 202 replaces the page with one line; a 409 names the running job in a toast.
QUIT_JS = r"""
(function(){
  var TOKEN = __TOKEN__;
  var timer = null;
  function toast(msg){
    var t = document.getElementById('rvm-toast');
    if(!t){
      t = document.createElement('div');
      t.id = 'rvm-toast';
      t.setAttribute('role','status');
      t.setAttribute('aria-live','polite');
      document.body.appendChild(t);
    }
    t.textContent = msg;
    t.style.display = 'block';
    clearTimeout(timer);
    timer = setTimeout(function(){ t.style.display = 'none'; }, 4000);
  }
  function stopped(){
    var p = document.createElement('p');
    p.textContent = 'RivalsVidMaker stopped. You can close this tab.';
    p.style.cssText = 'margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;';
    document.body.textContent = '';
    document.body.appendChild(p);
  }
  document.addEventListener('click', function(e){
    if(!e.target || !e.target.closest || !e.target.closest('#rvm-quit')) return;
    fetch('/__quit',{method:'POST',headers:{'X-RVM-Token':TOKEN},cache:'no-store'})
      .then(function(r){
        if(r.status===202){ stopped(); return; }
        if(r.status===409){
          return r.json().then(function(j){
            toast('Busy: '+j.busy+'. Quit when it finishes.');
          }, function(){ toast('Quit failed. Try again.'); });
        }
        toast('Quit failed. Try again.');
      })
      .catch(function(){ toast('Quit failed. Try again.'); });
  });
})();
"""

DEBUG_JS = r"""
(function(){
  window.__debug = {
    version: 1,
    state: function(){return fetch('/state.json').then(function(r){return r.json();});},
    setTab: function(k){var b=document.getElementById('tab-'+k);if(!b)return false;b.click();return true;},
    forceStatus: function(text,kind){
      var s=document.getElementById('rvm-state');
      var d=document.getElementById('rvm-dot');
      if(!s||!d)return false;
      s.textContent=text||'';
      s.setAttribute('data-kind',kind||'idle');
      d.setAttribute('data-kind',kind||'idle');
      return true;},
    help: function(){return 'window.__debug: state(), setTab(key), forceStatus(text, kind), help()';}
  };
})();
"""


def head_html() -> str:
    """Styles, error handler and debug surface for the page head. The token is per launch."""
    token_js = json.dumps(security.TOKEN)
    error_js = ERROR_JS.replace("__TOKEN__", token_js)
    quit_js = QUIT_JS.replace("__TOKEN__", token_js)
    return (f"{theme.HEAD_HTML}<script>{error_js}</script><script>{quit_js}</script>"
            f"<script>{DEBUG_JS}</script>")


def header_html(state_word: str = "Idle", state_kind: str = "idle") -> str:
    """Title on the left; state dot and word (live region) and Quit on the right."""
    word = html.escape(state_word)
    kind = html.escape(state_kind)
    return (
        '<header class="rvm-header" data-testid="header">'
        '<h1 class="rvm-title">RivalsVidMaker</h1>'
        '<div class="rvm-state">'
        f'<span id="rvm-dot" class="rvm-dot" data-kind="{kind}" aria-hidden="true"></span>'
        f'<span id="rvm-state" data-testid="state-word" aria-live="polite" data-kind="{kind}">{word}</span>'
        '<button id="rvm-quit" class="rvm-button" type="button" data-testid="quit">Quit</button>'
        '</div></header>'
    )


def footer_html(line: str, started_at, updated_seconds) -> str:
    """Build line, start time and time since the last state update, as separate fields."""
    updated = "not updated yet" if updated_seconds is None else f"updated {timefmt.ago(updated_seconds)}"
    return (
        '<footer class="rvm-footer" data-testid="build-footer">'
        f'<span data-testid="build-line">{html.escape(line)}</span>'
        f'<span data-testid="started-at">Started {html.escape(timefmt.stamp(started_at))}</span>'
        f'<span data-testid="updated-ago">{html.escape(updated)}</span>'
        '</footer>'
    )


def fixture_banner_html(scenario: str | None) -> str:
    """Empty outside fixture mode; in fixture mode, a strip that names the scenario."""
    if not scenario:
        return ""
    return (f'<div id="fixture-banner" data-testid="fixture-banner">'
            f'FIXTURE {html.escape(scenario)}: sample data, nothing is read from or written to disk</div>')


def body_html(state_word: str = "Idle", state_kind: str = "idle", fixture: str | None = None,
              started_at=None, updated_seconds=None) -> str:
    """Error banner, header, FIXTURE strip and footer, in one string."""
    started = build_info.STARTED_AT if started_at is None else started_at
    return (
        '<div id="error-banner" role="alert" data-testid="error-banner" hidden></div>'
        + header_html(state_word, state_kind)
        + fixture_banner_html(fixture)
        + footer_html(build_info.line(), started, updated_seconds)
    )
