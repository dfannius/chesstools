# TODO
# + Graph USCF rating as well
# + cur_tag should really be a stack
# + Refactor TournamentResultsParser and YearResultsParser
# + Cache rating information
# + Put files in a separate directory
# + Print name
# + Print date marks on x axis
# + Put name in png files
# - Reread pickled data when outdated
#   + Read pickled data
#   + Read game page starting from last year in pickled data
#   + If there are new games:
#     + Reread tournament pages until we have gotten all new xtbls
#     + Repickle
# + Mode that takes a single tournament's stats on the command and returns a perf rating
# + Combine parse_results and parse_new_results
# + Argument for initial year to graph
# - Why does the graph end just before the right edge?
# - Option to not read more data
# - Stop reading new tnmt_results the instant we see an old xtbl?
# - Use sets rather than lists to check for new results
# - Legend
# - Window size as command-line parameter?

import argparse
import pickle
import datetime
import math
import matplotlib.pyplot as plt
import numpy as np
import os
import re
import requests
import sys
from html.parser import HTMLParser
from operator import attrgetter

plt.style.use("seaborn")

tournament_rating_re = re.compile( r"=>" )
rating_re = re.compile( r"=>\s+(\d+)", re.MULTILINE )
xtbl_re = re.compile( r"XtblMain.php\?([\d]+)" )
tnmt_hst_re = re.compile( r"MbrDtlTnmtHst.php\?[\d]+\.[\d]+" )
name_re = re.compile( "<b>\d+: ([^<]+)" )

# Map from web page result code to number of points
result_to_value = { "L": 0.0, "S": 0.0,
                    "D": 0.5, "R": 0.5,
                    "W": 1.0, "N": 1.0  }

# The first year we don't need to look for results from
NEXT_YEAR = datetime.datetime.now().year + 1

# I'm rated d points above the other player; what's my EV?
def rating_diff_to_expected_value( d ):
    return 1.0 / (1.0 + pow( 10.0, -d / 400.0 ))

# What's my total expected value if I have a given rating and will be
# facing opponents with the given opponent ratings?
def expected_value_total( rating, opp_ratings ):
    return sum( rating_diff_to_expected_value( rating - r ) for r in opp_ratings )

# Like expected_value_total() but with each game weighted by a value in
# `weights`
def expected_value_total_weighted( rating, opp_ratings, weights ):
    return sum( weights[i] * rating_diff_to_expected_value( rating - r )
                for (i,r) in enumerate( opp_ratings ) )

# What rating would result in a total score of `score` against
# opponents rated by `opp_ratings`, where the corresponding games are
# weighted by `weights`?
def accurate_perf_rating_raw_weighted( opp_ratings, score, weights ):
    if score == 0:
        return min( opp_ratings ) - 400
    elif score == len( opp_ratings ):
        return max( opp_ratings ) + 400
    
    # Start by guessing our rating is the average of our opponents'
    test_rating = sum( opp_ratings ) / len( opp_ratings )
    iterations = 0
    
    # Use Newton's method
    while iterations < 50:
        eps = 1
        test_score = expected_value_total_weighted( test_rating, opp_ratings, weights )
        if abs( test_score - score ) < 0.001:
            break
        test_score_2 = expected_value_total_weighted( test_rating+eps, opp_ratings, weights )
        slope = float( test_score_2 - test_score ) / eps
        test_rating -= (test_score - score) / slope
        iterations += 1
        
    return test_rating

# Same but each game is of equal weight
def accurate_perf_rating_raw( opp_ratings, score ):
    return accurate_perf_rating_raw_weighted( opp_ratings, score, [1 for x in opp_ratings] )

# What rating would I have to have so that the total number of points
# scored in results is exactly what was expected?
def accurate_perf_rating( results ):
    actual_total = sum( result_to_value[ r.result ] for r in results )
    opp_ratings = [ r.opp_rating for r in results ]
    return accurate_perf_rating_raw( opp_ratings, actual_total )

# Same but the scores are to be weighted by `weights`
def accurate_perf_rating_weighted( results, weights ):
    actual_total = sum( weights[i] * result_to_value[ r.result ]
                        for (i,r) in enumerate( results ) )
    opp_ratings = [ r.opp_rating for r in results ]
    return accurate_perf_rating_raw_weighted( opp_ratings, actual_total, weights )

