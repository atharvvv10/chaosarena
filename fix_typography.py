from pathlib import Path
p = Path("dashboard/src/styles.css")
s = p.read_text(encoding="utf-8")
repls = [
 ("font: 9px var(--mono);", "font: 10px var(--mono);"),
 ("font: 10px var(--mono);", "font: 11px var(--mono);"),
 ("font: 10px/1.7 var(--mono);", "font: 11px/1.7 var(--mono);"),
 ("font: 11px var(--mono);", "font: 12px var(--mono);"),
 ("font: 12px/1.8 var(--mono);", "font: 13px/1.8 var(--mono);"),
 ("font: 13px var(--mono);", "font: 13px var(--mono);"),
 ("font: 13px/1.6 var(--sans);", "font: 14px/1.6 var(--sans);"),
 ("letter-spacing: 0.12em;", "letter-spacing: 0.08em;"),
 ("letter-spacing: .13em;", "letter-spacing: .08em;"),
 ("font-size: 34px;", "font-size: 30px;"),
]
for a,b in repls:
    s = s.replace(a,b)
p.write_text(s, encoding="utf-8")
print("done")