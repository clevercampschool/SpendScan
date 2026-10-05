import os
import json
import streamlit as st
import pandas as pd
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# Load environment variables
load_dotenv()

# Page Setup
st.set_page_config(
    page_title="SPENDSCAN | AI Expense Tracker",
    page_icon="💸",
    layout="wide",
)

st.title("💸 SPENDSCAN")
st.caption("Dynamic Expense Tracker, Categorizer & AI Budget Coach")

# Initialize Gemini API Client
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    st.error("⚠️ GEMINI_API_KEY not found in .env file. Please check your configuration.")
    st.stop()


@st.cache_resource
def get_gemini_client(key: str):
    return genai.Client(api_key=key)


client = get_gemini_client(api_key)


# Pydantic Schemas for Strict JSON Validation
class CategorizedExpense(BaseModel):
    name: str = Field(description="Name of the expense item.")
    cost: float = Field(description="Original numerical cost.")
    category: str = Field(
        description="Assigned category (e.g., Housing, Food & Dining, Utilities, Entertainment, Subscriptions, Savings/Debt, Miscelaneous)")
    is_essential: bool = Field(
        description="True if it is a Needs/Essential expense, False if it is a Wants/Discretionary expense.")


class ExpenseAuditReport(BaseModel):
    health_score: int = Field(
        description="Overall financial health/budget score from 0 to 100 based on spending balance.")
    score_rating: str = Field(description="Rating label: 'Excellent', 'Good', 'Fair', or 'Poor'")
    total_spent: float = Field(description="Total summed expense amount.")
    categorized_expenses: list[CategorizedExpense] = Field(
        description="List of all input expenses with assigned category and essential tags.")
    needs_vs_wants_summary: str = Field(description="Summary breakdown of essential vs non-essential spending ratio.")
    cost_cutting_opportunities: list[str] = Field(
        description="Specific actionable items where the user can optimize or cut back.")
    general_feedback: list[str] = Field(description="General advice and budget strategy recommendations.")


SYSTEM_INSTRUCTION = """
You are SPENDSCAN, a smart personal finance AI.
Analyze the user's provided expense list, categorize each item, determine if it is essential (Needs) or discretionary (Wants), calculate a financial health score (0-100), and provide tailored cost-cutting advice.

Output ONLY valid JSON adhering strictly to the requested schema.
"""

# Initialize Session State for Expenses
if "expenses" not in st.session_state:
    st.session_state.expenses = [
        {"name": "Apartment Rent", "cost": 1200.0},
        {"name": "Groceries", "cost": 350.0},
        {"name": "Netflix & Spotify", "cost": 30.0},
        {"name": "Dining Out", "cost": 220.0},
        {"name": "Electricity Bill", "cost": 90.0},
    ]

# Layout Columns: Left (Input Form), Right (Analysis Output)
left_col, right_col = st.columns([1, 1])

with left_col:
    st.subheader("📝 Your Expense Items")

    # Render Dynamic Expense Rows
    updated_expenses = []
    indices_to_remove = []

    for i, exp in enumerate(st.session_state.expenses):
        c1, c2, c3 = st.columns([3, 2, 1])
        with c1:
            name = st.text_input(f"Item #{i + 1}", value=exp["name"], key=f"name_{i}")
        with c2:
            cost = st.number_input(f"Cost ($)", value=float(exp["cost"]), min_value=0.0, step=5.0, key=f"cost_{i}")
        with c3:
            st.write("")
            st.write("")
            if st.button("❌", key=f"del_{i}"):
                indices_to_remove.append(i)

        updated_expenses.append({"name": name, "cost": cost})

    # Apply Removals
    if indices_to_remove:
        for idx in sorted(indices_to_remove, reverse=True):
            updated_expenses.pop(idx)
        st.session_state.expenses = updated_expenses
        st.rerun()

    st.session_state.expenses = updated_expenses

    # Add New Expense Row Button
    if st.button("➕ Add Expense Item"):
        st.session_state.expenses.append({"name": "New Item", "cost": 0.0})
        st.rerun()

    st.divider()

    # Trigger AI Analysis
    analyze_btn = st.button("📊 Categorize & Get Expense Advice", type="primary", use_container_width=True)


def render_dashboard(data: dict):
    """Renders structured JSON expense report into an interactive UI."""

    # 1. Health Score Metrics
    score = data.get("health_score", 50)
    rating = data.get("score_rating", "Fair")
    total = data.get("total_spent", 0.0)

    m1, m2, m3 = st.columns(3)
    m1.metric(label="Total Expenses", value=f"${total:,.2f}")

    score_color = "🟢" if score >= 80 else ("⚠️" if score >= 60 else "🚨")
    m2.metric(label="Budget Health Score", value=f"{score}/100 {score_color}")
    m3.metric(label="Score Rating", value=rating)

    st.divider()

    # 2. Categorized Expenses Table
    st.subheader("🏷️ Categorized Breakdown")
    items = data.get("categorized_expenses", [])
    if items:
        df = pd.DataFrame(items)
        df["Type"] = df["is_essential"].apply(lambda x: "Needs (Essential)" if x else "Wants (Discretionary)")
        df_display = df[["name", "cost", "category", "Type"]].rename(
            columns={"name": "Item", "cost": "Cost ($)", "category": "Category"}
        )
        st.dataframe(df_display, use_container_width=True, hide_index=True)

    st.caption(f"**Needs vs Wants Balance:** {data.get('needs_vs_wants_summary', '')}")

    st.divider()

    # 3. Cost-Cutting Opportunities & Feedback
    c_cut, c_adv = st.columns(2)

    with c_cut:
        st.subheader("✂️ Cost-Cutting Opportunities")
        for opp in data.get("cost_cutting_opportunities", []):
            st.markdown(f"- {opp}")

    with c_adv:
        st.subheader("💡 Budget Advice & Strategy")
        for adv in data.get("general_feedback", []):
            st.markdown(f"- {adv}")


with right_col:
    st.subheader("📈 AI Analysis & Recommendations")

    if analyze_btn:
        # Validate Non-Empty Inputs
        valid_items = [e for e in st.session_state.expenses if e["name"].strip() and e["cost"] > 0]

        if not valid_items:
            st.warning("Please add at least one valid expense item with a name and cost greater than $0.")
        else:
            with st.spinner("Analyzing spending balance and running calculations..."):
                try:
                    payload = json.dumps({"expenses": valid_items})

                    response = client.models.generate_content(
                        model="gemini-3.5-flash-lite",
                        contents=[f"Categorize and evaluate these expenses: {payload}"],
                        config=types.GenerateContentConfig(
                            system_instruction=SYSTEM_INSTRUCTION,
                            temperature=0.1,
                            response_mime_type="application/json",
                            response_schema=ExpenseAuditReport,
                        ),
                    )

                    report_data = json.loads(response.text)
                    render_dashboard(report_data)

                except Exception as e:
                    st.error(f"Error analyzing expenses: {e}")
    else:
        st.info("Click 'Categorize & Get Expense Advice' to view your budget health score and categorized breakdown.")