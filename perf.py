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
import cPickle as pickle
import datetime
import math
import matplotlib.pyplot as plt
import numpy as np
import re
import requests
import sys
from HTMLParser import HTMLParser
from operator import attrgetter

result_to_value = { "L": 0.0, "S": 0.0,
                    "D": 0.5, "R": 0.5,
                    "W": 1.0, "N": 1.0  }

NEXT_YEAR = datetime.datetime.now().year + 1

# I'm rated d points above the other player; what's my EV?
def rating_diff_to_expected_value( d ):
    return 1.0 / (1.0 + pow( 10.0, -d / 400.0 ))

# What's my total expected value if I have a given rating and will be
# facing opponents with the given opponent ratings?
def expected_value_total( rating, opp_ratings ):
    return sum( rating_diff_to_expected_value( rating - r ) for r in opp_ratings )

def expected_value_total_scaled( rating, opp_ratings, scales ):
    return sum( scales[i] * rating_diff_to_expected_value( rating - r )
                for (i,r) in enumerate( opp_ratings ) )

def accurate_perf_rating_raw( opp_ratings, score ):
    lo = None
    hi = None
    test = 0.0
    test_total = 0.0
    iterations = 0

    if score == 0:
        return min( opp_ratings ) - 400
    elif score == len( opp_ratings ):
        return max( opp_ratings ) + 400

    while abs( test_total - score ) > 0.001 and iterations < 50:
        if hi is None and lo is None:
            test = sum( opp_ratings ) / len( opp_ratings )
        elif hi is None:
            test = lo + 100.0
        elif lo is None:
            test = hi - 100.0
        else:
            test = (lo + hi) / 2.0
        test_total = expected_value_total( test, opp_ratings )
        if (test_total < score):
            lo = test
        else:
            hi = test
        iterations += 1
    return test

def accurate_perf_rating_raw_scaled( opp_ratings, score, distr ):
    lo = None
    hi = None
    test = 0.0
    test_total = 0.0
    iterations = 0

    if score == 0:
        return min( opp_ratings ) - 400
    elif score == len( opp_ratings ):
        return max( opp_ratings ) + 400

    while abs( test_total - score ) > 0.001 and iterations < 50:
        if hi is None and lo is None:
            test = sum( opp_ratings ) / len( opp_ratings )
        elif hi is None:
            test = lo + 100.0
        elif lo is None:
            test = hi - 100.0
        else:
            test = (lo + hi) / 2.0
        test_total = expected_value_total_scaled( test, opp_ratings, distr )
        if (test_total < score):
            lo = test
        else:
            hi = test
        iterations += 1
    return test

# What rating would I have to have so that the total number of points
# scored in results is exactly what was expected?
def accurate_perf_rating( results ):
    actual_total = sum( result_to_value[ r.result ] for r in results )
    opp_ratings = [ r.opp_rating for r in results ]
    return accurate_perf_rating_raw( opp_ratings, actual_total )

def accurate_perf_rating_scaled( results, distr ):
    actual_total = sum( distr[i] * result_to_value[ r.result ]
                        for (i,r) in enumerate( results ) )
    opp_ratings = [ r.opp_rating for r in results ]
    return accurate_perf_rating_raw_scaled( opp_ratings, actual_total, distr )

def xtbl_to_str( xtbl ):
    return "%s-%s-%s" % (xtbl[0:4], xtbl[4:6], xtbl[6:8] )

class TournamentResult():
    def __init__( self, xtbl, rating ):
        self.xtbl = xtbl
        self.rating = rating
    def __eq__( self, rhs ):
        return self.xtbl == rhs.xtbl
    def __repr__( self ):
        return "%s %d" % (self.xtbl, self.rating)
    def year( self ):
        return int( self.xtbl[0:4] )

class Result():
    def __init__( self, opp_rating, result, xtbl, rd ):
        self.opp_rating = opp_rating
        self.result = result
        self.xtbl = xtbl
        self.rd = rd
    def __eq__( self, rhs ):
        return self.xtbl == rhs.xtbl and self.rd == rhs.rd
    def __repr__( self ):
        return "%d %s (%s:%d)" % (self.opp_rating, self.result, self.xtbl, self.rd)
    def val( self ):
        return self.opp_rating + (result_to_value[ self.result ] - 0.5) * 800
    def year( self ):
        return int( self.xtbl[0:4] )

def alist_find( alist, key ):
    for (k,v) in alist:
        if k == key: return v
    return None

tournament_rating_re = re.compile( r"=>" )
rating_re = re.compile( r"=>\s+(\d+)", re.MULTILINE )
xtbl_re = re.compile( r"XtblMain.php\?([\d]+)" )
tnmt_hst_re = re.compile( r"MbrDtlTnmtHst.php\?[\d]+\.[\d]+" )

class TableParser( HTMLParser ):
    def __init__( self ):
        HTMLParser.__init__( self )
        self.tag_stack = []
        self.cur_col = 0
        self.in_td = 0

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

class TournamentResultsParser( TableParser ):
    def __init__( self ):
        TableParser.__init__( self )
        self.reading_data = False
        self.xtbl = None
        self.rating = 0
        self.results = []

    def handle_starttag( self, tag, attrs ):
        TableParser.handle_starttag( self, tag, attrs )
        if tag == "a":
            if self.cur_col == 1:
                xtbl_link = alist_find( attrs, "href" )
                m = xtbl_re.search( xtbl_link )
                if m:
                    self.xtbl = m.group( 1 )

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

