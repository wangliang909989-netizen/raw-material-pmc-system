import io
import math
from datetime import date, timedelta
import pandas as pd
import streamlit as st

st.set_page_config(page_title='原材料物控分析系统 V2.4', layout='wide')
st.title('📦 原材料物控分析系统 V2.4')
st.caption('模拟训练工具｜每日滚动库存 · IQC放行 · 采购可行性 · 风险预警')
st.info('仅用于原材料计划模拟。真实投料需核实ERP库存、IQC合格放行、供应商承诺和生产执行时点。')

with st.expander('① 基础参数', expanded=True):
    a,b,c=st.columns(3)
    material=a.text_input('原材料名称','电解液')
    stock=a.number_input('初始合格库存(kg)',min_value=0.0,value=200.0)
    pending=b.number_input('初始待检库存(kg)',min_value=0.0,value=0.0)
    frozen=b.number_input('冻结库存(kg，仅展示)',min_value=0.0,value=0.0)
    safety=c.number_input('安全库存(kg)',min_value=0.0,value=50.0)
    capacity=c.number_input('合格品库容上限(kg，0表示不限制)',min_value=0.0,value=300.0)
    d,e,f=st.columns(3)
    moq=d.number_input('最小订货量MOQ(kg)',min_value=0.01,value=50.0)
    multiple=e.number_input('订货倍量(kg)',min_value=0.01,value=50.0)
    lead=f.number_input('采购提前期(自然日)',min_value=0,value=3,step=1)
    iqc=d.number_input('IQC检验周期(自然日)',min_value=0,value=2,step=1)
    start=e.date_input('分析开始日期',value=date.today())
    days=f.number_input('分析天数',min_value=1,max_value=365,value=7,step=1)

st.subheader('② 每日订单需求')
orders_default=pd.DataFrame([
    {'订单':'A订单','需求日期':start,'需求量kg':100.0,'优先级':1},
    {'订单':'B订单','需求日期':start+timedelta(days=1),'需求量kg':150.0,'优先级':2},
    {'订单':'C订单','需求日期':start+timedelta(days=2),'需求量kg':120.0,'优先级':3},
])
orders=st.data_editor(orders_default,num_rows='dynamic',hide_index=True,key='orders24',use_container_width=True,
    column_config={'需求日期':st.column_config.DateColumn(format='YYYY-MM-DD'),'需求量kg':st.column_config.NumberColumn(min_value=0,format='%.2f'),'优先级':st.column_config.NumberColumn(min_value=1,step=1)})
st.caption('优先级数字越小越优先；同日订单按优先级分配。')

st.subheader('③ 已确认采购批次与IQC放行')
receipts_default=pd.DataFrame([{'批次':'采购批次1','计划到货日':start+timedelta(days=1),'IQC放行日':start+timedelta(days=3),'合格数量kg':0.0}])
receipts=st.data_editor(receipts_default,num_rows='dynamic',hide_index=True,key='receipts24',use_container_width=True,
    column_config={'计划到货日':st.column_config.DateColumn(format='YYYY-MM-DD'),'IQC放行日':st.column_config.DateColumn(format='YYYY-MM-DD'),'合格数量kg':st.column_config.NumberColumn(min_value=0,format='%.2f')})
st.caption('仅已确认且到达IQC放行日期的合格数量计入可用库存；预计到货不能直接当作合格库存。')

st.subheader('④ 初始待检库存放行计划')
release_pending=st.checkbox('计划在分析期内放行初始待检库存（仅用于模拟）',value=False)
release_day=st.date_input('计划放行日期',value=start,key='pending_day') if release_pending else None
release_qty=st.number_input('计划合格放行量(kg)',min_value=0.0,max_value=float(pending),value=0.0) if release_pending and pending>0 else 0.0

