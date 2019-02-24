# -*- coding: utf-8 -*-
"""
Support functions for Ubunut-Practice-Machine
Created on Tue Jan 22 18:02:17 2019

@author: User
"""
import copy
import dash
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
import dash_core_components as dcc
import dash_html_components as html
import datetime as dt
from dateutil.relativedelta import relativedelta
import gc
import matplotlib.pyplot as plt
import numpy as np
from osgeo import gdal
import os
import json
import scipy
from scipy.stats import rankdata
import sys
import xarray as xr

# Check if windows or linux
if sys.platform == 'win32':
    data_path = 'f:/'
    sys.path.extend(['Z:/Sync/Ubuntu-Practice-Machine/',
                     'C:/Users/travi/github/Ubuntu-Practice-Machine'])
else:
    home_path = '/root/Sync'
    data_path = '/root/Sync'
    os.chdir(os.path.join(home_path, 'Ubuntu-Practice-Machine'))

grid = np.load(data_path + "/data/prfgrid.npz")["grid"]


######## Functions ############################################################
def calculateCV(indexlist):
    '''
     A single array showing the distribution of coefficients of variation
         throughout the time period represented by the chosen rasters
    '''
    # is it a named list or not?
    if type(indexlist[0]) is list:
        # Get just the arrays from this
        indexlist = [a[1] for a in indexlist]
    else:
        indexlist = indexlist

    # Adjust for outliers
    sd = np.nanstd(indexlist)
    thresholds = [-3*sd, 3*sd]
    for a in indexlist:
        a[a <= thresholds[0]] = thresholds[0]
        a[a >= thresholds[1]] = thresholds[1]

    # Standardize Range
    indexlist = standardize(indexlist)

    # Simple Cellwise calculation of variance
    sds = np.nanstd(indexlist, axis=0)
    avs = np.nanmean(indexlist, axis=0)
    covs = sds/avs

    return covs


def coordinateDictionaries(source):
    '''
    Create Coordinate index positions from xarray
    '''
    # Geometry
    x_length = source.shape[2]
    y_length = source.shape[1]
    res = source.res[0]
    lon_min = source.transform[0]
    lat_max = source.transform[3] - res

    # Make dictionaires with coordinates and array index positions
    xs = range(x_length)
    ys = range(y_length)
    lons = [lon_min + res*x for x in xs]
    lats = [lat_max - res*y for y in ys]
    londict = dict(zip(lons, xs))
    latdict = dict(zip(lats, ys))

    return londict, latdict, res

def im(array):
    '''
    This just plots an array as an image
    '''
    plt.imshow(array)

######### Classes #############################################################
class Cacher:
    def __init__(self, key):
        self.cache={}
        self.key=key
    def memoize(self, function):
        def cacher(*args):
            arg = [a for a in args]
            key = json.dumps(arg)
            if key not in self.cache.keys():
                print("Generating/replacing dataset...")
                if self.cache:
                    del self.cache[list(self.cache.keys())[0]]
                self.cache.clear()
                gc.collect()
                self.cache[key] = function(*args)
            else:
                print("Returning existing dataset...")
            return self.cache[key]
        return cacher

