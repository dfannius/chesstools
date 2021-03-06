import argparse
import chessdiag
import filecmp
import os.path
import pyperclip

# import win32clipboard
# import win32con

# def clipboard_contents():
#     win32clipboard.OpenClipboard()
#     text = win32clipboard.GetClipboardData( win32con.CF_TEXT )
#     win32clipboard.CloseClipboard()
#     null_idx = text.find("\0")  # Some apps return garbage after the null
#     if null_idx != -1:
#         text = text[:null_idx]
#     return text

parser = argparse.ArgumentParser( description="Output a chessboard graphic corresponding to "
                                  "the FEN string currently occupying the clipboard." )
parser.add_argument( "output_name",
                     help="Base filename to output to (.png will be appended)")
parser.add_argument( "-b",
                     "--black_to_move",
                     help="To-move indicator shows that black is to move",
                     action="store_true" )
parser.add_argument( "-s",
                     "--show_side",
                     help="Show a to-move indicator and coordinates",
                     action="store_true" )
parser.add_argument( "-f",
                     "--flip",
                     help="Flip the board so Black is at the bottom",
                     action="store_true" )
parser.add_argument( "-o",
                     "--override",
                     help="Allow writing over files or creating duplicate diagrams",
                     action="store_true" )
global_options = parser.parse_args()

str = pyperclip.paste()
print "Using %s" % str
out_img = chessdiag.fen_to_image( str, global_options )
                    
ref_filename = ".last.png"
output_name = "%s.png" % global_options.output_name
if not global_options.override and (os.path.exists( output_name )):
    print "%s already exists" % output_name
else:
    out_img.save( output_name )
    if os.path.exists( ref_filename ) and filecmp.cmp( output_name, ref_filename ):
        print "Saved duplicate file"
    else:
        out_img.save (ref_filename )
