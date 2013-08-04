import argparse
import chessdiag
import win32clipboard
from PIL import Image

def set_clipboard( str ):
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardText( str )
    win32clipboard.CloseClipboard()

parser = argparse.ArgumentParser( description="Read a file with a chess diagram "
                                  "and output a FEN string that represents it." )
parser.add_argument( "input_name",
                     help="Name of diagram file to read from" )
global_options = parser.parse_args()

img = Image.open( global_options.input_name )
fen_str = chessdiag.image_to_fen( img )
set_clipboard( fen_str )
print fen_str
