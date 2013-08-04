import argparse
import chessdiag
import glob
import os.path
import re
from PIL import Image

parser = argparse.ArgumentParser( description="Read a file with a chess diagram, "
                                  "and if it doesn't have a margin showing the board orientation "
                                  "and side to move, replace it with one that does." )
parser.add_argument( "--input_file",
                     help="Name of diagram file to read from" )
parser.add_argument( "--input_dir",
                     help="Directory to read files from" )
parser.add_argument( "--ref_file",
                     help="Text file exported from Mnemosyne" )
                     
global_options = parser.parse_args()

str_to_side = {
    'B':     'Black',
    'W':     'White',
    'Black': 'Black',
    'White': 'White'
}

to_play_re = re.compile( r"(\w+) to (play|move)" )
img_url_re = re.compile( r'<img src="(.*?)">' )

# Generate mapping of image name to its line from the database file
img_to_line = {}
for l in open( global_options.ref_file ):
    m = img_url_re.search( l )
    if m:
        img_to_line[m.group( 1 )] = l

def process_file( fname, output_dir ):
    img = Image.open( fname )
    name = os.path.realpath( fname )
    img_name = fname[fname.find( "images" ):].replace( "\\", "/" )
    side = 'White'
    if img_to_line.has_key( img_name ):
        l = img_to_line[img_name]
        m = to_play_re.search( l )
        if m:
            side = str_to_side[ m.group( 1 ) ]
            diag = chessdiag.Diagram( img )
            fen_str = chessdiag.diag_to_fen( diag )
            # Only resave the file if it didn't have a margin already
            if not diag.has_margin:
                diag.black_to_move = (side == 'Black')
                options = argparse.Namespace()
                setattr( options, "show_side", True )
                setattr( options, "black_to_move", diag.black_to_move )
                setattr( options, "flip", diag.flipped )
                out_img = chessdiag.fen_to_image( fen_str, options )
                out_img.save( os.path.join( output_dir, os.path.basename( name ) ) )
        else:
            print "Couldn't find side to play for %s in %s" % (fname, global_options.ref_file)
    else:
        print "Couldn't find %s in %s" % (fname, global_options.ref_file)

if global_options.input_dir:
    for fname in glob.glob( os.path.join( global_options.input_dir, "*.png" ) ):
        process_file( fname, global_options.input_dir )
elif global_options.input_file:
    process_file( global_options.input_file, "." )
