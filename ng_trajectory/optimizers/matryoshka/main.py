#!/usr/bin/env python3.6
# main.py
"""Interface for Matryoshka mapping."""
######################
# Imports & Globals
######################

from ng_trajectory.interpolators.utils import *
import ng_trajectory.plot as ngplot

from ng_trajectory.segmentators.utils import gridCompute

from . import transform

import nevergrad

import sys, os

# Parallel computing of genetic algorithm
from concurrent import futures

# Thread lock for log file
from threading import Lock

# Typing
from typing import Tuple, Callable, Dict, TextIO, List, types


# Global variables
OPTIMIZER = None
MATRYOSHKA = None
VALID_POINTS = None
CRITERION = None
CRITERION_ARGS = None
INTERPOLATOR = None
INTERPOLATOR_ARGS = None
SEGMENTATOR = None
SEGMENTATOR_ARGS = None
SELECTOR = None
SELECTOR_ARGS = None
PENALIZER = None
PENALIZER_INIT = None
PENALIZER_ARGS = None
LOGFILE = None
VERBOSITY = 3
FILELOCK = Lock()
HOLDMAP = None
GRID = None
PENALTY = None
FIGURE = None
PLOT = None


# Parameters
from ng_trajectory.parameter import *
P = ParameterList()
P.createAdd("budget", 100, int, "Budget parameter for the genetic algorithm.", "init (general)")
P.createAdd("groups", 8, int, "Number of groups to segmentate the track into.", "init (general)")
P.createAdd("workers", "os.cpu_count()", int, "Number threads for the genetic algorithm.", "init (general)")
P.createAdd("penalty", 100, float, "Constant used for increasing the penalty criterion.", "init (general)")
P.createAdd("criterion", None, types.ModuleType, "Module to evaluate current criterion.", "init (general)")
P.createAdd("criterion_args", {}, dict, "Arguments for the criterion function.", "init (general)")
P.createAdd("interpolator", None, types.ModuleType, "Module to interpolate points.", "init (general)")
P.createAdd("interpolator_args", {}, dict, "Arguments for the interpolator function.", "init (general)")
P.createAdd("segmentator", None, types.ModuleType, "Module to segmentate track.", "init (general)")
P.createAdd("segmentator_args", {}, dict, "Arguments for the segmentator function.", "init (general)")
P.createAdd("selector", None, types.ModuleType, "Module to select path points as segment centers.", "init (general)")
P.createAdd("selector_args", {}, dict, "Arguments for the selector function.", "init (general)")
P.createAdd("penalizer", None, types.ModuleType, "Module to evaluate penalty criterion.", "init (general)")
P.createAdd("penalizer_init", {}, dict, "Arguments for the init part of the penalizer function.", "init (general)")
P.createAdd("penalizer_args", {}, dict, "Arguments for the penalizer function.", "init (general)")
P.createAdd("logging_verbosity", 2, int, "Index for verbosity of the logger.", "init (general)")
P.createAdd("hold_matryoshka", False, bool, "Whether the transformation should be created only once.", "init (Matryoshka)")
P.createAdd("plot", False, bool, "Whether a graphical representation should be created.", "init (viz.)")
P.createAdd("grid", "computed by default", list, "X-size and y-size of the grid used for points discretization.", "init (Matryoshka)")
P.createAdd("plot_mapping", False, bool, "Whether a grid should be mapped onto the track (to show the mapping).", "init (viz.)")


######################
# Functions
######################

