# ---------- app.py ----------
import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px

st.set_page_config(page_title="Local Food Wastage", page_icon="🍽", layout="wide")
import sqlite3
import pandas as pd

# Connect to SQLite
conn = sqlite3.connect("food_wastage.db")
import datetime


# Load CSV files
providers_df = pd.read_csv("providers_data.csv")
receivers_df = pd.read_csv("receivers_data.csv")
food_df = pd.read_csv("food_listings_data.csv")
claims_df = pd.read_csv("claims_data.csv")

# Save to SQL tables (overwrite each run)
providers_df.to_sql("providers", conn, if_exists="replace", index=False)
receivers_df.to_sql("receivers", conn, if_exists="replace", index=False)
food_df.to_sql("food_listings", conn, if_exists="replace", index=False)
claims_df.to_sql("claims", conn, if_exists="replace", index=False)

# Now your load_tables() can safely query these tables


@st.cache_resource
def get_conn():
    return sqlite3.connect("food_wastage.db", check_same_thread=False)

@st.cache_data
def load_tables(_conn):
    providers  = pd.read_sql("SELECT * FROM providers", _conn)
    receivers  = pd.read_sql("SELECT * FROM receivers", _conn)
    foods      = pd.read_sql("SELECT * FROM food_listings", _conn, parse_dates=["Expiry_Date"])
    claims     = pd.read_sql("SELECT * FROM claims", _conn, parse_dates=["Timestamp"])
    return providers, receivers, foods, claims

conn = get_conn()
providers_df, receivers_df, food_df, claims_df = load_tables(conn)

st.title("🍽 Local Food Wastage Management System")

# ---------------- Sidebar Filters ----------------
with st.sidebar:
    st.header("Filters")
    cities  = sorted(list(set(providers_df["City"].dropna().tolist() + food_df["Location"].dropna().tolist())))
    f_city  = st.selectbox("City", options=["All"] + cities, index=0)
    f_type  = st.selectbox("Food Type", options=["All"] + sorted(food_df["Food_Type"].unique().tolist()))
    f_meal  = st.selectbox("Meal Type", options=["All"] + sorted(food_df["Meal_Type"].unique().tolist()))
    provider_names = ["All"] + sorted(providers_df["Name"].unique().tolist())
    f_provider = st.selectbox("Provider", options=provider_names)

# --------------- Tabs ----------------
tabs = st.tabs(["📊 EDA", "🔎 SQL Queries", "🗂 Listings & Contacts", "✏️ CRUD / Claim"])

# ---------------- EDA ----------------
with tabs[0]:
    st.subheader("Overview")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Providers", len(providers_df))
    c2.metric("Receivers", len(receivers_df))
    c3.metric("Food Listings", len(food_df))
    c4.metric("Claims", len(claims_df))

    # filters applied to listings
    df = food_df.copy()
    if f_city != "All":    df = df[df["Location"] == f_city]
    if f_type != "All":    df = df[df["Food_Type"] == f_type]
    if f_meal != "All":    df = df[df["Meal_Type"] == f_meal]
    if f_provider != "All":
        pid = providers_df.loc[providers_df["Name"]==f_provider, "Provider_ID"]
        df  = df[df["Provider_ID"].isin(pid)]

    st.markdown("**Filtered Listings**")
    st.dataframe(df)

    colA, colB = st.columns(2)
    with colA:
        st.markdown("Listings by City")
        fig = px.bar(food_df.groupby("Location").size().reset_index(name="Count"),
                     x="Location", y="Count")
        st.plotly_chart(fig, use_container_width=True)
    with colB:
        st.markdown("Food Type Distribution")
        fig = px.bar(food_df.groupby("Food_Type").size().reset_index(name="Count"),
                     x="Food_Type", y="Count")
        st.plotly_chart(fig, use_container_width=True)

    colC, colD = st.columns(2)
    with colC:
        st.markdown("Meal Type Distribution")
        fig = px.bar(food_df.groupby("Meal_Type").size().reset_index(name="Count"),
                     x="Meal_Type", y="Count")
        st.plotly_chart(fig, use_container_width=True)
    with colD:
        if not claims_df.empty:
            st.markdown("Claim Status Split")
            fig = px.pie(claims_df, names="Status")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No claims yet to visualize.")

