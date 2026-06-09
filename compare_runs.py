"""Compare two output runs to identify regressions."""
import pandas as pd

FILES = [
    ("output/POWER_AND_SIGNAL_PLAN/circuits_20260603_141807.xlsx", "RUN-1 141807 (first paddle)"),
    ("output/POWER_AND_SIGNAL_PLAN/circuits_20260604_013421.xlsx", "RUN-2 013421 (merger fix)"),
]

datasets = {}
for fname, label in FILES:
    c = pd.read_excel(fname, sheet_name="Circuits")
    r = pd.read_excel(fname, sheet_name="Rejected")
    pc = c[c["classification"] == "panel_circuit"].copy()
    datasets[label] = {"circuits": c, "rejected": r, "pc": pc}

    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(f"  Total Circuits rows : {len(c)}")
    print(f"  panel_circuit count : {len(pc)}")
    h = (pc["confidence"] == "high").sum()
    m = (pc["confidence"] == "medium").sum()
    lo = (pc["confidence"] == "low").sum()
    nr = int(pc["needs_human_review"].sum())
    print(f"  HIGH   : {h}")
    print(f"  MEDIUM : {m}")
    print(f"  LOW    : {lo}")
    print(f"  needs_human_review : {nr}")
    print(f"  Rejected sheet rows: {len(r)}")
    panels = sorted(pc["panel"].dropna().unique())
    print(f"  Unique panels ({len(panels)}): {panels}")
    print()

    # Show reason breakdown for LOW confidence
    low_pc = pc[pc["confidence"] == "low"]
    if not low_pc.empty:
        print(f"  LOW confidence panel_circuit samples (first 10):")
        for _, row in low_pc.head(10).iterrows():
            print(f"    panel={row['panel']:<8}  circuit={row['circuit']:<15}  ocr_conf={row.get('ocr_confidence', '?')}")

# Regression: panels in RUN-1 but missing from RUN-2
pc1 = datasets[FILES[0][1]]["pc"]
pc2 = datasets[FILES[1][1]]["pc"]

pairs1 = set(zip(pc1["panel"].fillna(""), pc1["circuit"].astype(str).str.strip()))
pairs2 = set(zip(pc2["panel"].fillna(""), pc2["circuit"].astype(str).str.strip()))

lost = sorted(pairs1 - pairs2)
gained = sorted(pairs2 - pairs1)

print(f"\n{'='*60}")
print(f"REGRESSIONS: panel-circuit pairs in RUN-1 but LOST in RUN-2 ({len(lost)})")
print(f"{'='*60}")
for p, c in lost[:40]:
    print(f"  LOST  panel={p:<10}  circuit={c}")

print(f"\nNEW in RUN-2 (not in RUN-1) ({len(gained)})")
for p, c in gained[:20]:
    print(f"  NEW   panel={p:<10}  circuit={c}")

# What's in Rejected of RUN-1 that the user flagged
print("\n--- Rejected sheet of RUN-1 (classification=panel_circuit samples) ---")
r1 = datasets[FILES[0][1]]["rejected"]
r1_pc = r1[r1["classification"] == "panel_circuit"] if "classification" in r1.columns else r1
print(f"  Total rejected panel_circuit: {len(r1_pc)}")
for _, row in r1_pc.head(30).iterrows():
    print(f"  panel={row.get('panel','?'):<10}  circuit={row.get('circuit','?'):<15}  conf={row.get('confidence','?')}  ocr={row.get('needs_human_review','?')}")
