import streamlit as st
import pandas as pd
import datetime
import helpers as h
import schedexp as sched
import config as cf
import plotly.express as px
from typing import Collection

def run():
    # Open the data helper files
    res, blocks, rbs = load_residoodle_db('data/residoodle_db.xlsx')

    with st.expander('Options', expanded=True):
        # st.markdown('**Step 1**: Pick the date range you want to search.')
        date_cols = st.columns(2)
        start_date = date_cols[0].date_input('Search between **Start Date**', value=datetime.date.today(),
            min_value=datetime.date.today(), max_value=datetime.date(2024,6,30))
        end_date = date_cols[1].date_input('and **End Date**', value=start_date + datetime.timedelta(days=7),
            min_value=start_date, max_value=datetime.date(2024,6,30))
        
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
        # exclude_conf = st.checkbox('Treat Conference time as "busy"', value=True)
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

    # rbs 

    rbs = (rbs.groupby(['Resident','Start'])
            .apply(expand_os_to_days)
            .reset_index(drop=True)
            .filter(['userId','Resident','Block','Shift','Start','End','Site','Type']))
    # st.write('rbs days')
    # rbs

    # Load the schedule for the selected residents
    s = (
        load_shiftadmin_sched(start_date, end_date.date())
        .query('Resident in @sel_res')
    )

    # st.write('initial loaded schedule')
    # s
    # st.write(end_date)
    s = (
        pd.concat([s, rbs])
        .filter(['Resident','Shift','Site','Type','Start','End'])
        .query('(@start_date <= Start <= @end_date) or (Start <= @start_date <= End)')
    )

    # st.write('schedule with added offservice')
    # s

    # s

    def print_and_return(x):
        print(x)
        return x

    avail = (
        s.groupby(pd.Grouper(key='Start', freq='D'))
        .apply(get_busy_counts, sel_res, start_time, end_time)
        .reset_index()
        .groupby('Resident')
        .apply(lambda g: (g
            .reset_index()
            .drop_duplicates(subset=['Start'], keep='last') # protects against bad offservice rotations
            .set_index('Start', drop=True)
            .reindex(pd.date_range(start_date, end_date))
            .fillna({'Resident': g.name, 'Availability': 'Day Off', 'Shift': 'Off'})
        ))
        .drop(columns='Resident')
        .reset_index()
        .rename(columns={'level_1': 'Start'})
    )

    # 'avail'
    # avail

    avail_by_day_long = pd.DataFrame(
        avail.groupby(['Start','Availability'])['Resident']
        .count()
        ).join(
            pd.DataFrame(
                avail.assign(AvailShift= (avail['Resident'] + ' (' + avail['Shift'] + ')'))
                    .groupby(['Start','Availability'])['AvailShift']
                    .agg(lambda g: ', '.join(g))    
            )
    ).reset_index()

    # 'avail by day long'
    # avail_by_day_long

    avail_by_day = (
        avail_by_day_long
            .pivot(index='Availability', columns='Start', values='Resident')
            .reindex(['Day Off','On Shift','Off Service','Free'], fill_value=0)
            .T
            .reindex(pd.date_range(start_date, end_date, freq='D'))
            .fillna(0)
            .astype('int')
            .assign(Busy= lambda df_: df_['Off Service'] + df_['On Shift'],
                    Available= lambda df_: df_['Free'] + df_['Day Off']) # TODO Fix if one of these is missing
            .rename_axis('Start', axis=0)
    )

    # 'Avail by day'
    # avail_by_day

    avail_by_shift = pd.DataFrame(
        avail.assign(AvailShift= (avail['Resident'] + ' (' + avail['Shift'] + ')'))
            .groupby(['Start','Availability'])['AvailShift']
            .agg(lambda g: ', '.join(g))
            .reset_index()
            .pivot(index='Availability', columns='Start', values='AvailShift')
            .reindex(['Day Off','On Shift','Off Service','Free'])
            .T
            .reindex(pd.date_range(start_date, end_date, freq='D'))
            .fillna('None')    
    )

    # 'Avail by shift'
    # avail_by_shift

    st.markdown('# Best Days')
    st.markdown('The days with the most free residents in the range you selected.')

    # avail_by_shift

    best_days = avail_by_day.sort_values(['Available','Free','Day Off','Start'], ascending=[False, True, False, False]).iloc[:3, :].index
    # best_days = cbd.groupby(['Day'])[['Count']].sum().reset_index().sort_values(['Count','Day'], ascending=[False, True])
    # best_days = best_days.iloc[:3, :]
    # best_days
    cols = st.columns(len(best_days))
    titles = ['🥇', '🥈', '🥉']
    for i, c in enumerate(cols):
        d = best_days[i]

        c.markdown(f'## {titles[i]} {d.strftime("%m/%d")}')
        n_free = avail_by_day.loc[d, 'Available']

        c.markdown(f'**{n_free}** out of {len(sel_res)} residents free.')

        md_str = ''
        for k in ['Day Off','Free','On Shift','Off Service']:
            md_str += f'**{k}**: {avail_by_shift.loc[d, k]}\n\n'
        c.markdown(md_str)

    # st.write(avail_by_day_long)

    # avail_by_shift

    st.markdown('# All Days')
    st.markdown('A day-by-day look at how many residents are free over the selected date range. Mouse over the graph for more information.')

    avail_by_day_long_for_bar = (
        avail_by_day_long.rename({'Start': 'Day', 'Resident':'Count', 'AvailShift':'Residents'}, axis=1)
            .assign(Count= lambda df_: df_['Count'].where(df_['Availability'].isin(['Day Off','Free']), -1*df_['Count']))
    )
    plt = px.bar(avail_by_day_long_for_bar, x='Day', y='Count', color='Availability', hover_data=['Residents'],
        title='Number of Free Residents by Day',
        color_discrete_map={'Day Off': '#2ECC71', 'Free': '#82E0AA', 'Off Service': '#EC7063', 'On Shift': '#E74C3C'})
    opacities = [0.3, 0.15, 0.075]
    for i in range(len(best_days)):
        plt.add_vrect(x0=f'{best_days[i] - pd.Timedelta("12h")}', x1=f'{best_days[i] + pd.Timedelta("12h")}', 
            fillcolor='green', opacity=opacities[i], 
            annotation_font_size=16, 
            annotation_font_color='black',
            annotation_text=titles[i],
            annotation_position="inside top left")
    st.plotly_chart(plt)
    # blah = (avail_by_day.join(avail_by_shift))

    # st.write(blah.reset_index().pivot(index='Availability', columns='Start', values='Resident'))