# --------------- SQL QUERIES ---------------
with tabs[1]:
    st.subheader("Predefined SQL (15+)")
    PRESET_QUERIES = {
        "1 Providers & Receivers per City": """
          WITH p AS (SELECT City, COUNT(*) providers FROM providers GROUP BY City),
               r AS (SELECT City, COUNT(*) receivers FROM receivers GROUP BY City)
          SELECT COALESCE(p.City,r.City) City,
                 COALESCE(providers,0) Total_Providers,
                 COALESCE(receivers,0) Total_Receivers
          FROM p LEFT JOIN r ON p.City=r.City
          UNION
          SELECT r.City, 0, r.receivers FROM r
          WHERE r.City NOT IN (SELECT City FROM p)
        """,
        "2 Provider type by total quantity": """
          SELECT Provider_Type, SUM(Quantity) AS Total_Quantity
          FROM food_listings
          GROUP BY Provider_Type
          ORDER BY Total_Quantity DESC
        """,
        "3 Providers & contacts (choose city below)": "DYNAMIC_CITY",
        "4 Receivers with most claims": """
          SELECT r.Name, COUNT(*) AS Total_Claims
          FROM claims c JOIN receivers r ON c.Receiver_ID=r.Receiver_ID
          GROUP BY r.Name ORDER BY Total_Claims DESC
        """,
        "5 Total quantity available (not expired)": """
          SELECT SUM(Quantity) AS Total_Available
          FROM food_listings
          WHERE DATE(Expiry_Date) >= DATE('now')
        """,
        "6 City with highest number of listings": """
          SELECT Location AS City, COUNT(*) AS Listing_Count
          FROM food_listings GROUP BY Location ORDER BY Listing_Count DESC
        """,
        "7 Most common food types": """
          SELECT Food_Type, COUNT(*) AS Items
          FROM food_listings GROUP BY Food_Type ORDER BY Items DESC
        """,
        "8 Claims per food item": """
          SELECT f.Food_Name, COUNT(c.Claim_ID) AS Claims
          FROM claims c JOIN food_listings f ON c.Food_ID=f.Food_ID
          GROUP BY f.Food_Name ORDER BY Claims DESC
        """,
        "9 Provider with highest successful claims": """
          SELECT p.Name, COUNT(*) Successful_Claims
          FROM claims c
          JOIN food_listings f ON c.Food_ID=f.Food_ID
          JOIN providers p ON f.Provider_ID=p.Provider_ID
          WHERE c.Status='Completed'
          GROUP BY p.Name ORDER BY Successful_Claims DESC
        """,
        "10 Claim status percentages": """
          SELECT Status,
                 ROUND(COUNT(*)*100.0/(SELECT COUNT(*) FROM claims),2) AS Percentage
          FROM claims GROUP BY Status
        """,
        "11 Avg listed quantity of claimed items per receiver": """
          SELECT r.Name, ROUND(AVG(f.Quantity),2) AS Avg_Qty
          FROM claims c
          JOIN receivers r ON c.Receiver_ID=r.Receiver_ID
          JOIN food_listings f ON c.Food_ID=f.Food_ID
          GROUP BY r.Name ORDER BY Avg_Qty DESC
        """,
        "12 Most claimed meal type": """
          SELECT f.Meal_Type, COUNT(*) Claims
          FROM claims c JOIN food_listings f ON c.Food_ID=f.Food_ID
          GROUP BY f.Meal_Type ORDER BY Claims DESC
        """,
        "13 Total quantity donated by provider": """
          SELECT p.Name, SUM(f.Quantity) Total_Donated
          FROM food_listings f JOIN providers p ON f.Provider_ID=p.Provider_ID
          GROUP BY p.Name ORDER BY Total_Donated DESC
        """,
        "14 Cities with highest completed claims": """
          SELECT f.Location AS City, COUNT(*) Completed_Claims
          FROM claims c JOIN food_listings f ON c.Food_ID=f.Food_ID
          WHERE c.Status='Completed'
          GROUP BY f.Location ORDER BY Completed_Claims DESC
        """,
        "15 Expired items still listed": """
          SELECT Food_ID, Food_Name, Quantity, Expiry_Date, Location
          FROM food_listings WHERE DATE(Expiry_Date) < DATE('now')
          ORDER BY DATE(Expiry_Date)
        """,
        "16 Items expiring in next 2 days": """
          SELECT Food_ID, Food_Name, Quantity, Expiry_Date, Location
          FROM food_listings
          WHERE DATE(Expiry_Date) BETWEEN DATE('now') AND DATE('now','+2 day')
          ORDER BY DATE(Expiry_Date)
        """,
        "17 Unclaimed items": """
          SELECT f.Food_ID, f.Food_Name, f.Quantity, f.Expiry_Date, f.Location
          FROM food_listings f LEFT JOIN claims c ON f.Food_ID=c.Food_ID
          WHERE c.Claim_ID IS NULL ORDER BY f.Expiry_Date
        """,
        "18 Provider conversion rate (Completed/All)": """
          WITH stats AS (
            SELECT p.Name,
                   SUM(CASE WHEN c.Status='Completed' THEN 1 ELSE 0 END) Completed,
                   COUNT(*) Total
            FROM claims c
            JOIN food_listings f ON c.Food_ID=f.Food_ID
            JOIN providers p ON f.Provider_ID=p.Provider_ID
            GROUP BY p.Name
          )
          SELECT Name, Completed, Total,
                 ROUND(Completed*100.0/NULLIF(Total,0),2) AS Conversion_Percentage
          FROM stats ORDER BY Conversion_Percentage DESC
        """
    }

    qname = st.selectbox("Choose a query", list(PRESET_QUERIES.keys()))
    if qname == "3 Providers & contacts (choose city below)":
        city = st.selectbox("City", sorted(providers_df["City"].unique().tolist()))
        sql  = "SELECT Name, Type, City, Contact FROM providers WHERE City = ?"
        result = pd.read_sql(sql, conn, params=[city])
    else:
        sql = PRESET_QUERIES[qname]
        result = pd.read_sql(sql, conn)

    st.dataframe(result, use_container_width=True)

    # simple auto-viz for 2+ columns where 2nd is numeric
    if result.shape[1] >= 2 and pd.api.types.is_numeric_dtype(result.iloc[:,1]):
        st.bar_chart(result.set_index(result.columns[0]))

