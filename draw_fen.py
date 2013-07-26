# To do:
#  + read from clipboard
#  + option for displaying side to move
#  + option for flipping board
#  + clean up get_margin_img()
#  + put all source art in script directory
#  - move common code to separate file
#  - move bare code at end to a function
#  - put all source art in one file for speedup?
#  - refactor to copy_margin()
#  - determine correct output file automatically?

from PIL import Image
import argparse
import os.path
import win32clipboard
import win32con

REF_SQ_SIZE = 30                # size of squares in reference art
REF_MARGIN = 15                 # width of margin in reference art

options = None
script_dir = os.path.dirname( os.path.realpath( __file__ ) )

# 0: W at bottom, W to move (plus all pieces as specified by square_dict)
# 1: W at bottom, B to move
# 2: B at bottom, W to move
# 3: B at bottom, B to move
ref_imgs = [ Image.open( "%s/reference%d.png" % (script_dir, i) ) for i in range( 1, 5 ) ]

def get_margin_img():
    return ref_imgs[2 * options.flip + options.black_to_move]

# Mapping of FEN character to dark/light squares in ref_imgs[0]
square_dict = {
    'P': ('a1', 'a2'),
    'R': ('b2', 'b1'),
    'N': ('c1', 'c2'),
    'B': ('d2', 'd1'),
    'Q': ('e1', 'e2'),
    'K': ('f2', 'f1'),
    'p': ('a3', 'a4'),
    'r': ('b4', 'b3'),
    'n': ('c3', 'c4'),
    'b': ('d4', 'd3'),
    'q': ('e3', 'e4'),
    'k': ('f4', 'f3'),
    ' ': ('g1', 'g2')
}
    
# 0 = dark, 1 = light
def square_color( col, row ):
    return (col + row + 1) % 2

# Takes a square like 'a8' and turns it into a 4-tuple suitable for
# sending to PIL's Image.crop function
def sq_to_ref_img_coords( sq ):
    col = ord( sq[0] ) - ord( 'a' ) # 0 to 7 left to right
    row = ord( '8' ) - ord( sq[1] ) # 0 to 7 top to bottom
    return( (REF_SQ_SIZE * col + REF_MARGIN + 1,
             REF_SQ_SIZE * row + 1,
             REF_SQ_SIZE * (col + 1) + REF_MARGIN + 1,
             REF_SQ_SIZE * (row + 1) + 1) )

def sq_to_pic( sq ):
    coords = sq_to_ref_img_coords( sq )
    pic = ref_imgs[0].crop( coords )
    return pic

def add_square( img, col, row, piece ):
    color = square_color( col, row )
    sq_pic = sq_to_pic( square_dict[piece][color] )
    margin = REF_MARGIN if options.show_side else 0
    display_col = 7 - col if options.flip else col
    display_row = 7 - row if options.flip else row
    img.paste( sq_pic, (REF_SQ_SIZE * display_col + 1 + margin,
                        REF_SQ_SIZE * display_row + 1) )

def maybe_override_side( fen ):
    if options.black_to_move: return
    space_pos = fen.find( ' ' )
    if fen[space_pos+1] == 'b':
        options.black_to_move = True

def fen_to_image( fen ):
    SIZE = 8 * REF_SQ_SIZE + 2 + (REF_MARGIN if options.show_side else 0)
    img = Image.new( "RGB", (SIZE, SIZE) )
    col = 0
    row = 0
    maybe_override_side( fen )
    for c in fen:
        if c.isdigit():
            d = int( c )
            while d != 0:
                add_square( img, col, row, ' ')
                col += 1
                d -= 1
        elif c == '/':
            col = 0
            row += 1
        elif c == ' ':
            break
        else:
            add_square( img, col, row, c )
            col += 1
    return img

def clipboard_contents():
    win32clipboard.OpenClipboard()
    text = win32clipboard.GetClipboardData( win32con.CF_TEXT )
    win32clipboard.CloseClipboard()
    return text

parser = argparse.ArgumentParser( description="Output a chessboard graphic corresponding to the FEN string currently occupying the clipboard." )
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
options = parser.parse_args()

str = clipboard_contents()
print "Using %s" % str
out_img = fen_to_image( str )
if options.show_side:
    MARGIN_END = 8 * REF_SQ_SIZE + REF_MARGIN + 1
    margin_img = get_margin_img()
    left_margin_coords = (1, 1, REF_MARGIN + 1, MARGIN_END)
    left_margin = margin_img.crop( left_margin_coords )
    out_img.paste( left_margin, left_margin_coords )

    bottom_margin_coords = (1, MARGIN_END - REF_MARGIN, MARGIN_END, MARGIN_END)
    bottom_margin = margin_img.crop( bottom_margin_coords )
    out_img.paste( bottom_margin, bottom_margin_coords )
                    
output_name = "%s.png" % options.output_name
SAFETY_FIRST = True
if SAFETY_FIRST and (os.path.exists( output_name )):
    print "%s already exists" % output_name
else:
    out_img.save( output_name )