@st.experimental_memo(show_spinner=False)
def load_residoodle_db(rdb_fn : str):
    rdb = pd.read_excel(rdb_fn, index_col=0,
                        sheet_name=['Residents','Blocks','ResidentBlockSchedule'])
    res, blocks, rbs = rdb['Residents'], rdb['Blocks'], rdb['ResidentBlockSchedule']
    return res, blocks, rbs

@st.experimental_memo(show_spinner=False)
def load_shiftadmin_sched(start_date : datetime.date, end_date : datetime.date):
    s = sched.load_sched_api(start_date, end_date, remove_nonum_hurley=True)
    return s

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

def get_busy_counts(g : pd.DataFrame, sel_res : Collection[str], start_time : datetime.time, end_time : datetime.time):
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
    shift_res_shifts = on_shift['Shift'].tolist()
    # st.write(len(shift_res), len(shift_res_shifts))
    
    not_on_shift = (
        g[~is_os]#.assign(StartTime = g['Start'].dt.time, EndTime = g['End'].dt.time)
                .query('not ((@start_time <= StartTime <= @end_time) or (StartTime <= @start_time <= EndTime))')
    )
    free_res = set(not_on_shift['Resident'])
    free_res_shifts = not_on_shift['Shift'].tolist()
    # st.write(len(free_res), len(free_res_shifts))

    try: 
        return pd.DataFrame({
            'Availability': (['Day Off']*len(day_off_res) + ['Off Service']*len(os_res) + ['On Shift']*len(shift_res) + ['Free']*len(free_res)),
            'Resident': list(day_off_res) + list(os_res) + list(shift_res) + list(free_res),
            'Shift': day_off_shifts + os_shifts + shift_res_shifts + free_res_shifts
        }).set_index('Resident')
    except:
        st.write([(day_off_res ,day_off_shifts), (os_res, os_shifts), (shift_res, shift_res_shifts), (free_res, free_res_shifts)])
        st.error('Failure...')
        st.stop()