# Main Functions for app
class Index_Maps():
    '''
    This class creates a singular map as a function of some timeseries of
        rasters for use in the Ubuntu-Practice-Machine index comparison app.
        It also returns information needed for rendering.

        Initializing arguments:
            timerange (list)    = [[Year1, Year2], [Month1, Month2]]
            function (string)   = 'mean_perc': 'Average Percentiles',
                                  'max': 'Maxmium Percentile',
                                  'min': 'Minimum Percentile',
                                  'mean_original': 'Mean Original Values',
                                  'omax': 'Maximum Original Value',
                                  'omin': 'Minimum Original Value',
                                  'ocv': 'Coefficient of Variation - Original'
            choice (string)     = 'noaa', 'pdsi', 'pdsisc', 'pdsiz', 'spi1',
                                  'spi2', 'spi3', 'spi6', 'spei1', 'spei2',
                                  'spei3', 'spei6', 'eddi1', 'eddi2', 'eddi3',
                                  'eddi6'

        Each function returns:

            array      = Singular 2D Numpy array of function output
            arrays     = Timeseries of 2D Numpy arrays within time range
            dates      = List of Posix time stamps
            dmax       = maximum value of array
            dmin       = minimum value of array
    '''

    # Reduce memory by preallocating attribute slots
    __slots__ = ('year1', 'year2', 'month1', 'month2', 'function',
                 'colorscale', 'reverse', 'choice', 'grid', 'mask')

    # Create Initial Values
    def __init__(self, time_range=[[2000, 2017], [1, 12]],
                 colorscale='Viridis',reverse='no', choice='pdsi'): 
        self.year1 = time_range[0][0]
        self.year2 = time_range[0][1]
        if self.year1 == self.year2:
            self.month1 = time_range[1][0]
            self.month2 = time_range[1][1]
        else:
            self.month1 = 1
            self.month2 = 12
        self.colorscale = colorscale
        self.reverse = reverse
        self.choice = choice
        self.grid = np.load(os.path.join(data_path,
                                         "data/prfgrid.npz"))["grid"]
        self.mask = self.grid * 0 + 1

    def setColor(self, default='percentile'):
        '''
        This is tricky because the color can be a string pointing to
        a predefined plotly color scale, or an actual color scale, which is
        a list.        
        '''
        options = {'Blackbody': 'Blackbody', 'Bluered': 'Bluered',
                   'Blues': 'Blues', 'Default': 'Default', 'Earth': 'Earth',
                   'Electric': 'Electric', 'Greens': 'Greens',
                   'Greys': 'Greys', 'Hot': 'Hot', 'Jet': 'Jet',
                   'Picnic': 'Picnic', 'Portland': 'Portland',
                   'Rainbow': 'Rainbow', 'RdBu': 'RdBu',  'Viridis': 'Viridis',
                   'Reds': 'Reds', 
                   'RdWhBu': [[0.00, 'rgb(115,0,0)'],
                              [0.10, 'rgb(230,0,0)'],
                              [0.20, 'rgb(255,170,0)'],
                              [0.30, 'rgb(252,211,127)'],
                              [0.40, 'rgb(255, 255, 0)'],
                              [0.45, 'rgb(255, 255, 255)'],
                              [0.55, 'rgb(255, 255, 255)'],
                              [0.60, 'rgb(143, 238, 252)'],
                              [0.70, 'rgb(12,164,235)'],
                              [0.80, 'rgb(0,125,255)'],
                              [0.90, 'rgb(10,55,166)'],
                              [1.00, 'rgb(5,16,110)']],
                   'RdWhBu (NOAA PSD Scale)':  [[0.00, 'rgb(115,0,0)'],
                                                [0.02, 'rgb(230,0,0)'],
                                                [0.05, 'rgb(255,170,0)'],
                                                [0.10, 'rgb(252,211,127)'],
                                                [0.20, 'rgb(255, 255, 0)'],
                                                [0.30, 'rgb(255, 255, 255)'],
                                                [0.70, 'rgb(255, 255, 255)'],
                                                [0.80, 'rgb(143, 238, 252)'],
                                                [0.90, 'rgb(12,164,235)'],
                                                [0.95, 'rgb(0,125,255)'],
                                                [0.98, 'rgb(10,55,166)'],
                                                [1.00, 'rgb(5,16,110)']],
                   'RdYlGnBu':  [[0.00, 'rgb(124, 36, 36)'],
                                  [0.25, 'rgb(255, 255, 48)'],
                                  [0.5, 'rgb(76, 145, 33)'],
                                  [0.85, 'rgb(0, 92, 221)'],
                                   [1.00, 'rgb(0, 46, 110)']],                   
                   'BrGn':  [[0.00, 'rgb(91, 74, 35)'],  #darkest brown
                             [0.10, 'rgb(122, 99, 47)'], # almost darkest brown
                             [0.15, 'rgb(155, 129, 69)'], # medium brown 
                             [0.25, 'rgb(178, 150, 87)'],  # almost meduim brown
                             [0.30, 'rgb(223,193,124)'],  # light brown
                             [0.40, 'rgb(237, 208, 142)'],  #lighter brown
                             [0.45, 'rgb(245,245,245)'],  # white
                             [0.55, 'rgb(245,245,245)'],  # white
                             [0.60, 'rgb(198,234,229)'],  #lighter green
                             [0.70, 'rgb(127,204,192)'],  # light green
                             [0.75, 'rgb(62, 165, 157)'],  # almost medium green
                             [0.85, 'rgb(52,150,142)'],  # medium green
                             [0.90, 'rgb(1,102,94)'],  # almost darkest green
                             [1.00, 'rgb(0, 73, 68)']], # darkest green
                   }

        if self.colorscale == 'Default':
            if default == 'percentile':
                scale = options['RdWhBu']
            elif default == 'original':
                scale = options['BrGn']
            elif default == 'cv':
                scale = options['Portland'] 
        else:
            scale = options[self.colorscale]
        return scale

    def getData(self, array_path):
        '''
        The challenge is to read as little as possible into memory without
        slowing the app down.
        '''        
        # Get time series of values
        # filter by date and location
        d1 = dt.datetime(self.year1, self.month1, 1)
        d2 = dt.datetime(self.year2, self.month2, 1)
        d2 = d2 + relativedelta(months=+1) - relativedelta(days=+1)  # last day
        
        with xr.open_dataset(array_path) as data:
            limits = [abs(np.nanmin(data.value.data)),
                      abs(np.nanmax(data.value.data))]
            dmax = max(limits)  # Makes an even graph
            dmin = dmax*-1
            data = data.sel(time=slice(d1, d2)) * self.mask
            indexlist = data
            del data

        return [indexlist, dmax, dmin]
        
    def getOriginal(self):
        '''
        Retrieve Original Timeseries
        '''
        array_path = os.path.join(data_path,
                                  "data/droughtindices/netcdfs/",
                                  self.choice + '.nc')
        indexlist, dmin, dmax = self.getData(array_path)
        gc.collect()
        return [indexlist, dmin, dmax]

    def getPercentile(self):
        '''
        Retrieve Percentiles of Original Timeseries
        '''
        array_path = os.path.join(data_path,
                                  "data/droughtindices/netcdfs/percentiles",
                                  self.choice + '.nc')
        indexlist, dmin, dmax = self.getData(array_path)
        indexlist = indexlist * 100
        gc.collect()
        return [indexlist, dmin, dmax]

    def getAlbers(self):
        '''
        Retrieve Percentiles of Original Timeseries in North American
        Albers Equal Area Conic.
        '''
        array_path = os.path.join(data_path,
                                  "data/droughtindices/netcdfs/albers",
                                  self.choice + '.nc')
        indexlist, dmin, dmax = self.getData(array_path)
        gc.collect()
        return [indexlist, dmin, dmax]

    def calculateCV(indexlist):
        '''
         A single array showing the distribution of coefficients of variation
             throughout the time period represented by the chosen rasters
        '''
        # is it a named list or not?
        if type(indexlist[0]) is list:
            # Get just the arrays from this
            indexlist = [a[1] for a in indexlist]
        else:
            indexlist = indexlist
    
        # Adjust for outliers
        sd = np.nanstd(indexlist)
        thresholds = [-3*sd, 3*sd]
        for a in indexlist:
            a[a <= thresholds[0]] = thresholds[0]
            a[a >= thresholds[1]] = thresholds[1]
    
        # Standardize Range
        indexlist = standardize(indexlist)
    
        # Simple Cellwise calculation of variance
        sds = np.nanstd(indexlist, axis=0)
        avs = np.nanmean(indexlist, axis=0)
        covs = sds/avs
    
        return covs
    
    def meanOriginal(self):
        '''
        Calculate mean of original index values
        '''
        # Get time series of values
        [indexlist, dmin, dmax] = self.getOriginal()

        # Get data
        array = indexlist.mean('time').value.data
        arrays = indexlist.value.data
        dates = indexlist.time.data
        del indexlist
        
        # Get color scale        
        colorscale = self.setColor(default='original')

        # EDDI has a reversed scale
        if 'eddi' in self.choice:
            reverse = True
        else:
            reverse = False

        return [array, arrays, dates, colorscale, dmax, dmin, reverse]

    def maxOriginal(self):
        '''
        Calculate max of original index values
        '''
        # Get time series of values
        [indexlist, dmin, dmax] = self.getOriginal()

        # Get data
        array = indexlist.max('time').value.data
        arrays = indexlist.value.data
        dates = indexlist.time.data
        del indexlist
        
        # Get color scale        
        colorscale = self.setColor(default='original')

        # EDDI has a reversed scale
        if 'eddi' in self.choice:
            reverse = True
        else:
            reverse = False

        return [array, arrays, dates, colorscale, dmax, dmin, reverse]


    def minOriginal(self):
        '''
        Calculate max of original index values
        '''
        # Get time series of values
        [indexlist, dmin, dmax] = self.getOriginal()

        # Get data
        array = indexlist.min('time').value.data
        arrays = indexlist.value.data
        dates = indexlist.time.data
        del indexlist
        
        # Get color scale        
        colorscale = self.setColor(default='original')

        # EDDI has a reversed scale
        if 'eddi' in self.choice:
            reverse = True
        else:
            reverse = False
        return [array, arrays, dates, colorscale, dmax, dmin, reverse]


    def meanPercentile(self):
        '''
        Calculate mean of percentiles of original index values
        '''
        # Get time series of values
        [indexlist, dmin, dmax] = self.getPercentile()

        # Get data
        array = indexlist.mean('time').value.data
        arrays = indexlist.value.data 
        dates = indexlist.time.data
        del indexlist
        
        # Get color scale        
        colorscale = self.setColor(default='percentile')

        # EDDI has a reversed scale
        if 'eddi' in self.choice:
            reverse = True
        else:
            reverse = False
        return [array, arrays, dates, colorscale, dmax, dmin, reverse]


    def maxPercentile(self):
        '''
        Calculate mean of percentiles of original index values
        '''
         # Get time series of values
        [indexlist, dmin, dmax] = self.getPercentile()

        # Get data
        array = indexlist.max('time').value.data
        arrays = indexlist.value.data
        dates = indexlist.time.data
        del indexlist
        
        # Get color scale        
        colorscale = self.setColor(default='percentile')

        # EDDI has a reversed scale
        if 'eddi' in self.choice:
            reverse = True
        else:
            reverse = False

        return [array, arrays, dates, colorscale, dmax, dmin, reverse]


    def minPercentile(self):
        '''
        Calculate mean of percentiles of original index values
        '''
         # Get time series of values
        [indexlist, dmin, dmax] = self.getPercentile()

        # Get data
        array = indexlist.max('time').value.data
        arrays = indexlist.value.data
        dates = indexlist.time.data
        del indexlist
        
        # Get color scale        
        colorscale = self.setColor(default='percentile')

        # EDDI has a reversed scale
        if 'eddi' in self.choice:
            reverse = True
        else:
            reverse = False

        return [array, arrays, dates, colorscale, dmax, dmin, reverse]

    def coefficientVariation(self):
        '''
        Calculate mean of percentiles of original index values
        '''
        # Get time series of values
        [indexlist, dmin, dmax] = self.getOriginal()

        # Get data
        array = calculateCV(arrays)
        arrays = indexlist.value.data
        dates = indexlist.time.data
        del indexlist

        # Get color scale        
        colorscale = self.setColor(default='cv')

        # The colorscale will always mean the same thing
        reverse = False

        return [array, arrays, dates, colorscale, dmax, dmin, reverse]


