'''Set of utility functions for manipulating ShiftAdmin iCal'''

from icalevents.icalevents import events
import datetime
from dateutil.parser import parse
import pandas as pd
import numpy as np
import pytz
import urllib
import base64
from typing import Collection

def resident_df(resident_csv : str) -> pd.DataFrame:
    '''Load and preprocess resident list dataframe'''
    # Read in resident list
    resdf = pd.read_csv(resident_csv)
    return resdf

def blocks_df(blocks_csv : str) -> pd.DataFrame:
    '''Load and preprocess the blocks dataframe'''
    blocks = pd.read_csv('data/blocks.csv', parse_dates=[1,3])
    blocks.index.name = 'block_id'
    return blocks

def off_service_hours_df(osh_csv : str) -> pd.DataFrame:
    '''Load and precprocess off-service rotation hours listing'''
    # Read in off service hour listing
    osh = pd.read_csv(osh_csv)
    osh = osh.set_index('rotation')
    return osh

def master_block_sched_df(mbs_csv : str, osh : pd.DataFrame, sched : pd.DataFrame, tz : pytz.timezone) -> pd.DataFrame:
    # read the mbs CSV
    mbs = pd.read_csv(mbs_csv, header=[0,1,2,3], index_col=0)
    # flip and use only the columns we need
    mbs = mbs.T.reset_index().drop(['block','week','week_end'], axis=1)
    # each row represents a week-long period
    mbs.index = pd.period_range(mbs.loc[0, 'week_start'], freq='7D', periods=len(mbs), name='week')
    mbs = mbs.drop('week_start', axis=1)

    # upsample to get daily roations
    mbs = mbs.resample('D').ffill()
    mbs.index = mbs.index.rename('day')

    # now each row is "day|resident|rotation" - long format instead of wide
    mbs = (mbs.reset_index()
            .melt(id_vars='day', var_name='resident', value_name='rotation')
            .set_index('day'))

    # covert the mbs df in to a sched-like df
    # create the start and end times for these offservice "shifts'"
    mbs['start'] = pd.to_timedelta(mbs['rotation'].replace(osh['start'].to_dict()))
    mbs['end'] = pd.to_timedelta(mbs['rotation'].replace(osh['end'].to_dict()))
    mbs['start'] = mbs.index.to_timestamp() + mbs['start']
    mbs['end'] = mbs.index.to_timestamp() + mbs['end']
    mbs['start'] = mbs['start'].dt.tz_localize(tz)
    mbs['end'] = mbs['end'].dt.tz_localize(tz)

    # get rid of actual on-service times
    mbs = mbs[mbs['rotation'] != 'ED']

    # build the columns to make this df look like sched df 
    mbs['summary'] = 'OS ' + mbs['rotation'] + ' ' + mbs['resident']
    mbs['shift'] = mbs['rotation']
    mbs['type'] = 'Off Service'
    mbs['facility'] = 'NA'

    # filter to only the right columns
    mbs = mbs[sched.columns]

    # set index similar to sched
    mbs = mbs.reset_index(drop=True).set_index('start', drop=False).sort_index()

    return mbs

def download_ical(url : str, from_file=False) -> str:
    if not from_file:
        s = urllib.request.urlopen(url).read()
    else:
        with open(url) as f:
            s = bytes(f.read(), encoding='utf-8')
    return s

def ical_to_df(ical_str : str, start : datetime.date = None, end : datetime.date = None,
    tz=pytz.utc):
    start = datetime.date.today() if start is None else start # default to today
    end = parse("Jun 30 2022") if end is None else end # default to end of the academic year 

    es = events(string_content=ical_str, start=start, end=end)

    dicts = [e.__dict__ for e in es]
    df = pd.DataFrame(dicts)
    df = df[['summary','description','start','end']]

    split_summ = df['summary'].str.split(' ')
    names = split_summ.apply(lambda x: x[-2] + ' ' + x[-1])
    
    desc_rexp = r'Group\: (.*?)\nFacility\: (.*?)\nShift\: (.*?)\nShift Type\: (.*)'
    matches = df['description'].str.extract(desc_rexp)
    matches.columns = ['group','facility','shift','type']

    df['resident'] = names
    df = pd.concat([df, matches], axis=1)
    df = df[['summary','resident','shift','start','end','type','facility']]

    # convert to the specified timezone and reindex
    df = df.sort_values(['start','shift'])
    df['start'] = df['start'].dt.tz_convert(tz)
    df['end'] = df['end'].dt.tz_convert(tz)
    df = df.set_index('start', drop=False)

    return df

