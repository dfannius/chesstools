from PIL import Image, ImageChops
import os

def img_equal( im1, im2 ):
    return ImageChops.difference( im1, im2 ).getbbox() is None

REF_SQ_SIZE = 30                # size of squares in reference art
REF_MARGIN = 15                 # width of margin in reference art

script_dir = os.path.dirname( os.path.realpath( __file__ ) )

# Does this image have a margin?
def image_has_margin( img ):
    (width, height) = img.size
    if width == height:
        if width == 8 * REF_SQ_SIZE + 2:
            return False
        elif width == 8 * REF_SQ_SIZE + 2 + REF_MARGIN:
            return True
    raise Exception( "Bad image dimensions %dx%d" % (width, height) )

# Mapping of FEN character to dark/light squares in ref_diagrams[0]
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

# Declare this now so the Diagram constructor can refer to it
ref_diagrams = []

class Diagram:

    def __init__( self, img, flipped=None, black_to_move=None ):
        self.img = img
        self.has_margin = image_has_margin( img )
        self.margin = REF_MARGIN * self.has_margin
        if self.has_margin:
            if flipped is None:
                bottom_margin = self.bottom_margin_pic()
                for ref in ref_diagrams:
                    if img_equal( bottom_margin, ref.bottom_margin_pic() ):
                        self.flipped = ref.flipped
                        self.black_to_move = ref.black_to_move
            else:
                self.flipped = flipped
                self.black_to_move = black_to_move
        else:
            self.flipped = False
            self.black_to_move = False

    def left_margin_pic( self ):
        MARGIN_END = 8 * REF_SQ_SIZE + REF_MARGIN + 1
        return self.img.crop( (1, 1, REF_MARGIN + 1, MARGIN_END) )

    def bottom_margin_pic( self ):
        MARGIN_END = 8 * REF_SQ_SIZE + REF_MARGIN + 1
        return self.img.crop( (1, MARGIN_END - REF_MARGIN, MARGIN_END, MARGIN_END) )

    def coords_to_bounds( self, row, col ):
        if self.flipped:
            row = 7 - row
            col = 7 - col
        return ( (REF_SQ_SIZE * col + self.margin + 1,
                  REF_SQ_SIZE * row + 1,
                  REF_SQ_SIZE * (col + 1) + self.margin + 1,
                  REF_SQ_SIZE * (row + 1) + 1) )

    # Takes a square like 'a8' and turns it into a 4-tuple suitable for
    # sending to PIL's Image.crop function
    def sq_to_bounds( self, sq ):
        row = ord( '8' ) - ord( sq[1] ) # 0 to 7 top to bottom
        col = ord( sq[0] ) - ord( 'a' ) # 0 to 7 left to right
        return self.coords_to_bounds( row, col )

    def coords_to_pic( self, row, col ):
        return self.img.crop( self.coords_to_bounds( row, col ) )

    def sq_to_pic( self, sq ):
        return self.img.crop( self.sq_to_bounds( sq ) )

    def coords_to_char( self, row, col, ref_diag ):
        pic = self.coords_to_pic( row, col )
        for c in square_dict.keys():
            for sq in square_dict[c]:
                ref_pic = ref_diag.sq_to_pic( sq )
                if img_equal( pic, ref_pic ):
                    return c
        return None

# 0: W at bottom, W to move (plus all pieces as specified by square_dict)
# 1: W at bottom, B to move
# 2: B at bottom, W to move
# 3: B at bottom, B to move
ref_diagrams = [ Diagram( Image.open( "%s/reference%d.png" % (script_dir, i) ),
                          i > 2, i % 2 == 0 ) for i in range( 1, 5 ) ]

def get_margin_img( options ):
    return ref_diagrams[2 * options.flip + options.black_to_move].img

# 0 = dark, 1 = light
def square_color( col, row ):
    return (col + row + 1) % 2

def add_square( img, col, row, piece, options ):
    color = square_color( col, row )
    sq_pic = ref_diagrams[0].sq_to_pic( square_dict[piece][color] )
    margin = REF_MARGIN if options.show_side else 0
    display_col = 7 - col if options.flip else col
    display_row = 7 - row if options.flip else row
    img.paste( sq_pic, (REF_SQ_SIZE * display_col + 1 + margin,
                        REF_SQ_SIZE * display_row + 1) )

# If the FEN says it's black to move, that overrides the command line
def maybe_override_side( fen, options ):
    if options.black_to_move: return
    space_pos = fen.find( ' ' )
    if fen[space_pos+1] == 'b':
        options.black_to_move = True

# How tall and wide is the image? show_margin is whether the margin is
# displayed.
def image_size( show_margin ):
    return 8 * REF_SQ_SIZE + 2 + (REF_MARGIN if show_margin else 0)

def fen_to_image( fen, options ):
    size = image_size( options.show_side )
    img = Image.new( "RGB", (size, size) )
    col = 0
    row = 0
    maybe_override_side( fen, options )
    for c in fen:
        if c.isdigit():
            d = int( c )
            while d != 0:
                add_square( img, col, row, ' ', options )
                col += 1
                d -= 1
        elif c == '/':
            col = 0
            row += 1
        elif c == ' ':
            break
        else:
            add_square( img, col, row, c, options )
            col += 1
    if options.show_side:
        img = add_margins( img, options )
    return img

def add_margins( img, options ):
    MARGIN_END = 8 * REF_SQ_SIZE + REF_MARGIN + 1
    margin_img = get_margin_img( options )
    left_margin_coords = (1, 1, REF_MARGIN + 1, MARGIN_END)
    left_margin = margin_img.crop( left_margin_coords )
    img.paste( left_margin, left_margin_coords )
    bottom_margin_coords = (1, MARGIN_END - REF_MARGIN, MARGIN_END, MARGIN_END)
    bottom_margin = margin_img.crop( bottom_margin_coords )
    img.paste( bottom_margin, bottom_margin_coords )
    return img

def image_to_fen( img ):
    diag = Diagram( img )
    fen_str = ""
    num_spaces = 0
    for row in range( 8 ):
        for col in range( 8 ):
            c = diag.coords_to_char( row, col, ref_diagrams[0] )
            if c == " ":
                num_spaces += 1
            else:
                if num_spaces > 0:
                    fen_str += str( num_spaces )
                    num_spaces = 0
                fen_str += c
        if num_spaces > 0:
            fen_str += str( num_spaces )
            num_spaces = 0
        if row < 7:
            fen_str += "/"
    if num_spaces > 0:
        fen_str += str( num_spaces )
    fen_str += " "
    fen_str += ("b" if diag.black_to_move else "w")
    fen_str += " KQkq - 0 1"    # I don't really care about this
    return fen_str
