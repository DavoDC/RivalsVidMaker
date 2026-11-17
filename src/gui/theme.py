# copied from a sibling local GUI kit (theme.py)
"""Page head styles for the local GUI: base type, focus ring, reduced motion and tab styles.

Every colour, size and radius comes from tokens.py through fill(); this file holds no hex
literal (a test checks). Bahnschrift is a Windows system font, so nothing is downloaded.
"""
from gui import tokens

_CSS = """
  :root{color-scheme:dark;}
  html,body{background:@@GROUND@@;color:@@TEXT@@;margin:0;}
  body{font-family:@@FONT_STACK@@;font-size:@@SIZE_BODY@@px;line-height:1.4;}
  .num{font-variant-numeric: tabular-nums;}
  .rvm-dim{color:@@TEXT_DIM@@;}
  :focus{outline:none;}
  :focus-visible{outline:2px solid @@TEXT@@;outline-offset:2px;}
  .rvm-header{display:flex;align-items:center;justify-content:space-between;gap:@@SPACE_16@@px;
    padding:@@SPACE_12@@px @@SPACE_24@@px;border-bottom:1px solid @@LINE@@;}
  .rvm-title{font-size:@@SIZE_SECTION@@px;font-weight:600;font-stretch:87.5%;margin:0;}
  .rvm-state{display:flex;align-items:center;gap:@@SPACE_8@@px;font-size:@@SIZE_UI@@px;}
  .rvm-dot{display:inline-block;width:@@SPACE_8@@px;height:@@SPACE_8@@px;border-radius:50%;background:@@TEXT_DIM@@;}
  .rvm-dot[data-kind=working]{background:@@WORKING@@;}
  .rvm-dot[data-kind=error]{background:@@ERROR@@;}
  .rvm-button{font:inherit;font-size:@@SIZE_UI@@px;color:@@TEXT@@;background:@@PANEL@@;
    border:1px solid @@LINE@@;border-radius:@@RADIUS_PANEL@@px;padding:@@SPACE_4@@px @@SPACE_12@@px;cursor:pointer;}
  .rvm-tabs{display:flex;gap:@@SPACE_24@@px;padding:0 @@SPACE_24@@px;border-bottom:1px solid @@LINE@@;}
  .rvm-tab{font:inherit;font-size:@@SIZE_BODY@@px;font-weight:600;font-stretch:87.5%;color:@@TEXT_DIM@@;
    background:none;border:none;border-bottom:@@SPACE_4@@px solid transparent;padding:@@SPACE_12@@px 0;cursor:pointer;}
  .rvm-tab:hover{color:@@TEXT@@;}
  .rvm-tab[aria-selected=true]{color:@@TEXT@@;border-bottom-color:@@TEXT@@;}
  #error-banner{position:fixed;top:0;left:0;right:0;z-index:9999;background:@@PANEL@@;color:@@TEXT@@;
    border-left:@@SPACE_4@@px solid @@ERROR@@;padding:@@SPACE_8@@px @@SPACE_16@@px;font-size:@@SIZE_UI@@px;}
  #error-banner[hidden]{display:none;}
  #fixture-banner{background:@@PANEL@@;color:@@TEXT@@;font-size:@@SIZE_FINE@@px;padding:@@SPACE_4@@px @@SPACE_16@@px;
    border-bottom:1px solid @@LINE@@;}
  .rvm-footer{display:flex;flex-wrap:wrap;gap:@@SPACE_16@@px;padding:@@SPACE_8@@px @@SPACE_24@@px;
    border-top:1px solid @@LINE@@;font-size:@@SIZE_FINE@@px;color:@@TEXT_DIM@@;}
  .nicegui-content{padding:0 !important;gap:0 !important;}
  table{width:100%;}
  table th,table td{padding-left:@@SPACE_12@@px !important;padding-right:@@SPACE_12@@px !important;}
  @media (prefers-reduced-motion: reduce){
    *,*::before,*::after{transition:none !important;animation:none !important;scroll-behavior:auto !important;}
  }
"""

HEAD_CSS = tokens.fill(_CSS)
HEAD_HTML = f"<style>{HEAD_CSS}</style>"
