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
from osgeo import gdal
import os
import numpy as np
import json
import scipy
from scipy.stats import rankdata
from sys import platform
import xarray as xr

# Check if windows or linux
if platform == 'win32':
    data_path = 'f:/'
#     os.chdir(os.path.join(home_path, 'Ubuntu-Practice-Machine'))
else:
    data_path = '/root/Sync'
#     os.chdir(os.path.join(home_path, 'Ubuntu-Practice-Machine'))


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

class Cacher:
    def __init__(self,key):
        self.cache={}
        self.key=key
    def memoize(self, function):
        def cacher(*args):
            # print("Cache Key: " + str(self.key))
            arg = [a for a in args]
            key = json.dumps(arg)
            if key not in self.cache.keys():
                print("Generating/replacing dataset...")
                self.cache.clear()
                gc.collect()
                self.cache[key] = function(*args)
            else:
                print("Returning existing dataset...")
            return self.cache[key]
        return cacher


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
                 'colorscale', 'reverse', 'choice', 'mask',
                 'RdWhBu', 'RdWhBu2', 'RdYlGnBu')

    # Create Initial Values
    def __init__(self, time_range=[[2000, 2017], [1, 12]],
                 colorscale='Viridis', reverse='no', choice='pdsi'): 
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
        grid = np.load(os.path.join(data_path, "data/prfgrid.npz"))["grid"]
        self.mask = grid * 0 + 1
        self.RdWhBu = [[0.00, 'rgb(115,0,0)'],
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
                       [1.00, 'rgb(5,16,110)']]
        self.RdWhBu2 = [[0.00, 'rgb(115,0,0)'],
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
                        [1.00, 'rgb(5,16,110)']]
        self.RdYlGnBu = [[0.00, 'rgb(124, 36, 36)'],
                         [0.25, 'rgb(255, 255, 48)'],
                         [0.5, 'rgb(76, 145, 33)'],
                         [0.85, 'rgb(0, 92, 221)'],
                         [1.00, 'rgb(0, 46, 110)']]


    def getOriginal(self):
        '''
        Retrieve Original Timeseries
        '''
        # Get time series of values
        array_path = os.path.join(data_path,
                                  "data/droughtindices/netcdfs/",
                                  self.choice + '.nc')
        indexlist = xr.open_dataset(array_path)

        # Get total Min and Max Values for colors
        values = indexlist.value.data
        values[values == 0] = np.nan
        limits = [abs(np.nanmin(values)), abs(np.nanmax(values))]
        dmax = max(limits)
        dmin = dmax*-1
        del values

        # filter by date
        d1 = dt.datetime(self.year1, self.month1, 1)
        d2 = dt.datetime(self.year2, self.month2, 1)
        d2 = d2 + relativedelta(months=+1) - relativedelta(days=+1)  # last day
        arrays = indexlist.sel(time=slice(d1, d2))
        del indexlist

        return [arrays, dmin, dmax]


    def getPercentile(self):
        '''
        Retrieve Percentiles of Original Timeseries
        '''
        # Get time series of values
        array_path = os.path.join(data_path,
                                  "data/droughtindices/netcdfs/percentiles",
                                  self.choice + '.nc')
        indexlist = xr.open_dataset(array_path)

        # Get total Min and Max Values for colors
        dmax = 1
        dmin = 0

        # filter by date
        d1 = dt.datetime(self.year1, self.month1, 1)
        d2 = dt.datetime(self.year2, self.month2, 1)
        d2 = d2 + relativedelta(months=+1) - relativedelta(days=+1)  # last day
        arrays = indexlist.sel(time=slice(d1, d2))
        del indexlist

        return [arrays, dmin, dmax]

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
        [arrays, dmin, dmax] = self.getOriginal()

        # Get data
        data = arrays.mean('time')
        array = data.value.data
        del data
        array[array == 0] = np.nan
        # array = array*self.mask

        # It is easier to work with these in this format
        dates = arrays.time.data
        arrays = arrays.value.data
        
        # Colors - Default is a custom style
        if self.colorscale == 'Default':
            colorscale = self.RdYlGnBu
        else:
            colorscale = self.colorscale

        if 'eddi' in self.choice:
            reverse = True
        else:
            reverse = False

        return [[array, arrays, dates], colorscale, dmax, dmin, reverse]


    def maxOriginal(self):
        '''
        Calculate max of original index values
        '''
        # Get time series of values
        [arrays, dmin, dmax] = self.getOriginal()

        # Get data
        data = arrays.max('time')
        array = data.value.data
        del data
        array[array == 0] = np.nan
        # array = array*self.mask

        # It is easier to work with these in this format
        dates = arrays.time.data
        arrays = arrays.value.data
        
        # Colors - Default is a custom style
        if self.colorscale == 'Default':
            colorscale = self.RdYlGnBu
        else:
            colorscale = self.colorscale

        if 'eddi' in self.choice:
            reverse = True
        else:
            reverse = False

        return [[array, arrays, dates], colorscale, dmax, dmin, reverse]


    def minOriginal(self):
        '''
        Calculate max of original index values
        '''
        # Get time series of values
        [arrays, dmin, dmax] = self.getOriginal()

        # Get data
        data = arrays.min('time')
        array = data.value.data
        del data
        array[array == 0] = np.nan
        # array = array*self.mask

        # It is easier to work with these in this format
        dates = arrays.time.data
        arrays = arrays.value.data
        
        # Colors - Default is a custom style
        if self.colorscale == 'Default':
            colorscale = self.RdYlGnBu
        else:
            colorscale = self.colorscale

        if 'eddi' in self.choice:
            reverse = True
        else:
            reverse = False

        return [[array, arrays, dates], colorscale, dmax, dmin, reverse]


    def meanPercentile(self):
        '''
        Calculate mean of percentiles of original index values
        '''
        # Get time series of values
        [arrays, dmin, dmax] = self.getPercentile()

        # Get data
        data = arrays.mean('time')
        array = data.value.data
        del data
        array[array == 0] = np.nan
        # array = array*self.mask
        
        # It is easier to work with these in this format
        dates = arrays.time.data
        arrays = arrays.value.data

        # Colors - Default is USDM style, sort of
        if self.colorscale == 'Default':
            colorscale = self.RdWhBu
        else:
            colorscale = self.colorscale

        if 'eddi' in self.choice:
            reverse = True
        else:
            reverse = False

        return [[array, arrays, dates], colorscale, dmax, dmin, reverse]


    def maxPercentile(self):
        '''
        Calculate mean of percentiles of original index values
        '''
        # Get time series of values
        [arrays, dmin, dmax] = self.getPercentile()

        # Get data
        data = arrays.max('time')
        array = data.value.data
        del data
        array[array == 0] = np.nan
        # array = array*self.mask
        
        # It is easier to work with these in this format
        dates = arrays.time.data
        arrays = arrays.value.data

        # Colors - Default is USDM style, sort of
        if self.colorscale == 'Default':
            colorscale = self.RdWhBu
        else:
            colorscale = self.colorscale

        if 'eddi' in self.choice:
            reverse = True
        else:
            reverse = False

        return [[array, arrays, dates], colorscale, dmax, dmin, reverse]


    def minPercentile(self):
        '''
        Calculate mean of percentiles of original index values
        '''
        # Get time series of values
        [arrays, dmin, dmax] = self.getPercentile()

        # Get data
        data = arrays.min('time')
        array = data.value.data
        del data
        array[array == 0] = np.nan
        # array = array*self.mask
        
        # It is easier to work with these in this format
        dates = arrays.time.data
        arrays = arrays.value.data

        # Colors - Default is USDM style, sort of
        if self.colorscale == 'Default':
            colorscale = self.RdWhBu
        else:
            colorscale = self.colorscale

        if 'eddi' in self.choice:
            reverse = True
        else:
            reverse = False

        return [[array, arrays, dates], colorscale, dmax, dmin, reverse]

    def coefficientVariation(self):
        '''
        Calculate mean of percentiles of original index values
        '''
        # Get time series of values
        [arrays, dmin, dmax] = self.getOriginal()

        # Get data
        numpy_arrays = arrays.value.data
        array = calculateCV(numpy_arrays)
        del numpy_arrays
        array[array == 0] = np.nan
        # array = array*self.mask
        
        # It is easier to work with these in this format
        dates = arrays.time.data
        arrays = arrays.value.data

        # Colors - Default is USDM style, sort of
        if self.colorscale == 'Default':
            colorscale = 'Portland'
        else:
            colorscale = self.colorscale

        # The colorscale will always mean the same thing
        reverse = False

        return [[array, arrays, dates], colorscale, dmax, dmin, reverse]


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

    pcts = np.apply_along_axis(percentiles, axis=0, arr=arrays)

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
