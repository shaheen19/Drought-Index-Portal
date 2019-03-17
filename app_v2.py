# -*- coding: utf-8 -*-
"""
An Application to visualize time series of drought indices (or others soon).

Production notes:
	- There is a nonetype error when deselecting.

Created on Fri Jan 4 12:39:23 2019

@author: Travis Williams

Sync Check: 01/20/2019
"""

# Functions and Libraries
import os
import sys
import copy
import dash
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
import dash_core_components as dcc
import dash_html_components as html
import dash_table
import datetime as dt
from flask_caching import Cache
import gc
from inspect import currentframe, getframeinfo
import json
import numpy as np
import pandas as pd
import psutil
from osgeo import gdal
import warnings
import xarray as xr

# Set Working Directory - works if it's the same as the file location
frame = getframeinfo(currentframe()).filename
path = os.path.dirname(os.path.abspath(frame))
os.chdir(path)

# Import functions
from functions import Index_Maps, makeMap, areaSeries, droughtArea
from functions import Coordinate_Dictionaries, Location_Builder

# Check if we are working in Windows or Linux to find the data
if sys.platform == 'win32':
    data_path = 'f:/'
else:
    data_path = '/root/Sync'

# What to do with the mean of empty slice warning?
warnings.filterwarnings("ignore")

######################## Default Values #######################################
default_function = 'oarea'
default_years = [1985, 2019]

# Default click before the first click for any map
default_click = {'points': [{'curveNumber': 0, 'lat': 40.0, 'lon': -105.75,
                             'marker.color': 0, 'pointIndex': 0,
                             'pointNumber': 0, 'text': 'Boulder County, CO'}]}

# Default for click store (includes an index for most recent click)
default_clicks = [list(np.repeat(default_click.copy(), 4)), 0]
default_clicks = json.dumps(default_clicks)

# For testing
source_signal = [[[2000, 2017], [1, 12]], 'Viridis', 'no']
source_choice = 'pdsi'
source_function = 'pmean'

# For scaling
ranges = pd.read_csv('data/tables/index_ranges.csv')

############### The DASH application and server ###############################
app = dash.Dash(__name__)

# Go to stylesheet, styled after a DASH example (how to serve locally?)
app.css.append_css({'external_url':
                    'https://codepen.io/williamstravis/pen/maxwvK.css'})
app.scripts.config.serve_locally = True

# For the Loading screen
app.css.append_css({"external_url":
                    "https://codepen.io/williamstravis/pen/EGrWde.css"})

# Create Server Object
server = app.server

# Disable exceptions (attempt to speed things up)
app.config['suppress_callback_exceptions'] = True

# Create a simple file storeage cache, holds unique outputs of Index_Maps
cache = Cache(config={'CACHE_TYPE': 'filesystem',
                      'CACHE_DIR': 'data/cache',
                      'CACHE_THRESHOLD': 2})
cache2 = Cache(config={'CACHE_TYPE': 'filesystem',
                        'CACHE_DIR': 'data/cache2',
                        'CACHE_THRESHOLD': 2})
cache.init_app(server)
cache2.init_app(server)

####################### Options ###############################################
# Drought Index Options
indices = [{'label': 'PDSI', 'value': 'pdsi'},
           {'label': 'PDSI-Self Calibrated', 'value': 'pdsisc'},
           {'label': 'Palmer Z Index', 'value': 'pdsiz'},
           {'label': 'SPI-1', 'value': 'spi1'},
           {'label': 'SPI-2', 'value': 'spi2'},
           {'label': 'SPI-3', 'value': 'spi3'},
           {'label': 'SPI-6', 'value': 'spi6'},
           {'label': 'SPEI-1', 'value': 'spei1'},
           {'label': 'SPEI-2', 'value': 'spei2'},
           {'label': 'SPEI-3', 'value': 'spei3'},
           {'label': 'SPEI-6', 'value': 'spei6'},
           {'label': 'EDDI-1', 'value': 'eddi1'},
           {'label': 'EDDI-2', 'value': 'eddi2'},
           {'label': 'EDDI-3', 'value': 'eddi3'},
           {'label': 'EDDI-6', 'value': 'eddi6'}]

# Index dropdown labels
indexnames = {'pdsi': 'Palmer Drought Severity Index',
              'pdsisc': 'Self-Calibrated Palmer Drought Severity Index',
              'pdsiz': 'Palmer Z Index',
              'spi1': 'Standardized Precipitation Index - 1 month',
              'spi2': 'Standardized Precipitation Index - 2 month',
              'spi3': 'Standardized Precipitation Index - 3 month',
              'spi6': 'Standardized Precipitation Index - 6 month',
              'spei1': 'Standardized Precipitation-Evapotranspiration Index' +
                       ' - 1 month',
              'spei2': 'Standardized Precipitation-Evapotranspiration Index' +
                       ' - 2 month',
              'spei3': 'Standardized Precipitation-Evapotranspiration Index' +
                       ' - 3 month',
              'spei6': 'Standardized Precipitation-Evapotranspiration Index' +
                       ' - 6 month',
              'eddi1': 'Evaporative Demand Drought Index - 1 month',
              'eddi2': 'Evaporative Demand Drought Index - 2 month',
              'eddi3': 'Evaporative Demand Drought Index - 3 month',
              'eddi6': 'Evaporative Demand Drought Index - 6 month'}

# Function options (Percentile & Index Values)
function_options_perc = [{'label': 'Mean', 'value': 'pmean'},
                         {'label': 'Maximum', 'value': 'pmax'},
                         {'label': 'Minimum', 'value': 'pmin'}]

function_options_orig = [{'label': 'Mean', 'value': 'omean'},
                         {'label': 'Maximum', 'value': 'omax'},
                         {'label': 'Minimum', 'value': 'omin'},
                         # {'label': 'Coefficient of Variation', 'value': 'ocv'},
                         {'label': 'Drought Severity Area', 'value':'oarea'}]