def find_off_service(sched : pd.DataFrame, blocks: pd.DataFrame, res: pd.DataFrame,
    threshold: int = 1):
    '''Returns a DataFrame where each row is a `resident` who is off-service
    between `start_date` and `end_date`'''

    sched_by_block = [sched.loc[b['start_date']:b['end_date'], :] for _, b in blocks.iterrows()]

    def _get_zero_shift_counts_for_block(df: pd.DataFrame, block_id: int):
        scbb = df.groupby('resident')['shift'].count()
        scbb = pd.DataFrame(scbb)
        scbb = scbb.join(res.set_index('resident'), how='right')
        scbb.fillna(0, inplace=True)
        scbb['block_id'] = block_id
        scbb = scbb[scbb['shift'] <= threshold]
        scbb = scbb.rename({'shift': 'shift_count'}).drop('year', axis=1)
        scbb = scbb.reset_index(drop=False)
        return scbb

    zero_shift_counts_by_block = [_get_zero_shift_counts_for_block(df, block_idx) 
                                  for block_idx, df in enumerate(sched_by_block)
                                  if len(df) > 0]
    zero_shift_counts_by_block = pd.concat(zero_shift_counts_by_block, axis=0).reset_index(drop=True)
    zero_shift_counts_by_block = pd.merge(zero_shift_counts_by_block, blocks, on='block_id') # TODO
    return zero_shift_counts_by_block

def make_offservice_entries(off_service_residents_by_block: pd.DataFrame,
    off_service_start_time: pd.Timedelta = pd.Timedelta(0, 'h'),
    off_service_end_time: pd.Timedelta = pd.Timedelta(86399, 's'),
    off_service_shift_code: str = "OS",
    off_service_shift_name: str = 'Off Service',
    tz = pytz.timezone('America/Detroit')):

    sched_entries = []
    for _, off_service_res in off_service_residents_by_block.iterrows():
        for ts in pd.date_range(off_service_res['start_date'], off_service_res['end_date'], freq='1D', inclusive='left'):
            os_start_datetime = (ts + off_service_start_time).tz_localize(tz)
            os_end_datetime = (ts + off_service_end_time).tz_localize(tz)
            off_service_dummy_row = {
                'summary': f'{off_service_shift_code} {off_service_shift_code} {off_service_res["resident"]}',
                'resident': off_service_res['resident'],
                'shift': off_service_shift_code,
                'start': os_start_datetime,
                'end': os_end_datetime,
                'type': off_service_shift_name,
                'facility': off_service_shift_name 
            }
            sched_entries.append(off_service_dummy_row)
    sched_entries = pd.DataFrame(sched_entries)
    return sched_entries.set_index('start', drop=False)


def get_final_sched(sched: pd.DataFrame, blocks: pd.DataFrame, res: pd.DataFrame):
    '''Makes modifications to the vanilla iCal schedule to include things like 
    off service rotations, vacations (not implemented)'''

    # filter schedule to only UM residents
    sched = sched.loc[np.isin(sched['resident'], res['resident']), :]

    off_service_residents_by_block = find_off_service(sched, blocks, res)
    off_service_sched_entries = make_offservice_entries(off_service_residents_by_block)

    sched_final = pd.concat([sched, off_service_sched_entries], axis=0).sort_index()
    return sched_final

