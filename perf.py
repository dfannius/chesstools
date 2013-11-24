import re
import urllib2
import sys
from HTMLParser import HTMLParser

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

class Result():
    def __init__( self, opp_rating, result ):
        self.opp_rating = opp_rating
        self.result = result
    def __repr__( self ):
        return "%d %s" % (self.opp_rating, self.result)
    def val( self ):
        return self.opp_rating + (result_to_value[ self.result ] - 0.5) * 800

READ_RATING = 0
READ_RESULT = 1
rating_re = re.compile( "=> (\d+)" )
class ResultsParser( HTMLParser ):
    def __init__( self, results ):
        self.state = READ_RATING
        self.rating = 0
        self.results = results
        HTMLParser.__init__( self )

    def handle_data( self, data ):
        if self.state == READ_RATING:
            m = rating_re.search( data )
            if m:
                self.rating = int( m.group( 1 ) )
                self.state = READ_RESULT
        elif self.state == READ_RESULT:
            self.state = READ_RATING
            self.results.append( Result( self.rating, data[0] ) )
            self.rating = 0

def year_stats_page_url( id, year ):
    return "http://main.uschess.org/datapage/gamestats.php?memid=%s&ptype=Y&rs=R&dkey=%d&drill=Y" % (id, year )

def parse_year_stats( id, year ):
    u = urllib2.urlopen( year_stats_page_url( id, year ) )
    results = []
    parser = ResultsParser( results )
    parser.feed( u.read() )
    if len( results ) > 0:
        naive_perf = sum( r.val() for r in results ) / len( results )
        accurate_perf = accurate_perf_rating( results )
        print "%d: %4d %4d (%3d games)" % (year, round( naive_perf ), round( accurate_perf ), len( results ))

name_re = re.compile( "<b>\d+: ([^<]+)" )
def name_from_id( id ):
    u = urllib2.urlopen( "http://main.uschess.org/assets/msa_joomla/MbrDtlMain.php?%s" % id )
    for l in u:
        m = name_re.search( l )
        if m:
            return m.group( 1 )
    return None

def run():
    id = sys.argv[1]
    print "Year  Fast  Acc %s" % (name_from_id( id ))
    for y in range( 1994, 2014 ):
        parse_year_stats( id, y )

def dfan_perf():
    results = [Result( x, y ) for (x, y) in
               (1852, "W"),
               (1980, "W"),
               (2212, "L"),
               (1764, "W"),
               (2565, "L"),
               (1323, "W"),
               (1977, "D"),
               (2572, "W"),
               (1416, "W"),
               (2212, "D"),
               (2009, "W"),
               (1744, "W"),
               (1479, "W"),
               (2098, "W"),
               (2220, "L"),
               (1982, "W"),
               (2117, "D"),
               (2067, "D"),
               (2007, "D"),
               (1810, "D"),
               (2000, "D"),
               (1781, "W")
               ]
    print int( round( accurate_perf_rating( results ) ) )

run()





