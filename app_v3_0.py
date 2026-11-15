
import io
from datetime import datetime
from decimal import Decimal
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="原材料物控系统 V3.0",
    layout="wide"
)

st.title("原材料物控智能分析系统 V3.0")
st.caption("第一阶段：模拟数据、精确时间库存、IQC、缺料及补投分析")

st.warning(
    "当前为模拟测试版，不连接ERP/MES，"
    "不自动修改采购订单或正式生产计划。"
)

def num(value):
    result = Decimal(str(value))
    if not result.is_finite() or result < 0:
        raise ValueError("数量必须为非负有效数值")
    return result

def parse_time(value):
    result = pd.to_datetime(value, errors="raise")
    if pd.isna(result):
        raise ValueError("时间不能为空")
    return result

# SIM-001 标准模拟数据
demands_default = pd.DataFrame([
    ["MO-001", "2026-12-10 08:00", 120],
    ["MO-002", "2026-12-10 16:00", 80],
    ["MO-003", "2026-12-11 08:00", 100],
    ["MO-004", "2026-12-12 08:00", 90],
], columns=["需求编号", "投料时间", "需求kg"])

events_default = pd.DataFrame([
    ["IQC-B002", "2026-12-10 12:00", "IQC放行", 100],
    ["ARR-R001", "2026-12-10 14:00", "到厂待检", 150],
    ["IQC-R001", "2026-12-11 10:00", "IQC放行", 150],
], columns=["事件编号", "事件时间", "事件类型", "数量kg"])

st.subheader("一、初始库存")

c1, c2, c3, c4 = st.columns(4)

with c1:
    qualified = st.number_input(
        "合格库存kg", min_value=0.0, value=180.0
    )
with c2:
    pending = st.number_input(
        "待检库存kg", min_value=0.0, value=100.0
    )
with c3:
    frozen = st.number_input(
        "冻结库存kg", min_value=0.0, value=50.0
    )
with c4:
    reserved = st.number_input(
        "正式预留kg", min_value=0.0, value=20.0
    )

st.subheader("二、生产物料需求")

demands = st.data_editor(
    demands_default,
    num_rows="dynamic",
    hide_index=True,
    key="demands"
)

st.subheader("三、到货与IQC事件")

events = st.data_editor(
    events_default,
    num_rows="dynamic",
    hide_index=True,
    key="events"
)

st.subheader("四、缺料恢复情景")

recovery_mode = st.radio(
    "选择模拟方式",
    ["不补投", "12月11日11:00补投40kg"],
    horizontal=True
)

