import streamlit as st 
import helpers as h
import schedexp as sched

import pandas as pd 
import datetime

# Open the data helper files
rdb = pd.read_excel('data/residoodle_db.xlsx', index_col=0,
                    sheet_name=['Residents','Blocks','ResidentBlockSchedule'])
res, blocks, rbs = rdb['Residents'], rdb['Blocks'], rdb['ResidentBlockSchedule']

# rename a column in res to make it easier
res = res.rename({'schedName': 'Resident'}, axis=1)

# remove Kirstin Scott from rbs
rbs = rbs[rbs['Resident'] != 'Scott, Kirstin']
# join block dates to rbs
rbs = pd.merge(rbs, blocks, on='Block')
# join the right resident names to rbs
rbs = rbs.rename({'Resident':'fullName'}, axis=1).join(res[['Resident']], on='userId')

# Update blocks so that "Orient/ED" becomes just ED
rbs['Rotation'].replace({0: 'Leave', 'Orient/ED': 'ED'}, inplace=True)

# anything not (and not ED/EM/US) is straight off service for 4 weeks
rbs_os = rbs[(~rbs['Rotation'].str.contains('/')) & (~rbs['Rotation'].isin(['US','ED','EM']))]
rbs_os = rbs_os.drop(['MidDate','Block'], axis=1)

# anything with a slash is a split 2-week/2-week block
rbs_split = rbs[rbs['Rotation'].str.contains('/')]
rbs_split['Rotation'] = rbs_split['Rotation'].str.split('/')
# Create two rows for each split block
rbs_split = rbs_split.explode(column='Rotation')
rbs_split['Rotation'] = rbs_split['Rotation'].str.strip() # clean whitespace
# Beginning block gets 0, half gets 0.5
rbs_split['HalfBlock'] = rbs_split.groupby(['Resident','Block']).cumcount() * 0.5
# Get rid of half blocks that are in EM
rbs_split = rbs_split[~rbs_split['Rotation'].isin(['ED', 'US', 'EM'])]
# Impute the half block date as the end date for first half 
# split rotaions and as the start date for second half split rotations
rbs_split.loc[rbs_split['HalfBlock'] == 0, 'EndDate'] = rbs_split.loc[rbs_split['HalfBlock'] == 0, 'MidDate'] - pd.Timedelta('1d')
rbs_split.loc[rbs_split['HalfBlock'] == 0.5, 'StartDate'] = rbs_split.loc[rbs_split['HalfBlock'] == 0.5, 'MidDate']
# Get rid of unnecessary columns
rbs_split = rbs_split.drop(['MidDate','Block','HalfBlock'], axis=1)

# Combine the full-block and split-block rotations
rbs = pd.concat([rbs_os, rbs_split], axis=0)

'''
title_cols = st.columns([1, 5])
with title_cols[0]:
    st.image('raccoon.png', width=100)
with title_cols[1]:
    st.title('ResiDoodle')
    st.caption("It's like a doodle poll that fills itself out!")

with st.expander('About this App', expanded=False):
    st.markdown(cf.ABOUT_RESIDOODLE)
'''

with st.expander('Options', expanded=True):
    # st.markdown('**Step 1**: Pick the date range you want to search.')
    date_cols = st.columns(2)
    start_date = date_cols[0].date_input('Search between **Start Date**', value=datetime.date.today(),
        min_value=datetime.date.today(), max_value=datetime.date(2023,6,30))
    end_date = date_cols[1].date_input('and **End Date**', value=datetime.date.today() + datetime.timedelta(days=7),
        min_value=start_date, max_value=datetime.date(2023,6,30))

    # st.markdown('**Step 2**: Pick the time window you want your event to take place in. The app will score days by how many residents are available during this time window.')
    time_cols = st.columns(2)
    start_time = time_cols[0].time_input('Event **Start Time**', value=datetime.time(17,0,0))
    end_time = time_cols[1].time_input('Event **End Time**', value=datetime.time(22, 0, 0))

    if end_time < start_time:
        st.error('End time must be after start time.')
        st.stop()

    # st.markdown('**Step 3**: Choose the residents you want to attend your event.')
    msplc = st.empty()
    sel_res = msplc.multiselect('Choose **residents** (or select classes):', res['Resident'].tolist())
    cg = h.CheckGroup([1,2,3,4], ['PGY1','PGY2','PGY3','PGY4'])
    sel_pgy = cg.get_selected()
    if len(sel_pgy):
        sel_res = msplc.multiselect('Choose **residents** (or select classes):', res['Resident'].tolist(),
            default=res[res['pgy'].isin(sel_pgy)]['Resident'].tolist())
    exclude_conf = st.checkbox('Treat Conference time as "busy"', value=True)
    if not len(sel_res):
        st.info('Choose at least one resident.')
        st.stop()

# Load the schedule
s = sched.load_sched_api(start_date, end_date, remove_nonum_hurley=True)

# Filter the schedule and rbs to the selected residents
s = s[s['Resident'].isin(sel_res)]
rbs = rbs[rbs['Resident'].isin(sel_res)]

# Filter RBS so that only blocks which overlap with the selected dates
# are included
start_date = pd.Timestamp(start_date)
end_date = pd.Timestamp(end_date)
to_incl = (((start_date <= rbs['StartDate']) &
            (rbs['StartDate'] <= end_date)) | 
           ((rbs['StartDate'] <= start_date) &
            (start_date <= rbs['EndDate'])))
rbs = rbs[to_incl]
# ((itv_start <= r['Start'] <= itv_end) or (r['Start'] <= itv_start <= r['End']))
# rbs