def init(points: numpy.ndarray, group_centers: numpy.ndarray, group_centerline: numpy.ndarray, \
        budget: int = 100,
        layers: int = 5,
        groups: int = 8,
        workers: int = os.cpu_count(),
        penalty: float = 100,
        criterion: types.ModuleType = None,
        criterion_args: Dict[str, any] = {},
        interpolator: types.ModuleType = None,
        interpolator_args: Dict[str, any] = {},
        segmentator: types.ModuleType = None,
        segmentator_args: Dict[str, any] = {},
        selector: types.ModuleType = None,
        selector_args: Dict[str, any] = {},
        penalizer: types.ModuleType = None,
        penalizer_init: Dict[str, any] = {},
        penalizer_args: Dict[str, any] = {},
        logfile: TextIO = sys.stdout,
        logging_verbosity: int = 2,
        hold_matryoshka: bool = False,
        plot: bool = False,
        grid: List[float] = [],
        figure: ngplot.matplotlib.figure.Figure = None,
        **kwargs):
    """Initialize variables for Matryoshka transformation.

    Arguments:
    points -- valid area of the track, nx2 numpy.ndarray
    group_centers -- points for centers of individual groups, mx2 numpy.ndarray
    group_centerline -- line where the group centers lie, px2 numpy.ndarray
    budget -- number of generations of genetic algorithm, int, default 100
    layers -- number of layers for each Matryoshka, int, default 5
    groups -- number of groups to segmentate the track into, int, default 8
    workers -- number of threads for GA, int, default 4
    penalty -- constant used for increasing the penalty criterion, float, default 100
    criterion -- module to evaluate current criterion,
                 module with compute callable (mx2 numpy.ndarray -> float),
                 default None
    criterion_args -- arguments for the criterion function, dict, default {}
    interpolator -- module to interpolate points,
                    module with interpolate callable (mx2 numpy.ndarray -> qx2 numpy.ndarray),
                    default None
    interpolator_args -- arguments for the interpolation function, dict, default {}
    segmentator -- module to segmentate points,
                   module with segmentate callable (nx2 numpy.ndarray -> m-list of rx2 numpy.ndarray),
                   default None
    segmentator_args -- arguments for the segmentation function, dict, default {}
    selector -- module to select points as group centers,
                module with select callable (nx2 numpy.ndarray + m -> m-list of rx2 numpy.ndarray),
                default None
    selector_args -- arguments for the selector function, dict, default {}
    penalizer -- module to evaluate penalty criterion,
                 module with penalize callable (nx(>=2) numpy.ndarray + mx2 numpy.ndarray -> float),
                 default None
    penalizer_init -- arguments for the init part of the penalizer function, dict, default {}
    penalizer_args -- arguments for the penalizer function, dict, default {}
    logfile -- file descriptor for logging, TextIO, default sys.stdout
    logging_verbosity -- index for verbosity of logger, int, default 2
    hold_matryoshka -- whether the Matryoshka should be created only once, bool, default False
    plot -- whether a graphical representation should be created, bool, default False
    grid -- size of the grid used for the points discretization, 2-float List, computed by default
    figure -- target figure for plotting, matplotlib.figure.Figure, default None (get current)
    **kwargs -- arguments not caught by previous parts
    """
    global OPTIMIZER, MATRYOSHKA, VALID_POINTS, LOGFILE, VERBOSITY, HOLDMAP, GRID, PENALTY, FIGURE, PLOT
    global CRITERION, CRITERION_ARGS, INTERPOLATOR, INTERPOLATOR_ARGS, SEGMENTATOR, SEGMENTATOR_ARGS, SELECTOR, SELECTOR_ARGS, PENALIZER, PENALIZER_INIT, PENALIZER_ARGS

    # Local to global variables
    CRITERION = criterion
    CRITERION_ARGS = criterion_args
    INTERPOLATOR = interpolator
    INTERPOLATOR_ARGS = interpolator_args
    SEGMENTATOR = segmentator
    SEGMENTATOR_ARGS = segmentator_args
    SELECTOR = selector
    SELECTOR_ARGS = selector_args
    PENALIZER = penalizer
    PENALIZER_INIT = penalizer_init
    PENALIZER_ARGS = penalizer_args
    LOGFILE = logfile
    VERBOSITY = logging_verbosity
    _holdmatryoshka = hold_matryoshka
    PENALTY = penalty
    FIGURE = figure
    PLOT = plot


    VALID_POINTS = points

    if MATRYOSHKA is None or not _holdmatryoshka:
        # Note: In version <=1.3.0 the group_centerline passed to the SELECTOR was sorted using
        #       ng_trajectory.interpolators.utils.trajectorySort, but it sometimes rotated the
        #       already sorted centerline; interestingly, the result was counterclockwise at all
        #       times (or at least very very often).
        group_centers = SELECTOR.select(**{**{"points": group_centerline, "remain": groups}, **SELECTOR_ARGS})

        if plot:
            ngplot.indicesPlot(group_centers)

        # Matryoshka construction
        _groups = SEGMENTATOR.segmentate(points=points, group_centers=group_centers, **{**SEGMENTATOR_ARGS})

        # Call the init function of penalizer
        PENALIZER.init(
            valid_points = VALID_POINTS,
            start_points = group_centerline,
            map = SEGMENTATOR.main.MAP,
            map_origin = SEGMENTATOR.main.MAP_ORIGIN,
            map_grid = SEGMENTATOR.main.MAP_GRID,
            map_last = SEGMENTATOR.main.MAP_LAST,
            group_centers = group_centers,
            **{
                **{
                    key: value for key, value in kwargs.items() if key not in [
                        "valid_points", "start_points", "map", "map_origin", "map_grid", "map_last", "group_centers"
                    ]
                },
                **PENALIZER_INIT
            }
        )

        grouplayers = transform.groupsBorderObtain(_groups)
        grouplayers = transform.groupsBorderBeautify(grouplayers, 400)

        if plot:
            ngplot.bordersPlot(grouplayers, figure)

        layers_center = transform.groupsCenterCompute(_groups)
        layers_count = [ layers for i in range(len(grouplayers)) ]


        MATRYOSHKA = [ transform.matryoshkaCreate(grouplayers[_i], layers_center[_i], layers_count[_i]) for _i in range(len(_groups)) ]

        if plot and P.getValue("plot_mapping"):
            xx, yy = numpy.meshgrid(numpy.linspace(0, 1, 110), numpy.linspace(0, 1, 110))
            gridpoints = numpy.hstack((xx.flatten()[:, numpy.newaxis], yy.flatten()[:, numpy.newaxis]))

            for _g in range(len(_groups)):
                ngplot.pointsScatter(transform.matryoshkaMap(MATRYOSHKA[_g], gridpoints), marker="x", s=0.1)

        print ("Matryoshka mapping constructed.")

        if GRID is None:
            if len(grid) == 2:
                GRID = grid
            else:
                _GRID = gridCompute(points)
                GRID = [ _GRID, _GRID ]


    # Optimizer definition
    instrum = nevergrad.Instrumentation(nevergrad.var.Array(len(MATRYOSHKA), 2).bounded(0, 1))
    OPTIMIZER = nevergrad.optimizers.DoubleFastGADiscreteOnePlusOne(instrumentation = instrum, budget = budget, num_workers = workers)


