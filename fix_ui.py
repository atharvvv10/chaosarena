from pathlib import Path
p = Path("dashboard/src/styles.css")
s = p.read_text(encoding="utf-8")
repls = [
 ("font: 10px var(--mono);", "font: 11px var(--mono);"),
 ("font: 9px var(--mono);", "font: 10px var(--mono);"),
 ("font: 11px var(--mono);", "font: 12px var(--mono);"),
 ("font: 12px/1.8 var(--mono);", "font: 13px/1.8 var(--mono);"),
 (".gateverdict h3 {\n  font-size: 26px;", ".gateverdict h3 {\n  font-size: 32px;"),
 (".kpi .number {\n  font: 600 28px/1.2 var(--mono);", ".kpi .number {\n  font: 600 32px/1.2 var(--mono);"),
 (".kpi .number.success {\n  font: 600 28px/1.2 var(--sans);", ".kpi .number.success {\n  font: 600 32px/1.2 var(--sans);"),
 ("th {\n  text-align: left;\n  padding: 12px 16px;", "th {\n  text-align: left;\n  padding: 14px 18px;"),
 ("td {\n  padding: 14px 16px;", "td {\n  padding: 16px 18px;"),
 (".note { margin-top: 14px; }", ".note { margin-top: 12px; }"),
 (".recovery-note {\n  font: 10px/1.7 var(--mono);", ".recovery-note {\n  font: 11px/1.7 var(--mono);"),
 (".panelheader small {\n  font: 10px var(--mono);", ".panelheader small {\n  font: 11px var(--mono);"),
 (".arenahead .right {\n  display: flex;\n  gap: 12px;\n  align-items: center;\n  font: 10px var(--mono);", ".arenahead .right {\n  display: flex;\n  gap: 12px;\n  align-items: center;\n  font: 11px var(--mono);"),
 (".kpi .sub {\n  font: 10px var(--mono);", ".kpi .sub {\n  font: 11px var(--mono);"),
 (".field label {\n  font: 11px var(--mono);", ".field label {\n  font: 12px var(--mono);"),
 (".event .time {\n  font: 10px var(--mono);", ".event .time {\n  font: 11px var(--mono);"),
 (".gateverdict p {\n  font: 10px var(--mono);", ".gateverdict p {\n  font: 11px var(--mono);"),
 (".actions small, .note {\n  font: 10px/1.7 var(--mono);", ".actions small, .note {\n  font: 11px/1.7 var(--mono);"),
 (".evcard h3 {\n  font-size: 16px;", ".evcard h3 {\n  font-size: 17px;"),
 (".evcard p {\n  font-size: 13px;", ".evcard p {\n  font-size: 14px;"),
 (".metric-row {\n  display: flex;", ".metric-row {\n  display: flex;"),
]
for a,b in repls:
    if a in s:
        s = s.replace(a,b)
    else:
        print("NOT FOUND:", a[:60])
p.write_text(s, encoding="utf-8")
print("done")
PY