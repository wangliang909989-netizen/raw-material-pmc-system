import io
import math
from datetime import date, datetime, timedelta
import calendar
import pandas as pd
import streamlit as st

st.set_page_config(page_title='原材料物控系统 V3.1', layout='wide')
st.title('原材料物控综合滚动计划 V3.1')
st.caption('Sheet1：生产计划、BOM、库存、到货安排、库容及资金统一分析 ｜ Sheet2：采购到货计划邮件输出')
st.warning('模拟测试系统：不连接ERP/MES，不自动下单。建议到货与供应商确认到货、IQC实际放行须区分。')

PRODUCTS = ['电芯A', '电芯B']
TODAY = date.today()
MONTH = TODAY.replace(day=1)

def demo_data():
    ds = pd.date_range(MONTH, periods=calendar.monthrange(MONTH.year, MONTH.month)[1], freq='D')
    production = pd.DataFrame([{'日期': d.date(), '产品': p, '计划产量': (200 if p == '电芯A' else 70) if d.weekday() < 6 else 0, '生产良率': 0.95 if p == '电芯A' else 0.97} for d in ds for p in PRODUCTS])
    materials = pd.DataFrame([
        ['M001', '电解液', 'kg', 300., 0., 0., 0., 100., 1000., 80., 2, 100., 1, 0.],
        ['M002', '铝壳', '个', 600., 0., 0., 0., 200., 5000., 8., 1, 500., 0, 0.],
        ['M003', '铜箔', 'kg', 400., 40., 0., 0., 100., 800., 140., 4, 50., 1, 0.],
    ], columns=['物料编码','物料名称','单位','合格库存','待检库存','冻结库存','已预留','安全库存','最大库容','单价(元)','采购周期(天)','MOQ','IQC周期(天)','额外损耗率'])
    bom = pd.DataFrame([
        ['电芯A','M001',0.20], ['电芯B','M001',0.22], ['电芯A','M002',1.0], ['电芯B','M002',1.0], ['电芯A','M003',0.10], ['电芯B','M003',0.12],
    ], columns=['产品','物料编码','BOM单耗'])
    arrivals = pd.DataFrame([
        ['M001', TODAY + timedelta(days=2), 500., '计划安排', '', ''],
        ['M002', TODAY + timedelta(days=1), 1000., '计划安排', '', ''],
    ], columns=['物料编码','到厂日期','到货数量','到货状态','采购订单号','备注'])
    return production, materials, bom, arrivals

if 'v31_data' not in st.session_state:
    p, m, b, a = demo_data()
    st.session_state['v31_data'] = {'production':p, 'materials':m, 'bom':b, 'arrivals':a}

with st.sidebar:
    st.header('计划设置')
    selected_month = st.date_input('计划月份（选择该月任意日期）', value=MONTH)
    month_start = selected_month.replace(day=1)
    month_end = month_start.replace(day=calendar.monthrange(month_start.year, month_start.month)[1])
    monthly_cap = st.number_input('月末库存金额上限（元）', min_value=0., value=150000., step=10000.)
    show_all = st.checkbox('显示全部物料基础字段', value=True)
    material_filter = st.multiselect('筛选物料（留空显示全部）', options=st.session_state['v31_data']['materials']['物料名称'].tolist())
    if st.button('恢复全部演示数据'):
        p, m, b, a = demo_data()
        st.session_state['v31_data'] = {'production':p,'materials':m,'bom':b,'arrivals':a}
        st.rerun()

sheet1, sheet2 = st.tabs(['Sheet1｜综合滚动计划总表', 'Sheet2｜采购到货计划'])