def hourly_shift_info(fs: pd.DataFrame):
    sched = fs
    hdf_min = sched['start'].min()
    hdf_max = sched['end'].max()
    hdf_idx = pd.date_range(hdf_min, hdf_max, freq='1H', inclusive='left')
    hdf = pd.DataFrame({'shiftsInfo': [[] for _ in range(len(hdf_idx))]}, index=hdf_idx)
                                                                                                                                                                                                                           
    for _, shift in sched.iterrows():
        shiftidx = pd.date_range(shift['start'], shift['end'], freq='1H', inclusive='left')
        shiftInfo = {'resident': shift['resident'], 'shift': shift['shift'], 'summary': shift['summary']}
        hdf.loc[shiftidx, 'shiftsInfo'] = hdf.loc[shiftidx, 'shiftsInfo'].apply(lambda x: x + [shiftInfo])
    hdf['nUsersWorking'] = hdf['shiftsInfo'].apply(len)
    hdf.index.name = 'time'

    hdf['date'] = hdf.index.date
    hdf['time'] = hdf.index.time

    return hdf     

def working_free_for_date_time(sched: pd.DataFrame, resident_choices: Collection[str], bd: datetime.date, st: datetime.time, et: datetime.time, tz):
    '''For a given date, return a list of residents who are free, partially free, and working during given time interval'''

    fs = filter_sched_residents(sched, resident_choices)
    # select only the shifts that start on the bd day of interest
    fs = fs.loc[bd:(pd.Timestamp(bd) + pd.Timedelta(1439, 'm')), :]

    range_start = pd.Timestamp(datetime.datetime.combine(bd, st), tz=tz)
    range_end = pd.Timestamp(datetime.datetime.combine(bd, et), tz=tz)
    target_range = pd.date_range(range_start, range_end, freq='H').to_numpy()
    working, partial, free = [],[],[]
    fs_res_list = fs['resident'].drop_duplicates().to_list()
    fully_offday_res = [(res, 'Off') for res in resident_choices if not (res in fs_res_list)]

    for _, row in fs.iterrows():
        hr_range = pd.date_range(row['start'], row['end'], freq='H').to_numpy()
        hr_range_filt = hr_range[(hr_range >= range_start) & (hr_range <= range_end)]

        if len(hr_range_filt) == len(target_range): # fully working
            working.append((row['resident'], row['shift']))
        elif len(hr_range_filt) == 0: # no overlap
            free.append((row['resident'], row['shift']))
        else: # partially working
            partial.append((row['resident'], row['shift']))
    
    return working, partial, free, fully_offday_res



def hourly_shifts_being_worked(shiftInfo: pd.DataFrame, st: datetime.time, et: datetime.time, sd: datetime.date, ed: datetime.date):
    
    n_users_working = shiftInfo.pivot(index='time', columns='date', values='nUsersWorking')
    n_users_working.fillna(0, inplace=True)
    n_users_working = n_users_working.loc[st:et, sd:ed]
    return n_users_working

def free_resident_hours(hsbw: pd.DataFrame, n_residents: int):
    free_res_hrs = n_residents - hsbw
    return free_res_hrs
    
def best_dates(free_res_hrs: pd.DataFrame, n_best_days=3):
    avg_free_hours = free_res_hrs.mean(axis=0)
    # sort by free hours then date so ties are broken by earliest first
    avg_free_hours = pd.DataFrame(avg_free_hours).reset_index().sort_values([0, 'date'], ascending=[False, True])

    max_days = n_best_days if n_best_days <= len(avg_free_hours) else len(avg_free_hours)
    to_ret = [(avg_free_hours.iloc[i,0], avg_free_hours.iloc[i,1]) for i in range(max_days)]
    return to_ret

def filter_sched_dates(sched : pd.DataFrame, start_dt : pd.Timestamp, end_dt : pd.Timestamp):

    # filter the schedule to the requested dates
    fs = sched.copy()
    fs = fs[start_dt:end_dt]
    return fs

def filter_sched_residents(sched : pd.DataFrame, resident_choices = Collection[str]):

    fs = sched.copy()
    # filter the schedule to the requested residents
    fs = fs[fs['resident'].isin(resident_choices)]
    return fs

def resident_list(sched_df : pd.DataFrame):
    return list(sched_df['resident'].unique())

def image_data_str(image_fn : str) -> str:
    with open(image_fn, 'rb') as f:
        image_str = base64.b64encode(f.read()).decode()
    return image_str

if __name__ == "__main__":
    sched_df = ical_to_df('schedule.ics')
    res_list = resident_list(sched_df)
    with open('res_list.txt','w') as f:
        f.writelines([r + '\n' for r in res_list])
