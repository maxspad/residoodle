from collections import OrderedDict
import streamlit as st
import config as sc
import pandas as pd

faqs = [
    (
        f'How does {sc.APP_TITLE} work?',
        f'''{sc.APP_TITLE} starts by downloading the ED schedule for UM, SJ, and Hurley from ShiftAdmin.
Then, it augments it by adding in all the residents who are on off service rotations. To do this, it
looks for gaps in the schedule where a resident appears to be "off" for too long (over a week). If that's the case
the algorithm figures they are likley to be off-service and categorizes them as such. Because it's nearly impossible
to predict every off-service schedule, the algorithm considers them to be working fake "shifts" from 12AM to 11:59PM 
each day they're off sevice.

Over the specific time period requested by the user for the specific residents requested, it goes hour-by-hour,
totaling the number of residents who are *not* on shift (in the ED or off service), and reporting the results.''',
        False
    ),

    (
        f'What are {sc.APP_TITLE}\'s limitations?',
        f'''Because all the off-service rotations list their schedules in so many different ways (ShiftAdmin,
Amion, random excel spreadsheets), it's impossible to fully integrate them into {sc.APP_TITLE}.''',
        False
    ),

    (
        f'I think this is great! / I have ideas for improvement / I found a bug! 🪲',
        f'''Awesome! Let me know via the "Feedback" tab above.''',
        False
    )
]


about_app = f'''
# About {sc.APP_TITLE}
As EM residents, we tend to get more time off than our non-EM counterparts, but
finding  ways to actually *use* that time off together is tricky due to the disjointed
nature of our schedules. It's hard enough to keep track of your own schedule, trying
to reconcile it with a friend's or your whole class's schedule is impossible.

Doodle works but its slow and requires people to do extra work an we hate that. 

So I wrote this app to try and making *using* our slightly more abundant, if oddly-scheduled,
free time a little easier. I hope you like it!

💙 Max
'''

def display():
    st.markdown(about_app)
    st.markdown('## FAQs')
    for title, content, expanded in faqs:
        expander = st.expander(title, expanded=expanded)
        expander.markdown(f'#### {title}\n{content}', unsafe_allow_html=True)