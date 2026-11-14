import io
import math
from datetime import date, timedelta
import pandas as pd
import streamlit as st

st.set_page_config(page_title='原材料物控分析系统 V2.1', page_icon='📦', layout='wide')
st.title('📦 原材料物控分析系统')
st.caption('V2.1｜多批次到货 · IQC放行 · 滚动库存 · 缺料预警')
st.info('本工具用于计划模拟；实际投料必须核实ERP库存、质量放行及订单优先级。')

with st.expander('① 基础参数', expanded=True):
    material = st.text_input('原材料名称', '电解液')
    c1, c2, c3 = st.columns(3)
    with c1:
        stock = st.number_input('初始合格库存(kg)', min_value=0.0, value=200.0, step=10.0)
        safety = st.number_input('安全库存(kg)', min_value=0.0, value=50.0, step=10.0)
    with c2:
        pending = st.number_input('初始待检库存(kg)', min_value=0.0, value=0.0, step=10.0)
        frozen = st.number_input('冻结库存(kg)', min_value=0.0, value=0.0, step=10.0)
    with c3:
        moq = st.number_input('最小起订量 MOQ(kg)', min_value=1.0, value=50.0, step=10.0)
        lead = st.number_input('采购提前期(天)', min_value=0, value=3)
    start = st.date_input('分析开始日期', value=date.today())
    horizon = st.number_input('分析天数', min_value=1, max_value=90, value=7)

st.subheader('② 每日订单需求（优先级数字越小越优先）')
st.caption('日期可重复；同日需求按优先级顺序分配。可在表格底部添加行。')
orders_default = pd.DataFrame([
    {'订单':'A订单','需求日期':start,'需求量kg':100.0,'优先级':1},
    {'订单':'B订单','需求日期':start + timedelta(days=1),'需求量kg':150.0,'优先级':2},
    {'订单':'C订单','需求日期':start + timedelta(days=2),'需求量kg':120.0,'优先级':3},
])
orders = st.data_editor(orders_default, num_rows='dynamic', hide_index=True, use_container_width=True,
    column_config={'需求日期':st.column_config.DateColumn('需求日期', format='YYYY-MM-DD'),
                   '需求量kg':st.column_config.NumberColumn('需求量kg', min_value=0),
                   '优先级':st.column_config.NumberColumn('优先级', min_value=1, step=1)}, key='orders')

st.subheader('③ 多批次采购到货与 IQC 放行')
st.caption('到货日期仅作跟踪；实际放行日期到达后，合格数量才进入可用库存。')
receipts_default = pd.DataFrame([
    {'批次':'采购批次1','到货日期':start + timedelta(days=1),'IQC放行日期':start + timedelta(days=3),'放行合格量kg':200.0},
])
receipts = st.data_editor(receipts_default, num_rows='dynamic', hide_index=True, use_container_width=True,
    column_config={'到货日期':st.column_config.DateColumn('到货日期', format='YYYY-MM-DD'),
                   'IQC放行日期':st.column_config.DateColumn('IQC放行日期', format='YYYY-MM-DD'),
                   '放行合格量kg':st.column_config.NumberColumn('放行合格量kg', min_value=0)}, key='receipts')

st.subheader('④ 初始待检库存放行计划')
release_initial = st.checkbox('分析期内计划放行初始待检库存', value=False)
if release_initial:
    pending_release_date = st.date_input('初始待检库存预计放行日期', value=start)
    pending_release_qty = st.number_input('初始待检库存预计合格放行量(kg)', min_value=0.0, max_value=float(pending), value=float(pending))
else:
    pending_release_qty = 0.0
    pending_release_date = start

