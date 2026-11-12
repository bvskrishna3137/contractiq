"""ContractIQ web app.  Run:  streamlit run app/streamlit_app.py"""
import io
import os
from pathlib import Path

import pandas as pd
import streamlit as st

from contractiq.export import requirements_csv, to_json, to_xlsx
from contractiq.extractors.llm import load_dotenv
from contractiq.pipeline import run

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "fictional_rfp.pdf"
load_dotenv()

st.set_page_config(page_title="ContractIQ", page_icon="📑", layout="wide")
st.markdown("""<style>
.block-container{padding-top:2rem;max-width:1200px}
div[data-testid="stMetric"]{background:#f4f7fb;border:1px solid #dbe4f0;border-radius:10px;padding:10px 14px}
</style>""", unsafe_allow_html=True)

st.title("ContractIQ")
st.caption("Turn a federal solicitation PDF into a reviewable compliance matrix. Every row links back to a page and a quote.")

with st.sidebar:
    st.header("Document")
    up = st.file_uploader("Solicitation PDF", type=["pdf", "txt"])
    use_sample = st.button("Use the fictional sample RFP", disabled=not SAMPLE.is_file(), use_container_width=True)
    st.header("Extraction mode")
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    mode = st.radio("Mode", ["rules", "llm"], format_func=lambda m: {"rules": "Rules (offline, no key)", "llm": "LLM (Anthropic API)"}[m],
                    help="LLM mode sends the document text to Anthropic. Rules mode never leaves your machine.")
    if mode == "llm" and not has_key:
        st.warning("Set ANTHROPIC_API_KEY in .env to use LLM mode.")
    st.caption("Uploaded files are processed in memory and not saved.")

if use_sample:
    st.session_state["doc"] = (SAMPLE.read_bytes(), SAMPLE.name)
if up is not None:
    st.session_state["doc"] = (up.getvalue(), up.name)

doc = st.session_state.get("doc")
if not doc:
    st.info("Upload a solicitation PDF in the sidebar, or try the fictional sample.")
    st.stop()

key = (doc[1], len(doc[0]), mode)
if st.session_state.get("key") != key:
    try:
        with st.spinner("Reading the document..."):
            st.session_state["ex"] = run(doc[0], name=doc[1], mode=mode)
        st.session_state["key"] = key
    except Exception as e:  # shown to the user, not swallowed
        st.error(str(e))
        st.stop()
ex = st.session_state["ex"]
s = ex.stats()

if "fictional" in doc[1].lower():
    st.warning("This is a fictional sample document written for this demo. It is not a real solicitation.")

c = st.columns(5)
c[0].metric("Requirements", s["requirements"])
c[1].metric("Mandatory", s["mandatory"])
c[2].metric("Key dates", s["key_dates"])
c[3].metric("Eval factors", s["evaluation_factors"])
c[4].metric("CDRLs / CLINs", f"{s['deliverables']} / {s['clins']}")
for w in ex.warnings:
    st.warning(w)

t_sum, t_req, t_eval, t_del = st.tabs(["Summary", "Requirements", "Evaluation & pricing", "Deliverables & CLINs"])

with t_sum:
    left, right = st.columns(2)
    t = ex.terms
    left.subheader("Contract terms")
    left.table(pd.DataFrame([("Solicitation", t.solicitation_number), ("Title", t.title), ("Agency", t.agency),
                             ("Contract type", t.contract_type), ("NAICS", t.naics), ("Set-aside", t.set_aside),
                             ("Period of performance", t.period_of_performance),
                             ("Place of performance", t.place_of_performance)], columns=["Field", "Value"]).set_index("Field"))
    right.subheader("Key dates")
    right.table(pd.DataFrame([(d.label, d.date or d.raw, d.time, d.page) for d in ex.key_dates],
                             columns=["Event", "Date", "Time", "Page"]).set_index("Event"))

with t_req:
    df = pd.DataFrame([{"ID": r.id, "Page": r.page, "Section": r.section, "Category": r.category, "Party": r.party,
                        "Obligation": r.obligation, "Mandatory": r.mandatory, "Requirement": r.text,
                        "Grounded": r.grounded} for r in ex.requirements])
    f1, f2, f3 = st.columns([2, 2, 3])
    cats = f1.multiselect("Category", sorted(df["Category"].unique()) if not df.empty else [])
    parties = f2.multiselect("Party", sorted(df["Party"].unique()) if not df.empty else [])
    q = f3.text_input("Search text")
    if not df.empty:
        if cats:
            df = df[df["Category"].isin(cats)]
        if parties:
            df = df[df["Party"].isin(parties)]
        if q:
            df = df[df["Requirement"].str.contains(q, case=False, regex=False)]
    st.caption(f"{len(df)} shown. Page and quote are in the Excel export for every row.")
    st.dataframe(df, use_container_width=True, hide_index=True, height=460,
                 column_order=["ID", "Page", "Section", "Requirement", "Category", "Party", "Obligation", "Mandatory", "Grounded"],
                 column_config={"Requirement": st.column_config.TextColumn(width=430),
                                "Mandatory": st.column_config.CheckboxColumn(), "Grounded": st.column_config.CheckboxColumn()})

with t_eval:
    st.subheader("Evaluation factors")
    st.table(pd.DataFrame([(f.name, f.importance, "; ".join(f.subfactors)) for f in ex.evaluation_factors],
                          columns=["Factor", "Relative importance", "Subfactors"]).set_index("Factor"))
    st.subheader("Amounts")
    st.table(pd.DataFrame([(a.label, f"${a.amount:,.0f}", a.page) for a in ex.terms.amounts],
                          columns=["Meaning", "Amount", "Page"]).set_index("Meaning"))

with t_del:
    st.subheader("Deliverables (CDRL)")
    st.table(pd.DataFrame([(d.id, d.title, d.frequency, d.due) for d in ex.deliverables],
                          columns=["ID", "Title", "Frequency", "Due"]).set_index("ID"))
    st.subheader("Contract line items")
    st.table(pd.DataFrame([(x.number, x.description, x.type) for x in ex.clins],
                          columns=["CLIN", "Description", "Type"]).set_index("CLIN"))

st.divider()
buf = io.BytesIO()
to_xlsx(ex, buf)
stem = Path(doc[1]).stem
d1, d2, d3 = st.columns(3)
d1.download_button("Download Excel compliance matrix", buf.getvalue(), f"{stem}.xlsx",
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
d2.download_button("Download requirements CSV", requirements_csv(ex), f"{stem}_requirements.csv", "text/csv", use_container_width=True)
d3.download_button("Download full JSON", to_json(ex), f"{stem}.json", "application/json", use_container_width=True)