function_names = {'pmean': 'Average Percentiles',
                  'pmax': 'Maxmium Percentile',
                  'pmin': 'Minimum Percentile',
                  'omean': 'Average Index Values',
                  'omax': 'Maximum Index Value',
                  'omin': 'Minimum Index Value',
                  # 'ocv': 'Coefficient of Variation',
                  'oarea': 'Average Index Values'}

# County Data Frame and options  # <------------------------------------------- Clean this up, automate csv building from source
counties_df = pd.read_csv('data/tables/counties3.csv')
c_df = pd.read_csv('data/tables/unique_counties.csv')
rows = [r for idx, r in c_df.iterrows()]
county_options = [{'label': r['place'], 'value': r['grid']} for r in rows]
options_pos = {county_options[i]['label']: i for
               i in range(len(county_options))}
just_counties = [d['label'] for d in county_options]

# State options
states_df = counties_df[['STATE_NAME',
                         'STUSAB', 'FIPS State']].drop_duplicates().dropna()
states_df = states_df.sort_values('STUSAB')
rows = [r for idx, r in states_df.iterrows()]
state_options = [{'label': r['STUSAB'], 'value': r['FIPS State']} for
                  r in rows]

# Map type options
maptypes = [{'label': 'Light', 'value': 'light'},
            {'label': 'Dark', 'value': 'dark'},
            {'label': 'Basic', 'value': 'basic'},
            {'label': 'Outdoors', 'value': 'outdoors'},
            {'label': 'Satellite', 'value': 'satellite'},
            {'label': 'Satellite Streets', 'value': 'satellite-streets'}]

# Color scale options
colorscales = ['Default', 'Blackbody', 'Bluered', 'Blues', 'Earth', 'Electric',
               'Greens', 'Greys', 'Hot', 'Jet', 'Picnic', 'Portland',
               'Rainbow', 'RdBu', 'Reds', 'Viridis', 'RdWhBu',
               'RdWhBu (NOAA PSD Scale)', 'RdYlGnBu', 'BrGn']
color_options = [{'label': c, 'value': c} for c in colorscales]

# We need one external colorscale for a hard set drought area chart
RdWhBu = [[0.00, 'rgb(115,0,0)'], [0.10, 'rgb(230,0,0)'],
          [0.20, 'rgb(255,170,0)'], [0.30, 'rgb(252,211,127)'],
          [0.40, 'rgb(255, 255, 0)'], [0.45, 'rgb(255, 255, 255)'],
          [0.55, 'rgb(255, 255, 255)'], [0.60, 'rgb(143, 238, 252)'],
          [0.70, 'rgb(12,164,235)'], [0.80, 'rgb(0,125,255)'],
          [0.90, 'rgb(10,55,166)'], [1.00, 'rgb(5,16,110)']]

# Date Options
# Check the latest available date
with xr.open_dataset(
        os.path.join(data_path,
                     'data/droughtindices/netcdfs/spi1.nc')) as data:
    sample_nc = data
    data.close()
max_date = sample_nc.time.data[-1]
del sample_nc
max_year = pd.Timestamp(max_date).year
max_month = pd.Timestamp(max_date).month