def xtbl_to_str( xtbl ):
    return "%s-%s-%s" % (xtbl[0:4], xtbl[4:6], xtbl[6:8] )

# A single tournament
class TournamentResult():
    def __init__( self, xtbl, rating ):
        self.xtbl = xtbl        # URL of the crosstable
        self.rating = rating    # Rating after the tournament
    def __eq__( self, rhs ):
        return self.xtbl == rhs.xtbl
    def __repr__( self ):
        return "%s %d" % (self.xtbl, self.rating)
    def year( self ):
        return int( self.xtbl[0:4] )

# A single game
class Result():
    def __init__( self, opp_rating, result, xtbl, rd ):
        self.opp_rating = opp_rating # Opponent rating
        self.result = result         # Code for result (see result_to_value)
        self.xtbl = xtbl             # URL of crosstable
        self.rd = rd                 # Round number
    def __eq__( self, rhs ):
        return self.xtbl == rhs.xtbl and self.rd == rhs.rd
    def __repr__( self ):
        return "%d %s (%s:%d)" % (self.opp_rating, self.result, self.xtbl, self.rd)
    # Naive "performance rating" for this single game
    def val( self ):
        return self.opp_rating + (result_to_value[ self.result ] - 0.5) * 800
    def year( self ):
        return int( self.xtbl[0:4] )

# Returns the value associated with `key` in a list of (key, value) tuples,
# or None
def alist_find( alist, key ):
    for (k,v) in alist:
        if k == key: return v
    return None

# Base class to automatically keep track of some stuff
class TableParser( HTMLParser ):
    def __init__( self ):
        HTMLParser.__init__( self )
        self.tag_stack = []     # What tags are we nested in
        self.cur_col = 0        # Column of current table
        self.in_td = 0          # Are we in a <td> tag

    def handle_starttag( self, tag, attrs ):
        self.tag_stack.append( tag )
        if tag == "tr":
            self.cur_col = -1
        if tag == "td":
            self.cur_col += 1
            self.in_td += 1

    def handle_endtag( self, tag ):
        self.tag_stack = self.tag_stack[:-1]
        if tag == "td":
            self.in_td -= 1

    def cur_tag( self ):
        if len( self.tag_stack ) == 0:
            return None
        else:
            return self.tag_stack[-1]

# Reads a page of tournament results and stuffs the results into self.results
class TournamentResultsParser( TableParser ):
    def __init__( self ):
        TableParser.__init__( self )
        self.xtbl = None        # URL of current crosstable
        self.rating = 0         # Rating after current tournament
        self.results = []       # [TournamentResult]
        self.any_results = False # True if any tournaments, even blitz

    def handle_starttag( self, tag, attrs ):
        TableParser.handle_starttag( self, tag, attrs )
        if tag == "a":
            if self.cur_col == 1:
                xtbl_link = alist_find( attrs, "href" )
                m = xtbl_re.search( xtbl_link )
                if m:
                    self.xtbl = m.group( 1 )
                    self.any_results = True

    def handle_endtag( self, tag ):
        TableParser.handle_endtag( self, tag )
        if tag == "tr" and self.xtbl and self.rating != 0:
            self.results.append( TournamentResult( self.xtbl, self.rating ) )
            self.xtbl = None
            self.rating = 0

    def handle_data( self, data ):
        if self.in_td > 0:
            if self.cur_col == 2 and self.cur_tag() == "b" and self.xtbl:
                m = re.match( "\d+", data )
                self.rating = int( m.group( 0 ) )

