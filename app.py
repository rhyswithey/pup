import re
import io
import pandas as pd
import streamlit as st

# -------- Patterns --------
ORDER_RE = re.compile(r"\b(2\d{8})\b")
DATE_RE  = re.compile(r"\b(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\b")

STATUS_RE = re.compile(
    r"\b(checked|picked|picking|started|completed|complete|ready|packing|packed)\b",
    re.IGNORECASE
)

# Fallback text only if no location is found
NOTES_RE = re.compile(r"(Incom[^\n]*|remaining item[^\n]*|missing[^\n]*)", re.IGNORECASE)

def build_location_patterns():
    pats = []
    # A-01..A-13 PUP
    for i in range(1, 14):
        dd = f"{i:02d}"
        pats.append((
            re.compile(rf"\bA\s*-?\s*{dd}\s*\*?\s*-?\s*PUP\b", re.IGNORECASE),
            f"A-{dd} PUP"
        ))
    # B-01..B-12 PUP
    for i in range(1, 13):
        dd = f"{i:02d}"
        pats.append((
            re.compile(rf"\bB\s*-?\s*{dd}\s*\*?\s*-?\s*PUP\b", re.IGNORECASE),
            f"B-{dd} PUP"
        ))
    # PUP-BOX
    pats.append((
        re.compile(r"\bPUP\s*-?\s*BOX\b", re.IGNORECASE),
        "PUP-BOX"
    ))
    # RACK-HIGH-01..06-PUP and RACK-LOW-01..06-PUP
    for lvl in ["HIGH", "LOW"]:
        for i in range(1, 7):
            dd = f"{i:02d}"
            pats.append((
                re.compile(rf"\bRACK\s*-?\s*{lvl}\s*-?\s*{dd}\s*-?\s*PUP\b", re.IGNORECASE),
                f"RACK-{lvl}-{dd}-PUP"
            ))
    # CUBE-1..9-PUP
    for i in range(1, 10):
        pats.append((
            re.compile(rf"\bCUBE\s*-?\s*{i}\s*-?\s*\*?\s*PUP\b", re.IGNORECASE),
            f"CUBE-{i}-PUP"
        ))
    # PALLETS PUP
    pats.append((
        re.compile(r"\bPALLETS\s+PUP\b", re.IGNORECASE),
        "PALLETS PUP"
    ))
    # PUP DOOR
    pats.append((
        re.compile(r"\bPUP\s*-?\s*DOOR\b", re.IGNORECASE),
        "PUP DOOR"
    ))
    # NEXT TO CUBES
    pats.append((
        re.compile(r"\bNEXT\s+TO\s+CUBES\b", re.IGNORECASE),
        "NEXT TO CUBES"
    ))
    return pats

LOC_PATTERNS = build_location_patterns()

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
    """
    Return (canonical_location, start_index) for the LAST occurrence in the block,
    matching ONLY the allowed location list, but forgiving spaces/hyphens and optional '*'.
    Trailing notes like '2 trolleys' won't be included.
    """
    best = None  # (start_index, canonical)
    for rx, canon in LOC_PATTERNS:
        for m in rx.finditer(block_text):
            if (best is None) or (m.start() > best[0]):
                best = (m.start(), canon)
    if best:
        return best[1], best[0]
    return "", None

def extract_service_date(block_text: str, loc_start: int | None) -> str:
    # Take the last date BEFORE the location (if found). Otherwise last date in the block.
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

            # If no allowed location is found, fall back to notes-like text in Location (as requested).
            if not loc:
                fallback = extract_notes(block)
                loc = fallback if fallback else ""

            rows.append({
                "Order number": order_no,
                "Status": status,
                "Service date": svc_date,
                "Location": loc,
            })

        df = pd.DataFrame(rows, columns=["Order number", "Status", "Service date", "Location"])
        df["Service date"] = pd.to_datetime(df["Service date"], errors="coerce")
        df = df.sort_values("Service date", ascending=not sort_desc).reset_index(drop=True)

        st.subheader("Parsed table")
        st.dataframe(df, use_container_width=True)

        # QA helper
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

st.caption("Location is restricted to your approved list, with tolerant matching. If no location is found, 'notes-like' text is used instead.")
