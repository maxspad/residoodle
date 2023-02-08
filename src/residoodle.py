import streamlit as st 

import datetime
import pandas as pd
import plotly.express as px
import plotly.io as pio

from typing import Tuple

import helpers as h
import config as cf
import schedexp as sched

import logging as log

pio.templates.default = 'seaborn'

@st.experimental_memo
def load_schedule(start_date : datetime.date, end_date : datetime.date):

    s = sched.load_sched_api(start_date, end_date, remove_nonum_hurley=True)

    return s

@st.experimental_memo
def get_helper_data() -> Tuple[pd.DataFrame, pd.DataFrame]:
    '''Load helper dataframes'''
    bd = sched.load_block_dates(cf.BLOCK_DATES_FN).set_index('Block')
    half_bd = sched.bd_to_half_blocks(bd)
    res = sched.load_residents(cf.RESIDENTS_FN)
    return bd, half_bd, res


# Load helper data
bd, half_bd, res = get_helper_data()
bd.index = [f'Block {b}' for b in bd.index]

DATE_FMT = "%m/%d/%y"

title_cols = st.columns([1, 5])
with title_cols[0]:
    st.image('raccoon.png', width=100)
with title_cols[1]:
    st.title('ResiDoodle')
    st.caption("It's like a doodle poll that fills itself out!")

with st.expander('About this App', expanded=False):
    st.markdown(cf.ABOUT_RESIDOODLE)

with st.expander('Options', expanded=True):
    # st.markdown('**Step 1**: Pick the date range you want to search.')
    date_cols = st.columns(2)
    start_date = date_cols[0].date_input('Start Date', value=datetime.date.today(),
        min_value=datetime.date.today(), max_value=datetime.date(2023,6,30))
    end_date = date_cols[1].date_input('End Date', value=datetime.date.today() + datetime.timedelta(days=7),
        min_value=start_date, max_value=datetime.date(2023,6,30))

    # st.markdown('**Step 2**: Pick the time window you want your event to take place in. The app will score days by how many residents are available during this time window.')
    time_cols = st.columns(2)
    start_time = time_cols[0].time_input('Start Time', value=datetime.time(17,0,0))
    end_time = time_cols[1].time_input('End Time', value=datetime.time(22, 0, 0))

    if end_time < start_time:
        st.error('End time must be after start time.')
        st.stop()

    # st.markdown('**Step 3**: Choose the residents you want to attend your event.')
    msplc = st.empty()
    sel_res = msplc.multiselect('Choose residents:', res['Resident'].tolist())
    cg = h.CheckGroup([1,2,3,4], ['PGY1','PGY2','PGY3','PGY4'])
    sel_pgy = cg.get_selected()
    if len(sel_pgy):
        sel_res = msplc.multiselect('Choose residents', res['Resident'].tolist(),
            default=res[res['pgy'].isin(sel_pgy)]['Resident'].tolist())
    if not len(sel_res):
        st.info('Choose at least one resident.')
        st.stop()

block_start, block_end = sched.get_flanking_block_dates(half_bd, start_date, end_date)

log.info(f'Loading schedule between {block_start} and {block_end}')
# load the schedule for the block dates flanking the selected start date/time
s = load_schedule(block_start, block_end) 
# add residents and block dates
s = sched.add_res_to_sched(s, res)
s = sched.add_bd_to_sched(s, bd)
s = s.dropna(subset=['PGY']) # filter out unknown (non-em) residents
s = s[s['Resident'].isin(sel_res)] # filter to selected residents
# get shift counts grouped by half-block and resident
scbrb = (s.groupby(['Resident','Block'])['Shift']
          .count()
          .reset_index()
          .pivot(index='Block', columns='Resident', values='Shift')
          .fillna(0.0)).T


# Add special "Off Service" shifts to those who aren't scheduled for a full block
to_concat = []
for blk in scbrb:
    os = scbrb.loc[scbrb[blk] == 0.0, blk].index.tolist()
    block_days = pd.date_range(half_bd.loc[blk, 'Start Date'], half_bd.loc[blk+0.5, 'Start Date'], freq='D')
    for res in os:
        for d in block_days:
            start = d
            end = d + pd.Timedelta(hours=23, minutes=59, seconds=59)
            to_concat.append({
                'Resident': res,
                'Block': blk,
                'Start': start,
                'Start Date': start.date(),
                'Start Hour': start.hour,
                'End': end,
                'End Date': end.date(),
                'End Hour': end.hour,
                'Shift': 'Off Service'
            })
s = pd.concat([s, pd.DataFrame(to_concat)], axis=0)