class YearResultsParser( TableParser ):
    def __init__( self ):
        TableParser.__init__( self )
        self.rating = 0
        self.results = []
        self.reading_data = False
        self.xtbl = None
        self.rd = 0
        self.rating = 0
        self.result = None

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

def year_stats_page_url( id, year ):
    return "http://main.uschess.org/datapage/gamestats.php?memid=%s&ptype=Y&rs=R&dkey=%d&drill=Y" % (id, year )

def tournament_stats_page_url( id ):
    return "http://main.uschess.org/assets/msa_joomla/MbrDtlTnmtHst.php?%s" % id

def year_stats( id, year ):
    r = requests.get( year_stats_page_url( id, year ) )
    parser = YearResultsParser()
    parser.feed( r.text )
    return parser.results

def parse_year_stats( id, year ):
    results = year_stats( id, year )
    if len( results ) > 0:
        naive_perf = sum( r.val() for r in results ) / len( results )
        accurate_perf = accurate_perf_rating( results )
        print "%d: %4d %4d (%3d games)" % (year,
                                           round( naive_perf ),
                                           round( accurate_perf ),
                                           len( results ))

name_re = re.compile( "<b>\d+: ([^<]+)" )
def name_from_id( id ):
    url = "http://main.uschess.org/assets/msa_joomla/MbrDtlMain.php?%s" % id
    r = requests.get( url )
    for l in r.text.split("\n"):
        m = name_re.search( l )
        if m:
            return m.group( 1 ).replace( "&nbsp;", " " )
    return ""

def run_by_year( id ):
    print "Year  Fast  Acc %s" % (name_from_id( id ))
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

def pickle_file( id ):
    return "pickle/%s.pickle" % id

# id -> [Result] -> [TournamentResult] -> ([Result], [TournamentResult])
def parse_results( id, results, tnmt_results ):
    max_saved_year = max( r.year() for r in results ) if results else 1994
    print "Getting new yearly stats starting from %s..." % max_saved_year
    new_results = []
    for y in range( max_saved_year, NEXT_YEAR ):
        for new_result in year_stats( id, y ):
            if new_result not in results:
                results.append( new_result )
    results.sort( key=attrgetter( "xtbl", "rd" ) )
    print "Getting new tournament history..."
    tnmt_results = get_tournament_history( id, tnmt_results )
    return (results, tnmt_results)

# id -> ([Result], [TournamentResult])
def read_results( id ):
    results = []
    tnmt_results = []

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
    return [ math.exp( - float(i - center)**2 / (2*std_dev**2)) for i in range( length ) ]

def run_by_window( id ):
    window_size = 32

    (results, tnmt_results) = read_results( id )
    tnmt_map = { r.xtbl: r.rating for r in tnmt_results } # xtbl -> rating

    ratings = []                # recent perf rating after each game
    xtbls = []                  # crosstable id of each game
    if len( results ) < window_size:
        print "Not enough games yet."
        return

    print "Generating graph..."
    for x in range( 0, len( results ) + 1):
        begin = max( 0, x - window_size )
        end = min( len( results ), x + window_size )
        distr = normal_distribution( 10, end - begin, x - begin )
        ratings.append( accurate_perf_rating_scaled( results[begin:end], distr ) )
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

    plt.plot( range( len( ratings ) ), ratings )
    plt.plot( tnmt_indices, tnmt_ratings )
    plt.title( name + "\n" )
    year_changes = year_change_indices( active_results )
    plt.xlim( 0, len( ratings ) )
    (indices, years) = zip( *year_changes )
    plt.xticks( indices, years, rotation = 'vertical', size = 'small' )
    plt.savefig( "out/%s %s.png" % (id, name) )

    print "Done."

# Id -> [TournamentResult] -> [TournamentResult]
def get_tournament_history( id, tnmt_results ):
    u = tournament_stats_page_url( id )
    tnmt_r = requests.get( u )
    tnmt_pages = []
    for l in tnmt_r.text.split("\n"):
        m = tnmt_hst_re.search( l )
        if m:
            tnmt_pages.append( "http://main.uschess.org/assets/msa_joomla/" + m.group( 0 ) )
    if len( tnmt_pages ) == 0:
        tnmt_pages.append( u )  # Just a single page
    for page in tnmt_pages:
        r = requests.get( page )
        parser = TournamentResultsParser()
        parser.feed( r.text )
        saw_new_result = False
        for new_result in parser.results:
            if new_result not in tnmt_results:
                saw_new_result = True
                tnmt_results.append( new_result )
        if not saw_new_result:
            break
    return tnmt_results
    
def run():
    run_by_window( sys.argv[1] )

parser = argparse.ArgumentParser( description="Analyze USCF tournament performance results." )
parser.add_argument( "-i", "--id", help="USCF ID" )
parser.add_argument( "-y", "--year", help="Initial year", type=int )
parser.add_argument( "-t", "--tnmt", help="Tournament results", nargs="*" )
global_options = parser.parse_args()

if global_options.id:
    run_by_window( global_options.id )
elif global_options.tnmt:
    ratings = global_options.tnmt[:-1]
    score = global_options.tnmt[-1]
    print int( round( accurate_perf_rating_raw( [int( r ) for r in ratings],
                                                float( score ) ) ) )
