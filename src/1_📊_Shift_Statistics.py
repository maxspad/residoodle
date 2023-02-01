import streamlit as st 

import datetime
import pandas as pd
import plotly.express as px
import plotly.io as pio

from typing import Tuple

import helpers as h
import config as cf
import schedexp as sched

pio.templates.default = 'seaborn'

@st.experimental_memo
def load_schedule(start_date : datetime.date, end_date : datetime.date, 
    res : pd.DataFrame, exclude_nonem: bool):

    s = sched.load_sched_api(start_date, end_date)
    s = sched.add_res_to_sched(s, res)
    if exclude_nonem:
        s = s.dropna(subset=['PGY'])
    return s

@st.experimental_memo
def get_helper_data() -> Tuple[pd.DataFrame, pd.DataFrame]:
    '''Load helper dataframes'''
    bd = sched.load_block_dates(cf.BLOCK_DATES_FN).set_index('Block')
    res = sched.load_residents(cf.RESIDENTS_FN)
    return bd, res

# Set Title 
st.set_page_config(page_title='Shift Statistics', page_icon='📊', layout='wide')

# Load helper data
bd, res = get_helper_data()
bd.index = [f'Block {b}' for b in bd.index]

DATE_FMT = "%m/%d/%y"

# Configure sidebar
with st.sidebar:
    bd_list = {f'Year to Date: {datetime.date(2022, 7, 1).strftime(DATE_FMT)} to {datetime.date.today().strftime(DATE_FMT)}': 'YTD', 'Custom Date Range': 'Custom'}
    for b, r in bd.iterrows():
        bd_list[f'{b}: {r["Start Date"].strftime(DATE_FMT)} to {r["End Date"].strftime(DATE_FMT)}'] = b

    sel = st.selectbox('Choose a block or date range:', bd_list.keys())
    sel_block = bd_list[sel]
    if sel_block == 'YTD':
        start_date = datetime.date(2022, 7, 1)
        end_date = datetime.date.today()
    elif sel_block == 'Custom':
        start_date = st.date_input('Custom start date:', value=datetime.date(2022, 7, 1))
        end_date = st.date_input('Custom end date:', value=datetime.date.today())
    else:
        start_date = bd.loc[sel_block,'Start Date']
        end_date = bd.loc[sel_block,'End Date']
    exclude_nonem = True # st.checkbox('Exclude off-service residents', value=True)

st.title(f'Shift Breakdown')
st.markdown('*Useful statistics for evaluating the schedule. Use the sidebar on the left to fiilter by date range, and make sure to scroll down!*')
st.markdown('Jump to breakdown by:&nbsp;&nbsp;[Overall](#overall-shift-breakdown) | [Class](#shift-breakdown-by-class) | [Resident](#shift-breakdown-by-resident)')

# Download the shiftadmin data
try:
    s = load_schedule(start_date, end_date, res, exclude_nonem)
except sched.ScheduleError:
    st.error('End Date must come after Start Date')
    st.stop()

st.markdown('## Overall Shift Breakdown')

st.markdown(f'Between **{start_date.strftime(DATE_FMT)}** and **{end_date.strftime(DATE_FMT)}**, there are **{len(s)}** shifts, ' +
    f'totaling **{int(s["Length"].sum())}** person-hours ' +
    f'across **{len(s["Resident"].unique())}** residents.')
pgy_counts = s['PGY'].value_counts().sort_index()
pgy_norm = s['PGY'].value_counts(normalize=True).sort_index() * 100
tod_counts = s['Type'].value_counts()
tod_norm = s['Type'].value_counts(normalize=True) * 100
site_counts = s['Site'].value_counts()
site_norm = s['Site'].value_counts(normalize=True) * 100
md_breakdown_str = ('\t* By class, ' + ', '.join([f'**{pgy_counts[i]}** ({pgy_norm[i]:.0f}%) are worked by PGY{i:.0f}s' for i in pgy_counts.index]) + '.\n' +
                   '\t* By time of day, ' + ', '.join([f'**{tod_counts[t]}** ({tod_norm[t]:.0f}%) are {t} shifts' for t in ['Morning','Evening','Night']]) + '.\n' +
                   '\t* By site, ' + ', '.join([f'**{site_counts[s]}** ({site_norm[s]:.0f}%) are at {s}' for s in ['UM','SJ','HMC']]) + '.')
st.markdown(md_breakdown_str)

cols = st.columns(3)

plt = px.histogram(s, x='PGY', color='PGY',
        title='Shifts by Class',
        category_orders={'PGY':[1,2,3,4]},
        color_discrete_map=h.PGY_COLORS_MAP,
        text_auto='.0f')
plt.update_layout(bargap=0.2)
cols[0].plotly_chart(plt, use_container_width=True)

plt = px.histogram(s, x='Type', color='Type',
        color_discrete_map=h.TOD_COLORS_MAP,
        title='Shifts by Time of Day',
        text_auto='.0f')
cols[1].plotly_chart(plt, use_container_width=True)

plt = px.histogram(s, x='Site', color='Site',
        color_discrete_map=h.SITE_COLORS_MAP,
        title='Shifts by Site',
        text_auto='.0f')
cols[2].plotly_chart(plt, use_container_width=True)

###############################################################################

st.markdown('## Shift Breakdown by *Class*')
st.markdown('Shift counts by class, broken down by site and time of day.')

abs_vs_rel_by_class =st.radio('Show shift counts as:', ('Raw Counts','Percents'), horizontal=True)
use_rel_by_class = (abs_vs_rel_by_class == 'Percents')

cols = st.columns(2)
plt = px.histogram(s, y='PGY', color='Site',
        color_discrete_map=h.SITE_COLORS_MAP,
        orientation='h',
        title='Shift Counts by Site and Class',
        barnorm=('percent' if use_rel_by_class else None),
        text_auto=".0f")
plt.update_layout(bargap=0.2)
cols[0].plotly_chart(plt, use_container_width=True)

plt = px.histogram(s, y='PGY', color='Type',
        color_discrete_map=h.TOD_COLORS_MAP,
        orientation='h',
        title='Shift Counts by Time of Day and Class',
        barnorm=('percent' if use_rel_by_class else None),
        text_auto='.0f')
plt.update_layout(bargap=0.2)
cols[1].plotly_chart(plt, use_container_width=True)

###############################################################################

st.markdown('## Shift Breakdown by *Resident*')
st.markdown('Shift counts by individual resident')

cols = st.columns([2,2,6])
with cols[0]:
    abs_vs_rel_by_res = st.radio('Show shift counts as:', ('Raw Counts','Percents'), horizontal=True, key='res_radio')
    use_rel_by_res = (abs_vs_rel_by_res == 'Percents')
with cols[1]:
    sel_exp_type = st.selectbox('Explore shift totals by:',
        ['Time of Day', 'Site', 'Shift Area (UM Only)'])

plot_func = {'Time of Day': h.res_type_cat_plot,
             'Site': h.res_site_cat_plot,
             'Shift Area (UM Only)': h.res_shift_cat_plot}[sel_exp_type]

h.two_by_two_plot(plot_func, s, use_relative=use_rel_by_res)

###############################################################################

s = s.set_index('Start')
st.dataframe(s)
s['Block'] = ''
for blk, r in bd.iterrows():
    s.loc[(s.index >= r['Start Date']) & (s.index < (r['End Date'] + datetime.timedelta(days=1))), 'Block'] = blk


blah = s.groupby(['Block','Type'])['Shift'].count().reset_index()
plt = px.line(blah, x='Block', y='Shift', color='Type', markers=True)
st.plotly_chart(plt)