if st.button('开始物控分析', type='primary'):
    errors = []
    order_rows = []
    receipt_rows = []
    for _, r in orders.iterrows():
        if pd.isna(r['需求日期']) or pd.isna(r['需求量kg']) or pd.isna(r['优先级']):
            errors.append('订单存在空白日期、需求量或优先级')
            continue
        d = pd.to_datetime(r['需求日期']).date()
        if float(r['需求量kg']) < 0 or int(r['优先级']) < 1:
            errors.append('需求量不得为负，优先级必须大于等于1')
        order_rows.append({'订单':str(r['订单']), '日期':d, '需求':float(r['需求量kg']), '优先级':int(r['优先级'])})
    for _, r in receipts.iterrows():
        if pd.isna(r['到货日期']) or pd.isna(r['IQC放行日期']) or pd.isna(r['放行合格量kg']):
            errors.append('采购批次存在空白日期或数量')
            continue
        arrived = pd.to_datetime(r['到货日期']).date()
        released = pd.to_datetime(r['IQC放行日期']).date()
        if released < arrived:
            errors.append(f"{r['批次']}：IQC放行日期不能早于到货日期")
        if float(r['放行合格量kg']) < 0:
            errors.append('放行合格量不得为负')
        receipt_rows.append({'批次':str(r['批次']), '到货':arrived, '放行':released, '数量':float(r['放行合格量kg'])})
    if errors:
        for e in sorted(set(errors)):
            st.error(e)
        st.stop()

    balance = float(stock)
    theoretical = float(stock)
    daily = []
    allocations = []
    first_shortage = None
    first_safety = None
    for i in range(int(horizon)):
        day = start + timedelta(days=i)
        releases = sum(r['数量'] for r in receipt_rows if r['放行'] == day)
        if release_initial and pending_release_date == day:
            releases += float(pending_release_qty)
        available = balance + releases
        day_orders = sorted([r for r in order_rows if r['日期'] == day], key=lambda r:r['优先级'])
        gross = sum(r['需求'] for r in day_orders)
        supplied = 0.0
        for o in day_orders:
            fulfilled = min(available, o['需求'])
            shortage = o['需求'] - fulfilled
            available -= fulfilled
            supplied += fulfilled
            allocations.append({'日期':str(day), '订单':o['订单'], '优先级':o['优先级'],
                                '需求kg':o['需求'], '分配kg':round(fulfilled, 2), '缺口kg':round(shortage, 2)})
        shortage_day = gross - supplied
        balance = available
        theoretical += releases - gross
        if shortage_day > 0 and first_shortage is None:
            first_shortage = (day, shortage_day)
        if balance < safety and first_safety is None:
            first_safety = day
        risk = '缺料' if shortage_day > 0 else ('高风险' if balance < safety else ('中风险' if balance == safety else '正常'))
        daily.append({'日期':str(day), '需求kg':round(gross,2), 'IQC放行kg':round(releases,2),
                      '实际投料kg':round(supplied,2), '当日缺口kg':round(shortage_day,2),
                      '可用期末库存kg':round(balance,2), '理论结存kg':round(theoretical,2), '风险':risk})

    result = pd.DataFrame(daily)
    detail = pd.DataFrame(allocations, columns=['日期','订单','优先级','需求kg','分配kg','缺口kg'])
    st.subheader('⑤ 每日滚动库存与风险结果')
    st.dataframe(result, use_container_width=True, hide_index=True)
    st.subheader('⑥ 订单优先级分配明细')
    st.dataframe(detail, use_container_width=True, hide_index=True)
    if first_shortage:
        st.error(f'首次缺料：{first_shortage[0]}，当日未满足需求 {first_shortage[1]:.2f} kg')
        target = first_shortage[1] + max(0, safety - balance)
        recommended = math.ceil(target / moq) * moq
        latest_order = first_shortage[0] - timedelta(days=int(lead))
        st.warning(f'采购建议（简化测算）：首缺口至少 {first_shortage[1]:.2f} kg；按MOQ向上取整至少 {math.ceil(first_shortage[1]/moq)*moq:.2f} kg。若要在首次缺料日可用，且不计IQC检验时间，最迟下单日期为 {latest_order}。实际应提前考虑IQC检验、运输及供应商承诺。')
    else:
        st.success('分析期内没有未满足的生产需求。')
    if first_safety:
        st.warning(f'首次低于安全库存：{first_safety}（不代表一定停线）')
    st.caption('理论结存允许负数，仅用于表达累计供需缺口；实际可用库存不会为负。未满足需求未自动结转至下一日，需另行调整订单计划。冻结库存不计可用；期前已放行批次请计入初始合格库存。')
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        result.to_excel(writer, sheet_name='每日滚动库存', index=False)
        detail.to_excel(writer, sheet_name='订单分配', index=False)
        pd.DataFrame(receipt_rows).to_excel(writer, sheet_name='采购批次', index=False)
    st.download_button('📥 下载Excel分析结果', data=output.getvalue(), file_name='原材料物控分析_V2.1.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')