with sheet1:
    st.subheader('生产计划、良率与原材料滚动计划（同一张总表）')
    st.caption('先在下方编辑生产计划、BOM、库存参数和到货安排；系统自动重新计算上方的综合滚动表。')
    with st.expander('① 编辑每日生产计划及良率', expanded=False):
        p_edit = st.data_editor(st.session_state['v31_data']['production'], num_rows='dynamic', hide_index=True, key='v31_prod_editor', use_container_width=True)
        st.session_state['v31_data']['production'] = p_edit
    with st.expander('② 编辑物料参数（库存、安全库存、库容、单价、采购周期、MOQ）', expanded=False):
        m_edit = st.data_editor(st.session_state['v31_data']['materials'], num_rows='dynamic', hide_index=True, key='v31_mat_editor', use_container_width=True)
        st.session_state['v31_data']['materials'] = m_edit
    with st.expander('③ 编辑产品BOM用量', expanded=False):
        b_edit = st.data_editor(st.session_state['v31_data']['bom'], num_rows='dynamic', hide_index=True, key='v31_bom_editor', use_container_width=True)
        st.session_state['v31_data']['bom'] = b_edit
    with st.expander('④ 在总表安排到货（Sheet2自动提取）', expanded=True):
        st.caption('到货状态：计划安排=内部计划，采购确认=已获供应商确认，实际到厂=到厂待检，IQC已放行=已可用。仅“采购确认”和“IQC已放行”按其放行日计入保障预测；计划安排只用于方案模拟。')
        a_edit = st.data_editor(st.session_state['v31_data']['arrivals'], num_rows='dynamic', hide_index=True, key='v31_arr_editor', use_container_width=True,
            column_config={'到货状态':st.column_config.SelectboxColumn('到货状态', options=['计划安排','采购确认','实际到厂','IQC已放行'])})
        st.session_state['v31_data']['arrivals'] = a_edit

p = st.session_state['v31_data']['production'].copy()
m = st.session_state['v31_data']['materials'].copy()
b = st.session_state['v31_data']['bom'].copy()
a = st.session_state['v31_data']['arrivals'].copy()

