import re
import io
import pandas as pd
import streamlit as st

# -------- Patterns (tuned) --------
ORDER_RE = re.compile(r"\b(2\d{8})\b")
DATE_RE  = re.compile(r"\b(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\b")

STATUS_RE = re.compile(
    r"\b(checked|picked|picking|started|completed|complete|ready|packing|packed)\b",
    re.IGNORECASE
)

# Handles: RACK HIGH-04-PUP / RACK LOW-05-PUP / CUBE-7-PUP /
# A-02-PUP / A-03 PUP / B-01PUP / B-08*PUP / BOX-PUP / PUP-BOX
LOC_RE = re.compile(r"""
(
    RACK \s+ (?:HIGH|LOW) \s* -? \s* \d{2} \s* - \s* PUP |
    CUBE \s* - \s* \d+ \s* - \s* PUP |
    [A-Z] \s* - \s* \d{2} \s* \*? \s* -? \s* PUP |
    [A-Z] \s* -? \s* \d{2} PUP |
    PUP \s* - \s* BOX |
    BOX \s* - \s* PUP
)
""", re.IGNORECASE | re.VERBOSE)

# Notes like "Incom missing 2 x 111.111.22", "remaining item 1x 80166124", "missing ..."
NOTES_RE = re.compile(r"(Incom[^\n]*|remaining item[^\n]*|missing[^\n]*)", re.IGNORECASE)

# -------- Extractors --------
def parse_blocks(text: str):
    blocks = []
    matches = list(ORDER_RE.finditer(text))
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i+1].start() if i+1 < len(matches) else len(text)
        blocks.append((m.group(1), text[start:end]))
    return blocks

def extract_status(block_text: str) -> str:
    m = STATUS_RE.search(block_text)
    return m.group(1).capitalize() if m else ""

def extract_location(block_text: str):
    # Return the *last* matching location (closest to the end)
    locs = list(LOC_RE.finditer(block_text))
    return (locs[-1].group(1) if locs else ""), (locs[-1].start() if locs else None)

def extract_service_date(block_text: str, loc_start: int | None) -> str:
    # Take the last date BEFORE the location (if found). Otherwise last date in block.
    scan_upto = loc_start if loc_start is not None else len(block_text)
    candidates = [m.group(1) for m in DATE_RE.finditer(block_text[:scan_upto])]
    return candidates[-1] if candidates else ""

def extract_notes(block_text: str) -> str:
    notes = NOTES_RE.findall(block_text)
    return "; ".join(n.strip() for n in notes) if notes else ""

# -------- UI --------
st.set_page_config(page_title="Order Text → Table", page_icon="📦")
st.title("📦 Paste raw data → get clean table")

with st.sidebar:
    st.subheader("Options")
    include_notes = st.checkbox("Include 'Notes' column (Incom / remaining / missing)", value=False)
    sort_desc = st.checkbox("Sort Service date: Newest → Oldest", value=True)

raw = st.text_area("Paste the raw text here", height=250, placeholder="Paste the text dump…")

col_a, col_b = st.columns(2)
parse_clicked = col_a.button("Parse")
clear_clicked = col_b.button("Clear")

if clear_clicked:
    raw = ""
    st.experimental_rerun()

if parse_clicked:
    if not raw.strip():
        st.warning("Please paste some text first.")
    else:
        rows = []
        for order_no, block in parse_blocks(raw):
            loc, loc_start = extract_location(block)
            svc_date = extract_service_date(block, loc_start)
            status = extract_status(block)
            row = {
                "Order number": order_no,
                "Status": status,
                "Service date": svc_date,
                "Location": loc.upper().replace("  ", " ").replace(" -", "-").replace("- ", "-"),
            }
            if include_notes:
                row["Notes"] = extract_notes(block)
            rows.append(row)

        cols = ["Order number", "Status", "Service date", "Location"] + (["Notes"] if include_notes else [])
        df = pd.DataFrame(rows, columns=cols)

        # Parse date for sorting/display
        df["Service date"] = pd.to_datetime(df["Service date"], errors="coerce")
        df = df.sort_values("Service date", ascending=not sort_desc).reset_index(drop=True)

        st.subheader("Parsed table")
        st.dataframe(df, use_container_width=True)

        # Quick QA helpers
        with st.expander("⚙️ Quality checks / troubleshooting"):
            missing = df[
                (df["Order number"].isna()) |
                (df["Status"].eq("") | df["Status"].isna()) |
                (df["Service date"].isna()) |
                (df["Location"].eq("") | df["Location"].isna())
            ]
            st.write(f"Rows with missing fields: {len(missing)}")
            if len(missing):
                st.dataframe(missing, use_container_width=True)

        # Downloads
        csv = df.to_csv(index=False).encode("utf-8")
        xls_buf = io.BytesIO()
        with pd.ExcelWriter(xls_buf, engine="xlsxwriter") as writer:
            df.to_excel(writer, index=False, sheet_name="Orders")
        st.download_button("Download CSV", data=csv, file_name="orders.csv", mime="text/csv")
        st.download_button("Download Excel", data=xls_buf.getvalue(), file_name="orders.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

st.caption("Notes: service date = last timestamp before the location. Location matching is robust to spacing, asterisks, and hyphen variants.")
