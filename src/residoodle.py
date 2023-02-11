import streamlit as st
import pandas as pd
import datetime
import helpers as h
import schedexp as sched

# Open the data helper files
rdb = pd.read_excel('data/residoodle_db.xlsx', index_col=0,
                    sheet_name=['Residents','Blocks','ResidentBlockSchedule'])
res, blocks, rbs = rdb['Residents'], rdb['Blocks'], rdb['ResidentBlockSchedule']

with st.expander('Options', expanded=True):
    # st.markdown('**Step 1**: Pick the date range you want to search.')
    date_cols = st.columns(2)
    start_date = date_cols[0].date_input('Search between **Start Date**', value=datetime.date.today(),
        min_value=datetime.date.today(), max_value=datetime.date(2023,6,30))
    end_date = date_cols[1].date_input('and **End Date**', value=start_date + datetime.timedelta(days=7),
        min_value=start_date, max_value=datetime.date(2023,6,30))
    
    end_date = datetime.datetime(year=end_date.year, month=end_date.month, day=end_date.day,
                                 hour=23, minute=59, second=59)

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

rbs = (
    rbs.join(blocks, on='Block', rsuffix='hi') # add block dates
       .replace(to_replace={'Rotation': {0: 'Leave', 'Orient/ED': 'ED'}}) # correct rotation names
       .assign(Rotation=lambda df_: df_['Rotation'].str.split('/')) # split rotation names by slash
       # if no slash (tuple len = 1) then add that rotation as the second-half rotation
       .assign(Rotation=lambda df_: df_['Rotation'].apply(lambda r: r if len(r) > 1 else (r[0], r[0])))
       # creat the start/end dates for each half-block as tuples
       .assign(StartDate= lambda df_: list(zip(df_['StartDate'],df_['MidDate'])),
               EndDate= lambda df_: list(zip(df_['MidDate'] - pd.Timedelta('1d'), df_['EndDate'])),
               Block= lambda df_: list(zip(df_['Block'], df_['Block'] + 0.5)))
       .drop(columns=['MidDate','fullName']) # get rid of now-uncessary columns
       # turn the tuples into rows
       .explode(column=['Block','Rotation','StartDate','EndDate'])
       # get rid of extra whitespace
       .assign(Rotation=lambda df_: df_['Rotation'].str.strip())
       # fix some rotation name aliases
       .replace({'Rotation': {'EM': 'ED', 'HMC Trauma': 'HTrauma', 'H Trauma': 'HTrauma'}})
       # add the correct resident names
       .join(res[['Resident']], on='userId')
        # .query('Resident in ["R Moschella", "K Muraglia"]')

       # select only off-service rotations and only for selected residents
       .query('Rotation != "ED" and Resident in @sel_res')
       # Rename columns to be consistent with ShiftAdmin dataframe
       .rename({'StartDate':'Start', 'EndDate':'End','Rotation':'Shift'}, axis=1)
       .assign(Site='OS', Type='Off Service')
       # select only those rotations which intersect the selected dates
       .query('(@start_date <= Start <= @end_date) or (Start <= @start_date <= End)')
)

rbs 

def expand_os_to_days(r : pd.DataFrame):
    ser = r.iloc[0,:]
    sd = ser['Start']; ed = ser['End']
    # st.write([sd, ed])
    r = (r.set_index('Start')
          .reindex(pd.date_range(sd, ed, inclusive='both', freq='D'), 
                   method='ffill')
          .assign(Start= lambda df_: df_.index,
                  End= lambda df_: df_.index + pd.Timedelta(hours=23, minutes=59, seconds=59))
          .reset_index(drop=True))
    return r

rbs = (rbs.groupby(['Resident','Start'])
          .apply(expand_os_to_days)
          .reset_index(drop=True)
          .filter(['userId','Resident','Block','Shift','Start','End','Site','Type']))
st.write('rbs days')
rbs

# Load the schedule for the selected residents
s = (sched.load_sched_api(start_date, end_date.date(), remove_nonum_hurley=True)
          .query('Resident in @sel_res'))
st.write('initial loaded schedule')
s
st.write(end_date)
s = (
    pd.concat([s, rbs])
      .filter(['Resident','Shift','Site','Type','Start','End'])
      .query('(@start_date <= Start <= @end_date) or (Start <= @start_date <= End)')
)
st.write('schedule with added offservice')
s

def get_busy_counts(g : pd.DataFrame):
    day_off_res = set(sel_res) - set(g['Resident'].unique())
    day_off_shifts = ['Off'] * len(day_off_res)
    # st.write(len(day_off_res), len(day_off_shifts))
    grp_day = g.name
    g = g.assign(StartTime = g['Start'].dt.time, EndTime = g['End'].dt.time)
    
    is_os = g['Type'] == 'Off Service'
    os_res = set(g[is_os]['Resident'].unique())
    os_shifts = ['OS'] * len(os_res)
    # st.write(len(os_res), len(os_shifts))
    # st.write(grp_day)
    # st.write(g)
    on_shift = (
        g[~is_os]#.assign(StartTime = g['Start'].dt.time, EndTime = g['End'].dt.time)
                 .query('(@start_time <= StartTime <= @end_time) or (StartTime <= @start_time <= EndTime)')
    )
    shift_res = set(on_shift['Resident'])
    shift_res_shifts = on_shift['Shift'].unique().tolist()
    # st.write(len(shift_res), len(shift_res_shifts))
    
    not_on_shift = (
        g[~is_os]#.assign(StartTime = g['Start'].dt.time, EndTime = g['End'].dt.time)
                 .query('not ((@start_time <= StartTime <= @end_time) or (StartTime <= @start_time <= EndTime))')
    )
    free_res = set(not_on_shift['Resident'])
    free_res_shifts = not_on_shift['Shift'].unique().tolist()
    # st.write(len(free_res), len(free_res_shifts))

    return pd.DataFrame({
        'Availability': (['Day Off']*len(day_off_res) + ['Off Service']*len(os_res) + ['On Shift']*len(shift_res) + ['Free']*len(free_res)),
        'Resident': list(day_off_res) + list(os_res) + list(shift_res) + list(free_res),
        'Shift': day_off_shifts + os_shifts + shift_res_shifts + free_res_shifts
    }).set_index('Resident')

avail = (
    s.groupby(pd.Grouper(key='Start', freq='D')).apply(get_busy_counts)
     .reset_index()
)
avail
st.write(avail.groupby(['Start','Availability'])['Resident']
              .count()
              .reset_index()
              .pivot(index='Availability', columns='Start', values='Resident')
              .fillna(0).astype('int'))