days = pd.date_range(start_date, end_date, freq='D')
# s
to_cat = []
s_to_cat = []
for d in days:

    itv_start = d + pd.Timedelta(hours=start_time.hour, minutes=start_time.minute)
    itv_end = d + pd.Timedelta(hours=end_time.hour, minutes=end_time.minute)

    s_for_day = s[['Resident','Shift','Start','End']]
    s_for_day = s_for_day[(s_for_day['Start'] >= d) & (s_for_day['Start'] <= (d + pd.Timedelta(hours=23, minutes=59, seconds=59)))]
    if len(s_for_day):
        s_for_day['Overlap'] = s_for_day.apply(lambda r: ((itv_start <= r['Start'] <= itv_end) or (r['Start'] <= itv_start <= r['End'])), axis=1)
    
    sel_res_set = set(sel_res)
    identif_res_set = set(s_for_day['Resident'].unique())
    off_res_set = sel_res_set - identif_res_set

    # st.write(d)
    # st.write(s_for_day)

    off_to_add = [
        {'Resident': r,
         'Shift': 'Day Off',
         'Start': d,
         'End': d + pd.Timedelta(hours=23, minutes=59, seconds=59),
         'Overlap': False}
         for r in off_res_set
    ]
    s_for_day = pd.concat([s_for_day, pd.DataFrame(off_to_add)])
    s_for_day['Availability'] = s_for_day['Shift']
    s_for_day.loc[(~s_for_day['Shift'].isin(['Day Off','Off Service'])) & (s_for_day['Overlap']), 'Availability'] = 'Shift'
    s_for_day.loc[(~s_for_day['Shift'].isin(['Day Off','Off Service'])) & (~s_for_day['Overlap']), 'Availability'] = 'Available'

    free_counts = s_for_day.groupby(['Availability'])[['Resident']].count()
    s_for_day['Day'] = d
    s_to_cat.append(s_for_day)
    # st.dataframe(s_for_day.groupby(['Availability'])['Resident'].apply(lambda x: ' '.join(x)))
    free_counts.rename({'Resident': d}, inplace=True, axis=1)
    to_cat.append(free_counts)

avail = pd.concat(s_to_cat)[['Day','Resident','Availability','Shift']]
avail['Free or Busy'] = avail['Availability'].replace({'Shift': 'Busy', 'Off Service': 'Busy', 'Available': 'Free', 'Day Off': 'Free'})

cbd = avail.groupby(['Day','Availability'])['Resident'].count().reset_index()
cbd = avail.groupby(['Day','Availability'])['Resident'].agg([('Count','count'),('Residents', lambda x: ', '.join(x))]).reset_index()
cbd.loc[cbd['Availability'].isin(['Shift','Off Service']), 'Count'] *= -1
cbd['isFree'] = cbd['Availability'].isin(['Day Off','Available'])

st.markdown('# Best Days')
st.markdown('The days with the most free residents in the range you selected.')

best_days = cbd.groupby(['Day'])[['Count']].sum().reset_index().sort_values(['Count','Day'], ascending=[False, True])
best_days = best_days.iloc[:3, :]

cols = st.columns(len(best_days))
titles = ['🥇', '🥈', '🥉']
for i, c in enumerate(cols):
    cbd_for_day = cbd[cbd['Day'] == d].set_index('Availability')
    c.markdown(f'## {titles[i]} {best_days.iloc[i, 0].strftime("%m/%d")}')
    n_free = cbd_for_day.loc[~cbd_for_day.index.isin(['Off Service','Shift']), 'Count'].sum()
    c.markdown(f'**{n_free}** out of {len(sel_res)} residents free.')

    d = best_days.iloc[i,:]['Day']
    md_str = ''
    for k in ['Day Off','Available','Shift','Off Service']:
        if k in cbd_for_day.index:
            md_str += f'**{k}**: {cbd_for_day.loc[k, "Residents"]}\n\n'
        else:
            md_str += f'**{k}**: None\n\n'
    c.markdown(md_str)

# avail
# cbd
# best_days

plt = px.bar(cbd, x='Day', y='Count', color='Availability', hover_data=['Residents'],
    title='Number of Free Residents by Day',
    color_discrete_map={'Day Off': '#2ECC71', 'Available': '#82E0AA', 'Off Service': '#EC7063', 'Shift': '#E74C3C'})
plt.add_vrect(x0=f'{best_days.iloc[0,0] - pd.Timedelta("13h")}', x1=f'{best_days.iloc[0,0] + pd.Timedelta("13h")}', 
    fillcolor='green', opacity=0.25, 
    annotation_font_size=16, 
    annotation_font_color='black',
    annotation_text='Best Day!',
    annotation_position="inside bottom left")
st.plotly_chart(plt)


