# Take a pgn file and split it up by time control
# Particularly meant for PGN from ICC (chessclub.com)

import os.path
import re
import sys

file_dict = {}                  # time control to file handle

in_header = True
game_lines = []
time_control = "_"

def tc_to_file( rootname, tc ):
    try:
        return file_dict[tc]
    except KeyError:
        f = open( rootname + " " + tc + ".pgn", "w" )
        file_dict[tc] = f
        return f

def time_control_to_str( time_control ):
    elts = time_control.split( '+' )
    if len( elts ) > 1:
        return "%d %s" % (int( elts[0] ) / 60, elts[1])
    else:
        return time_control

def dump_game( rootname ):
    global game_lines
    global time_control
    time_control_str = time_control_to_str( time_control )
    f = tc_to_file( rootname, time_control_str )
    f.writelines( game_lines )
    time_control = "_"
    game_lines = []

in_filename = sys.argv[1]
rootname = os.path.splitext( in_filename )[0]
for l in open( in_filename ):
    if l[0] == "[" and not in_header:
        dump_game( rootname )
        in_header = True
    if in_header:
        if l[0] == "[":
            m = re.search( "TimeControl \"(.+)\"", l )
            if m:
                time_control = m.group( 1 )
        else:
            in_header = False
    game_lines += l

dump_game( rootname )
for f in file_dict.values():
    f.close()