# --------------- Listings & Contacts ---------------
with tabs[2]:
    st.subheader("Browse Listings + Provider Contacts")
    df = food_df.copy()
    if f_city != "All": df = df[df["Location"] == f_city]
    if f_type != "All": df = df[df["Food_Type"] == f_type]
    if f_meal != "All": df = df[df["Meal_Type"] == f_meal]
    if f_provider != "All":
        pid = providers_df.loc[providers_df["Name"]==f_provider, "Provider_ID"]
        df = df[df["Provider_ID"].isin(pid)]
    # attach provider contact
    df = df.merge(providers_df[["Provider_ID","Name","Contact","City"]],
                  on="Provider_ID", how="left", suffixes=("","_Provider"))
    st.dataframe(df[["Food_ID","Food_Name","Quantity","Expiry_Date","Food_Type","Meal_Type",
                     "Location","Name","Contact"]].sort_values("Expiry_Date"))

# --------------- CRUD / Claim ---------------
with tabs[3]:
    st.subheader("Add Food Listing")
    with st.form("addfood"):
        c1, c2 = st.columns(2)
        with c1:
            fid   = st.number_input("Food_ID", step=1)
            fname = st.text_input("Food_Name")
            qty   = st.number_input("Quantity", step=1, min_value=0)
            exp   = st.date_input("Expiry_Date")
        with c2:
            pid   = st.selectbox("Provider_ID", sorted(providers_df["Provider_ID"].tolist()))
            ptype = st.text_input("Provider_Type")
            loc   = st.text_input("Location")
            ftype = st.text_input("Food_Type")
            mtype = st.text_input("Meal_Type")
        if st.form_submit_button("Create"):
            conn.execute("INSERT INTO food_listings VALUES (?,?,?,?,?,?,?,?,?)",
                (int(fid), fname, int(qty), str(exp), int(pid), ptype, loc, ftype, mtype))
            conn.commit()
            st.success("Food listing added.")

    st.divider()
    st.subheader("Update Quantity")
    ufid = st.number_input("Food_ID to update", step=1)
    newq = st.number_input("New Quantity", step=1, min_value=0)
    if st.button("Update"):
        conn.execute("UPDATE food_listings SET Quantity=? WHERE Food_ID=?", (int(newq), int(ufid)))
        conn.commit()
        st.success("Quantity updated.")

    st.subheader("Delete Listing")
    dfid = st.number_input("Food_ID to delete", step=1)
    if st.button("Delete"):
        conn.execute("DELETE FROM food_listings WHERE Food_ID=?", (int(dfid),))
        conn.commit()
        st.success("Listing deleted.")

    st.divider()
    st.subheader("Create a Claim")
    with st.form("claimform"):
        food_id   = st.number_input("Food_ID", step=1)
        receiver  = st.selectbox("Receiver_ID", sorted(receivers_df["Receiver_ID"].tolist()))
        status    = st.selectbox("Status", ["Pending","Completed","Cancelled"])
        date = st.date_input("Select Date", datetime.date.today())
        time = st.time_input("Select Time", datetime.datetime.now().time())
        ts = datetime.datetime.combine(date, time)
        if st.form_submit_button("Submit Claim"):
            conn.execute("INSERT INTO claims (Food_ID, Receiver_ID, Status, Timestamp) VALUES (?,?,?,?)",
                         (int(food_id), int(receiver), status, str(ts)))
            conn.commit()
            st.success("Claim recorded.")
  

# ---------- end app.py ----------




