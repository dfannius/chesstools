# TODO
# + Graph USCF rating as well
# - Cache rating information
# - Print date marks on x axis
# - Refactor TournamentResultsParser and YearResultsParser
# - cur_tag should really be a stack

import matplotlib.pyplot as plt
import numpy as np
import re
import urllib2
import sys
from HTMLParser import HTMLParser
from operator import attrgetter

result_to_value = { "L": 0.0, "S": 0.0,
                    "D": 0.5, "R": 0.5,
                    "W": 1.0, "N": 1.0  }

# I'm rated d points above the other player; what's my EV?
def rating_diff_to_expected_value( d ):
    return 1.0 / (1.0 + pow( 10.0, -d / 400.0 ))

# What's my total expected value if I have a given rating and will be
# facing opponents with the given opponent ratings?
def expected_value_total( rating, opp_ratings ):
    return sum( rating_diff_to_expected_value( rating - r ) for r in opp_ratings )

# What rating would I have to have so that the total number of points
# scored in results is exactly what was expected?
def accurate_perf_rating( results ):
    lo = None
    hi = None
    test = 0.0
    test_total = 0.0
    actual_total = sum( result_to_value[ r.result ] for r in results )
    opp_ratings = [ r.opp_rating for r in results ]
    iterations = 0

    while abs( test_total - actual_total ) > 0.001 and iterations < 50:
        if hi is None and lo is None:
            test = sum( r.val() for r in results ) / len( results )
        elif hi is None:
            test = lo + 100.0
        elif lo is None:
            test = hi - 100.0
        else:
            test = (lo + hi) / 2.0
        test_total = expected_value_total( test, opp_ratings )
        if (test_total < actual_total):
            lo = test
        else:
            hi = test
        iterations += 1
    return test

def xtbl_to_str( xtbl ):
    return "%s-%s-%s" % (xtbl[0:4], xtbl[4:6], xtbl[6:8] )

class TournamentResult():
    def __init__( self, xtbl, rating ):
        self.xtbl = xtbl
        self.rating = rating
    def __repr__( self ):
        return "%s %d" % (self.xtbl, self.rating)

class Result():
    def __init__( self, opp_rating, result, xtbl, rd ):
        self.opp_rating = opp_rating
        self.result = result
        self.xtbl = xtbl
        self.rd = rd
    def __repr__( self ):
        return "%d %s (%s:%d)" % (self.opp_rating, self.result, self.xtbl, self.rd)
    def val( self ):
        return self.opp_rating + (result_to_value[ self.result ] - 0.5) * 800

def alist_find( alist, key ):
    for (k,v) in alist:
        if k == key: return v
    return None

tournament_rating_re = re.compile( r"=>" )
rating_re = re.compile( r"=>\s+(\d+)", re.MULTILINE )
xtbl_re = re.compile( r"XtblMain.php\?([\d]+)" )
tnmt_hst_re = re.compile( r"MbrDtlTnmtHst.php\?[\d]+\.[\d]+" )

class TournamentResultsParser( HTMLParser ):
    def __init__( self ):
        self.reading_data = False
        self.tag_stack = []
        self.cur_col = 0
        self.in_td = 0
        self.xtbl = None
        self.rating = 0
        self.results = []
        HTMLParser.__init__( self )

    def handle_starttag( self, tag, attrs ):
        self.tag_stack += tag
        if tag == "tr":
            self.cur_col = -1
        if tag == "td":
            self.cur_col += 1
            self.in_td += 1
        if tag == "a":
            if self.cur_col == 1:
                xtbl_link = alist_find( attrs, "href" )
                m = xtbl_re.search( xtbl_link )
                if m:
                    self.xtbl = m.group( 1 )

    def handle_endtag( self, tag ):
        self.tag_stack = self.tag_stack[:-1]
        if tag == "td":
            self.in_td -= 1
        if tag == "tr" and self.xtbl and self.rating != 0:
            self.results.append( TournamentResult( self.xtbl, self.rating ) )
            self.xtbl = None
            self.rating = 0

    def cur_tag( self ):
        if len( self.tag_stack ) == 0:
            return None
        else:
            return self.tag_stack[-1]

    def handle_data( self, data ):
        if self.in_td > 0:
            if self.cur_col == 2 and self.cur_tag() == "b" and self.xtbl:
                m = re.match( "\d+", data )
                self.rating = int( m.group( 0 ) )

class YearResultsParser( HTMLParser ):
    def __init__( self ):
        self.rating = 0
        self.results = []
        self.indent = 0
        self.reading_data = False
        self.cur_tag = None
        self.cur_col = 0
        self.xtbl = None
        self.rd = 0
        self.rating = 0
        self.result = None
        self.in_td = 0
        HTMLParser.__init__( self )

    def handle_starttag( self, tag, attrs ):