# Create the date options
years = [int(y) for y in range(1900, max_year + 1)]
yearmarks = dict(zip(years, years))
monthmarks = {1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun',
              7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'}

# Only display every 5 years for space
for y in yearmarks:
    if y % 5 != 0:
        yearmarks[y] = ""

################## Map Section ################################################
# A source data set for geometry and crs information (not fully there yet)
source_path = "data/rasters/source_array.nc"

# For translating geographic coordinates to numpy coordinates and back
cd = Coordinate_Dictionaries(source_path)
source = cd.source

# For filtering by state, or defaulting to CONUS
mask = cd.grid * 0 + 1
state_arrays = gdal.Open('data/rasters/us_states.tif').ReadAsArray()

# NA map for when EDDI before 1980 is selected
with np.load("data/npy/NA_overlay.npz") as data:  # <-------------------------- Redo this to look more professional
    na = data.f.arr_0
    data.close()

# Make the NA map color scale stand out
for i in range(na.shape[0]):
    na[i] = na[i]*i

# Mapbox Access
mapbox_access_token = ('pk.eyJ1IjoidHJhdmlzc2l1cyIsImEiOiJjamZiaHh4b28waXNk' +
                       'MnptaWlwcHZvdzdoIn0.9pxpgXxyyhM6qEF_dcyjIQ')

# Mapbox initial layout
# (Check this out! https://paulcbauer.shinyapps.io/plotlylayout/)
layout = dict(
    autosize=True,
    height=500,
    font=dict(color='#CCCCCC',
              fontweight='bold'),
    titlefont=dict(color='#CCCCCC',
                   size='20',
                   family='Time New Roman',
                   fontweight='bold'),
    margin=dict(l=55, r=35, b=65, t=90, pad=4),
    hovermode="closest",
    plot_bgcolor="#083C04",
    paper_bgcolor="#0D347C",
    legend=dict(font=dict(size=10, fontweight='bold'), orientation='h'),
    title='<b>Index Values/b>',
    mapbox=dict(
        accesstoken=mapbox_access_token,
        style="satellite-streets",
        center=dict(lon=-95.7, lat=37.1),
        zoom=2))


################### Temporary CSS Items #######################################
# For css later  <------------------------------------------------------------- Move all styling to css
tab_height = '25px'
tab_style = {'height': tab_height, 'padding': '0'}
tablet_style = {'line-height': tab_height, 'padding': '0'}
selected_style = {'color': 'black', 'box-shadow': '1px 1px 0px white',
                  'border-left': '1px solid lightgrey',
                  'border-right': '1px solid lightgrey',
                  'border-top': '3px solid #e36209'}
unselected_style = {'border-top-left-radius': '3px',
                    'background-color': '#f9f9f9',
                    'padding': '0px 24px',
                    'border-bottom': '1px solid #d6d6d6'}

################### Application Layout ########################################
# Create a Div maker
def divMaker(id_num, index='noaa'):
    div = html.Div([
                html.Div([
                    html.Div([
                            dcc.Tabs(id='choice_tab_{}'.format(id_num),
                                     value='index',
                                     style=tab_style,
                                     children=dcc.Tab(value='index',
                                                      label='Drought Index',
                                                      style=tablet_style,
                                                      selected_style=
                                                                tablet_style)),
                            dcc.Dropdown(id='choice_{}'.format(id_num),
                                         options=indices, value=index)],
                            style={'width': '30%',
                                   'float': 'left'}),
                    html.Div([
                            dcc.Tabs(id='location_tab_{}'.format(id_num),
                                     value='county',
                                     style=tab_style,
                                     children=[
                                         dcc.Tab(value='county',
                                                 label='County',
                                                 style=tablet_style,
                                                 selected_style=tablet_style),
                                         dcc.Tab(value='state',
                                                 label='State/States',
                                                 style=tablet_style,
                                                 selected_style=tablet_style
                                                 )]),
                                html.Div(id='location_div_{}'.format(id_num),
                                         children=[
                                            html.Div(
                                             id='county_div_{}'.format(id_num),
                                             children=
                                               [dcc.Dropdown(
                                                 id='county_{}'.format(id_num),
                                                 options=county_options,
                                                 clearable=False,
                                                 multi=False,
                                                 value=24098)]),
                                            html.Div(
                                             id='state_div_{}'.format(id_num),
                                             children=
                                               [dcc.Dropdown(
                                                 id='state_{}'.format(id_num),
                                                 options=state_options,
                                                 clearable=False,
                                                 multi=True,
                                                 placeholder=('Contiguous ' +
                                                              'United States'),
                                                 value=None)],
                                               style={'display': 'none'})])],
                                style={'width': '50%',
                                       'float': 'left'}),
                        html.Button(id='update_graphs_{}'.format(id_num),
                                    children=['Update Graphs'],
                                    style={'width': '20%',
                                           'background-color': '#C7D4EA',
                                           'font-family': 'Times New Roman',
                                           'padding': '0px',
                                           'margin-top': '26'
                                           })],
                        className='row'),
                 dcc.Graph(id='map_{}'.format(id_num),
                           config={'showSendToCloud': True}),
                 html.Div([dcc.Graph(id='series_{}'.format(id_num),
                                     config={'showSendToCloud': True})]),
                 html.Div(id='coverage_div_{}'.format(id_num),
                          style={'margin-bottom': '25'}),
                 html.Button(
                         id='dsci_button_{}'.format(id_num),
                         title=('The Drought Severity ' +
                          'Coverage Index (DSCI) is a way to aggregate the ' +
                          'five drought severity classifications into a '+
                          'single number. It is calculated by taking the ' +
                          'percentage of an area in each drought category, ' +
                          'weighting each by their severity, and adding ' +
                          'them together:                                  ' +
                          '%D0*1 + %D1*2 + %D2*3 + %D3*4 + %D4*5'),
                          type='button',
                          n_clicks=2,
                          children=['Show DSCI: Off'],
                          # style={'dsiplay': 'none'}
                          ),
                 html.Hr(),
            ], className='six columns')
    return div

app.layout = html.Div([  # <--------------------------------------------------- Line all brackets and parens up
               html.Div([

                # Sponsers
                html.A(html.Img(
                    src = ("https://github.com/WilliamsTravis/" +
                            "Pasture-Rangeland-Forage/blob/master/" +
                            "data/earthlab.png?raw=true"),
                    className='one columns',
                    style={
                        'height': '40',
                        'width': '100',
                        'float': 'right',
                        'position': 'static'
                           }),
                        href="https://www.colorado.edu/earthlab/",
                        target="_blank"),
                html.A(html.Img(
                    src = ('https://github.com/WilliamsTravis/Pasture-' +
                           'Rangeland-Forage/blob/master/data/' +
                           'wwa_logo2015.png?raw=true'),
                    className='one columns',
                    style={
                        'height': '50',
                        'width': '150',
                        'float': 'right',
                        'position': 'static',
                        }),
                        href = "http://wwa.colorado.edu/",
                        target = "_blank"),
                 html.A(html.Img(
                    src =( "https://github.com/WilliamsTravis/Pasture-" +
                          "Rangeland-Forage/blob/master/data/" +
                          "nidis.png?raw=true"),
                    className='one columns',
                    style={
                        'height': '50',
                        'width': '200',
                        'float': 'right',
                        'position': 'relative',
                        }),
                        href = "https://www.drought.gov/drought/",
                        target = "_blank"),
                 html.A(html.Img(
                    src = ("https://github.com/WilliamsTravis/Pasture-" +
                           "Rangeland-Forage/blob/master/data/" +
                           "cires.png?raw=true"),
                    className='one columns',
                    style={
                        'height': '50',
                        'width': '100',
                        'float': 'right',
                        'position': 'relative',
                        'margin-right': '20',
                        }),
                        href = "https://cires.colorado.edu/",
                        target = "_blank"
                        )],
                className = 'row'),

        # Title
        html.Div([html.H1('Drought Index Comparison Portal'),
                  html.Hr()],
                 className='twelve columns',
                 style={'font-weight': 'bolder',
                        'text-align': 'center',
                        'font-size': '50px',
                        'font-family': 'Times New Roman',
                        'margin-top': '25'}),

        # Toggle Options
        html.Div([
                html.Button(id='toggle_options',
                            children='Toggle Options: Off',
                            type='button',
                            title='Click to collapse the options above',
                            style={'display': 'none'}),
                html.Button(id="desc_button",
                            children="Project Description: Off",
                            title=("Toggle this on and off to show a " +
                                   "description of the project with " +
                                   "some instructions."),
                            style={'display': 'none'}),
                html.Button(id="click_sync",
                            children="Location Syncing: On",
                            title=("Toggle on and off to sync the location " +
                                   "of the time series between each map"),
                            style={'display': 'none'})],
                style={'margin-bottom': '30',
                       'text-align': 'center'}),

    # Description
        html.Div([
            html.Div([dcc.Markdown(id='description')],
                     style={'text-align':'center',
                            'width':'70%',
                            'margin':'0px auto'})],
            style={'text-align':'center',
                   'margin': '0 auto',
                   'width': '100%'}),

        # Year Slider
        html.Div(id='options',
                 children=[
                     html.Div([
                             html.H3(id='date_range',
                                     children=['Study Period Year Range']),
                             html.Div([dcc.RangeSlider(
                                                     id='year_slider',
                                                     value=default_years,
                                                     min=1900,
                                                     max=max_year,
                                                     updatemode='drag',
                                                     marks=yearmarks)],
                                      style={'margin-top': '0',
                                             'margin-bottom': '40'}),

                     # Month Slider
                     html.Div(id='month_slider',
                              children=[
                                      html.H3(id='month_range',
                                              children=['Month Range']),
                                      html.Div(id='month_slider_holder',
                                               children=[
                                                   dcc.RangeSlider(
                                                       id='month',
                                                       value=[1, 12],
                                                       min=1, max=12,
                                                       updatemode='drag',
                                                       marks=monthmarks)],
                                               style={'width': '35%'})],
                              style={'display': 'none'},
                              )],
                     className="row",
                     style={'margin-bottom': '55'}),

            # Options
            html.Div(id='options_div',
                     children=[
                        # Maptype
                        html.Div([
                                html.H3("Map Type"),
                                 dcc.Dropdown(
                                        id="map_type",
                                        value="basic",
                                        options=maptypes)],
                                 className='two columns'),

                        # Functions
                        html.Div([
                                 html.H3("Function"),
                                 dcc.Tabs(
                                    id='function_type', value='perc',
                                    style=tab_style,
                                    children=[
                                        dcc.Tab(label='Percentiles',
                                                value='perc',
                                                style=tablet_style,
                                                selected_style=tablet_style),
                                        dcc.Tab(label='Index Values',
                                                value='index',
                                                style=tablet_style,
                                                selected_style=tablet_style)]),
                                 dcc.Dropdown(id='function_choice',
                                                options=function_options_perc,
                                                value='pmean')],
                                 className='three columns'),

                        # Customize Color Scales
                        html.Div([
                                html.H3('Color Gradient'),
                                dcc.Tabs(
                                    id='reverse', value='no',
                                    style=tab_style,
                                    children=[
                                        dcc.Tab(value='yes',
                                                label='Reversed',
                                                style=tab_style,
                                                selected_style=tablet_style),
                                        dcc.Tab(value='no',
                                                label="Not Reversed",
                                                style=tab_style,
                                                selected_style=tablet_style)]),
                                dcc.Dropdown(id='colors',
                                             options=color_options,
                                             value='Default')],
                                 className='three columns')],
                       className='row',
                       style={'margin-bottom': '50',
                              'margin-top': '0'}),
        ]),

        # Break
        html.Br(style={'line-height': '500%'}),

        # Submission Button
        html.Div([
            html.Button(id='submit',
                        children='Submit Options',
                        type='button',
                        style={'background-color': '#C7D4EA',
                               'border-radius': '2px',
                               'font-family': 'Times New Roman',})],
            style={'text-align': 'center'}),

        # Break line
        html.Hr(),

        # Four by Four Map Layout
        # Row 1
        html.Div([divMaker(1, 'pdsi'), divMaker(2, 'spei1')],
                 className='row'),

        # Row 2
        # html.Div([divMaker(3, 'spei6'), divMaker(4, 'spi3')],  # <----------- Consider only including two until we free more memory/get better machine
        #          className='row'),

        # Signals  # <--------------------------------------------------------- Destruction Zone! Most of these aren't needed with the dash updates
        html.Div(id='signal', style={'display': 'none'}),
        html.Div(id='key_1', children='1', style={'display': 'none'}),
        html.Div(id='key_2', children='2', style={'display': 'none'}),
        html.Div(id='location_store', style={'display': 'none'}),
        html.Div(id='choice_store', style={'display': 'none'}),

        ],
    className='ten columns offset-by-one') # The end!


################ App Callbacks ################################################
# Option Callbacks
@app.callback([Output('month_slider', 'style'),
               Output('month_slider_holder', 'children'),
               Output('date_range', 'children')],
              [Input('year_slider', 'value')])
def monthSlider(year_range):
    '''
    If users select the most recent, adjust available months
    '''
    if year_range[0] == year_range[1]:
        style={}
        if year_range[1] == max_year:
            month2 = max_month
            marks = {key: value for key, value in monthmarks.items() if
                     key <= month2}
        else:
            month2 = 12
            marks = monthmarks
        slider = [dcc.RangeSlider(id='month',
                                  value=[1, month2],
                                  min=1, max=month2,
                                  updatemode='drag',
                                  marks=marks)]
        string = 'Study Period Year Range: {}'.format(year_range[0])

    else:
        style={'display': 'none'}
        slider = [dcc.RangeSlider(id='month',
                                  value=[1, 12],
                                  min=1, max=12,
                                  updatemode='drag',
                                  marks=monthmarks)]
        string = 'Study Period Year Range: {} - {}'.format(year_range[0],
                                                           year_range[1])

    return style, slider, string


@app.callback(Output('month_range', 'children'),
              [Input('month', 'value')])
def printMonthRange(months):
    '''
    Output text of the month range/single month selection
    '''
    if months[0] != months[1]:
        string = 'Month Range: {} - {}'.format(monthmarks[months[0]],
                                               monthmarks[months[1]])
    else:
        string = 'Month Range: {}'.format(monthmarks[months[0]])
    return string


@app.callback([Output('options', 'style'),
               Output('toggle_options', 'style'),
               Output('toggle_options', 'children')],
              [Input('toggle_options', 'n_clicks')])
def toggleOptions(click):
    '''
    Toggle options on/off
    '''
    if not click:
        click = 0
    if click % 2 == 0:
        div_style = {'display': 'none'}
        button_style = {'background-color': '#a8b3c4',
                        'border-radius': '4px',
                        'font-family': 'Times New Roman'}
        children = "Display Options: Off"
    else:
        div_style = {}
        button_style = {'background-color': '#c7d4ea',
                        'border-radius': '4px',
                        'font-family': 'Times New Roman'}
        children = "Display Options: On"
    return div_style, button_style, children


@app.callback([Output('click_sync', 'style'),
               Output('click_sync', 'children')],
              [Input('click_sync', 'n_clicks')])
def toggleSyncButton(click):
    '''
    change the color of on/off location syncing button  - for css
    '''
    if not click:
        click = 0
    if click % 2 == 0:
        children = "Location Syncing: On"
        style = {'background-color': '#c7d4ea',
                 'border-radius': '4px',
                 'font-family': 'Times New Roman',  # Specified in css?
                 }
    else:
        children = "Location Syncing: Off"
        style = {'background-color': '#a8b3c4',
                 'border-radius': '4px',
                 'font-family': 'Times New Roman',}
    return style, children


@app.callback([Output('description', 'children'),
               Output('desc_button', 'style'),
               Output('desc_button', 'children')],
              [Input('desc_button', 'n_clicks')])
def toggleDescription(click):
    '''
    Toggle description on/off
    '''
    if not click:
        click = 0
    if click % 2 == 0:
        desc_children = ""
        style = {'background-color': '#a8b3c4',
                  'border-radius': '4px',
                  'font-family': 'Times New Roman'}
        button_children = "Description: Off"

    else:
        desc_children = open('data/tables/description.txt').read()
        style = {'background-color': '#c7d4ea',
                 'border-radius': '4px',
                 'font-family': 'Times New Roman'}
        button_children = "Description: On"

    return desc_children, style, button_children


@app.callback([Output('function_choice', 'options'),
               Output('function_choice', 'value')],
              [Input('function_type', 'value')])
def functionOptions(function_type):
    '''
    Use the Percentile/Index tab to decide which functions options to
    display.
    '''
    if function_type == 'perc':
        return function_options_perc, 'pmean'
    else:
        return function_options_orig, 'omean'


# Function callbacks
@cache.memoize() # To be replaced with something more efficient
def retrieve_data(signal, function, choice):
    [time_range, colorscale, reverse_override] = signal
    data = Index_Maps(time_range, colorscale, reverse_override, choice)
    delivery = makeMap(data, function)
    return delivery

@cache2.memoize()
def getDroughtArea(arrays, choice):
    return droughtArea(arrays, choice)

# Output list of all index choices for syncing
@app.callback(Output('choice_store', 'children'),
              [Input('choice_1', 'value'),
               Input('choice_2', 'value')])
def choiceStore(choice1, choice2):
    return (json.dumps([choice1, choice2]))


# Store data in the cache and hide the signal to activate it in the hidden div
@app.callback(Output('signal', 'children'),
              [Input('submit', 'n_clicks')],
              [State('colors', 'value'),
               State('reverse', 'value'),
               State('year_slider', 'value'),
               State('month', 'value')])
def submitSignal(click, colorscale, reverse, year_range, month_range):
    '''
    Collect and hide the options signal in the hidden div.
    '''
    if not month_range:
        month_range = [1, 1]
    signal = [[year_range, month_range], colorscale, reverse]
    return json.dumps(signal)


@app.callback(Output('location_store', 'children'),
              [Input('map_1', 'clickData'),
               Input('map_2', 'clickData'),
               Input('map_1', 'selectedData'),
               Input('map_2', 'selectedData'),
               Input('county_1', 'value'),
               Input('county_2', 'value'),
               Input('update_graphs_1', 'n_clicks'),
               Input('update_graphs_2', 'n_clicks')],
              [State('state_1', 'value'),
               State('state_2', 'value')])
def locationPicker(click1, click2, select1, select2, county1, county2, update1, 
                   update2, state1, state2):
        '''
        With the context strategy it is still useful to have an independent
        selection filter callback. Because there are many types of buttons and
        clicks that could trigger a graph update we would have to parse through
        each input to check if it is a location. It's still much nicer than
        setting up a dozen hidden divs, timing callbacks, and writing long
        lines of logic to determine which was most recently updated.
        '''
        # package the selections for indexing
        locations = [click1, click2, select1, select2, county1, county2,
                     state1, state2]
        updates = [update1, update2]
        context = dash.callback_context
        triggered_value = context.triggered[0]['value']
        triggered_id = context.triggered[0]['prop_id']
        print('Triggered Prop ID ' + str(triggered_id))
        if 'selectedData' in triggered_id:
            print('Selected Data Point Length: ' +
                  str(len(triggered_value['points'])))

        # The update graph button activates state selections
        if 'update_graph' in context.triggered[0]['prop_id']:
            # When you switch from county to state, there is no initial value -- This is also the initializing condition, by chance 
            if triggered_value is None:
                print("Triggered selection is update button and value is None \
                      Defaulting to CONUS")
                triggered_value = 'all'
                sel_idx = 0
            else:
                update_idx = updates.index(triggered_value) - 2  # <----------- We need the position of the most recent update...
                if locations[update_idx] is None:
                    raise PreventUpdate
                triggered_value = locations[update_idx]  # <------------------- ...to be -2 or -1 to serve as the index to the selected state
                sel_idx = locations.index(triggered_value)
        else:
            sel_idx = locations.index(triggered_value)
        
        selector = Location_Builder(triggered_value, cd)
        location = selector.chooseRecent()
        try:
            location.append(sel_idx)
        except:
            print('empty location')
            raise PreventUpdate
        # print('locationPicker selection: ' + str(location))
        return location


# In[] Any callback with multiple instances goes here
for i in range(1, 3):
    @app.callback([Output('county_div_{}'.format(i), 'style'),
                   Output('state_div_{}'.format(i), 'style')],
                  [Input('location_tab_{}'.format(i), 'value')],
                  [State('key_{}'.format(i), 'children')])
    def displayLocOptions(tab_choice, key):
        key = int(key)
        if tab_choice == 'county':
            county_style = {}
            state_style = {'display': 'none'}
        else:
            county_style = {'display': 'none'}
            state_style = {}
        return county_style, state_style

    @app.callback(Output('coverage_div_{}'.format(i), 'children'),
                  [Input('series_{}'.format(i), 'hoverData'),
                   Input('dsci_button_{}'.format(i), 'n_clicks'),
                   Input('submit', 'n_clicks')],
                  [State('function_choice', 'value')])
    def hoverCoverage(hover, click1, click2, function):
        '''
        The tooltips on the drought severity coverage area graph were
        overlapping, so this outputs the hover data to a chart below instead.
        '''
        if function == 'oarea':
            try:
                date = dt.datetime.strptime(hover['points'][0]['x'], '%Y-%m-%d')
                date = dt.datetime.strftime(date, '%b, %Y')
                # print(str(hover))
                if click1 % 2 == 0:
                    ds = ['{0:.2f}'.format(hover['points'][i]['y']) for
                          i in range(5)]
                    coverage_df = pd.DataFrame({'D0 - D4 (Dry)': ds[0],
                                                'D1 - D4 (Moderate)': ds[1],
                                                'D2 - D4 (Severe)': ds[2],
                                                'D3 - D4 (Extreme)': ds[3],
                                                'D4 (Exceptional)': ds[4]},
                                               index=[0])
    
                else:
                    ds = ['{0:.2f}'.format(hover['points'][i]['y']) for
                          i in range(6)]
                    coverage_df = pd.DataFrame({'D0 - D4 (Dry)': ds[0],
                                                'D1 - D4 (Moderate)': ds[1],
                                                'D2 - D4 (Severe)': ds[2],
                                                'D3 - D4 (Extreme)': ds[3],
                                                'D4 (Exceptional)': ds[4],
                                                'DSCI':ds[5]},
                                               index=[0])
                children=[html.H6([date],
                                  style={'text-align': 'left'}),
                          dash_table.DataTable(
                           data=coverage_df.to_dict('rows'),
                           columns=[
                              {"name": i, "id": i} for i in coverage_df.columns],
                           style_cell={'textAlign': 'center'},
                           style_header={'fontWeight': 'bold'},
                           style_header_conditional=[
                                   {'if': {'column_id': 'D0 - D4 (Dry)'},
                                           'backgroundColor': '#ffff00',
                                           'color': 'black'},
                                   {'if': {'column_id': 'D1 - D4 (Moderate)'},
                                               'backgroundColor': '#fcd37f',
                                               'color': 'black'},
                                   {'if': {'column_id': 'D2 - D4 (Severe)'},
                                          'backgroundColor': '#ffaa00',
                                          'color': 'black'},
                                   {'if': {'column_id': 'DSCI'},
                                          'backgroundColor': '#27397F',
                                          'color': 'white',
                                          'width': '75'},
                                   {'if': {'column_id': 'D3 - D4 (Extreme)'},
                                          'backgroundColor': '#e60000',
                                          'color': 'white'},
                                   {'if': {'column_id': 'D4 (Exceptional)'},
                                           'backgroundColor': '#730000',
                                           'color': 'white'}],
                           style_data_conditional=[
                                   {'if': {'column_id': 'D0 - D4 (Dry)'},
                                           'backgroundColor': '#ffffa5',
                                           'color': 'black'},
                                   {'if': {'column_id': 'D1 - D4 (Moderate)'},
                                           'backgroundColor': '#ffe5af',
                                           'color': 'black'},
                                   {'if': {'column_id': 'D2 - D4 (Severe)'},
                                           'backgroundColor': '#ffc554',
                                           'color': 'black'},
                                   {'if': {'column_id': 'DSCI'},
                                          'backgroundColor': '#5c678e',
                                          'color': 'white',
                                          'width': '75'},
                                   {'if': {'column_id': 'D3 - D4 (Extreme)'},
                                           'backgroundColor': '#dd6666',
                                           'color': 'white'},
                                   {'if': {'column_id': 'D4 (Exceptional)'},
                                           'backgroundColor': '#a35858',
                                           'color': 'white'}])]
            except:
                raise PreventUpdate
        else:
            children = None
        return children

    @app.callback([Output('dsci_button_{}'.format(i), 'style'),
                   Output('dsci_button_{}'.format(i), 'children')],
                  [Input('submit', 'n_clicks'),
                   Input('dsci_button_{}'.format(i), 'n_clicks')],
                  [State('function_choice', 'value')])
    def displayDSCI(click1, click2, function):
        if function == 'oarea':
            if click2 % 2 == 0:
                style = {'background-color': '#a8b3c4',
                         'border-radius': '4px',
                         'font-family': 'Times New Roman'}
                children = 'Show DSCI: Off'
            else:
                style = {'background-color': '#c7d4ea',
                         'border-radius': '4px',
                         'font-family': 'Times New Roman'}
                children = 'Show DSCI: On'
        else:
            style = {'display': 'none'}
            children = 'Show DSCI: Off'

        return style, children


    @app.callback(Output('county_{}'.format(i), 'options'),  # <--------------- Dropdown label updates, old version
                  [Input('location_store', 'children')],
                  [State('county_{}'.format(i), 'value'),
                   State('key_{}'.format(i), 'children'),
                   State('click_sync', 'children')])
    def dropOne(location, previous_grid, key, sync):
        '''
        As a work around to updating synced dropdown labels and because we
        can't change the dropdown value with out creating an infinite loop, we
        are temporarily changing the options so that the value stays the same,
        but the one label to that value is the synced county name.

        Check that we are working with the right selection, and do this first
        to prevent update if not syncing
        '''

        # Check which element the selection came from
        sel_idx = location[-1]
        if 'On' not in sync:  # <---------------------------------------------- If the triggering click index doesn't match the key, prevent update
            idx = int(key) - 1
            if sel_idx not in idx + np.array([0, 2, 4, 6]):  # <--------------- [0, 4, 8] for the full panel
                raise PreventUpdate
        try:
            if type(location[0]) is int:
                current_county = location[2]
            else:
                current_county = "Multiple Counties"

            current_options = county_options.copy()
            previous_county = counties_df['place'][
                                  counties_df['grid'] == previous_grid].item()
            old_idx = options_pos[previous_county]
            current_options[old_idx]['label'] = current_county

            return current_options
        except:
            raise PreventUpdate


    @app.callback(Output("map_{}".format(i), 'figure'),
                  [Input('choice_1', 'value'),
                   Input('choice_2', 'value'),
                   Input('map_type', 'value'),
                   Input('signal', 'children'),
                   Input('location_store', 'children')],
                  [State('function_choice', 'value'),
                   State('key_{}'.format(i), 'children'),
                   State('click_sync', 'children')])
    def makeGraph(choice1, choice2, map_type, signal, location, function, key, sync):
        # Prevent update from location unless it is a state filter
        trig = dash.callback_context.triggered[0]['prop_id']
        print("Map Trigger: " + str(trig))
        if trig == 'location_store.children' and location[0] != 'state_mask':
            raise PreventUpdate

        # Check which element the selection came from
        sel_idx = location[-1]
        if 'On' not in sync:  # <---------------------------------------------- If the triggering click index doesn't match the key, prevent update
            idx = int(key) - 1
            if sel_idx not in idx + np.array([0, 2, 4, 6]):  # <--------------- [0, 4, 8] for the full panel
                raise PreventUpdate

        print("Rendering Map #{}".format(int(key)))

        # Clear memory space
        gc.collect()

        # Create signal for the global_store
        signal = json.loads(signal)

        # Collect and adjust signal
        [[year_range, month_range], colorscale, reverse_override] = signal

        # Figure which choice is this panel's and which the other
        key = int(key) - 1
        choices = [choice1, choice2]
        choice = choices[key]
        choice2 = choices[~key]

        # Get/cache data
        [array, arrays, dates, colorscale,
         dmax, dmin, reverse] = retrieve_data(signal, function, choice)

        # Individual array min/max
        amax = np.nanmax(array)
        amin = np.nanmin(array)


        # Now, we want to use the same base value range
        if function == 'pmean':
            # Get the data for the other panel for its value range
            array2 = retrieve_data(signal, function, choice2)[0]
            amax2 = np.nanmax(array2)
            amin2 = np.nanmin(array2)        
            amax = np.nanmax([amax, amax2])        
            amin = np.nanmin([amin, amin2])
        # if function == 'omean':  # <----------------------------------------- This might require a pre-made chart from probability distributions, much like strike level matching. Other theory behind comparing different index values?
        #     abmax = ranges['max'][ranges['index'] == choice]
        #     abmin = ranges['min'][ranges['index'] == choice]
        #     abmax2 = ranges['max'][ranges['index'] == choice2]
        #     abmin2 = ranges['min'][ranges['index'] == choice2]

        #Filter by state
        if location:
            if location[0] == 'state_mask':
                flag, states, label, idx = location
                if states != 'all':
                    states = json.loads(states)
                    state_mask = state_arrays.copy()
                    state_mask[~np.isin(state_mask, states)] = np.nan
                    state_mask = state_mask * 0 + 1
                else:
                    state_mask = mask
            else:
                state_mask = mask
        else:
            state_mask = mask
        array = array * state_mask

        # Check on Memory
        print("\nCPU: {}% \nMemory: {}%\n".format(psutil.cpu_percent(),
                                        psutil.virtual_memory().percent))


        # There's a lot of colorscale switching in the default settings
        if reverse_override == 'yes':
            reverse = not reverse

        # Because EDDI only extends back to 1980
        if len(arrays) == 0:
            source.data[0] = na
        else:
            source.data[0] = array * mask

        # Trying to free up space for more workers
        del array
        del arrays

        # Now all this
        dfs = xr.DataArray(source, name="data")
        pdf = dfs.to_dataframe()
        step = cd.res
        to_bin = lambda x: np.floor(x / step) * step
        pdf["latbin"] = pdf.index.get_level_values('y').map(to_bin)
        pdf["lonbin"] = pdf.index.get_level_values('x').map(to_bin)
        pdf['gridx'] = pdf['lonbin'].map(cd.londict)
        pdf['gridy'] = pdf['latbin'].map(cd.latdict)

        # For hover information
        grid2 = np.copy(cd.grid)
        grid2[np.isnan(grid2)] = 0
        pdf['grid'] = grid2[pdf['gridy'], pdf['gridx']]
        pdf = pd.merge(pdf, counties_df, how='inner')
        pdf['data'] = pdf['data'].astype(float)
        pdf['printdata'] = (pdf['place'] + ":<br>    " +
                            pdf['data'].round(3).apply(str))

        df_flat = pdf.drop_duplicates(subset=['latbin', 'lonbin'])
        df = df_flat[np.isfinite(df_flat['data'])]

        # There are several possible date ranges to display
        y1 = year_range[0]
        y2 = year_range[1]
        m1 = month_range[0]
        m2 = month_range[1]

        if y1 != y2:
            date_print = '{} - {}'.format(y1, y2)
        elif y1 == y2 and m1 != m2:
            date_print = "{} - {}, {}".format(monthmarks[m1],
                                              monthmarks[m2], y1)
        else:
            date_print = "{}, {}".format(monthmarks[m1], y1)

        # The y-axis depends on the chosen function
        if 'p' in function and 'mean' in function:
            # The maximum distance from 50
            delta = max([amax - 50, 50 - amin])
    
            # The same distance above and below 50
            amin = 50 - delta
            amax = 50 + delta

        elif 'min' in function or 'max' in function:
            amin = amin
            amax = amax

        elif 'o' in function and 'mean' in function and function != 'oarea':
            alimit = max([abs(amax), abs(amin)])
            amax = alimit
            amin = alimit * -1

        elif function == 'oarea':
            alimit = max([abs(amax), abs(amin)])
            amax = alimit
            amin = alimit * -1
            colorscale = RdWhBu

        # Create the scattermapbox object
        data = [
            dict(
                type='scattermapbox',
                lon=df['lonbin'],
                lat=df['latbin'],
                text=df['printdata'],
                mode='markers',
                hoverinfo='text',
                hovermode='closest',
                marker=dict(
                    colorscale=colorscale,
                    reversescale=reverse,
                    color=df['data'],
                    cmax=amax,
                    cmin=amin,
                    opacity=1.0,
                    size=5,
                    colorbar=dict(
                        textposition="auto",
                        orientation="h",
                        font=dict(size=15,
                                  fontweight='bold')
                    )
                )
            )]

        layout_copy = copy.deepcopy(layout)
        layout_copy['mapbox'] = dict(
            accesstoken=mapbox_access_token,
            style=map_type,
            center=dict(lon=-95.7, lat=37.1),
            zoom=2)
        layout_copy['title'] = (indexnames[choice] + '<br>' +
                                function_names[function] + ': ' +
                                date_print)

        figure = dict(data=data, layout=layout_copy)
        return figure


    @app.callback(Output('series_{}'.format(i), 'figure'),
                  [Input('submit', 'n_clicks'),
                   Input('signal', 'children'),
                   Input('choice_{}'.format(i), 'value'),
                   Input('choice_store', 'children'),
                   Input('click_sync', 'children'),
                   Input('location_store', 'children'),
                   Input('dsci_button_{}'.format(i), 'n_clicks')],
                  [State('key_{}'.format(i), 'children'),
                   State('function_choice', 'value')])
    def makeSeries(submit, signal, choice, choice_store, sync, location,
                   show_dsci, key, function):
        # Troubleshooting limited selection problem
        trig = dash.callback_context.triggered[0]['prop_id']
        print("Series Trigger: " + str(trig))

        # Check which element the selection came from
        sel_idx = location[-1]
        if 'On' not in sync:  # <---------------------------------------------- If the triggering click index doesn't match the key, prevent update (not syncing)
            idx = int(key) - 1
            if sel_idx not in idx + np.array([0, 2, 4, 6]):  # <--------------- [0, 4, 8] for the full panel
                raise PreventUpdate

        # Create signal for the global_store
        choice_store = json.loads(choice_store)
        signal = json.loads(signal)

        # Collect signals
        [[year_range, month_range], colorscale, reverse_override] = signal

        # Get/cache data
        [array, arrays, dates, colorscale,
          dmax, dmin, reverse] = retrieve_data(signal, function, choice)

        # There's a lot of color scale switching in the default settings...
        # ...so sorry any one who's trying to figure this out, I will fix this
        if reverse_override == 'yes':
            reverse = not reverse

        # If the function is oarea, we plot five overlapping timeseries
        if function != 'oarea':
            # print("LOCATION: " + str(location))
            timeseries, arrays, label = areaSeries(location, arrays, dates,
                                                    reproject=False)
            bar_type = 'bar'
        else:
            bar_type = 'overlay'
            timeseries, arrays, label = areaSeries(location, arrays,
                                                   dates, reproject=True)

            ts_series, dsci = getDroughtArea(arrays, choice)

        # Format dates
        dates = [pd.to_datetime(str(d)).strftime('%Y-%m') for d in dates]

        # The y-axis depends on the chosen function
        if 'p' in function and function != 'oarea':
            yaxis = dict(title='Percentiles',
                          range=[0, 100])
        elif 'o' in function and 'cv' not in function and function != 'oarea':
            yaxis = dict(range=[dmin, dmax],
                          title='Index')
            sd = np.nanstd(arrays)
            if 'eddi' in choice:
                sd = sd*-1
            dmin = 3*sd
            dmax = 3*sd*-1
    
        elif 'min' in function or 'max' in function:
            dmin = dmin
            dmax = dmax
        elif function == 'oarea':
            yaxis = dict(title='Percent Area (%)',
                          range=[0, 100],
                          hovermode='y')

        # Trying to free up space for more workers
        del array
        del arrays

        # Build the data dictionaries that plotly reads
        if function != 'oarea':
            data = [
                dict(
                    type='bar',
                    x=dates,
                    y=timeseries,
                    marker=dict(color=timeseries,
                                colorscale=colorscale,
                                reversescale=reverse,
                                autocolorscale=False,
                                cmin=dmin,
                                cmax=dmax,
                                line=dict(width=0.2, color="#000000")))]
        else:         
            colors = ['rgb(255, 255, 0)','rgb(252, 211, 127)',
                      'rgb(255, 170, 0)', 'rgb(230, 0, 0)', 'rgb(115, 0, 0)']
            line_width = 1 + ((1/(year_range[1] - year_range[0])) * 50)
            data = []
            for i in range(5):
                trace = dict(type='scatter', fill='tozeroy', mode='none',
                             showlegend=False, x=dates, y=ts_series[i],
                             hoverinfo='x', fillcolor=colors[i])
                data.append(trace)
            if show_dsci % 2 != 0:
                data.insert(5, dict(x=dates, y=dsci, yaxis='y2', hoverinfo='x',
                                    showlegend=False,
                                    line=dict(color='rgba(39, 57, 127, 0.85)',
                                              width=line_width)))

        # Copy and customize Layout
        layout_copy = copy.deepcopy(layout)
        layout_copy['title'] = (indexnames[choice] +
                                "<Br>" + label)
        layout_copy['plot_bgcolor'] = "white"
        layout_copy['paper_bgcolor'] = "white"
        layout_copy['height'] = 300
        layout_copy['yaxis'] = yaxis
        if function == 'oarea':
            if type(location[0]) is int:
                layout_copy['title'] = (indexnames[choice] +
                                        "<Br>" + 'Contiguous US ' +
                                        '(point estimates not available)')
            layout_copy['xaxis'] = dict(type='date')
            layout_copy['yaxis2'] = dict(title='<br>DSCI',
                                         range=[0, 500],
                                         anchor='x',
                                         overlaying='y',
                                         side='right',
                                         position=0.15,
                                         font=dict(size=8))
            layout_copy['margin'] = dict(l=55, r=55, b=25, t=90, pad=10)
        layout_copy['hovermode'] = 'x'
        layout_copy['barmode'] = bar_type
        layout_copy['legend'] = dict(orientation='h',
                                      y=-.5, markers=dict(size=10),
                                      font=dict(size=10))
        layout_copy['titlefont']['color'] = '#636363'
        layout_copy['font']['color'] = '#636363'

        figure = dict(data=data, layout=layout_copy)

        return figure

# In[] Run Application through the server
if __name__ == '__main__':
    app.run_server()
