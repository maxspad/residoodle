'''Set of utility functions for manipulating ShiftAdmin iCal'''

from icalevents.icalevents import events
import datetime
from dateutil.parser import parse
import pandas as pd
import pytz
import urllib
import base64

def resident_df(resident_csv : str) -> pd.DataFrame:
    '''Load and preprocess resident list dataframe'''
    # Read in resident list
    resdf = pd.read_csv(resident_csv)
    return resdf

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