def optimize() -> Tuple[float, numpy.ndarray, numpy.ndarray, numpy.ndarray]:
    """Run genetic algorithm via Nevergrad.

    Returns:
    final -- best value of the criterion, float
    points -- points in the best solution in real coordinates, nx2 numpy.ndarray
    tcpoints -- points in the best solution in transformed coordinates, nx2 numpy.ndarray
    trajectory -- trajectory of the best solution in real coordinates, mx2 numpy.ndarray
    """
    global OPTIMIZER, MATRYOSHKA, LOGFILE, FILELOCK, VERBOSITY, INTERPOLATOR, INTERPOLATOR_ARGS, FIGURE, PLOT, PENALIZER, PENALIZER_ARGS

    with futures.ProcessPoolExecutor(max_workers=OPTIMIZER.num_workers) as executor:
        recommendation = OPTIMIZER.minimize(_opt, executor=executor, batch_mode=False)

    points = [ transform.matryoshkaMap(MATRYOSHKA[i], [p])[0] for i, p in enumerate(numpy.asarray(recommendation.args[0])) ]

    PENALIZER_ARGS["optimization"] = False
    final = _opt(numpy.asarray(recommendation.args[0]))


    ## Plot invalid points if available

    # Interpolate received points
    # It is expected that they are unique and sorted.
    _points = INTERPOLATOR.interpolate(**{**{"points": numpy.asarray(points)}, **INTERPOLATOR_ARGS})

    # Display invalid points if found
    if PLOT and len(PENALIZER.INVALID_POINTS) > 0:
        ngplot.pointsScatter(numpy.asarray(PENALIZER.INVALID_POINTS), FIGURE, color="red", marker="x")


    ##

    with FILELOCK:
        if VERBOSITY > 0:
            print ("solution:%s" % str(numpy.asarray(points).tolist()), file=LOGFILE)
            print ("final:%f" % final, file=LOGFILE)

    return final, numpy.asarray(points), numpy.asarray(recommendation.args[0]), INTERPOLATOR.interpolate(**{**{"points": numpy.asarray(points)}, **INTERPOLATOR_ARGS})


def _opt(points: numpy.ndarray) -> float:
    """Interpolate points, verify feasibility and calculate criterion.

    Function to be optimized.

    Arguments:
    points -- selected points to interpolate, nx2 numpy.ndarray

    Returns:
    _c -- criterion value, float

    Note: It receives selected points from the groups (see callback_centerline).

    Note: The result of this function is 'criterion' when possible, otherwise
    number of invalid points (multiplied by some value) is returned.

    Note: This function is called after all necessary data is received.
    """
    global VALID_POINTS, CRITERION, CRITERION_ARGS, INTERPOLATOR, INTERPOLATOR_ARGS, PENALIZER, PENALIZER_ARGS
    global MATRYOSHKA, LOGFILE, FILELOCK, VERBOSITY, GRID, PENALTY

    # Transform points
    points = [ transform.matryoshkaMap(MATRYOSHKA[i], [p])[0] for i, p in enumerate(points) ]

    # Interpolate received points
    # It is expected that they are unique and sorted.
    _points = INTERPOLATOR.interpolate(**{**{"points": numpy.asarray(points)}, **INTERPOLATOR_ARGS})

    # Check the correctness of the points and compute penalty
    penalty = PENALIZER.penalize(**{**{"points": _points, "valid_points": VALID_POINTS, "grid": GRID, "penalty": PENALTY, "candidate": points}, **PENALIZER_ARGS})

    if ( penalty != 0 ):
        with FILELOCK:
            if VERBOSITY > 2:
                print ("pointsA:%s" % str(points), file=LOGFILE)
                print ("pointsT:%s" % str(_points.tolist()), file=LOGFILE)
            if VERBOSITY > 1:
                print ("penalty:%f" % penalty, file=LOGFILE)
            LOGFILE.flush()
        return penalty

    _c = CRITERION.compute(**{**{'points': _points}, **CRITERION_ARGS})
    with FILELOCK:
        if VERBOSITY > 2:
            print ("pointsA:%s" % str(points), file=LOGFILE)
            print ("pointsT:%s" % str(_points.tolist()), file=LOGFILE)
        if VERBOSITY > 1:
            print ("correct:%f" % _c, file=LOGFILE)
        LOGFILE.flush()

    return _c