# Reads a page of results for a given year and stuffs the results into self.results
class YearResultsParser( TableParser ):
    def __init__( self ):
        TableParser.__init__( self )
        self.rating = 0           # Rating for this game
        self.results = []         # [Result]
        self.reading_data = False # Have we gotten to the actual data
        self.xtbl = None          # URL of crosstable
        self.rd = 0               # Round of this game
        self.result = None        # code for game result

    def handle_starttag( self, tag, attrs ):
        TableParser.handle_starttag( self, tag, attrs )
        if tag == "a":
            if self.cur_col == 0:
                xtbl_link = alist_find( attrs, "href" )
                m = xtbl_re.search( xtbl_link )
                if m:
                    self.xtbl = m.group( 1 )

    def handle_endtag( self, tag ):
        TableParser.handle_endtag( self, tag )
        if tag == "tr" and self.result:
            self.results.append( Result( self.rating, self.result, self.xtbl, self.rd ) )
            self.xtbl = None
            self.rd = 0
            self.rating = 0
            self.result = None

    def handle_data( self, data ):
        if not self.reading_data and self.cur_tag() == "th" and data == "Event Name":
            self.reading_data = True

        if self.reading_data:
            if self.in_td > 0:
                if self.cur_col == 2:
                    self.rd = int( data )
                elif self.cur_col == 6:
                    m = rating_re.search( data )
                    if m:
                        self.rating = int( m.group( 1 ) )
                elif self.cur_col == 7:
                    self.result = data[0]

# Return the URL providing the stats for the player with USCF ID `id`
# in the given year
def year_stats_page_url( id, year ):
    return "http://main.uschess.org/datapage/gamestats.php?memid=%s&ptype=Y&rs=R&dkey=%d&drill=Y" % (id, year )

# Return the URL corresponding to the player with USCF ID `id`
def tournament_stats_page_url( id ):
    return "http://main.uschess.org/assets/msa_joomla/MbrDtlTnmtHst.php?%s" % id

# id -> year -> [Result]
def year_stats( id, year ):
    r = requests.get( year_stats_page_url( id, year ) )
    parser = YearResultsParser()
    parser.feed( r.text )
    return parser.results

def name_from_id( id ):
    url = "http://main.uschess.org/assets/msa_joomla/MbrDtlMain.php?%s" % id
    r = requests.get( url )
    for l in r.text.split("\n"):
        m = name_re.search( l )
        if m:
            return m.group( 1 ).replace( "&nbsp;", " " )
    return ""

# Display one year's stats textually
def parse_year_stats( id, year ):
    results = year_stats( id, year )
    if len( results ) > 0:
        naive_perf = sum( r.val() for r in results ) / len( results )
        accurate_perf = accurate_perf_rating( results )
        print( "%d: %4d %4d (%3d games)" % (year,
                                            round( naive_perf ),
                                            round( accurate_perf ),
                                            len( results )) )

# Display all years' stats textually
def run_by_year( id ):
    print( "Year  Fast  Acc %s" % (name_from_id( id )) )
    for y in range( 1994, NEXT_YEAR ):
        parse_year_stats( id, y )

# Return a list of (i, x) pairs, where i = last game # with crosstable x
def xtbl_indices( xtbls ):
    mapping = {}
    for (i, x) in enumerate( xtbls ):
        mapping[x] = i          # overwrite earlier indices with later ones
    vals = []
    for (k, v) in mapping.items():
        vals.append( (v, k) )
    return sorted( vals )

# Filename of pickle file corresponding to `id`
def pickle_file( id ):
    return "pickle/%s.pickle" % id

# Id -> [TournamentResult]
def get_tournament_history( id, tnmt_results ):
    u = tournament_stats_page_url( id )
    tnmt_r = requests.get( u )
    tnmt_pages = []             # URLs of pages listing tournaments
    for l in tnmt_r.text.split("\n"):
        m = tnmt_hst_re.search( l )
        if m:
            tnmt_pages.append( "http://main.uschess.org/assets/msa_joomla/" + m.group( 0 ) )
    if len( tnmt_pages ) == 0:
        tnmt_pages.append( u )  # All tournaments were on the first page
    for page in tnmt_pages:
        r = requests.get( page )
        parser = TournamentResultsParser()
        parser.feed( r.text )
        saw_new_result = False
        for new_result in parser.results:
            # It's possible to see a tournament twice if it was dual-rated
            if new_result not in tnmt_results:
                saw_new_result = True
                tnmt_results.append( new_result )
        if not parser.any_results:
            break
    return tnmt_results
    
