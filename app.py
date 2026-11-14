
import streamlit as st
from datetime import date, timedelta

st.set_page_config(
    page_title="原材料物控分析系统",
    page_icon="📦",
    layout="wide"
)

st.title("📦 原材料物控分析系统")
st.caption("V2.0 | 滚动库存与缺料预警")

material = st.text_input("物料名称", "电解液")
stock = st.number_input(
    "初始合格库存(kg)", min_value=0, value=200
)
safety = st.number_input(
    "安全库存(kg)", min_value=0, value=50
)

start = st.date_input(
    "分析开始日期", date(2026, 11, 16)
)

st.subheader("每日生产需求")
demands = []
for i in range(5):
    day = start + timedelta(days=i)
    qty = st.number_input(
        str(day) + " 需求(kg)",
        min_value=0,
        value=[100, 150, 120, 0, 100][i],
        key=f"d{i}"
    )
    demands.append(qty)

st.subheader("采购到货与检验放行")
arrival = st.date_input(
    "采购到货日期", start + timedelta(days=1)
)
release = st.date_input(
    "IQC实际/预计放行日期",
    start + timedelta(days=3)
)
incoming = st.number_input(
    "放行合格数量(kg)",
    min_value=0,
    value=200
)

if st.button("开始物控分析", type="primary"):
    if release < arrival:
        st.error("IQC放行日期不能早于到货日期")
        st.stop()

    balance = stock
    first_shortage = None
    rows = []

    for i, demand in enumerate(demands):
        day = start + timedelta(days=i)

        usable = incoming if day == release else 0
        available = balance + usable
        shortage = max(0, demand - available)

        if shortage > 0 and first_shortage is None:
            first_shortage = (day, shortage)

        # 未满足的需求保留为欠料
        balance = available - demand

        if shortage > 0 or balance < 0:
            risk = "缺料"
        elif balance < safety:
            risk = "高风险"
        elif balance == safety:
            risk = "中风险"
        else:
            risk = "正常"

        rows.append({
            "日期": str(day),
            "需求kg": demand,
            "当日放行kg": usable,
            "理论结存kg": balance,
            "风险": risk
        })

    st.subheader("分析结果")
    st.dataframe(rows, use_container_width=True)

    if first_shortage:
        st.error(
            f"首次缺料：{first_shortage[0]}，"
            f"当日缺口{first_shortage[1]}kg"
        )
    else:
        st.success("分析期内未发现缺料")