################################## new function ###########################################################
    def droughtArea(self, inclusive=False):
        '''
        This will take in a time series of arrays and a drought severity category
        and mask out all cells with values above or below the category thresholds.
        If inclusive is 'True' it will only mask out all cells that fall above the
        chosen category.

        For now this requires percentiles.
        '''

        # arrays = self.getAlbersPercentile()  # Don't have albers percentiles just yet
        indexlist, dmin, dmax = self.getPercentile()
        arrays = indexlist.value.data

        # Just use the average value map for now
        data = indexlist.mean('time')
        array = data.value.data
        del data

        # Drought Categories
        drought_cats = {0: [.20, .30], 1: [.10, .20], 2: [.05, .10],
                        3: [.02, .05], 4: [.00, .02]}

        # Total number of pixels
        total_area = np.nansum(self.mask)

        # We want an ndarray for each category, too
        dm_arrays = {}

        # We want a map for each drought category?
        for i in range(5):
            d = drought_cats[i]
            a = arrays.copy()

            # Filter above or below thresholds
            if inclusive is False:
                a[(a < d[0]) | (a > d[1])] = np.nan
            else:
                a[a > d[1]] = np.nan

            dm_arrays[i] = a

        # Below will have to be outside after the area is filtered
        # a1 = a[0]
        # im(a1)
        #
        # # get percent of land 'area' in drought
        # a2 = a1 * 0 + 1
        # drought_area = np.nansum(a2)
        # percent = round(100 * (drought_area / total_area), 4)
        #
        # print('DM ' + str(i)  + ': %' + str(percent))

        del arrays

        # It is easier to work with these in this format
        dates = indexlist.time.data

        # Get color scale
        colorscale = self.setColor(default='percentile')

        # The colorscale will always mean the same thing
        reverse = False

        # Return a list of five layers, the signal might need to be adjusted
        # for inclusive
        return [array, dm_arrays, dates, colorscale, dmax, dmin, reverse]


