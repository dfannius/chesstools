import argparse
import chessdiag
import os.path
import re
from PIL import Image

parser = argparse.ArgumentParser( description="Read a file with a chess diagram, "
                                  "and if it doesn't have a margin showing the board orientation "
                                  "and side to move, replace it with one that does." )
parser.add_argument( "input_name",
                     help="Name of diagram file to read from" )
parser.add_argument( "--ref_file",
                     help="Text file exported from Mnemosyne" )
                     
global_options = parser.parse_args()

img = Image.open( global_options.input_name )
# fen_str = chessdiag.image_to_fen( img )
name = os.path.realpath( global_options.input_name )
name = name[name.find( "images" ):].replace( "\\", "/" )
print name

str_to_side = {
    'B':     'Black',
    'W':     'White',
    'Black': 'Black',
    'White': 'White'
}

side = 'White'

to_play_re = re.compile( r"(\w+) to play" )
for l in open( global_options.ref_file ):
    if l.find( name ) != -1:
        m = to_play_re.search( l )
        if m:
            side = str_to_side[ m.group( 1 ) ]
        break

diag = chessdiag.Diagram( img )
fen_str = chessdiag.diag_to_fen( diag )
if not diag.has_margin:
    diag.black_to_move = (side == 'Black')
options = argparse.Namespace()
setattr( options, "show_side", True )
setattr( options, "black_to_move", diag.black_to_move )
setattr( options, "flip", diag.flipped )
out_img = chessdiag.fen_to_image( fen_str, options )
out_img.save( "foo.png" )
