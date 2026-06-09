"""Quick inspection script for circuits.xlsx and circuits.json output."""
import json
import pandas as pd
import collections

# --- Load ---
df_all     = pd.read_excel("output/circuits.xlsx", sheet_name="Circuits")
df_summary = pd.read_excel("output/circuits.xlsx", sheet_name="Summary")
df_rejected= pd.read_excel("output/circuits.xlsx", sheet_name="Rejected")

pc  = df_all[df_all["classification"] == "panel_circuit"].copy()
non = df_all[df_all["classification"] != "panel_circuit"].copy()

SEP = "=" * 70

# ── 1. Overview ──────────────────────────────────────────────────────────────
print(SEP)
print("1. OVERALL COUNTS")
print(SEP)
print(f"  Total rows in Circuits sheet : {len(df_all)}")
print(f"  classification=panel_circuit : {len(pc)}")
print(f"    confidence HIGH            : {(pc['confidence']=='high').sum()}")
print(f"    confidence MEDIUM          : {(pc['confidence']=='medium').sum()}")
print(f"    confidence LOW             : {(pc['confidence']=='low').sum()}")
print(f"    needs_human_review=True    : {int(pc['needs_human_review'].sum())}")
print()

# ── 2. Classification breakdown ───────────────────────────────────────────────
print(SEP)
print("2. ALL CLASSIFICATION LABELS")
print(SEP)
print(df_all["classification"].value_counts().to_string())
print()

# ── 3. Panel summary ─────────────────────────────────────────────────────────
print(SEP)
print("3. PANEL SUMMARY (unique panels extracted)")
print(SEP)
print(df_summary.to_string(index=False))
print()

# ── 4. Suspected false positives ─────────────────────────────────────────────
print(SEP)
print("4. SUSPECTED FALSE POSITIVES — panel_circuit where raw_text looks wrong")
print("   (panel name is very short 1-char, or circuit > 42, or low OCR conf)")
print(SEP)
fp_flags = pc[
    (pc["panel"].str.len() <= 1) |
    (pc["circuit"].apply(lambda c: any(int(x) > 42 for x in str(c).split(",") if x.strip().isdigit()))) |
    (pc["confidence"] == "low")
].copy()
if fp_flags.empty:
    print("  None found — all pass basic sanity checks.")
else:
    print(fp_flags[["raw_text","panel","circuit","confidence","reason"]].to_string(index=False))
print()

# ── 5. High-confidence sample ────────────────────────────────────────────────
print(SEP)
print("5. HIGH-CONFIDENCE panel_circuit (first 30 — most trusted)")
print(SEP)
high = pc[pc["confidence"] == "high"][["raw_text","panel","circuit","confidence"]].head(30)
print(high.to_string(index=False))
print()

# ── 6. Medium-confidence sample ───────────────────────────────────────────────
print(SEP)
print("6. MEDIUM-CONFIDENCE panel_circuit (first 30)")
print(SEP)
med = pc[pc["confidence"] == "medium"][["raw_text","panel","circuit","confidence"]].head(30)
print(med.to_string(index=False))
print()

# ── 7. Low-confidence — all ───────────────────────────────────────────────────
print(SEP)
print("7. ALL LOW-CONFIDENCE panel_circuit (review these — possible noise)")
print(SEP)
low = pc[pc["confidence"] == "low"][["raw_text","panel","circuit","reason"]]
if low.empty:
    print("  None.")
else:
    print(low.to_string(index=False))
print()

# ── 8. Duplicate panel-circuit pairs ─────────────────────────────────────────
print(SEP)
print("8. DUPLICATE panel-circuit pairs (same panel+circuit extracted twice)")
print(SEP)
dupes = pc.groupby(["panel", "circuit"]).size().reset_index(name="count")
dupes = dupes[dupes["count"] > 1].sort_values("count", ascending=False)
if dupes.empty:
    print("  None.")
else:
    print(dupes.to_string(index=False))
print()

# ── 9. Circuit range sanity ───────────────────────────────────────────────────
print(SEP)
print("9. CIRCUIT RANGE CHECK — all circuits must be 1-84")
print(SEP)
bad_range = []
for _, row in pc.iterrows():
    for c in str(row["circuit"]).split(","):
        c = c.strip()
        if c.isdigit():
            v = int(c)
            if v < 1 or v > 84:
                bad_range.append({"raw_text": row["raw_text"], "panel": row["panel"], "circuit": row["circuit"]})
if bad_range:
    print(f"  WARNING — {len(bad_range)} rows with circuits outside 1-84:")
    print(pd.DataFrame(bad_range).to_string(index=False))
else:
    print("  All circuits are within valid range 1-84. ✓")
print()

# ── 10. JSON spot-check ───────────────────────────────────────────────────────
print(SEP)
print("10. JSON SPOT-CHECK (first 5 panel_circuit candidates)")
print(SEP)
with open("output/circuits.json", encoding="utf-8") as f:
    data = json.load(f)
print(f"  pdf_path      : {data['pdf_path']}")
print(f"  total_pages   : {data['total_pages']}")
print(f"  known_panels  : {data['known_panels']}")
print(f"  total candidates in JSON: {len(data['candidates'])}")
pc_json = [c for c in data["candidates"] if c["classification"] == "panel_circuit"]
print(f"  panel_circuit in JSON   : {len(pc_json)}")
print("  First 5:")
for c in pc_json[:5]:
    print(f"    panel={c['panel']:<10} circuit={c['circuit']:<8} conf={c['confidence']}  raw={c['raw_text']!r}")