try:
    for frame, cols in [(p,['计划产量','生产良率']),(m,['合格库存','待检库存','冻结库存','已预留','安全库存','最大库容','单价(元)','采购周期(天)','MOQ','IQC周期(天)','额外损耗率']),(b,['BOM单耗']),(a,['到货数量'])]:
        for col in cols:
            frame[col] = pd.to_numeric(frame[col], errors='raise')
            if frame[col].isna().any() or (~frame[col].map(math.isfinite)).any() or (frame[col] < 0).any():
                raise ValueError(f'{col}存在空值、负数或无效数值')
    if (p['生产良率'] <= 0).any() or (p['生产良率'] > 1).any():
        raise ValueError('生产良率必须大于0且不超过1（例如95%输入0.95）')
    if (m['额外损耗率'] >= 1).any():
        raise ValueError('额外损耗率须小于1')
    if m['物料编码'].isna().any() or m['物料编码'].duplicated().any():
        raise ValueError('物料编码必须唯一且不能为空')
    if (m['合格库存'] < m['已预留']).any():
        raise ValueError('已预留数量不得超过合格库存')
    if ((m['最大库容'] <= 0) | (m['MOQ'] <= 0)).any():
        raise ValueError('最大库容和MOQ必须大于0')
    p['日期'] = pd.to_datetime(p['日期'], errors='raise').dt.date
    a['到厂日期'] = pd.to_datetime(a['到厂日期'], errors='raise').dt.date
    if p[['日期','产品']].duplicated().any():
        raise ValueError('每日同一产品只能有一条生产计划，请合并数量')
    if b[['产品','物料编码']].duplicated().any():
        raise ValueError('同一产品与物料编码的BOM组合不能重复')
    if not set(b['物料编码']).issubset(set(m['物料编码'])):
        raise ValueError('BOM存在未定义的物料编码')
    if not set(b['产品']).issubset(set(p['产品'])):
        raise ValueError('BOM存在未定义的产品，请先维护生产计划')
    if not set(a['物料编码'].dropna()).issubset(set(m['物料编码'])):
        raise ValueError('到货计划存在未定义的物料编码')
    if not set(a['到货状态'].dropna()).issubset({'计划安排','采购确认','实际到厂','IQC已放行'}):
        raise ValueError('到货状态无效')
    days = list(pd.date_range(month_start, month_end, freq='D').date)
    p = p[p['日期'].isin(days)]
    demand = {}
    for _, pr in p.iterrows():
        for _, bom_row in b[b['产品'] == pr['产品']].iterrows():
            code = bom_row['物料编码']
            mat_row = m[m['物料编码'] == code].iloc[0]
            # 合格品计划产量 / 良率 × BOM单耗 / (1-额外损耗率)
            qty = pr['计划产量'] / pr['生产良率'] * bom_row['BOM单耗'] / (1 - mat_row['额外损耗率'])
            demand[(code,pr['日期'])] = demand.get((code,pr['日期']),0.) + qty
    day_headers = [d.strftime('%m/%d') for d in days]
    plan_by_product = p.pivot_table(index='产品', columns='日期', values='计划产量', aggfunc='sum', fill_value=0)
    yield_by_product = p.pivot_table(index='产品', columns='日期', values='生产良率', aggfunc='first')
    header_rows = []
    for product in sorted(p['产品'].unique()):
        for typ, src, fmt in [('生产计划',plan_by_product,lambda x:round(float(x),2)),('生产良率',yield_by_product,lambda x: f'{float(x):.1%}' if pd.notna(x) else '')]:
            row = {'物料编码':'—','物料名称':f'【{product}】{typ}','指标':typ}
            for d, h in zip(days, day_headers):
                val = src.loc[product,d] if product in src.index and d in src.columns else (0 if typ=='生产计划' else float('nan'))
                row[h] = fmt(val)
            header_rows.append(row)
    all_rows = []
    daily_rows = []
    summaries = []
    warnings = []
    for _, mat in m.iterrows():
        code = mat['物料编码']
        if material_filter and mat['物料名称'] not in material_filter:
            continue
        free_start = float(mat['合格库存'] - mat['已预留'])
        unit = str(mat['单位'])
        material_arrivals = a[a['物料编码']==code].copy()
        # 计划安排和到厂待检均不算已确认可用；采购确认需要IQC周期后才可用。
        confirmed = {}
        proposed = {}
        for _, ar in material_arrivals.iterrows():
            qty = float(ar['到货数量'])
            if qty <= 0:
                continue
            status = ar['到货状态']
            dt = ar['到厂日期']
            proposed[dt] = proposed.get(dt,0.) + qty
            if status == 'IQC已放行':
                ready = dt
            elif status == '采购确认':
                ready = dt + timedelta(days=int(math.ceil(mat['IQC周期(天)'])))
            else:
                continue
            confirmed[ready] = confirmed.get(ready,0.) + qty
        # 日初现货保障天数与确认供给保障天数，按需求日期推进，不区分自然/工作日。
        only_stock = free_start
        with_supply = free_start
        stock_cover = 0
        supply_cover = 0
        stock_broken = False
        supply_broken = False
        first_shortage = None
        first_safety = None
        day_need = {}
        day_arrival = {}
        day_end = {}
        day_risk = {}
        for d in days:
            need = float(demand.get((code,d),0.))
            inbound = float(confirmed.get(d,0.))
            only_stock -= need
            with_supply += inbound - need
            if not stock_broken:
                if only_stock < -1e-8:
                    stock_broken = True
                else:
                    stock_cover += 1
            if not supply_broken:
                if with_supply < -1e-8:
                    supply_broken = True
                else:
                    supply_cover += 1
            if first_shortage is None and with_supply < -1e-8:
                first_shortage = d
            if first_safety is None and with_supply <= float(mat['安全库存']) + 1e-8:
                first_safety = d
            if with_supply < 0:
                risk = '缺料'
            elif with_supply < float(mat['安全库存']):
                risk = '低于安全库存'
            elif with_supply > float(mat['最大库容']):
                risk = '超库容'
            else:
                risk = '正常'
            day_need[d] = need
            day_arrival[d] = inbound
            day_end[d] = with_supply
            day_risk[d] = risk
            daily_rows.append({'日期':d.isoformat(),'物料编码':code,'物料名称':mat['物料名称'],'单位':unit,'生产需求':round(need,3),'确认可用到货':round(inbound,3),'预计结存':round(with_supply,3),'预计库存金额':round(max(with_supply,0)*mat['单价(元)'],2),'库存风险':risk})
        # 采购建议：只在已确认供给不足安全库存时提出；不把计划安排视为确认供给。
        trigger = first_safety or first_shortage
        lead = int(math.ceil(mat['采购周期(天)'] + mat['IQC周期(天)']))
        order_day = trigger - timedelta(days=lead) if trigger else None
        suggested_qty = 0.
        if trigger:
            future_needs = sum(day_need[d] for d in days if d >= trigger)
            future_confirmed = sum(q for d,q in confirmed.items() if d > trigger and d <= month_end)
            baseline = day_end[trigger]
            shortage_to_cover = max(0., float(mat['安全库存']) - baseline + future_needs - day_need[trigger] - future_confirmed)
            suggested_qty = math.ceil(shortage_to_cover / mat['MOQ']) * mat['MOQ'] if shortage_to_cover > 0 else 0.
        if order_day and order_day < TODAY:
            warnings.append(f'{mat["物料名称"]}：建议下单日 {order_day} 已早于今天，需协调加急或调整生产/到货。')
        max_stock = max([free_start] + list(day_end.values()))
        if max_stock > float(mat['最大库容']):
            warnings.append(f'{mat["物料名称"]}：预测库存峰值 {max_stock:.2f}{unit} 超过最大库容 {mat["最大库容"]:.2f}{unit}。')
        monthly_end = day_end[days[-1]]
        summary = {'物料编码':code,'物料名称':mat['物料名称'],'单位':unit,'BOM信息':'；'.join(f'{x["产品"]}:{x["BOM单耗"]:g}' for _,x in b[b['物料编码']==code].iterrows()),
            '合格库存':mat['合格库存'],'待检库存':mat['待检库存'],'冻结库存':mat['冻结库存'],'已预留':mat['已预留'],
            '在途/安排总量':round(material_arrivals['到货数量'].sum(),3),'仅现货可用天数':stock_cover,'含确认到货可用天数':supply_cover,
            '安全库存':mat['安全库存'],'最大库容':mat['最大库容'],'采购周期(天)':mat['采购周期(天)'],'MOQ':mat['MOQ'],'单价(元)':mat['单价(元)'],
            '当前库存金额(元)':round(mat['合格库存']*mat['单价(元)'],2),
            '月需求总量':round(sum(day_need.values()),3),'月末预计结存':round(monthly_end,3),'月末预计库存金额(元)':round(max(monthly_end,0)*mat['单价(元)'],2),
            '首次缺料日':first_shortage.isoformat() if first_shortage else '本月无',
            '安全库存触发日':first_safety.isoformat() if first_safety else '本月无',
            '建议下单日期':order_day.isoformat() if order_day else '暂无',
            '建议下单量':round(suggested_qty,3),
            '建议到货日期':(order_day+timedelta(days=int(math.ceil(mat['采购周期(天)'])))).isoformat() if order_day else '暂无',
            '建议放行日期':trigger.isoformat() if trigger else '暂无',
            '预计峰值库存':round(max_stock,3)}
        summaries.append(summary)
        base = {'物料编码':code,'物料名称':mat['物料名称']}
        fixed_cols = ['BOM信息','合格库存','在途/安排总量','仅现货可用天数','含确认到货可用天数','安全库存','最大库容','采购周期(天)','MOQ','单价(元)','月末预计库存金额(元)','建议下单日期','建议下单量','建议到货日期','首次缺料日']
        if show_all:
            fixed_cols = ['BOM信息','合格库存','待检库存','冻结库存','已预留','在途/安排总量','仅现货可用天数','含确认到货可用天数','安全库存','最大库容','采购周期(天)','MOQ','单价(元)','当前库存金额(元)','月需求总量','月末预计结存','月末预计库存金额(元)','首次缺料日','安全库存触发日','建议下单日期','建议下单量','建议到货日期','建议放行日期','预计峰值库存']
        for metric, values in [('需求',day_need),('确认可用到货',day_arrival),('预计结存',day_end),('风险',day_risk)]:
            row = dict(base)
            row['指标'] = metric
            for col in fixed_cols:
                row[col] = summary[col] if metric == '预计结存' else ''
            for d,h in zip(days,day_headers):
                v = values[d]
                row[h] = round(v,2) if isinstance(v,(float,int)) else v
            all_rows.append(row)
    summary_df = pd.DataFrame(summaries)
    daily_df = pd.DataFrame(daily_rows)
    grid_df = pd.DataFrame(header_rows + all_rows)
    if not grid_df.empty:
        first = ['物料编码','物料名称','指标']
        fixed = [x for x in grid_df.columns if x not in first and x not in day_headers]
        grid_df = grid_df[first+fixed+day_headers]
    month_total = summary_df['月末预计库存金额(元)'].sum() if not summary_df.empty else 0.
    with sheet1:
        c1,c2,c3,c4 = st.columns(4)
        c1.metric('月末预计库存金额',f'¥{month_total:,.2f}')
        c2.metric('月末金额控制上限',f'¥{monthly_cap:,.2f}')
        c3.metric('金额余量',f'¥{monthly_cap-month_total:,.2f}')
        c4.metric('本月预测缺料物料数',str((summary_df['首次缺料日']!='本月无').sum()) if not summary_df.empty else '0')
        if month_total > monthly_cap:
            st.error(f'预计月末库存金额超标 ¥{month_total-monthly_cap:,.2f}。请调整总表到货计划，确保不影响生产及安全库存。')
        st.dataframe(grid_df, use_container_width=True, hide_index=True, height=560)
        st.caption('顶部为每日生产计划与良率；每个物料按需求、确认可用到货、预计结存和风险分行，横向日期滚动。固定信息显示在“预计结存”行。')
        if warnings:
            with st.expander(f'异常提示（{len(warnings)}条）'):
                for w in warnings:
                    st.warning(w)
        st.caption('可用天数=本月起连续能够满足每日需求的日期数；若月内始终满足，则显示本月覆盖天数（不代表下月也安全）。零需求日计入连续覆盖。')

    # Sheet2只输出需要安排的到货批次，不泄露内部库存金额等字段。
    orders = a[a['到货数量'] > 0].copy()
    if not orders.empty:
        names = m.set_index('物料编码')['物料名称'].to_dict()
        units = m.set_index('物料编码')['单位'].to_dict()
        orders.insert(1,'物料名称',orders['物料编码'].map(names))
        orders.insert(2,'单位',orders['物料编码'].map(units))
        orders['要求到货日期'] = orders['到厂日期'].map(lambda d: d.isoformat())
        orders = orders[['物料编码','物料名称','单位','到货数量','要求到货日期','到货状态','采购订单号','备注']]
        orders = orders.sort_values(['要求到货日期','物料编码'])
    else:
        orders = pd.DataFrame(columns=['物料编码','物料名称','单位','到货数量','要求到货日期','到货状态','采购订单号','备注'])
    with sheet2:
        st.subheader('采购到货计划（只提取Sheet1安排到货的物料）')
        st.caption('数量大于0的到货批次自动提取；不显示BOM、库存金额、库容和内部风险分析。发送前请核实日期、数量及状态。')
        st.dataframe(orders, use_container_width=True, hide_index=True)
        mail_cols = ['物料编码','物料名称','单位','到货数量','要求到货日期','备注']
        mail_table = orders[mail_cols].to_csv(sep='\t',index=False)
        st.text_area('复制以下内容粘贴到邮件或WPS', value=mail_table, height=170)
        st.code('各位采购同事：\n请按以下到货计划协调供应商，并反馈可执行的到货日期及数量。\n如无法满足，请及时反馈，以便调整生产物料保障方案。\n\n'+mail_table, language=None)
    output = io.BytesIO()
    with pd.ExcelWriter(output,engine='openpyxl') as writer:
        grid_df.to_excel(writer,index=False,sheet_name='Sheet1综合滚动计划')
        orders.to_excel(writer,index=False,sheet_name='Sheet2采购到货计划')
    with sheet2:
        st.download_button('下载两张计划表',output.getvalue(),file_name=f'原材料物控V3.1_{month_start:%Y%m}.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    with sheet1:
        st.download_button('导出综合计划Excel',output.getvalue(),file_name=f'原材料综合滚动计划_{month_start:%Y%m}.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
except Exception as e:
    st.error(f'数据校验或计算失败：{e}')
    st.info('请检查日期、物料编码、良率、库存和到货计划输入。')