if st.button('开始物控分析',type='primary'):
    try:
        demand=orders.copy()
        receipts2=receipts.copy()
        for col in ['需求日期']:
            demand[col]=pd.to_datetime(demand[col],errors='coerce').dt.date
        for col in ['计划到货日','IQC放行日']:
            receipts2[col]=pd.to_datetime(receipts2[col],errors='coerce').dt.date
        demand['需求量kg']=pd.to_numeric(demand['需求量kg'],errors='coerce')
        demand['优先级']=pd.to_numeric(demand['优先级'],errors='coerce')
        receipts2['合格数量kg']=pd.to_numeric(receipts2['合格数量kg'],errors='coerce')
        if demand[['需求日期','需求量kg','优先级']].isna().any().any() or receipts2[['计划到货日','IQC放行日','合格数量kg']].isna().any().any():
            raise ValueError('存在空白或无效的日期、数量、优先级')
        if (demand['需求量kg']<0).any() or (receipts2['合格数量kg']<0).any() or (demand['优先级']<1).any():
            raise ValueError('数量不能为负，优先级至少为1')
        if any(r['IQC放行日']<r['计划到货日'] for _,r in receipts2.iterrows()):
            raise ValueError('IQC放行日不能早于采购到货日')
        demand=demand.sort_values(['需求日期','优先级','订单'],kind='stable')
        begin=start; end=start+timedelta(days=int(days)-1)
        available=float(stock); rows=[]; allocations=[]; first_short=None; first_safety=None
        for i in range(int(days)):
            today=begin+timedelta(days=i)
            incoming=float(receipts2.loc[receipts2['IQC放行日']==today,'合格数量kg'].sum())
            if release_pending and today==release_day:
                incoming+=float(release_qty)
            opening=available
            available+=incoming
            before_demand=available
            day_orders=demand.loc[demand['需求日期']==today]
            total_demand=float(day_orders['需求量kg'].sum())
            total_alloc=0.0
            for _,o in day_orders.iterrows():
                needed=float(o['需求量kg'])
                given=min(available,needed)
                short=max(0.0,needed-given)
                available-=given; total_alloc+=given
                allocations.append({'日期':today,'订单':str(o['订单']),'优先级':int(o['优先级']),'需求kg':needed,'分配kg':given,'缺口kg':short})
                if short>0 and first_short is None:
                    first_short=(today,short)
            risk='缺料' if total_alloc<total_demand else ('低于安全库存' if available<safety else ('等于安全库存' if available==safety else '正常'))
            if available<safety and first_safety is None: first_safety=today
            rows.append({'日期':today,'期初合格kg':opening,'当日合格放行kg':incoming,'可分配kg':before_demand,'需求kg':total_demand,'实际分配kg':total_alloc,'当日缺口kg':total_demand-total_alloc,'期末合格kg':available,'安全库存kg':safety,'风险':risk,'库容超限kg':max(0.0,before_demand-capacity) if capacity>0 else 0.0})
        result=pd.DataFrame(rows)
        detail=pd.DataFrame(allocations,columns=['日期','订单','优先级','需求kg','分配kg','缺口kg'])
        st.subheader('⑤ 每日滚动库存与风险结果')
        st.dataframe(result,use_container_width=True,hide_index=True)
        st.subheader('⑥ 订单优先级分配')
        st.dataframe(detail,use_container_width=True,hide_index=True)
        st.subheader('⑦ 缺料与采购可行性')
        if first_short:
            day,qty=first_short
            st.error(f'首次缺料：{day}；该订单未满足数量 {qty:.2f} kg（当日总缺口见上表）')
            required=max(float(moq),math.ceil(qty/float(multiple))*float(multiple))
            arrival=day-timedelta(days=int(iqc))
            order_date=arrival-timedelta(days=int(lead))
            st.warning(f'简化补货建议：至少 {required:.2f} kg；为在 {day} 投料，最迟到货 {arrival}，最迟下单 {order_date}。此数量仅针对首次缺口，未覆盖后续缺口和安全库存恢复。')
            if order_date<start:
                st.error('按分析起始日计算，正常采购下单窗口已过：需要核实加急、替代料、IQC提前放行或生产调整。')
            else:
                st.info('按自然日提前期推算仍有计划窗口，但必须由采购确认供应商产能与交货承诺。')
            st.write(f'跨部门协调：采购确认 {arrival} 前可到货的合格候选数量及分批方案；质量确认 {day} 投料前可放行的时间和数量；PC确认优先订单、分批生产或调整计划；销售核实客户交期及延期容忍。')
        else:
            st.success('分析期内所有订单需求均得到分配。')
        if first_safety:
            st.warning(f'首次低于安全库存：{first_safety}。低于安全库存不等于当天一定停线。')
        else:
            st.success('分析期内未低于安全库存。')
        if (result['库容超限kg']>0).any():
            st.warning('存在合格品库容超限日期，请协调分批放行/分批到货；本版本仅预警，不自动限制放行。')
        st.caption('边界：当日先合格放行后分配；未模拟日内时点、订单跨日欠交回补、在途可信度、供应商产能及替代料认证。')
        out=io.BytesIO()
        with pd.ExcelWriter(out,engine='openpyxl') as writer:
            result.to_excel(writer,sheet_name='每日滚动库存',index=False)
            detail.to_excel(writer,sheet_name='订单分配',index=False)
            demand.to_excel(writer,sheet_name='订单输入',index=False)
            receipts2.to_excel(writer,sheet_name='采购批次',index=False)
            pd.DataFrame([{'原材料':material,'初始合格kg':stock,'初始待检kg':pending,'冻结kg':frozen,'安全库存kg':safety,'库容kg':capacity,'MOQkg':moq,'订货倍量kg':multiple,'采购提前期天':lead,'IQC天':iqc}]).to_excel(writer,sheet_name='参数',index=False)
        st.download_button('📥 下载Excel分析结果',data=out.getvalue(),file_name='原材料物控分析_V2.4.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except (ValueError,TypeError,OverflowError) as exc:
        st.error(f'请检查输入数据：{exc}')