#       print " " * self.indent, "start tag:", tag
#       print " " * self.indent, "attrs:", attrs
        self.indent += 2
        self.cur_tag = tag
        if tag == "tr":
            self.cur_col = -1
        if tag == "td":
            self.cur_col += 1
            self.in_td += 1
        if tag == "a":
            if self.cur_col == 0:
                xtbl_link = alist_find( attrs, "href" )
                m = xtbl_re.search( xtbl_link )
                if m:
                    self.xtbl = m.group( 1 )

    def handle_endtag( self, tag ):
        self.indent -= 2
#       print " " * self.indent, "end tag:", tag
        if tag == "td":
            self.in_td -= 1
        if tag == "tr" and self.result:
            self.results.append( Result( self.rating, self.result, self.xtbl, self.rd ) )
            self.xtbl = None
            self.rd = 0
            self.rating = 0
            self.result = None

    def handle_data( self, data ):
#       print " " * self.indent, "data:", data
        if not self.reading_data and self.cur_tag == "th" and data == "Event Name":
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
    u = urllib2.urlopen( year_stats_page_url( id, year ) )
    parser = YearResultsParser()
    parser.feed( u.read() )
    return parser.results

def parse_year_stats( id, year ):
    results = year_stats( id, year )
    print results
    if len( results ) > 0:
        naive_perf = sum( r.val() for r in results ) / len( results )
        accurate_perf = accurate_perf_rating( results )
        print "%d: %4d %4d (%3d games)" % (year,
                                           round( naive_perf ),
                                           round( accurate_perf ),
                                           len( results ))
        

name_re = re.compile( "<b>\d+: ([^<]+)" )
def name_from_id( id ):
    u = urllib2.urlopen( "http://main.uschess.org/assets/msa_joomla/MbrDtlMain.php?%s" % id )
    for l in u:
        m = name_re.search( l )
        if m:
            return m.group( 1 )
    return None

def run_by_year( id ):
    print "Year  Fast  Acc %s" % (name_from_id( id ))
    for y in range( 1994, 1995 ):
        parse_year_stats( id, y )

def xtbls_to_ratings( xtbls ):
    mapping = {}
    for (i, x) in enumerate( xtbls ):
        mapping[x] = i          # overwrite earlier indices with later ones
    vals = []
    for (k, v) in mapping.items():
        vals.append( (v, k ) )
    return sorted( vals )

def run_by_window( id ):
    print "Getting tournament history..."
    tnmt_results = get_tournament_history( id )
    tnmt_map = {}
    for r in tnmt_results:
        tnmt_map[r.xtbl] = r.rating
    results = []
    window_size = 40
    print "Getting yearly stats..."
    for y in range( 1994, 2014 ):
        results.extend( year_stats( id, y ) )
    results.sort( key=attrgetter( "xtbl", "rd" ) )
#   print "      Date  Fast  Acc Result"
    ratings = []
    tnmt_ratings = []
    xtbls = []
    print "Generating graph..."
    for x in range( window_size, len( results ) ):
        begin = max( 0, x - window_size )
        r = results[begin:x]
        naive_perf = sum( r.val() for r in r ) / len( r )
        accurate_perf = accurate_perf_rating( r )
        ratings.append( accurate_perf )
        xtbls.append( r[-1].xtbl )
#        print "%s: %4d %4d %s %d" % (xtbl_to_str( r[-1].xtbl ),
#                                     round( naive_perf ),
#                                     round( accurate_perf ),
#                                     r[-1].result,
#                                     r[-1].opp_rating)
    tnmt_ratings = xtbls_to_ratings( xtbls )
    tnmt_indices = [i for (i,x) in tnmt_ratings]
    tnmt_ratings = [tnmt_map[x] for (i,x) in tnmt_ratings]
    plt.plot( range( len( ratings ) ), ratings )
    plt.plot( tnmt_indices, tnmt_ratings )
    plt.savefig( "%s.png" % id )
    print "Done."

def get_tournament_history( id ):
    tnmt_u = urllib2.urlopen( tournament_stats_page_url( id ) )
    tnmt_pages = []
    results = []
    for l in tnmt_u:
        m = tnmt_hst_re.search( l )
        if m:
            tnmt_pages.append( m.group( 0 ) )
    for page in tnmt_pages:
        u = urllib2.urlopen( "http://main.uschess.org/assets/msa_joomla/" + page )
        parser = TournamentResultsParser()
        parser.feed( u.read() )
        results.extend( parser.results )
    return results
    
def run():
    run_by_window( sys.argv[1] )

run()
