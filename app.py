import re
import io
import pandas as pd
import streamlit as st

ORDER_RE = re.compile(r"\b(2\d{8})\b")
DATE_RE  = re.compile(r"\b(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\b")
STATUS_TERMS = ["checked","picked","picking","started","completed","complete","ready","packing","packed"]
LOC_RE = re.compile(
    r"(?:(?:RACK\s+(?:HIGH|LOW)-\d{2}-PUP)|"
    r"(?:CUBE-\d+-PUP)|"
    r"(?:[A-Z]-\d{2}\*?-?PUP)|"
    r"(?:[A-Z]-\d{2}\sPUP)|"
    r"(?:PUP-BOX)|"
    r"(?:BOX-?PUP))",
    flags=re.IGNORECASE
)

def parse_blocks(text: str):
    blocks = []
    matches = list(ORDER_RE.finditer(text))
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i+1].start() if i+1 < len(matches) else len(text)
        blocks.append((m.group(1), text[start:end]))
    return blocks

def extract_status(block_text: str):
    s = block_text.lower()
    pos, term = 10**9, ""
    for t in STATUS_TERMS:
        p = s.find(t)
        if p != -1 and p < pos:
            pos, term = p, t
    return term.capitalize() if term else ""

def extract_service_date(block_text: str):
    dates = DATE_RE.findall(block_text)
    return dates[-1] if dates else ""

def extract_location(block_text: str):
    locs = LOC_RE.findall(block_text)
    if not locs: return ""
    return locs[-1].upper().replace("  "," ").replace(" -","-").replace("- ","-")

st.set_page_config(page_title="Order Text → Table", page_icon="📦")
st.title("📦 Paste raw data → get clean table")

raw = st.text_area("Paste the raw text here", height=250, placeholder="Paste the text dump…")
if st.button("Parse"):
    if not raw.strip():
        st.warning("Please paste some text first.")
    else:
        rows = []
        for order_no, block in parse_blocks(raw):
            rows.append({
                "Order number": order_no,
                "Status": extract_status(block),
                "Service date": extract_service_date(block),
                "Location": extract_location(block),
            })
        df = pd.DataFrame(rows, columns=["Order number","Status","Service date","Location"])
        df["Service date"] = pd.to_datetime(df["Service date"], errors="coerce")
        df = df.sort_values("Service date", ascending=False).reset_index(drop=True)
        st.dataframe(df, use_container_width=True)

        # Download buttons
        csv = df.to_csv(index=False).encode("utf-8")
        xls_buf = io.BytesIO()
        with pd.ExcelWriter(xls_buf, engine="xlsxwriter") as writer:
            df.to_excel(writer, index=False, sheet_name="Orders")
        st.download_button("Download CSV", data=csv, file_name="orders.csv", mime="text/csv")
        st.download_button("Download Excel", data=xls_buf.getvalue(), file_name="orders.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

st.caption("Notes: Service date = last timestamp in each order block; Location = last PUP/BOX-like token.")
