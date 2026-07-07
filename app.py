import streamlit as st

'''
run the following command to run the app:
python -m streamlit run app.py
'''

st.set_page_config(
    page_title="Startup Investments Dashboard",
    layout="wide"
)

st.title("Startup Investments Dashboard")

st.write("""
This dashboard explores startup investment data from Kaggle.
The goal is to understand funding trends, startup markets, countries, and company outcomes.
""")

st.markdown("""
### Main questions

1. Which startup markets receive the most funding?
2. Which countries have the most startup activity?
3. How did startup funding change over time?
4. Which companies reached acquisitions or IPOs?
5. What useful patterns can we find in the startup investment ecosystem?
""")