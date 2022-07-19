'''Main entrypoint for the application'''

import streamlit as st
# from streamlit_option_menu import option_menu
import sched_consts
# import sched_helpers
import sched
# import feedback
# import about

# This command can only be run once per streamlit app
st.set_page_config(
    page_title=sched_consts.APP_TITLE,
    page_icon="🦝",
    menu_items={
        'Get Help':None,
        "Report a Bug":None,
        "About":sched_consts.ABOUT_MARKDOWN
    }
)
# Display the header
raccoon_string = sched.image_data_str('assets/raccoon.png')
html = f'''
<hr style='margin: 0.25em'/>
<h1 style='text-align: center'>
    <img height="70px" src="data:image/png;base64,{raccoon_string}"/>
    <span style='margin-left: 0.5em'>{sched_consts.APP_TITLE}</span>
</h1>
<hr style='margin: 0.25em'  />
'''
st.write(html, unsafe_allow_html=True)

# # Display the Navigation Bar
# nav_bar_selected = option_menu(None, sched_consts.APP_PAGES,
#     icons=['house','info-circle','card-checklist'],
#     menu_icon='cast', default_index=0, orientation='horizontal')


# # Display the selected page
# if nav_bar_selected == "Home":
#     sched.display()
# elif nav_bar_selected == "About":
#     about.display()
# elif nav_bar_selected == 'Feedback':
#     feedback.display()