def calculate():
    available = num(qualified) - num(reserved)
    waiting = num(pending)
    frozen_qty = num(frozen)

    if available < 0:
        raise ValueError("预留数量不能超过合格库存")

    timeline = []
    event_ids = set()
    demand_ids = set()

    for _, row in events.iterrows():
        event_id = str(row["事件编号"]).strip()
        if not event_id or event_id in event_ids:
            raise ValueError("事件编号为空或重复")
        event_ids.add(event_id)

        kind = str(row["事件类型"])
        if kind not in ["IQC放行", "到厂待检"]:
            raise ValueError("不支持的事件类型：" + kind)

        timeline.append((
            parse_time(row["事件时间"]),
            0,
            event_id,
            kind,
            num(row["数量kg"])
        ))

    for _, row in demands.iterrows():
        demand_id = str(row["需求编号"]).strip()
        if not demand_id or demand_id in demand_ids:
            raise ValueError("需求编号为空或重复")
        demand_ids.add(demand_id)

        timeline.append((
            parse_time(row["投料时间"]),
            1,
            demand_id,
            "生产需求",
            num(row["需求kg"])
        ))

    if recovery_mode != "不补投":
        timeline.append((
            parse_time("2026-12-11 11:00"),
            2,
            "REC-001",
            "模拟补投",
            Decimal("40")
        ))

    release_times = {
        x[0] for x in timeline if x[3] == "IQC放行"
    }
    demand_times = {
        x[0] for x in timeline if x[3] == "生产需求"
    }

    if release_times & demand_times:
        raise ValueError(
            "IQC放行与投料时间相同，"
            "请确认真实先后顺序后再计算"
        )

    timeline.sort(key=lambda x: (x[0], x[1], x[2]))

    records = []
    shortages = {}

    for time, _, event_id, kind, amount in timeline:
        fulfilled = Decimal("0")
        new_shortage = Decimal("0")

        if kind == "到厂待检":
            waiting += amount

        elif kind == "IQC放行":
            if amount > waiting:
                raise ValueError(
                    f"{event_id}：放行数量超过待检库存"
                )
            waiting -= amount
            available += amount

        elif kind == "生产需求":
            fulfilled = min(available, amount)
            new_shortage = amount - fulfilled
            available -= fulfilled

            shortages[event_id] = {
                "原需求时间": str(time),
                "原需求kg": amount,
                "按时满足kg": fulfilled,
                "未满足kg": new_shortage
            }

        elif kind == "模拟补投":
            outstanding = sum(
                (v["未满足kg"] for v in shortages.values()),
                Decimal("0")
            )

            if amount > outstanding:
                raise ValueError(
                    "补投量超过当前未满足需求"
                )

            if amount > available:
                raise ValueError(
                    "补投量超过当前可用库存"
                )

            available -= amount
            fulfilled = amount
            remainder = amount

            for item in shortages.values():
                take = min(item["未满足kg"], remainder)
                item["未满足kg"] -= take
                remainder -= take

                if remainder == 0:
                    break

        total_unfulfilled = sum(
            (v["未满足kg"] for v in shortages.values()),
            Decimal("0")
        )

        records.append({
            "时间": str(time),
            "事件编号": event_id,
            "事件类型": kind,
            "事件数量kg": float(amount),
            "本次满足kg": float(fulfilled),
            "本次新增缺口kg": float(new_shortage),
            "自由可用库存kg": float(available),
            "待检库存kg": float(waiting),
            "冻结库存kg": float(frozen_qty),
            "累计未满足kg": float(total_unfulfilled)
        })

    backlog = []

    for demand_id, item in shortages.items():
        backlog.append({
            "需求编号": demand_id,
            "原需求时间": item["原需求时间"],
            "原需求kg": float(item["原需求kg"]),
            "按时满足kg": float(item["按时满足kg"]),
            "剩余未满足kg": float(item["未满足kg"])
        })

    return pd.DataFrame(records), pd.DataFrame(backlog)

if st.button("开始计算", type="primary"):
    try:
        ledger, backlog = calculate()
        st.session_state["result"] = (ledger, backlog)
    except Exception as error:
        st.session_state.pop("result", None)
        st.error(f"计算失败：{error}")

if "result" in st.session_state:
    ledger, backlog = st.session_state["result"]

    shortage_rows = ledger[
        ledger["本次新增缺口kg"] > 0
    ]

    first_time = (
        shortage_rows.iloc[0]["时间"]
        if not shortage_rows.empty else "无"
    )

    first_qty = (
        shortage_rows.iloc[0]["本次新增缺口kg"]
        if not shortage_rows.empty else 0
    )

    remaining = (
        backlog["剩余未满足kg"].sum()
        if not backlog.empty else 0
    )

    m1, m2, m3 = st.columns(3)
    m1.metric("首次缺料时间", first_time)
    m2.metric("首次缺口", f"{first_qty:.2f} kg")
    m3.metric("剩余未满足", f"{remaining:.2f} kg")

    st.subheader("五、模拟滚动库存账本")
    st.dataframe(
        ledger, use_container_width=True, hide_index=True
    )

    st.subheader("六、未满足需求账本")
    st.dataframe(
        backlog, use_container_width=True, hide_index=True
    )

    st.subheader("七、库存变化趋势")
    st.line_chart(
        ledger.set_index("时间")["自由可用库存kg"]
    )

    output = io.BytesIO()

    with pd.ExcelWriter(
        output, engine="openpyxl"
    ) as writer:
        ledger.to_excel(
            writer, sheet_name="滚动库存", index=False
        )
        backlog.to_excel(
            writer, sheet_name="未满足需求", index=False
        )
        demands.to_excel(
            writer, sheet_name="生产需求", index=False
        )
        events.to_excel(
            writer, sheet_name="到货IQC", index=False
        )

    st.download_button(
        "下载Excel分析结果",
        data=output.getvalue(),
        file_name="原材料物控V3_0模拟结果.xlsx",
        mime=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        )
    )

st.divider()
st.caption(
    "V3.0第一阶段测试原型｜"
    "模拟库存分配不等于ERP实际领料，"
    "IQC预计放行不等于实际放行。"
)