# id -> [Result] -> [TournamentResult] -> ([Result], [TournamentResult])
#
# `results` and `tnmt_results` are the individual game results and
# tournament results we already know about. Grab whatever data we don't
# have yet and return the updated lists.
def parse_results( id, results, tnmt_results ):
    # We should never have to look at an earlier year than we already have
    # some data for
    max_saved_year = max( r.year() for r in results ) if results else 1994
    print( "Getting new yearly stats starting from %s..." % max_saved_year )
    new_results = []
    for y in range( max_saved_year, NEXT_YEAR ):
        for new_result in year_stats( id, y ):
            if new_result not in results:
                results.append( new_result )
    results.sort( key=attrgetter( "xtbl", "rd" ) )
    print( "Getting new tournament history..." )
    tnmt_results = get_tournament_history( id, tnmt_results )
    return (results, tnmt_results)

# id -> ([Result], [TournamentResult])
def read_results( id ):
    results = []
    tnmt_results = []

    # Read pickled data if present
    try:
        pf = pickle_file( id )
        f = open( pf, "rb" )
        results = pickle.load( f )
        tnmt_results = pickle.load( f )
        f.close()
    except IOError:
        pass

    (results, tnmt_results) = parse_results( id, results, tnmt_results )

    f = open( pf, "wb" )
    pickle.dump( results, f )
    pickle.dump( tnmt_results, f )
    f.close()
    return (results, tnmt_results)

def year_change_indices( results ):
    cur_year = 0
    ans = []
    for (i, result) in enumerate( results ):
        y = result.year()
        if (y != cur_year):
            ans.append( (i, y) )
        cur_year = y
    return ans

PI = 3.14159265

def normal_distribution( std_dev, length, center ):
    return [ math.exp( - float(i - center)**2 / (2*std_dev**2))
             for i in range( length ) ]

def run_by_window( id ):
    window_size = 60            # how many games to look at at once

    (results, tnmt_results) = read_results( id )
    tnmt_map = { r.xtbl: r.rating for r in tnmt_results } # xtbl -> rating

    ratings = []                # recent perf rating after each game
    xtbls = []                  # crosstable id of each game
    if len( results ) < window_size:
        print( "Not enough games yet." )
        return

    print( "Generating graph..." )
    for x in range( 0, len( results ) + 1):
        begin = max( 0, x - window_size )
        end = min( len( results ), x + window_size )
        distr = normal_distribution( 20, end - begin, x - begin )
        ratings.append( accurate_perf_rating_weighted( results[begin:end], distr ) )
        xtbls.append( results[x-1].xtbl )
    (tnmt_indices, tnmt_xtbls) = zip( *xtbl_indices( xtbls ) )
    tnmt_ratings = [tnmt_map[x] for x in tnmt_xtbls]
    name = name_from_id( id )

    # Chop off results before the initial year
    initial_year = global_options.year or 0
    active_results = results
    first_idx = next( i for i,v in enumerate( active_results ) if v.year() >= initial_year )
    ratings = ratings[first_idx:]
    active_results = active_results[first_idx:]
    tnmt_indices = [i - first_idx for i in tnmt_indices if i >= first_idx]
    tnmt_ratings = tnmt_ratings[len(tnmt_ratings) - len(tnmt_indices):]

    plt.plot( tnmt_indices, tnmt_ratings, color="#b0b0b0" )
    plt.plot( range( len( ratings ) ), ratings )
    plt.title( name + "\n" )
    year_changes = year_change_indices( active_results )
    plt.xlim( 0, len( ratings ) )
    (indices, years) = zip( *year_changes )
    plt.xticks( indices, years, rotation = 'vertical', size = 'small' )
    out_name = "out/%s %s.pdf" % (id, name)
    plt.savefig( out_name )

    if global_options.open:
        os.system( 'open "%s"' % out_name )

    print( "Done." )

def run():
    run_by_window( sys.argv[1] )

parser = argparse.ArgumentParser( description="Analyze USCF tournament performance results." )
parser.add_argument( "-i", "--id", help="USCF ID" )
parser.add_argument( "-y", "--year", help="Initial year", type=int )
parser.add_argument( "-t", "--tnmt", help="Tournament results", nargs="*" )
parser.add_argument( "-o", "--open", help="Open graph after computation", action="store_true" )
global_options = parser.parse_args()

if global_options.id:
    run_by_window( global_options.id )
elif global_options.tnmt:
    ratings = global_options.tnmt[:-1]
    score = global_options.tnmt[-1]
    print( int( round( accurate_perf_rating_raw( [int( r ) for r in ratings],
                                                 float( score ) ) ) ) )