# For any off-service rotation in the block schedule, add a "dummy"
# shift for each day in the Block StartDate-EndDate interval, inclusive 
# of EndDate
dummy_os_shifts = []
for i in range(len(rbs)):
    r = rbs.iloc[i,:]
    # if not (r['Resident'] in sel_res): continue # SKIP if not in the selected residents
    block_days = pd.date_range(r['StartDate'], r['EndDate'], freq='D', inclusive='both')
    for d in block_days:
        dummy_start = d
        dummy_end = d + pd.Timedelta(hours=23, minutes=59, seconds=59)
        dummy_os_shifts.append({
            'Resident': r['Resident'],
            'userID': r['userId'],
            'Shift': r['Rotation'],
            'Start': d,
            'End': d + pd.Timedelta(hours=23, minutes=59, seconds=59),
            'Type': 'Off Service',
            'Site': 'OS',
            'Length': 24,
            'Start Date': dummy_start.date(),
            'Start Hour': dummy_start.hour,
            'End Date': dummy_end.date(),
            'End Hour': dummy_end.hour
        })

# Add a dummy conference shift for every selected resident on every wednesday in the
# interval
dummy_conf_shifts = []
sel_date_range = pd.date_range(start_date, end_date, freq='D', inclusive='both')
wed_date_range = sel_date_range[sel_date_range.weekday == 2]
for d in wed_date_range:
    for r in sel_res:
        dummy_conf_shifts.append({
            'Resident': r,
            'Shift': 'Conference',
            'Start': d + pd.Timedelta(hours=10),
            'End': d + pd.Timedelta(hours=14),
            'Type': 'Conference',
            'Length': 4,
            'Start Date': d.date(),
            'Start Hour': 10,
            'End Date': d.date(),
            'End Hour': 14
        })
s = pd.concat([s, pd.DataFrame(dummy_os_shifts), pd.DataFrame(dummy_conf_shifts)])

# s

# For each day in the selected range, create the selected time interval
# within that day and see which shifts in s overlap
def overlap_for_day(day_grp: pd.DataFrame):
    d = day_grp.name
    start = pd.Timestamp(d) + pd.Timedelta(hours=start_time.hour, minutes=start_time.minute)
    end = pd.Timestamp(d) + pd.Timedelta(hours=end_time.hour, minutes=end_time.minute)
    is_overlap = (((start <= day_grp['Start']) &
                   (day_grp['Start'] <= end)) | 
                  ((day_grp['Start'] <= start) &
                   (start <= day_grp['End'])))
    return is_overlap

s['Overlap'] = False
for d in sel_date_range:
    start = pd.Timestamp(d) + pd.Timedelta(hours=start_time.hour, minutes=start_time.minute)
    end = pd.Timestamp(d) + pd.Timedelta(hours=end_time.hour, minutes=end_time.minute)
    is_overlap = (((start <= s['Start']) &
                   (s['Start'] <= end)) | 
                  ((s['Start'] <= start) &
                   (start <= s['End'])))
    s.loc[is_overlap, 'Overlap'] = True
s['Free'] = ~s['Overlap']

s


'''
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

sel_res_df = pd.DataFrame({'Resident':sel_res})
sel_res_df = sel_res_df.join(scbrb, on='Resident').fillna(0.0).set_index('Resident')
scbrb = sel_res_df.copy()

scbrb
# scbrb.join(pd.Series(sel_res, name='Resident'), on='Resident')
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
# best_days
cols = st.columns(len(best_days))
titles = ['🥇', '🥈', '🥉']
for i, c in enumerate(cols):
    d = best_days.iloc[i,:]['Day']
    cbd_for_day = cbd[cbd['Day'] == d].set_index('Availability')
    # cbd_for_day
    c.markdown(f'## {titles[i]} {best_days.iloc[i, 0].strftime("%m/%d")}')
    # st.write(cbd_for_day[~cbd_for_day.index.isin(['Off Service','Shift'])]['Count'].sum())
    n_free = cbd_for_day[~cbd_for_day.index.isin(['Off Service','Shift'])]['Count'].sum()
    c.markdown(f'**{n_free}** out of {len(sel_res)} residents free.')

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

st.markdown('# All Days')
st.markdown('A day-by-day look at how many residents are free over the selected date range. Mouse over the graph for more information.')

plt = px.bar(cbd, x='Day', y='Count', color='Availability', hover_data=['Residents'],
    title='Number of Free Residents by Day',
    color_discrete_map={'Day Off': '#2ECC71', 'Available': '#82E0AA', 'Off Service': '#EC7063', 'Shift': '#E74C3C'})
opacities = [0.3, 0.15, 0.075]
for i in range(len(best_days)):
    plt.add_vrect(x0=f'{best_days.iloc[i,0] - pd.Timedelta("12h")}', x1=f'{best_days.iloc[i,0] + pd.Timedelta("12h")}', 
        fillcolor='green', opacity=opacities[i], 
        annotation_font_size=16, 
        annotation_font_color='black',
        annotation_text=titles[i],
        annotation_position="inside top left")
st.plotly_chart(plt)


st.markdown('# All Shifts')
st.markdown('The shifts worked by the residents over the selected date range. You may want to click the arrows in the corner of the table to view it full screen.')
all_shifts = avail.groupby(['Day','Shift'])['Resident'].apply(lambda x: ', '.join(x)).reset_index().pivot(index='Shift', columns='Day', values='Resident').fillna('').sort_index()
all_shifts.columns = [c.strftime('%m/%d') for c in all_shifts.columns]
# blah = blah.style.set_properties(**{'white-space': 'pre-wrap'})
st.dataframe(all_shifts)
# blah = pd.pivot(avail, index='Day', columns='Shift', values='Resident')

'''