#########################################################################
def makeMap(maps, function):
    '''
    To choose which function to return from Index_Maps
    '''
    gc.collect()
    if function == "omean":
        data = maps.meanOriginal()
    if function == "omax":
        data = maps.maxOriginal()
    if function == "omin":
        data = maps.minOriginal()
    if function == "pmean":
        data = maps.meanPercentile()
    if function == "pmax":
        data = maps.maxPercentile()
    if function == "pmin":
        data = maps.minPercentile()
    if function == "ocv":
        data = maps.coefficientVariation()
    if function == "parea":
        data = maps.droughtArea()  # This will require some extra doing...
    return data




###########################################################################################################

def percentileArrays(arrays):
    '''
    a list of 2d numpy arrays or a 3d numpy array
    '''
    def percentiles(lst):
        '''
        lst = single time series of numbers as a list
        '''
        import scipy.stats
        scipy.stats.moment(lst, 1)

        pct = rankdata(lst)/len(lst)
        return pct

    mask = arrays[0] * 0 + 1
    pcts = np.apply_along_axis(percentiles, axis=0, arr=arrays)
    pcts = pcts*mask
    return pcts


def readRaster(rasterpath, band, navalue=-9999):
    """
    rasterpath = path to folder containing a series of rasters
    navalue = a number (float) for nan values if we forgot 
                to translate the file with one originally

    This converts a raster into a numpy array along with spatial features
    needed to write any results to a raster file. The return order is:
                
      array (numpy), spatial geometry (gdal object),
                                      coordinate reference system (gdal object)
    """
    raster = gdal.Open(rasterpath)
    geometry = raster.GetGeoTransform()
    arrayref = raster.GetProjection()
    array = np.array(raster.GetRasterBand(band).ReadAsArray())
    del raster
    array = array.astype(float)
    if np.nanmin(array) < navalue:
        navalue = np.nanmin(array)
    array[array==navalue] = np.nan
    return(array, geometry, arrayref)

def standardize(indexlist):
    '''
    Min/max standardization
    '''    
    def single(array, mins, maxes):
        newarray = (array - mins)/(maxes - mins)
        return(newarray)

    if type(indexlist[0][0]) == str:
        arrays = [a[1] for a in indexlist]
        mins = np.nanmin(arrays)
        maxes = np.nanmax(arrays)
        standardizedlist = [[indexlist[i][0],
                             single(indexlist[i][1],
                                    mins,
                                    maxes)] for i in range(len(indexlist))]

    else:
        mins = np.nanmin(indexlist)
        maxes = np.nanmax(indexlist)
        standardizedlist = [single(indexlist[i],
                                   mins, maxes) for i in range(len(indexlist))]
    return(standardizedlist)



# For making outlines...move to css, maybe
def outLine(color, width):
    string = ('-{1}px -{1}px 0 {0}, {1}px -{1}px 0 {0}, ' +
              '-{1}px {1}px 0 {0}, {1}px {1}px 0 {0}').format(color, width)
    return string
